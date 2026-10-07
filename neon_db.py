"""
Neon DB Client & Query Adapter for Think.4U
Provides a thread-safe connection pool to Neon Serverless PostgreSQL,
supporting both fluent table operations (PostgREST-compatible) and raw SQL.
Includes robust connection pooling, auto-reconnect, keepalives, SSL enforcement,
parameterized queries, and integration with Cloudflare R2 storage.
"""

import os
import re
import time
import json
import datetime
import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from contextlib import contextmanager
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json

logger = logging.getLogger("neon_db")

# Strict identifier regex (letters, numbers, underscore only)
_IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_]+$")


def _sanitize_identifier(name: str) -> str:
    """Validate and double-quote PostgreSQL identifier to prevent SQL injection."""
    name = (name or "").strip()
    if not name or not _IDENTIFIER_REGEX.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f'"{name}"'


def _mask_db_url(url: str) -> str:
    """Mask password in PostgreSQL URL for safe logging."""
    if not url:
        return "<none>"
    try:
        parsed = urlparse(url)
        netloc = ""
        if parsed.username:
            netloc += parsed.username
            if parsed.password:
                netloc += ":****"
            netloc += "@"
        netloc += parsed.hostname or ""
        if parsed.port:
            netloc += f":{parsed.port}"
        return f"{parsed.scheme}://{netloc}{parsed.path}"
    except Exception:
        return "<database-url-masked>"


class NeonResponse:
    """Standardized response object matching PostgREST / Supabase response format."""
    def __init__(self, data=None, count=None):
        self.data = data if data is not None else []
        self.count = count

    def __repr__(self):
        return f"<NeonResponse rows={len(self.data)} count={self.count}>"


class NeonQueryBuilder:
    """Fluent query builder converting chained calls to parameterized PostgreSQL statements."""

    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name
        self.quoted_table = _sanitize_identifier(table_name)
        self.operation = "select"  # select, insert, update, delete, upsert
        self.columns = "*"
        self.payload = None
        self.where_clauses = []
        self.params = []
        self.order_clauses = []
        self.limit_val = None
        self.offset_val = None
        self.count_mode = None
        self.conflict_target = None

    def select(self, columns="*", count=None):
        self.operation = "select"
        self.columns = columns or "*"
        self.count_mode = count
        return self

    def insert(self, data):
        self.operation = "insert"
        self.payload = data
        return self

    def update(self, data):
        self.operation = "update"
        self.payload = data
        return self

    def upsert(self, data, on_conflict=None):
        self.operation = "upsert"
        self.payload = data
        self.conflict_target = on_conflict
        return self

    def delete(self):
        self.operation = "delete"
        return self

    # Filter methods
    def eq(self, column: str, value):
        quoted_col = _sanitize_identifier(column)
        if value is None:
            self.where_clauses.append(f"{quoted_col} IS NULL")
        else:
            self.where_clauses.append(f"{quoted_col} = %s")
            self.params.append(self._format_param(value))
        return self

    def neq(self, column: str, value):
        quoted_col = _sanitize_identifier(column)
        if value is None:
            self.where_clauses.append(f"{quoted_col} IS NOT NULL")
        else:
            self.where_clauses.append(f"{quoted_col} != %s")
            self.params.append(self._format_param(value))
        return self

    def gt(self, column: str, value):
        quoted_col = _sanitize_identifier(column)
        self.where_clauses.append(f"{quoted_col} > %s")
        self.params.append(self._format_param(value))
        return self

    def gte(self, column: str, value):
        quoted_col = _sanitize_identifier(column)
        self.where_clauses.append(f"{quoted_col} >= %s")
        self.params.append(self._format_param(value))
        return self

    def lt(self, column: str, value):
        quoted_col = _sanitize_identifier(column)
        self.where_clauses.append(f"{quoted_col} < %s")
        self.params.append(self._format_param(value))
        return self

    def lte(self, column: str, value):
        quoted_col = _sanitize_identifier(column)
        self.where_clauses.append(f"{quoted_col} <= %s")
        self.params.append(self._format_param(value))
        return self

    def in_(self, column: str, values):
        if not values:
            self.where_clauses.append("1=0")
            return self
        quoted_col = _sanitize_identifier(column)
        val_list = list(values)
        self.where_clauses.append(f"{quoted_col} = ANY(%s)")
        self.params.append(val_list)
        return self

    def like(self, column: str, pattern: str):
        quoted_col = _sanitize_identifier(column)
        self.where_clauses.append(f"{quoted_col} LIKE %s")
        self.params.append(pattern)
        return self

    def ilike(self, column: str, pattern: str):
        quoted_col = _sanitize_identifier(column)
        self.where_clauses.append(f"{quoted_col} ILIKE %s")
        self.params.append(pattern)
        return self

    def is_(self, column: str, value):
        quoted_col = _sanitize_identifier(column)
        if value is None or str(value).lower() in ("null", "none"):
            self.where_clauses.append(f"{quoted_col} IS NULL")
        else:
            self.where_clauses.append(f"{quoted_col} IS %s")
            self.params.append(value)
        return self

    def order(self, column: str, desc=False):
        quoted_col = _sanitize_identifier(column)
        direction = "DESC" if desc else "ASC"
        self.order_clauses.append(f"{quoted_col} {direction}")
        return self

    def limit(self, count: int):
        self.limit_val = int(count)
        return self

    def range(self, start: int, end: int):
        start = int(start)
        end = int(end)
        self.offset_val = start
        self.limit_val = max(0, (end - start) + 1)
        return self

    def _format_param(self, val):
        if isinstance(val, (dict, list)):
            return Json(val)
        return val

    def _build_where(self) -> str:
        if not self.where_clauses:
            return ""
        return " WHERE " + " AND ".join(self.where_clauses)

    def execute(self) -> NeonResponse:
        """Compiles and executes the query against the Neon DB connection pool."""
        where_sql = self._build_where()

        if self.operation == "select":
            cols_clause = "*"
            if self.columns and self.columns.strip() != "*":
                parts = [c.strip() for c in self.columns.split(",") if c.strip()]
                quoted_parts = []
                for p in parts:
                    if p.lower() == "count(*)":
                        quoted_parts.append("count(*)")
                    else:
                        quoted_parts.append(_sanitize_identifier(p))
                cols_clause = ", ".join(quoted_parts) if quoted_parts else "*"

            sql = f"SELECT {cols_clause} FROM {self.quoted_table}{where_sql}"
            params = list(self.params)

            if self.order_clauses:
                sql += " ORDER BY " + ", ".join(self.order_clauses)
            if self.limit_val is not None:
                sql += f" LIMIT {self.limit_val}"
            if self.offset_val is not None:
                sql += f" OFFSET {self.offset_val}"

            data = self.client.execute_sql(sql, params)

            total_count = None
            if self.count_mode == "exact":
                count_sql = f"SELECT count(*) AS total FROM {self.quoted_table}{where_sql}"
                count_res = self.client.execute_sql(count_sql, self.params)
                if count_res:
                    total_count = int(count_res[0].get("total", 0))

            return NeonResponse(data=data, count=total_count)

        elif self.operation == "insert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            if not rows or not rows[0]:
                return NeonResponse(data=[])

            all_returned = []
            for row in rows:
                cols = list(row.keys())
                col_names = ", ".join(_sanitize_identifier(c) for c in cols)
                placeholders = ", ".join(["%s"] * len(cols))
                row_params = [self._format_param(row[c]) for c in cols]

                sql = f"INSERT INTO {self.quoted_table} ({col_names}) VALUES ({placeholders}) RETURNING *"
                res = self.client.execute_sql(sql, row_params)
                if res:
                    all_returned.extend(res)

            return NeonResponse(data=all_returned)

        elif self.operation == "update":
            if not self.payload:
                return NeonResponse(data=[])

            set_clauses = []
            update_params = []
            for k, v in self.payload.items():
                set_clauses.append(f"{_sanitize_identifier(k)} = %s")
                update_params.append(self._format_param(v))

            set_sql = ", ".join(set_clauses)
            sql = f"UPDATE {self.quoted_table} SET {set_sql}{where_sql} RETURNING *"
            params = update_params + list(self.params)

            data = self.client.execute_sql(sql, params)
            return NeonResponse(data=data)

        elif self.operation == "delete":
            sql = f"DELETE FROM {self.quoted_table}{where_sql} RETURNING *"
            data = self.client.execute_sql(sql, self.params)
            return NeonResponse(data=data)

        elif self.operation == "upsert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            if not rows or not rows[0]:
                return NeonResponse(data=[])

            all_returned = []
            conflict_col = self.conflict_target or "id"
            quoted_conflict = _sanitize_identifier(conflict_col)

            for row in rows:
                cols = list(row.keys())
                col_names = ", ".join(_sanitize_identifier(c) for c in cols)
                placeholders = ", ".join(["%s"] * len(cols))
                update_sets = [f"{_sanitize_identifier(c)} = EXCLUDED.{_sanitize_identifier(c)}" for c in cols if c != conflict_col]
                row_params = [self._format_param(row[c]) for c in cols]

                do_update = f"DO UPDATE SET {', '.join(update_sets)}" if update_sets else "DO NOTHING"
                sql = (
                    f"INSERT INTO {self.quoted_table} ({col_names}) VALUES ({placeholders}) "
                    f"ON CONFLICT ({quoted_conflict}) {do_update} RETURNING *"
                )
                res = self.client.execute_sql(sql, row_params)
                if res:
                    all_returned.extend(res)

            return NeonResponse(data=all_returned)

        return NeonResponse(data=[])


class _NeonStorageBucket:
    """Storage adapter supporting Cloudflare R2 with fallback to local static folder."""

    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name

    def list(self):
        return []

    def create_bucket(self, name, options=None):
        return True

    def upload(self, file_path: str, file_data: bytes, file_options=None):
        file_options = file_options or {}
        content_type = file_options.get("content-type") or file_options.get("contentType") or "application/octet-stream"

        try:
            from r2_storage import is_r2_configured, upload_to_r2
            if is_r2_configured():
                object_key = f"{self.bucket_name}/{file_path}".strip("/")
                url = upload_to_r2(file_data, object_key, content_type=content_type)
                return bool(url)
        except Exception as e:
            logger.warning(f"R2 upload fallback to local storage: {e}")

        # Local fallback
        target_dir = os.path.join("static", "uploads", self.bucket_name)
        full_path = os.path.join(target_dir, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(file_data)
        return True

    def get_public_url(self, file_path: str) -> str:
        normalized = file_path.replace("\\", "/").strip("/")
        try:
            from r2_storage import is_r2_configured, format_r2_url
            if is_r2_configured():
                return format_r2_url(f"{self.bucket_name}/{normalized}")
        except Exception:
            pass
        return f"/static/uploads/{self.bucket_name}/{normalized}"

    def remove(self, file_paths):
        return True


class _NeonStorage:
    def from_(self, bucket_name: str):
        return _NeonStorageBucket(bucket_name)

    def create_bucket(self, name, options=None):
        return True


class NeonClient:
    """
    Thread-safe connection pool manager for Neon PostgreSQL.
    Features:
      - SSL mode enforcement (sslmode=require)
      - Keepalive & timeout parameters for serverless resilience
      - Auto-reconnect on broken or idle connections
      - 100% parameterized queries
      - Integrated health check & metric diagnostics
      - Storage bridging to Cloudflare R2
    """

    def __init__(self, connection_url=None, min_conn=1, max_conn=10):
        self.connection_url = connection_url or os.getenv("DATABASE_URL")
        self.min_conn = min_conn
        self.max_conn = max_conn
        self.pool = None
        self.is_connected = False
        self.storage = _NeonStorage()
        self._init_pool()

    def _prepare_dsn(self, raw_url: str) -> str:
        """Sanitize URL, enforce sslmode=require and add keepalive parameters for Neon serverless."""
        url = raw_url.strip().strip('"').strip("'")
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        # Force sslmode=require
        query_params["sslmode"] = ["require"]

        # Keepalive settings for Neon serverless connection stability
        if "connect_timeout" not in query_params:
            query_params["connect_timeout"] = ["10"]
        if "keepalives" not in query_params:
            query_params["keepalives"] = ["1"]
        if "keepalives_idle" not in query_params:
            query_params["keepalives_idle"] = ["30"]
        if "keepalives_interval" not in query_params:
            query_params["keepalives_interval"] = ["10"]
        if "keepalives_count" not in query_params:
            query_params["keepalives_count"] = ["5"]

        flat_query = {k: v[0] for k, v in query_params.items()}
        new_query_str = urlencode(flat_query)

        new_parsed = parsed._replace(query=new_query_str)
        return urlunparse(new_parsed)

    def _init_pool(self):
        if not self.connection_url:
            logger.warning("DATABASE_URL not configured. Neon client running in uninitialized mode.")
            return

        try:
            dsn = self._prepare_dsn(self.connection_url)
            self.pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=self.min_conn,
                maxconn=self.max_conn,
                dsn=dsn
            )
            # Verify initial connectivity
            conn = self.pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS ready;")
            finally:
                self.pool.putconn(conn)

            self.is_connected = True
            logger.info("Connected to Neon DB successfully (%s).", _mask_db_url(self.connection_url))
        except Exception as e:
            logger.error("Failed to connect to Neon DB: %s", e)
            self.pool = None
            self.is_connected = False

    @contextmanager
    def get_connection(self):
        """Thread-safe connection context manager with automatic rollback and health retry."""
        if not self.pool:
            # Attempt lazy reconnection if connection URL exists
            if self.connection_url:
                self._init_pool()
            if not self.pool:
                raise RuntimeError("Neon DB connection pool is not initialized.")

        conn = None
        try:
            conn = self.pool.getconn()
            # Fast liveness test; recreate if broken by Neon suspend
            try:
                if conn.closed:
                    raise psycopg2.InterfaceError("Connection is closed.")
            except Exception:
                self.pool.putconn(conn, close=True)
                conn = self.pool.getconn()
            yield conn
        except psycopg2.OperationalError as oe:
            if conn:
                try:
                    self.pool.putconn(conn, close=True)
                except Exception:
                    pass
                conn = None
            logger.warning("Database connection error: %s. Attempting fresh connection...", oe)
            # Recreate pool if broken
            self._init_pool()
            if not self.pool:
                raise
            conn = self.pool.getconn()
            yield conn
        finally:
            if conn:
                try:
                    self.pool.putconn(conn)
                except Exception:
                    pass

    def table(self, table_name: str) -> NeonQueryBuilder:
        """Returns a fluent query builder for the given table."""
        return NeonQueryBuilder(self, table_name)

    def execute_sql(self, sql: str, params=None):
        """Executes a SQL statement and returns rows as dicts."""
        t_start = time.perf_counter()
        with self.get_connection() as conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(sql, params or ())
                    if cur.description:
                        raw_rows = cur.fetchall()
                        results = []
                        for r in raw_rows:
                            row_dict = dict(r)
                            for col, val in row_dict.items():
                                if isinstance(val, (datetime.datetime, datetime.date)):
                                    row_dict[col] = val.isoformat()
                            results.append(row_dict)
                    else:
                        results = []
                conn.commit()
                return results
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                duration = round((time.perf_counter() - t_start) * 1000, 2)
                logger.error("SQL error after %sms: %s | Statement: %s", duration, e, sql[:200])
                raise e

    def ping(self) -> bool:
        """Fast health check verifying database connectivity."""
        try:
            res = self.execute_sql("SELECT 1 AS alive;")
            return bool(res and res[0].get("alive") == 1)
        except Exception:
            return False

    def get_health_status(self) -> dict:
        """Detailed health and security diagnostics."""
        t0 = time.perf_counter()
        is_alive = False
        error_msg = None
        ssl_active = False

        if not self.connection_url:
            return {
                "status": "unconfigured",
                "healthy": False,
                "error": "DATABASE_URL is not set"
            }

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS ping, pg_is_in_recovery() AS is_replica, current_database() AS db;")
                    row = cur.fetchone()
                    is_alive = bool(row and row[0] == 1)
                    cur.execute("SHOW ssl;")
                    ssl_row = cur.fetchone()
                    ssl_active = (ssl_row[0].lower() == "on") if ssl_row else False
        except Exception as e:
            error_msg = str(e)

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        parsed = urlparse(self.connection_url or "")
        return {
            "status": "healthy" if is_alive else "unhealthy",
            "healthy": is_alive,
            "backend": "neon_postgresql",
            "host": parsed.hostname,
            "database": parsed.path.lstrip("/"),
            "ssl_enforced": True,
            "ssl_active": ssl_active,
            "latency_ms": latency_ms,
            "error": error_msg,
            "pool": {
                "min_connections": self.min_conn,
                "max_connections": self.max_conn,
            }
        }

    def close(self):
        """Close connection pool cleanly."""
        if self.pool:
            try:
                self.pool.closeall()
            except Exception:
                pass
            self.pool = None
            self.is_connected = False
