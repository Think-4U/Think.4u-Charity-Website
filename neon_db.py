"""
Neon DB Client & Query Adapter for Think.4U
Provides a thread-safe connection pool to Neon Serverless PostgreSQL,
supporting both fluent table operations (PostgREST-compatible) and raw SQL.
"""

import os
import json
import logging
from urllib.parse import urlparse
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json

logger = logging.getLogger("neon_db")

class NeonResponse:
    """Standardized response object matching PostgREST / Supabase response format."""
    def __init__(self, data=None, count=None):
        self.data = data if data is not None else []
        self.count = count

    def __repr__(self):
        return f"<NeonResponse rows={len(self.data)} count={self.count}>"


class NeonQueryBuilder:
    """Fluent query builder converting chained calls to parameterized PostgreSQL statements."""

    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
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
    def eq(self, column, value):
        if value is None:
            self.where_clauses.append(f'"{column}" IS NULL')
        else:
            self.where_clauses.append(f'"{column}" = %s')
            self.params.append(self._format_param(value))
        return self

    def neq(self, column, value):
        if value is None:
            self.where_clauses.append(f'"{column}" IS NOT NULL')
        else:
            self.where_clauses.append(f'"{column}" != %s')
            self.params.append(self._format_param(value))
        return self

    def gt(self, column, value):
        self.where_clauses.append(f'"{column}" > %s')
        self.params.append(self._format_param(value))
        return self

    def gte(self, column, value):
        self.where_clauses.append(f'"{column}" >= %s')
        self.params.append(self._format_param(value))
        return self

    def lt(self, column, value):
        self.where_clauses.append(f'"{column}" < %s')
        self.params.append(self._format_param(value))
        return self

    def lte(self, column, value):
        self.where_clauses.append(f'"{column}" <= %s')
        self.params.append(self._format_param(value))
        return self

    def in_(self, column, values):
        if not values:
            self.where_clauses.append("1=0")
            return self
        val_list = list(values)
        self.where_clauses.append(f'"{column}" = ANY(%s)')
        self.params.append(val_list)
        return self

    def like(self, column, pattern):
        self.where_clauses.append(f'"{column}" LIKE %s')
        self.params.append(pattern)
        return self

    def ilike(self, column, pattern):
        self.where_clauses.append(f'"{column}" ILIKE %s')
        self.params.append(pattern)
        return self

    def is_(self, column, value):
        if value is None or str(value).lower() in ("null", "none"):
            self.where_clauses.append(f'"{column}" IS NULL')
        else:
            self.where_clauses.append(f'"{column}" IS %s')
            self.params.append(value)
        return self

    def order(self, column, desc=False):
        direction = "DESC" if desc else "ASC"
        self.order_clauses.append(f'"{column}" {direction}')
        return self

    def limit(self, count):
        self.limit_val = int(count)
        return self

    def range(self, start, end):
        start = int(start)
        end = int(end)
        self.offset_val = start
        self.limit_val = (end - start) + 1
        return self

    def _format_param(self, val):
        if isinstance(val, (dict, list)):
            return Json(val)
        return val

    def _build_where(self):
        if not self.where_clauses:
            return ""
        return " WHERE " + " AND ".join(self.where_clauses)

    def execute(self):
        """Compiles and executes the query against the Neon DB connection pool."""
        where_sql = self._build_where()

        if self.operation == "select":
            # Sanitize column projection
            cols_clause = "*"
            if self.columns and self.columns != "*":
                # Handle comma separated column names
                parts = [c.strip() for c in self.columns.split(",") if c.strip()]
                quoted_parts = []
                for p in parts:
                    if p.lower() == "count(*)":
                        quoted_parts.append("count(*)")
                    else:
                        quoted_parts.append(f'"{p}"')
                cols_clause = ", ".join(quoted_parts) if quoted_parts else "*"

            sql = f'SELECT {cols_clause} FROM "{self.table_name}"{where_sql}'
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
                count_sql = f'SELECT count(*) AS total FROM "{self.table_name}"{where_sql}'
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
                col_names = ", ".join(f'"{c}"' for c in cols)
                placeholders = ", ".join(["%s"] * len(cols))
                row_params = [self._format_param(row[c]) for c in cols]

                sql = f'INSERT INTO "{self.table_name}" ({col_names}) VALUES ({placeholders}) RETURNING *'
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
                set_clauses.append(f'"{k}" = %s')
                update_params.append(self._format_param(v))

            set_sql = ", ".join(set_clauses)
            sql = f'UPDATE "{self.table_name}" SET {set_sql}{where_sql} RETURNING *'
            params = update_params + list(self.params)

            data = self.client.execute_sql(sql, params)
            return NeonResponse(data=data)

        elif self.operation == "delete":
            sql = f'DELETE FROM "{self.table_name}"{where_sql} RETURNING *'
            data = self.client.execute_sql(sql, self.params)
            return NeonResponse(data=data)

        elif self.operation == "upsert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            if not rows or not rows[0]:
                return NeonResponse(data=[])

            all_returned = []
            conflict_col = self.conflict_target or "id"
            for row in rows:
                cols = list(row.keys())
                col_names = ", ".join(f'"{c}"' for c in cols)
                placeholders = ", ".join(["%s"] * len(cols))
                update_sets = [f'"{c}" = EXCLUDED."{c}"' for c in cols if c != conflict_col]
                row_params = [self._format_param(row[c]) for c in cols]

                do_update = f"DO UPDATE SET {', '.join(update_sets)}" if update_sets else "DO NOTHING"
                sql = (
                    f'INSERT INTO "{self.table_name}" ({col_names}) VALUES ({placeholders}) '
                    f'ON CONFLICT ("{conflict_col}") {do_update} RETURNING *'
                )
                res = self.client.execute_sql(sql, row_params)
                if res:
                    all_returned.extend(res)

            return NeonResponse(data=all_returned)

        return NeonResponse(data=[])


class _LocalStorageBucket:
    def __init__(self, bucket_name):
        self.bucket_name = bucket_name

    def list(self):
        return []

    def create_bucket(self, name, options=None):
        return True

    def upload(self, file_path, file_data, file_options=None):
        target_dir = os.path.join("static", "uploads", self.bucket_name)
        full_path = os.path.join(target_dir, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(file_data)
        return True

    def get_public_url(self, file_path):
        normalized = file_path.replace("\\", "/")
        return f"/static/uploads/{self.bucket_name}/{normalized}"

    def remove(self, file_paths):
        return True


class _NeonStorage:
    def from_(self, bucket_name):
        return _LocalStorageBucket(bucket_name)

    def create_bucket(self, name, options=None):
        return True


class NeonClient:
    """Thread-safe connection pool manager for Neon PostgreSQL."""

    def __init__(self, connection_url=None, min_conn=1, max_conn=10):
        self.connection_url = connection_url or os.getenv("DATABASE_URL")
        self.pool = None
        self.is_connected = False
        self.storage = _NeonStorage()
        self._init_pool(min_conn, max_conn)

    def _init_pool(self, min_conn, max_conn):
        if not self.connection_url:
            logger.warning("DATABASE_URL not set. Neon client running in uninitialized mode.")
            return

        try:
            url = self.connection_url.strip().strip('"').strip("'")

            # Ensure sslmode=require is present
            if "sslmode" not in url:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}sslmode=require"

            self.pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=min_conn,
                maxconn=max_conn,
                dsn=url
            )
            self.is_connected = True
            logger.info("Connected to Neon DB successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to Neon DB: {e}")
            self.pool = None
            self.is_connected = False

    def table(self, table_name):
        """Returns a fluent query builder for the given table."""
        return NeonQueryBuilder(self, table_name)

    def execute_sql(self, sql, params=None):
        """Executes a SQL statement and returns rows as dicts."""
        if not self.pool:
            logger.error("Database connection pool is not initialized.")
            return []

        conn = None
        try:
            conn = self.pool.getconn()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params or ())
                if cur.description:
                    results = [dict(row) for row in cur.fetchall()]
                else:
                    results = []
            conn.commit()
            return results
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"SQL execution error: {e} | Query: {sql}")
            raise e
        finally:
            if conn:
                self.pool.putconn(conn)

    def ping(self):
        """Health check method verifying the database connection."""
        try:
            res = self.execute_sql("SELECT 1 AS alive;")
            return bool(res and res[0].get("alive") == 1)
        except Exception:
            return False

    def close(self):
        if self.pool:
            self.pool.closeall()
            self.is_connected = False
