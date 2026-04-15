# ------------------------------
# Think.4U - Charity Platform
# ------------------------------
from flask_mail import Mail, Message
import os
import io
import csv
import secrets
import re
import threading
import hashlib
import hmac
import html
import json as pyjson
from collections import defaultdict, deque
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file, abort
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from supabase import create_client, Client
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException
from datetime import datetime, timezone, timedelta
import traceback
import tempfile
import qrcode
import httpx
from io import BytesIO
import base64
from num2words import num2words
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from io import BytesIO
from PIL import Image, ImageDraw

# Load environment variables
load_dotenv()


class _NoOpResponse:
    def __init__(self):
        self.data = []
        self.count = 0


class _NoOpQuery:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: self

    def execute(self):
        return _NoOpResponse()


class _NoOpSupabase:
    def table(self, _table_name):
        return _NoOpQuery()

# ------------------------------
# Flask App Configuration
# ------------------------------
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
UPI_VPA = os.getenv("UPI_VPA")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)

if app.secret_key == "dev-secret-key-change-in-production":
    app.logger.warning("SECRET_KEY is using the default value. Set a strong SECRET_KEY before production.")

ENFORCE_HTTPS = os.getenv("ENFORCE_HTTPS", "false").lower() == "true"
OTP_EXPIRY_SECONDS = int(os.getenv("OTP_EXPIRY_SECONDS", "600"))
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_BLOCK_SECONDS = int(os.getenv("LOGIN_BLOCK_SECONDS", "900"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "90"))
AUTH_RATE_LIMIT_MAX_REQUESTS = int(os.getenv("AUTH_RATE_LIMIT_MAX_REQUESTS", "20"))
INACTIVITY_TIMEOUT_SECONDS = int(os.getenv("INACTIVITY_TIMEOUT_SECONDS", "900"))
ALLOW_DEV_OTP_FALLBACK = os.getenv("ALLOW_DEV_OTP_FALLBACK", "true").lower() == "true"
PAYMENT_PENDING_TIMEOUT_MINUTES = int(os.getenv("PAYMENT_PENDING_TIMEOUT_MINUTES", "15"))

REQUEST_RATE_STATE = defaultdict(deque)
FAILED_LOGIN_STATE = {}
CMS_CACHE = {}
CMS_CACHE_EXPIRY = {}
CMS_FAILURE_UNTIL = 0
CMS_CACHE_TTL_SECONDS = int(os.getenv("CMS_CACHE_TTL_SECONDS", "300"))
CMS_FAILURE_BACKOFF_SECONDS = int(os.getenv("CMS_FAILURE_BACKOFF_SECONDS", "30"))

# ------------------------------
# Flask-Login Setup
# ------------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.session_protection = "strong"

# ------------------------------
# Supabase Configuration
# ------------------------------
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_KEY)
if SUPABASE_ENABLED:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as supabase_init_error:
        app.logger.error(f"Supabase initialization failed: {supabase_init_error}")
        supabase = _NoOpSupabase()
        SUPABASE_ENABLED = False
else:
    app.logger.warning("Supabase env vars missing. Running in limited mode.")
    supabase = _NoOpSupabase()


def get_supabase_key_role(key):
    try:
        payload = key.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode()).decode()
        claims = pyjson.loads(decoded)
        return claims.get("role")
    except Exception:
        return None


supabase_key_role = get_supabase_key_role(SUPABASE_KEY or "")
if SUPABASE_ENABLED and supabase_key_role != "service_role":
    app.logger.warning(
        "SUPABASE_KEY role is '%s'. For backend writes with RLS, use service_role key in .env.",
        supabase_key_role or "unknown"
    )


# ------------------------------
# Razorpay Configuration
# ------------------------------
RAZOR_KEY = os.getenv('RAZOR_KEY_ID')
RAZOR_SECRET = os.getenv('RAZOR_KEY_SECRET')
RAZORPAY_ENABLED = bool(RAZOR_KEY and RAZOR_SECRET)

if not RAZORPAY_ENABLED:
    app.logger.warning("Razorpay keys missing. Online payment routes are disabled.")


def create_razorpay_order(amount, currency, receipt):
    if not RAZORPAY_ENABLED:
        raise RuntimeError("Razorpay is not configured")
    response = httpx.post(
        "https://api.razorpay.com/v1/orders",
        auth=(RAZOR_KEY, RAZOR_SECRET),
        data={
            "amount": amount,
            "currency": currency,
            "receipt": receipt,
            "payment_capture": 1,
        },
        timeout=15.0,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Razorpay order creation failed: {response.status_code} {response.text}")
    return response.json()


def verify_checkout_signature(payload):
    """Verify Razorpay checkout signature without SDK."""
    order_id = payload.get("razorpay_order_id")
    payment_id = payload.get("razorpay_payment_id")
    signature = payload.get("razorpay_signature")
    if not all([order_id, payment_id, signature, RAZOR_SECRET]):
        return False

    message = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(RAZOR_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(webhook_body, webhook_signature, webhook_secret):
    if not webhook_secret:
        return True
    if not webhook_signature:
        return False
    expected = hmac.new(webhook_secret.encode("utf-8"), webhook_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, webhook_signature)


# ------------------------------
# Admin Credentials
# ------------------------------
app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_DEFAULT_SENDER=("Think.4U", os.getenv("MAIL_USERNAME"))
)

mail = Mail(app)


# ------------------------------
# Upload Configuration
# ------------------------------
if os.environ.get("VERCEL") or os.environ.get("RENDER"):
    UPLOAD_FOLDER = tempfile.gettempdir()  # /tmp
else:
    UPLOAD_FOLDER = "static/uploads"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024



def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ------------------------------
# User Model for Flask-Login
# ------------------------------
class User(UserMixin):
    def __init__(self, id, email, name=None, is_admin=False, role="donor"):
        self.id = id
        self.email = email
        self.name = name or 'User'
        self.is_admin = bool(is_admin)
        self.role = role or "donor"
        self.username = name or email.split('@')[0]  # Extract username from email if no name
    
    def get_display_name(self):
        """Get user's display name"""
        return self.name or self.email
    
    def get_initials(self):
        """Get user's initials for avatar"""
        if self.name:
            parts = self.name.split()
            if len(parts) >= 2:
                return (parts[0][0] + parts[-1][0]).upper()
            return self.name[0].upper()
        return self.email[0].upper()


@login_manager.user_loader
def load_user(user_id):
    """Load user from Supabase"""
    try:
        response = supabase.table('users').select('*').eq('id', int(user_id)).execute()
        if response.data:
            u = response.data[0]
            return User(
                id=u['id'],
                email=u['email'],
                name=u.get('name'),
                is_admin=u.get('is_admin', False),
                role=u.get('role', 'donor')
            )
        return None
    except Exception as e:
        app.logger.error(f"Error loading user from Supabase: {e}")
        return None


@login_manager.unauthorized_handler
def unauthorized():
    flash("Please log in to access this page", "error")
    return redirect(url_for('login', next=request.path))


def get_client_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


def clean_text(value, max_length=255, keep_new_lines=False):
    text = (value or "").strip()
    if not keep_new_lines:
        text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    text = text.replace("<", "").replace(">", "")
    return text[:max_length]


def normalize_email(value):
    email = clean_text(value, max_length=320).lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return None
    return email


def normalize_phone(value):
    digits = re.sub(r"\D", "", value or "")
    return digits if len(digits) == 10 else None


def validate_password_strength(password):
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", password):
        return False, "Password must include at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must include at least one lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must include at least one number."
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Password must include at least one special character."
    return True, ""


def validate_image_upload(file_obj):
    if not file_obj or not file_obj.filename:
        return False, "No file selected"

    filename = secure_filename(file_obj.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in {"png", "jpg", "jpeg", "gif", "webp"}:
        return False, "Invalid file type. Use PNG, JPG, JPEG, GIF, or WEBP"

    if not (file_obj.content_type or "").startswith("image/"):
        return False, "Invalid image content type"

    try:
        probe = Image.open(file_obj.stream)
        probe.verify()
        file_obj.stream.seek(0)
    except Exception:
        return False, "Uploaded file is not a valid image"

    return True, filename


def generate_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def verify_csrf_token():
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return True
    if request.endpoint in {"razorpay_webhook"}:
        return True
    provided = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    expected = session.get("_csrf_token")
    return bool(expected and provided and secrets.compare_digest(provided, expected))


def rate_limit_key(endpoint, identifier=None):
    ip = get_client_ip()
    suffix = identifier or ip
    return f"{endpoint}:{suffix}"


def is_rate_limited(key, max_requests=RATE_LIMIT_MAX_REQUESTS, window_seconds=RATE_LIMIT_WINDOW_SECONDS):
    now = datetime.now(timezone.utc).timestamp()
    queue = REQUEST_RATE_STATE[key]
    while queue and (now - queue[0]) > window_seconds:
        queue.popleft()
    if len(queue) >= max_requests:
        return True
    queue.append(now)
    return False


def record_failed_login(identity):
    now = datetime.now(timezone.utc).timestamp()
    state = FAILED_LOGIN_STATE.get(identity, {"count": 0, "blocked_until": 0})
    if now < state["blocked_until"]:
        return
    state["count"] += 1
    if state["count"] >= LOGIN_MAX_ATTEMPTS:
        state["blocked_until"] = now + LOGIN_BLOCK_SECONDS
        state["count"] = 0
    FAILED_LOGIN_STATE[identity] = state


def reset_failed_login(identity):
    FAILED_LOGIN_STATE.pop(identity, None)


def get_login_block_remaining(identity):
    state = FAILED_LOGIN_STATE.get(identity)
    if not state:
        return 0
    remaining = int(state.get("blocked_until", 0) - datetime.now(timezone.utc).timestamp())
    return remaining if remaining > 0 else 0


def generate_math_captcha(purpose):
    a = secrets.randbelow(9) + 1
    b = secrets.randbelow(9) + 1
    answer = a + b
    session[f"captcha_{purpose}"] = str(answer)
    return f"{a} + {b} = ?"


def verify_math_captcha(purpose, answer):
    expected = session.get(f"captcha_{purpose}")
    return bool(expected and answer and expected == str(answer).strip())


def generate_otp():
    return f"{secrets.randbelow(1000000):06d}"


def set_pending_otp(flow, email, payload):
    otp = generate_otp()
    session[f"pending_{flow}"] = {
        "email": email,
        "otp_hash": generate_password_hash(otp),
        "expires_at": int(datetime.now(timezone.utc).timestamp()) + OTP_EXPIRY_SECONDS,
        "attempts": 0,
        "payload": payload,
    }
    return otp


def validate_pending_otp(flow, otp_code):
    pending = session.get(f"pending_{flow}")
    if not pending:
        return False, "Verification session expired. Please try again."
    if int(datetime.now(timezone.utc).timestamp()) > pending.get("expires_at", 0):
        session.pop(f"pending_{flow}", None)
        return False, "OTP expired. Please try again."
    if not check_password_hash(pending.get("otp_hash", ""), clean_text(otp_code, 10)):
        pending["attempts"] = pending.get("attempts", 0) + 1
        session[f"pending_{flow}"] = pending
        if pending["attempts"] >= 5:
            session.pop(f"pending_{flow}", None)
            return False, "Too many invalid OTP attempts. Please start again."
        return False, "Invalid OTP."
    return True, pending


def send_otp_email(email, otp_code, flow_label):
    subject = f"Think.4U {flow_label} OTP"
    html_content = render_template(
        "emails/otp_email.html",
        otp=otp_code,
        expires_minutes=max(1, OTP_EXPIRY_SECONDS // 60),
        flow_label=flow_label
    )
    ok, _err = send_email_sync(subject=subject, recipients=[email], html=html_content)
    return ok


def create_notification_for_user(user_id, title, body):
    try:
        supabase.table("notifications").insert({
            "user_id": user_id,
            "title": clean_text(title, 120),
            "body": clean_text(body, 500, keep_new_lines=True),
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        trim_user_notifications(user_id=user_id, max_keep=4)
    except Exception as e:
        app.logger.warning(f"Notification insert skipped: {e}")


def create_notification_for_email(email, title, body):
    try:
        user_response = supabase.table("users").select("id").eq("email", email).limit(1).execute()
        if user_response.data:
            create_notification_for_user(user_response.data[0]["id"], title, body)
    except Exception as e:
        app.logger.warning(f"Notification by email skipped: {e}")


def trim_user_notifications(user_id, max_keep=4):
    """Keep only latest notification records for a user."""
    try:
        rows_response = supabase.table("notifications") \
            .select("id") \
            .eq("user_id", int(user_id)) \
            .order("created_at", desc=True) \
            .execute()
        rows = rows_response.data or []
        stale_ids = [item["id"] for item in rows[max_keep:] if item.get("id") is not None]
        if stale_ids:
            supabase.table("notifications").delete().in_("id", stale_ids).execute()
    except Exception as e:
        app.logger.warning(f"Notification cleanup skipped: {e}")


def ensure_event_for_program(program_row):
    """Programs and events are treated as the same registration unit."""
    if not program_row or not program_row.get("id"):
        return None

    program_id = int(program_row["id"])
    existing_event = None

    try:
        existing_response = supabase.table("volunteer_events") \
            .select("*") \
            .eq("program_id", program_id) \
            .limit(1) \
            .execute()
        existing_event = (existing_response.data or [None])[0]
    except Exception:
        existing_event = None

    if existing_event:
        return existing_event

    try:
        legacy_response = supabase.table("volunteer_events") \
            .select("*") \
            .eq("title", program_row.get("title")) \
            .limit(1) \
            .execute()
        existing_event = (legacy_response.data or [None])[0]
        if existing_event:
            return existing_event
    except Exception:
        pass

    event_payload = {
        "title": clean_text(program_row.get("title"), 200) or "Program Event",
        "description": clean_text(program_row.get("description"), 2000, keep_new_lines=True),
        "event_date": (program_row.get("created_at") or "")[:10] or datetime.now(timezone.utc).date().isoformat(),
        "location": "Program Venue",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "program_id": program_id,
    }

    try:
        create_response = supabase.table("volunteer_events").insert(event_payload).execute()
        created_event = (create_response.data or [None])[0]
        if created_event:
            return created_event
    except Exception:
        fallback_payload = {
            "title": event_payload["title"],
            "description": event_payload["description"],
            "event_date": event_payload["event_date"],
            "location": event_payload["location"],
            "created_at": event_payload["created_at"],
        }
        try:
            create_response = supabase.table("volunteer_events").insert(fallback_payload).execute()
            return (create_response.data or [None])[0]
        except Exception as e:
            app.logger.warning(f"Program-event sync failed: {e}")

    return None


def expire_stale_pending_donations(user_id=None, email=None):
    """Mark pending donations older than timeout as failed."""
    if user_id is None and not email:
        return 0

    timeout_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=PAYMENT_PENDING_TIMEOUT_MINUTES)).isoformat()
    updated_count = 0

    try:
        if user_id is not None:
            response = supabase.table("donations").update(
                {"status": "failed"}
            ).eq(
                "status", "pending"
            ).eq(
                "user_id", int(user_id)
            ).lte(
                "created_at", timeout_cutoff
            ).execute()
            updated_count += len(response.data or [])
    except Exception as e:
        app.logger.warning(f"Donation timeout update by user failed: {e}")

    try:
        if email:
            response = supabase.table("donations").update(
                {"status": "failed"}
            ).eq(
                "status", "pending"
            ).eq(
                "email", email
            ).lte(
                "created_at", timeout_cutoff
            ).execute()
            updated_count += len(response.data or [])
    except Exception as e:
        app.logger.warning(f"Donation timeout update by email failed: {e}")

    return updated_count


@app.before_request
def apply_security_controls():
    if ENFORCE_HTTPS and not app.debug and not request.is_secure:
        proto = request.headers.get("X-Forwarded-Proto", "http")
        if proto != "https" and request.host.split(":")[0] not in {"localhost", "127.0.0.1"}:
            return redirect(request.url.replace("http://", "https://", 1), code=301)

    endpoint = request.endpoint or ""
    if current_user.is_authenticated and endpoint != "static":
        now_ts = int(datetime.now(timezone.utc).timestamp())
        last_activity = session.get("last_activity_ts")
        try:
            last_activity = int(last_activity) if last_activity is not None else None
        except (TypeError, ValueError):
            last_activity = None

        if last_activity and (now_ts - last_activity) > INACTIVITY_TIMEOUT_SECONDS:
            logout_user()
            session.pop("pending_login", None)
            session.pop("pending_signup", None)
            session.pop("last_activity_ts", None)
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Session expired due to inactivity"}), 401
            timeout_minutes = max(1, INACTIVITY_TIMEOUT_SECONDS // 60)
            flash(f"Session expired after {timeout_minutes} minute(s) of inactivity. Please log in again.", "warning")
            return redirect(url_for("login", next=request.path))

        session.permanent = True
        session["last_activity_ts"] = now_ts
    else:
        session.pop("last_activity_ts", None)

    if request.method == "POST":
        auth_endpoint = request.endpoint in {"login", "signup", "verify_login", "verify_signup"}
        limit = AUTH_RATE_LIMIT_MAX_REQUESTS if auth_endpoint else RATE_LIMIT_MAX_REQUESTS
        if is_rate_limited(rate_limit_key(request.endpoint or "post"), max_requests=limit):
            return (jsonify({"error": "Too many requests"}), 429) if request.is_json else abort(429)

    if not verify_csrf_token():
        if request.is_json:
            return jsonify({"error": "Invalid CSRF token"}), 403
        flash("Security validation failed. Please refresh and try again.", "error")
        return redirect(request.referrer or url_for("index"))

    if request.path.startswith("/admin") or request.endpoint in {"api_analytics", "chart_donations", "chart_volunteers"}:
        if not current_user.is_authenticated:
            return unauthorized()
        if not getattr(current_user, "is_admin", False):
            flash("Admin access required", "error")
            return redirect(url_for("dashboard"))


@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), "
        "microphone=(), "
        "geolocation=(), "
        "accelerometer=(self \"https://checkout.razorpay.com\"), "
        "gyroscope=(self \"https://checkout.razorpay.com\"), "
        "magnetometer=(self \"https://checkout.razorpay.com\")"
    )
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if ENFORCE_HTTPS:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data: https:; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net https://*.razorpay.com; "
        "script-src-elem 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net https://*.razorpay.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "style-src-elem 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "connect-src 'self' https://unpkg.com https://cdn.jsdelivr.net https://*.razorpay.com; "
        "frame-src https://*.razorpay.com; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none'"
    )
    return response


# ===================================
# HELPER FUNCTIONS
# ===================================
def send_email_async(subject, recipients, html):
    """Send email in background thread"""
    def send():
        try:
            with app.app_context():
                msg = Message(subject=subject, recipients=recipients, html=html)
                mail.send(msg)
                app.logger.info(f"Email sent to {recipients}")
        except Exception as e:
            app.logger.warning(f"Email failed: {e}")

    threading.Thread(target=send, daemon=True).start()


def send_email_sync(subject, recipients, html):
    """Send email synchronously and return success status"""
    try:
        with app.app_context():
            msg = Message(subject=subject, recipients=recipients, html=html)
            mail.send(msg)
        return True, None
    except Exception as e:
        app.logger.warning(f"Email failed: {e}")
        return False, str(e)

# ===================================
# PUBLIC ROUTES
# ===================================
@app.route("/")
def index():
    """Homepage with stats"""
    # Fetch programs
    try:
        response = supabase.table('programs').select('*').execute()
        programs = response.data if response.data else []
    except Exception as e:
        app.logger.warning(f"Error fetching programs: {e}")
        programs = []
    
    # Calculate stats
    stats = {
        'total_donations': 0,
        'total_volunteers': 0,
        'total_programs': len(programs)
    }
    
    # Get donation count
    try:
        donations_response = supabase.table('donations').select('*', count='exact').execute()
        stats['total_donations'] = donations_response.count if hasattr(donations_response, 'count') else len(donations_response.data)
    except Exception as e:
        app.logger.warning(f"Error fetching donation count: {e}")
    
    # Get volunteer count
    try:
        volunteers_response = supabase.table('volunteers').select('*', count='exact').execute()
        stats['total_volunteers'] = volunteers_response.count if hasattr(volunteers_response, 'count') else len(volunteers_response.data)
    except Exception as e:
        app.logger.warning(f"Error fetching volunteer count: {e}")
    
    return render_template("index.html", 
                         programs=programs, 
                         razor_key=RAZOR_KEY,
                         stats=stats)


@app.route("/favicon.ico")
@app.route("/favicon.png")
def favicon():
    if request.path.endswith(".png"):
        return redirect(url_for("static", filename="images/favicon.png"))
    return redirect(url_for("static", filename="images/favicon.ico"))


@app.route("/healthz")
def healthz():
    return jsonify({
        "status": "ok",
        "supabase_enabled": SUPABASE_ENABLED,
        "razorpay_enabled": RAZORPAY_ENABLED,
    }), 200



@app.route("/donate")
@login_required
def donate():
    """Donation page (logged-in users only)"""
    amount_rupees = request.args.get("amount", "")
    amount_paise = None
    if amount_rupees:
        try:
            amount_paise = int(float(amount_rupees) * 100)
        except Exception:
            amount_paise = None

    return render_template(
        "donate.html",
        amount_display=amount_rupees,
        amount_paise=amount_paise,
        razor_key=RAZOR_KEY,
        donor_name=current_user.name,
        donor_email=current_user.email,
    )


@app.route("/donate-upi")
@login_required
def donate_upi():
    """UPI donation page"""
    amount = request.args.get('amount', '')
    return render_template("donate_upi.html", upi_vpa=UPI_VPA, amount=amount)


@app.route("/create-order", methods=["POST"])
@login_required
def create_order():
    """Create Razorpay order for logged-in donor"""
    if not RAZORPAY_ENABLED:
        return jsonify({"error": "Payment gateway is temporarily unavailable"}), 503

    data = request.get_json(silent=True) or {}

    try:
        amount = int(data.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid amount"}), 400

    donor_name = clean_text(data.get("name") or current_user.name or current_user.email.split("@")[0], 120)
    donor_email = current_user.email
    donor_phone = normalize_phone(data.get("phone", ""))

    if amount < 1000:
        return jsonify({"error": "Minimum donation is Rs 10"}), 400

    if not donor_name or not donor_phone:
        return jsonify({"error": "Missing donor details"}), 400

    receipt = f"rcpt_{int(datetime.now(timezone.utc).timestamp())}_{current_user.id}"

    try:
        order = create_razorpay_order(
            amount=amount,
            currency="INR",
            receipt=receipt,
        )

        supabase.table("donations").insert({
            "user_id": int(current_user.id),
            "name": donor_name,
            "email": donor_email,
            "phone": donor_phone,
            "amount": amount,
            "razorpay_order_id": order["id"],
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()

        return jsonify({
            "id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "key_id": RAZOR_KEY
        })

    except RuntimeError as e:
        app.logger.error(f"Razorpay error: {e}")
        return jsonify({"error": "Payment service unavailable"}), 503
    except Exception as e:
        app.logger.error(f"Order creation failed: {e}")
        return jsonify({"error": "Could not create order"}), 500


@app.route("/payment-success", methods=["GET"])
@login_required
def payment_success_redirect():
    """Handle payment success redirect"""
    if not RAZORPAY_ENABLED:
        flash("Payment verification service unavailable. Please contact support.", "error")
        return redirect(url_for("donate"))

    payment_id = request.args.get('razorpay_payment_id')
    order_id = request.args.get('razorpay_order_id')
    signature = request.args.get('razorpay_signature')

    if not all([payment_id, order_id, signature]):
        flash('Invalid payment data', 'error')
        return redirect(url_for('donate'))

    payload = {
        'razorpay_order_id': order_id,
        'razorpay_payment_id': payment_id,
        'razorpay_signature': signature
    }

    try:
        if not verify_checkout_signature(payload):
            flash('Payment verification failed', 'error')
            return redirect(url_for('donate'))

        response = supabase.table('donations') \
            .update({
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
                "status": "paid",
                "payment_method": "Razorpay"
            }) \
            .eq('razorpay_order_id', order_id) \
            .eq('user_id', int(current_user.id)) \
            .execute()

        if not response.data:
            response = supabase.table('donations') \
                .update({
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                    "status": "paid",
                    "payment_method": "Razorpay"
                }) \
                .eq('razorpay_order_id', order_id) \
                .execute()

        if response.data:
            donation = response.data[0]
            create_notification_for_user(
                int(current_user.id),
                "Donation successful",
                f"Your donation of ?{donation.get('amount', 0)/100:.2f} was received successfully."
            )
            flash('Thank you for your donation!', 'success')
            return redirect(url_for('donation_receipt', donation_id=donation['id']))

        flash('Donation record not found', 'error')
        return redirect(url_for('donate'))

    except Exception as e:
        app.logger.error(f"Payment success handling error: {e}")
        flash('Error processing payment', 'error')

    return redirect(url_for('donate'))


@app.route("/razorpay-webhook", methods=["POST"])
def razorpay_webhook():
    """Handle Razorpay webhook events"""
    if not RAZORPAY_ENABLED:
        return jsonify({"error": "Razorpay not configured"}), 503

    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    webhook_signature = request.headers.get('X-Razorpay-Signature')
    webhook_body = request.get_data()

    try:
        if not verify_webhook_signature(webhook_body, webhook_signature, webhook_secret):
            return jsonify({"error": "Invalid webhook signature"}), 400

        event = request.json or {}
        event_type = event.get('event')

        if event_type == 'payment.captured':
            payment = event.get('payload', {}).get('payment', {}).get('entity', {})
            order_id = payment.get('order_id')
            payment_id = payment.get('id')
            if order_id and payment_id:
                supabase.table('donations') \
                    .update({
                        "razorpay_payment_id": payment_id,
                        "status": "paid",
                        "payment_method": "Razorpay"
                    }) \
                    .eq('razorpay_order_id', order_id) \
                    .execute()
        elif event_type == 'payment.failed':
            payment = event.get('payload', {}).get('payment', {}).get('entity', {})
            order_id = payment.get('order_id')
            payment_id = payment.get('id')
            if order_id:
                update_payload = {"status": "failed"}
                if payment_id:
                    update_payload["razorpay_payment_id"] = payment_id
                supabase.table('donations') \
                    .update(update_payload) \
                    .eq('razorpay_order_id', order_id) \
                    .eq('status', 'pending') \
                    .execute()

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        app.logger.error(f"Webhook error: {e}")
        return jsonify({"error": "Webhook validation failed"}), 400


@app.route("/upi-qr")
def upi_qr():
    """Generate UPI QR code"""
    try:
        amount = request.args.get('amount', '')

        upi_string = f"upi://pay?pa={UPI_VPA}&pn=Think.4U"
        if amount:
            upi_string += f"&am={amount}"
        upi_string += "&cu=INR"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(upi_string)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)

        return send_file(img_io, mimetype='image/png')

    except Exception as e:
        app.logger.error(f"Error generating QR code: {e}")
        img = Image.new('RGB', (300, 300), color='white')
        d = ImageDraw.Draw(img)
        d.text((150, 150), "QR Error", fill='black', anchor="mm")

        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)

        return send_file(img_io, mimetype='image/png')


@app.route("/donation-receipt/<int:donation_id>")
@login_required
def donation_receipt(donation_id):
    try:
        response = supabase.table("donations").select("*").eq("id", donation_id).execute()

        if not response.data:
            flash("Donation not found", "error")
            return redirect(url_for("donate"))

        donation = response.data[0]

        owner_id = donation.get("user_id")
        owner_email = donation.get("email")
        is_owner = (owner_id is not None and str(owner_id) == str(current_user.id)) or (owner_email == current_user.email)

        if not current_user.is_admin and not is_owner:
            flash("You can only view your own donation receipts.", "error")
            return redirect(url_for("user_donations"))

        if donation.get("status") != "paid":
            flash("Payment not completed", "warning")
            return redirect(url_for("donate"))

        created_at_raw = donation.get("created_at")
        if created_at_raw:
            donation["created_at"] = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))

        receipt_url = url_for("donation_receipt", donation_id=donation_id, _external=True)
        qr_code = generate_qr(receipt_url)

        context = {
            "donation": donation,
            "amount": donation.get("amount", 0),
            "payment_method": donation.get("payment_method", "Online"),
            "qr_code": qr_code,
        }

        if not donation.get("receipt_emailed") and donation.get("email"):
            email_html = render_template(
                "emails/donation_receipt_email.html",
                donation=donation,
                amount=donation.get("amount", 0)
            )
            try:
                send_email_async(
                    subject="Thank you for your donation - Think.4U (80G Eligible)",
                    recipients=[donation.get("email")],
                    html=email_html,
                )
                supabase.table("donations").update(
                    {"receipt_emailed": True}
                ).eq("id", donation_id).execute()
            except Exception as e:
                app.logger.error(f"Email failed, but receipt shown: {e}")

        return render_template("emails/donation_receipt.html", **context)

    except Exception:
        traceback.print_exc()
        flash("Error loading receipt", "error")
        return redirect(url_for("donate"))


def generate_receipt_pdf(context):
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=25*mm,
        leftMargin=25*mm,
        topMargin=25*mm,
        bottomMargin=25*mm
    )

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"<b>{context['org_name']}</b>", styles["Title"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(
        f"Donation Receipt<br/>"
        f"Receipt No: T4U-{context['donation']['id']}<br/>"
        f"Date: {context['created_at'].strftime('%d-%m-%Y')}",
        styles["Normal"]
    ))

    story.append(Spacer(1, 12))

    story.append(Paragraph(
        f"<b>Donor:</b> {context['donation'].get('name','Anonymous')}<br/>"
        f"<b>Email:</b> {context['donation'].get('email','N/A')}<br/>"
        f"<b>Amount:</b> â‚¹{context['amount']/100:.2f}",
        styles["Normal"]
    ))

    story.append(Spacer(1, 12))

    story.append(Paragraph(
        "This donation is eligible under Section 80G of the Income Tax Act, 1961.",
        styles["Normal"]
    ))

    story.append(Spacer(1, 12))

    story.append(Paragraph(
        f"80G Reg No: {context['org_80g']}<br/>PAN: {context['org_pan']}",
        styles["Normal"]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


@app.route("/volunteer", methods=["GET", "POST"])
@login_required
def volunteer():
    """Volunteer registration for logged-in users"""
    existing_application = None

    try:
        existing_response = supabase.table('volunteers') \
            .select('*') \
            .eq('user_id', int(current_user.id)) \
            .order('created_at', desc=True) \
            .limit(1) \
            .execute()
        if existing_response.data:
            existing_application = existing_response.data[0]
    except Exception:
        try:
            fallback_response = supabase.table('volunteers') \
                .select('*') \
                .eq('email', current_user.email) \
                .order('created_at', desc=True) \
                .limit(1) \
                .execute()
            if fallback_response.data:
                existing_application = fallback_response.data[0]
        except Exception as e:
            app.logger.warning(f"Volunteer lookup failed: {e}")

    if request.method == "POST":
        if existing_application and existing_application.get("status") in {"pending", "approved"}:
            flash("You already have an active volunteer registration.", "info")
            return redirect(url_for("volunteer"))

        phone = normalize_phone(request.form.get("phone"))
        message = clean_text(request.form.get("message"), 1000, keep_new_lines=True)
        interest = clean_text(request.form.get("interest"), 80)

        if not phone:
            flash("Please enter a valid 10-digit phone number.", "error")
            return redirect(url_for("volunteer"))

        try:
            supabase.table('volunteers').insert({
                "user_id": int(current_user.id),
                "name": clean_text(current_user.name, 120),
                "email": current_user.email,
                "phone": phone,
                "interest": interest,
                "message": message,
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat()
            }).execute()

            create_notification_for_user(
                int(current_user.id),
                "Volunteer request submitted",
                "Your volunteer application is pending admin review."
            )
            if current_user.email:
                submit_html = f"""
                <div style='font-family: Arial, sans-serif; line-height: 1.6; color: #0f172a;'>
                    <h2 style='color:#0ea5e9;'>Thank you for your submission</h2>
                    <p>Hello {html.escape(clean_text(current_user.name, 120) or 'Volunteer')},</p>
                    <p>We received your volunteer request successfully.</p>
                    <p>Our team will get back to you soon.</p>
                </div>
                """
                send_email_async(
                    subject="Think.4U Volunteer Submission Received",
                    recipients=[current_user.email],
                    html=submit_html
                )
            flash("Volunteer registration submitted. We will notify you after review.", "success")
            return redirect(url_for("volunteer"))
        except Exception as e:
            app.logger.error(f"Error creating volunteer: {e}")
            flash("Error submitting volunteer form. Please try again.", "error")

    volunteer_events = []
    if existing_application and existing_application.get("status") == "approved":
        try:
            events_response = supabase.table("volunteer_events") \
                .select("*") \
                .order("event_date") \
                .limit(20) \
                .execute()
            volunteer_events = events_response.data or []
        except Exception:
            volunteer_events = [
                {
                    "title": "Community Food Drive",
                    "event_date": datetime.now(timezone.utc).date().isoformat(),
                    "location": "Main Community Hall",
                    "description": "Distribute food kits and support local families."
                }
            ]

    return render_template(
        "volunteer.html",
        existing_application=existing_application,
        volunteer_events=volunteer_events,
    )


# ===================================
# AUTH ROUTES
# ===================================
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard" if not current_user.is_admin else "admin_dashboard"))

    if request.method == "POST":
        name = clean_text(request.form.get("name"), 120)
        email = normalize_email(request.form.get("email"))
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        role = clean_text(request.form.get("role") or "donor", 20).lower()
        captcha_answer = request.form.get("captcha_answer")

        if not verify_math_captcha("signup", captcha_answer):
            flash("Captcha verification failed.", "error")
            return render_template("signup.html", captcha_question=generate_math_captcha("signup"))

        if not name or not email:
            flash("Name and a valid email are required.", "error")
            return render_template("signup.html", captcha_question=generate_math_captcha("signup"))

        password_ok, password_error = validate_password_strength(password)
        if not password_ok:
            flash(password_error, "error")
            return render_template("signup.html", captcha_question=generate_math_captcha("signup"))

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("signup.html", captcha_question=generate_math_captcha("signup"))

        if role not in {"donor", "volunteer", "both"}:
            role = "donor"

        try:
            existing = supabase.table("users").select("id").eq("email", email).limit(1).execute()
            if existing.data:
                flash("Account already exists. Please log in.", "info")
                return redirect(url_for("login"))

            otp = set_pending_otp("signup", email, {
                "name": name,
                "password_hash": generate_password_hash(password),
                "role": role,
            })
            email_sent = send_otp_email(email, otp, "Signup Verification")
            if email_sent:
                flash("Signup OTP sent to your email.", "success")
            else:
                if app.debug and ALLOW_DEV_OTP_FALLBACK:
                    app.logger.warning(f"DEV OTP fallback (signup) for {email}: {otp}")
                    flash("Email OTP failed. In dev mode, use the OTP shown in server logs.", "warning")
                else:
                    session.pop("pending_signup", None)
                    flash("Unable to send OTP email. Please verify mail settings and try again.", "error")
                    return redirect(url_for("signup"))
            return redirect(url_for("verify_signup"))
        except Exception as e:
            app.logger.error(f"Signup error: {e}")
            flash("Unable to start signup. Please try again.", "error")
            return render_template("signup.html", captcha_question=generate_math_captcha("signup"))

    return render_template("signup.html", captcha_question=generate_math_captcha("signup"))


@app.route("/verify-signup", methods=["GET", "POST"])
def verify_signup():
    pending = session.get("pending_signup")
    if not pending:
        flash("Signup session expired. Please sign up again.", "error")
        return redirect(url_for("signup"))

    if request.method == "POST":
        otp_code = clean_text(request.form.get("otp"), 10)
        ok, payload_or_message = validate_pending_otp("signup", otp_code)
        if not ok:
            flash(payload_or_message, "error")
            return redirect(url_for("verify_signup"))

        payload = payload_or_message.get("payload", {})
        email = payload_or_message.get("email")

        try:
            existing = supabase.table("users").select("*").eq("email", email).limit(1).execute()
            if existing.data:
                session.pop("pending_signup", None)
                flash("Account already exists. Please login.", "info")
                return redirect(url_for("login"))

            insert_payload = {
                "email": email,
                "name": clean_text(payload.get("name"), 120),
                "password_hash": payload.get("password_hash"),
                "role": payload.get("role", "donor"),
                "is_admin": False,
                "email_verified": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            try:
                create_response = supabase.table("users").insert(insert_payload).execute()
            except Exception:
                fallback_payload = {
                    "email": insert_payload["email"],
                    "name": insert_payload["name"],
                    "password_hash": insert_payload["password_hash"],
                    "role": insert_payload["role"],
                    "is_admin": False,
                    "created_at": insert_payload["created_at"],
                }
                create_response = supabase.table("users").insert(fallback_payload).execute()

            user_row = (create_response.data or [None])[0]
            if not user_row:
                fetch_response = supabase.table("users").select("*").eq("email", email).limit(1).execute()
                user_row = (fetch_response.data or [None])[0]

            if not user_row:
                raise ValueError("User could not be created")

            user = User(
                id=user_row["id"],
                email=user_row["email"],
                name=user_row.get("name", "User"),
                is_admin=user_row.get("is_admin", False),
                role=user_row.get("role", "donor")
            )
            login_user(user)
            session.pop("pending_signup", None)

            create_notification_for_user(
                int(user.id),
                "Welcome to Think.4U",
                "Your account is ready. You can now donate, volunteer, and access your dashboard."
            )

            flash("Signup complete. Welcome!", "success")
            return redirect(url_for("dashboard"))
        except Exception as e:
            app.logger.error(f"Signup verification error: {e}")
            flash("Unable to verify signup. Please try again.", "error")

    return render_template("verify_otp.html", flow="signup")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin_dashboard" if current_user.is_admin else "dashboard"))

    if request.method == "POST":
        email = normalize_email(request.form.get("email"))
        password = request.form.get("password", "")
        captcha_answer = request.form.get("captcha_answer")
        next_page = request.args.get("next") or request.form.get("next")

        if not email:
            flash("Please enter a valid email address.", "error")
            return render_template("login.html", captcha_question=generate_math_captcha("login"), next_page=next_page)

        identity = f"{get_client_ip()}:{email}"
        blocked_for = get_login_block_remaining(identity)
        if blocked_for > 0:
            flash(f"Too many attempts. Try again in {blocked_for // 60 + 1} minute(s).", "error")
            return render_template("login.html", captcha_question=generate_math_captcha("login"), next_page=next_page)

        if not verify_math_captcha("login", captcha_answer):
            record_failed_login(identity)
            flash("Captcha verification failed.", "error")
            return render_template("login.html", captcha_question=generate_math_captcha("login"), next_page=next_page)

        try:
            response = supabase.table('users').select('*').eq('email', email).limit(1).execute()
            if not response.data:
                record_failed_login(identity)
                flash("No account found. Please sign up first.", "info")
                return redirect(url_for("signup"))

            user_data = response.data[0]
            if not check_password_hash(user_data.get('password_hash', ''), password):
                record_failed_login(identity)
                flash("Invalid email or password.", "error")
                return render_template("login.html", captcha_question=generate_math_captcha("login"), next_page=next_page)

            reset_failed_login(identity)

            otp = set_pending_otp("login", email, {
                "id": user_data["id"],
                "email": user_data["email"],
                "name": user_data.get("name", "User"),
                "is_admin": user_data.get("is_admin", False),
                "role": user_data.get("role", "donor"),
                "next_page": next_page,
            })
            email_sent = send_otp_email(email, otp, "Login Verification")
            if email_sent:
                flash("OTP sent to your email.", "success")
            else:
                if app.debug and ALLOW_DEV_OTP_FALLBACK:
                    app.logger.warning(f"DEV OTP fallback (login) for {email}: {otp}")
                    flash("Email OTP failed. In dev mode, use the OTP shown in server logs.", "warning")
                else:
                    session.pop("pending_login", None)
                    flash("Unable to send OTP email. Please verify mail settings and try again.", "error")
                    return redirect(url_for("login"))
            return redirect(url_for("verify_login"))
        except Exception as e:
            app.logger.error(f"Login error: {e}")
            flash("Login error. Please try again.", "error")
            return render_template("login.html", captcha_question=generate_math_captcha("login"), next_page=next_page)

    return render_template("login.html", captcha_question=generate_math_captcha("login"))


@app.route("/verify-login", methods=["GET", "POST"])
def verify_login():
    pending = session.get("pending_login")
    if not pending:
        flash("Login session expired. Please login again.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        otp_code = clean_text(request.form.get("otp"), 10)
        ok, payload_or_message = validate_pending_otp("login", otp_code)
        if not ok:
            flash(payload_or_message, "error")
            return redirect(url_for("verify_login"))

        payload = payload_or_message.get("payload", {})
        user = User(
            id=payload.get("id"),
            email=payload.get("email"),
            name=payload.get("name", "User"),
            is_admin=payload.get("is_admin", False),
            role=payload.get("role", "donor"),
        )
        login_user(user)
        session.pop("pending_login", None)

        flash("Logged in successfully.", "success")
        next_page = payload.get("next_page")
        if next_page:
            return redirect(next_page)
        return redirect(url_for("admin_dashboard" if user.is_admin else "dashboard"))

    return render_template("verify_otp.html", flow="login")


@app.route("/logout")
@login_required
def logout():
    """Logout"""
    reason = clean_text(request.args.get("reason", ""), 40).lower()
    logout_user()
    session.pop("pending_login", None)
    session.pop("pending_signup", None)
    session.pop("last_activity_ts", None)
    if reason == "inactive":
        timeout_minutes = max(1, INACTIVITY_TIMEOUT_SECONDS // 60)
        flash(f"You were logged out after {timeout_minutes} minute(s) of inactivity.", "warning")
        return redirect(url_for("login"))
    flash("Logged out successfully", "info")
    return redirect("/")


@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))

    donations = []
    notifications = []
    volunteer_application = None
    volunteer_events = []
    approved_certificates_count = 0

    expire_stale_pending_donations(user_id=current_user.id, email=current_user.email)

    try:
        donations_response = supabase.table("donations") \
            .select("*") \
            .eq("user_id", int(current_user.id)) \
            .order("created_at", desc=True) \
            .limit(10) \
            .execute()
        donations = donations_response.data or []

        if not donations:
            donations_response = supabase.table("donations") \
                .select("*") \
                .eq("email", current_user.email) \
                .order("created_at", desc=True) \
                .limit(10) \
                .execute()
            donations = donations_response.data or []
    except Exception as e:
        app.logger.warning(f"Dashboard donations lookup failed: {e}")

    try:
        trim_user_notifications(user_id=int(current_user.id), max_keep=4)
        notifications_response = supabase.table("notifications") \
            .select("*") \
            .eq("user_id", int(current_user.id)) \
            .order("created_at", desc=True) \
            .limit(4) \
            .execute()
        notifications = notifications_response.data or []
    except Exception:
        notifications = []

    try:
        volunteer_response = supabase.table("volunteers") \
            .select("*") \
            .eq("user_id", int(current_user.id)) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        volunteer_application = (volunteer_response.data or [None])[0]

        if volunteer_application and volunteer_application.get("status") == "approved":
            events_response = supabase.table("volunteer_events") \
                .select("*") \
                .order("event_date") \
                .limit(10) \
                .execute()
            volunteer_events = events_response.data or []
    except Exception:
        volunteer_application = volunteer_application or None

    try:
        cert_response = supabase.table("event_certificates") \
            .select("id") \
            .eq("user_id", int(current_user.id)) \
            .eq("status", "approved") \
            .execute()
        approved_certificates_count = len(cert_response.data or [])
    except Exception:
        approved_certificates_count = 0

    total_donated = sum((d.get("amount") or 0) for d in donations if d.get("status") == "paid") / 100

    return render_template(
        "dashboard.html",
        recent_donations=donations,
        notifications=notifications,
        total_donated=total_donated,
        volunteer_application=volunteer_application,
        volunteer_events=volunteer_events,
        approved_certificates_count=approved_certificates_count,
    )


@app.route("/dashboard/donations")
@login_required
def user_donations():
    donations = []
    expire_stale_pending_donations(user_id=current_user.id, email=current_user.email)

    try:
        response = supabase.table("donations") \
            .select("*") \
            .eq("user_id", int(current_user.id)) \
            .order("created_at", desc=True) \
            .execute()
        donations = response.data or []

        if not donations:
            response = supabase.table("donations") \
                .select("*") \
                .eq("email", current_user.email) \
                .order("created_at", desc=True) \
                .execute()
            donations = response.data or []
    except Exception as e:
        app.logger.warning(f"User donations lookup failed: {e}")

    return render_template("donation_history.html", donations=donations)


@app.route("/previous-donations")
@login_required
def previous_donations():
    return redirect(url_for("user_donations"))


@app.route("/appointments", methods=["GET", "POST"])
@login_required
def appointments():
    if request.method == "POST":
        appointment_date = clean_text(request.form.get("appointment_date"), 20)
        appointment_time = clean_text(request.form.get("appointment_time"), 20)
        purpose = clean_text(request.form.get("purpose"), 120)
        notes = clean_text(request.form.get("notes"), 1000, keep_new_lines=True)

        if not appointment_date or not appointment_time or not purpose:
            flash("Please fill all required appointment fields.", "error")
            return redirect(url_for("appointments"))

        try:
            supabase.table("appointments").insert({
                "user_id": int(current_user.id),
                "name": clean_text(current_user.name, 120),
                "email": current_user.email,
                "appointment_date": appointment_date,
                "appointment_time": appointment_time,
                "purpose": purpose,
                "notes": notes,
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            create_notification_for_user(
                int(current_user.id),
                "Appointment submitted",
                "Your appointment request has been submitted and is awaiting confirmation."
            )
            flash("Appointment request submitted.", "success")
            return redirect(url_for("appointments"))
        except Exception as e:
            app.logger.error(f"Appointment save failed: {e}")
            flash("Could not save appointment. Please contact support.", "error")

    items = []
    try:
        response = supabase.table("appointments") \
            .select("*") \
            .eq("user_id", int(current_user.id)) \
            .order("created_at", desc=True) \
            .limit(20) \
            .execute()
        items = response.data or []
    except Exception:
        items = []

    return render_template("appointments.html", appointments=items)


@app.route("/fundraising")
def fundraising():
    campaigns = []
    try:
        response = supabase.table("fundraisers").select("*").eq("status", "active").order("created_at", desc=True).limit(30).execute()
        campaigns = response.data or []
    except Exception:
        try:
            response = supabase.table("fundraisers").select("*").order("created_at", desc=True).limit(30).execute()
            campaigns = response.data or []
        except Exception:
            campaigns = [
                {
                    "title": "Education Scholarship Fund",
                    "description": "Support school and college scholarships for underprivileged students.",
                    "target_amount": 500000,
                    "raised_amount": 125000,
                },
                {
                    "title": "Rural Health Access",
                    "description": "Help us run preventive health camps in remote communities.",
                    "target_amount": 350000,
                    "raised_amount": 78000,
                }
            ]

    return render_template("fundraising.html", campaigns=campaigns)


@app.route("/events")
@login_required
def events_page():
    events = []
    registration_map = {}
    certificate_map = {}

    try:
        programs_response = supabase.table("programs").select("*").order("created_at", desc=True).limit(100).execute()
        for program in (programs_response.data or []):
            ensure_event_for_program(program)
    except Exception as e:
        app.logger.warning(f"Program-event sync skipped: {e}")

    try:
        response = supabase.table("volunteer_events").select("*").order("event_date").limit(100).execute()
        events = response.data or []
    except Exception:
        events = []

    try:
        registration_response = supabase.table("event_participants") \
            .select("*") \
            .eq("user_id", int(current_user.id)) \
            .execute()
        registrations = registration_response.data or []
        if not registrations:
            fallback_response = supabase.table("event_participants") \
                .select("*") \
                .eq("email", current_user.email) \
                .execute()
            registrations = fallback_response.data or []
        for item in registrations:
            event_id = item.get("event_id")
            if event_id is not None:
                registration_map[int(event_id)] = item
    except Exception:
        registration_map = {}

    try:
        certificate_response = supabase.table("event_certificates") \
            .select("*") \
            .eq("user_id", int(current_user.id)) \
            .execute()
        for item in (certificate_response.data or []):
            event_id = item.get("event_id")
            if event_id is not None:
                certificate_map[int(event_id)] = item
    except Exception:
        certificate_map = {}

    return render_template(
        "events.html",
        events=events,
        registration_map=registration_map,
        certificate_map=certificate_map
    )


@app.route("/events/register/<int:event_id>", methods=["POST"])
@login_required
def register_for_event(event_id):
    try:
        event_response = supabase.table("volunteer_events").select("*").eq("id", event_id).limit(1).execute()
        event_row = (event_response.data or [None])[0]
        if not event_row:
            flash("Event not found.", "error")
            return redirect(url_for("events_page"))

        existing_response = supabase.table("event_participants") \
            .select("id") \
            .eq("event_id", event_id) \
            .eq("user_id", int(current_user.id)) \
            .limit(1) \
            .execute()
        existing_data = existing_response.data or []
        if not existing_data:
            email_existing_response = supabase.table("event_participants") \
                .select("id") \
                .eq("event_id", event_id) \
                .eq("email", current_user.email) \
                .limit(1) \
                .execute()
            existing_data = email_existing_response.data or []

        if existing_data:
            flash("You are already registered for this event.", "info")
            return redirect(url_for("events_page"))

        supabase.table("event_participants").insert({
            "event_id": event_id,
            "user_id": int(current_user.id),
            "name": clean_text(current_user.name, 120),
            "email": current_user.email,
            "role": current_user.role if current_user.role in {"donor", "volunteer", "both", "admin"} else "donor",
            "status": "registered",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        try:
            supabase.table("event_certificates").upsert({
                "event_id": event_id,
                "user_id": int(current_user.id),
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="event_id,user_id").execute()
        except Exception as cert_error:
            app.logger.warning(f"Certificate request upsert skipped: {cert_error}")

        create_notification_for_user(
            int(current_user.id),
            "Event registration confirmed",
            f"You are registered for {event_row.get('title', 'the event')}. Certificate status will update after admin review."
        )
        flash("Event registration successful.", "success")
    except Exception as e:
        app.logger.error(f"Event registration failed: {e}")
        flash("Unable to register for event right now.", "error")

    return redirect(url_for("events_page"))


@app.route("/certificates")
@login_required
def certificates_page():
    participation_rows = []
    certificate_rows = []
    event_map = {}
    certificate_map = {}
    rows = []

    try:
        response = supabase.table("event_participants") \
            .select("*") \
            .eq("user_id", int(current_user.id)) \
            .order("created_at", desc=True) \
            .execute()
        participation_rows = response.data or []
        if not participation_rows:
            fallback = supabase.table("event_participants") \
                .select("*") \
                .eq("email", current_user.email) \
                .order("created_at", desc=True) \
                .execute()
            participation_rows = fallback.data or []
    except Exception:
        participation_rows = []

    event_ids = sorted({
        int(item.get("event_id"))
        for item in participation_rows
        if item.get("event_id") is not None
    })

    if event_ids:
        try:
            events_response = supabase.table("volunteer_events") \
                .select("*") \
                .in_("id", event_ids) \
                .execute()
            event_map = {int(evt["id"]): evt for evt in (events_response.data or [])}
        except Exception:
            event_map = {}

        try:
            cert_response = supabase.table("event_certificates") \
                .select("*") \
                .eq("user_id", int(current_user.id)) \
                .in_("event_id", event_ids) \
                .execute()
            certificate_rows = cert_response.data or []
            certificate_map = {
                int(item["event_id"]): item
                for item in certificate_rows
                if item.get("event_id") is not None
            }
        except Exception:
            certificate_rows = []
            certificate_map = {}

    for item in participation_rows:
        event_id = item.get("event_id")
        if event_id is None:
            continue
        event_id = int(event_id)
        event_row = event_map.get(event_id, {})
        cert_row = certificate_map.get(event_id, {})
        rows.append({
            "event_id": event_id,
            "event_title": event_row.get("title", "Event"),
            "event_date": event_row.get("event_date") or event_row.get("date"),
            "event_location": event_row.get("location"),
            "participation_status": item.get("status", "registered"),
            "registered_at": item.get("created_at"),
            "certificate_status": cert_row.get("status", "pending"),
            "certificate_url": cert_row.get("certificate_url"),
            "certificate_note": cert_row.get("review_note"),
        })

    approved_count = sum(1 for item in rows if item.get("certificate_status") == "approved")

    return render_template(
        "certificates.html",
        certificates=rows,
        approved_count=approved_count
    )


@app.route("/tax-exemption")
@login_required
def tax_exemption_page():
    return render_template("tax_exemption.html")


@app.route("/grievance", methods=["GET", "POST"])
@login_required
def grievance_feedback():
    if request.method == "POST":
        issue_type = clean_text(request.form.get("issue_type"), 40)
        subject = clean_text(request.form.get("subject"), 120)
        message = clean_text(request.form.get("message"), 2000, keep_new_lines=True)

        if not issue_type or not subject or not message:
            flash("Please fill all grievance fields.", "error")
            return redirect(url_for("grievance_feedback"))

        try:
            supabase.table("grievances").insert({
                "user_id": int(current_user.id),
                "name": clean_text(current_user.name, 120),
                "email": current_user.email,
                "issue_type": issue_type,
                "subject": subject,
                "message": message,
                "status": "open",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            create_notification_for_user(
                int(current_user.id),
                "Grievance submitted",
                "Your grievance/feedback has been submitted. Our team will follow up soon."
            )
            if current_user.email:
                grievance_html = f"""
                <div style='font-family: Arial, sans-serif; line-height: 1.6; color: #0f172a;'>
                    <h2 style='color:#0ea5e9;'>Thank you for your submission</h2>
                    <p>Hello {html.escape(clean_text(current_user.name, 120) or 'Supporter')},</p>
                    <p>We received your grievance/feedback successfully.</p>
                    <p>Our support team will get back to you soon.</p>
                </div>
                """
                send_email_async(
                    subject="Think.4U Support Request Received",
                    recipients=[current_user.email],
                    html=grievance_html
                )
            flash("Your grievance/feedback has been submitted.", "success")
            return redirect(url_for("grievance_feedback"))
        except Exception as e:
            app.logger.error(f"Grievance save failed: {e}")
            flash("Unable to submit grievance right now.", "error")

    items = []
    try:
        response = supabase.table("grievances") \
            .select("*") \
            .eq("user_id", int(current_user.id)) \
            .order("created_at", desc=True) \
            .limit(20) \
            .execute()
        items = response.data or []
    except Exception:
        items = []

    return render_template("grievance.html", grievances=items)


@app.route("/policy-terms")
def policy_terms():
    return render_template("policy_terms.html")


@app.route("/error-help")
def error_help():
    return render_template("error_help.html")


def _render_error(status_code, title, message):
    if request.path.startswith("/api/") or request.is_json:
        return jsonify({
            "status": status_code,
            "error": title,
            "message": message,
        }), status_code
    return render_template(
        "errors/error_page.html",
        status_code=status_code,
        error_title=title,
        error_message=message,
    ), status_code


@app.errorhandler(403)
def handle_403(_error):
    return _render_error(403, "Access denied", "You do not have permission to access this page.")


@app.errorhandler(400)
def handle_400(_error):
    return _render_error(400, "Bad request", "The request could not be understood. Please try again.")


@app.errorhandler(404)
def handle_404(_error):
    return _render_error(404, "Page not found", "The page you requested does not exist or may have been moved.")


@app.errorhandler(405)
def handle_405(_error):
    return _render_error(405, "Method not allowed", "This action is not allowed for the requested page.")


@app.errorhandler(429)
def handle_429(_error):
    return _render_error(429, "Too many requests", "You are sending requests too quickly. Please wait and try again.")


@app.errorhandler(500)
def handle_500(error):
    app.logger.error(f"Server error: {error}", exc_info=True)
    return _render_error(500, "Server error", "Something went wrong on our side. Please try again shortly.")


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        return error
    app.logger.error(f"Unhandled exception: {error}", exc_info=True)
    return _render_error(500, "Unexpected error", "An unexpected error occurred. Please try again.")


# ===================================
# ADMIN ROUTES
# ===================================
@app.route("/api/analytics")
@login_required
def api_analytics():
    """API endpoint for analytics"""
    try:
        # Get total donations
        donations_response = supabase.table('donations') \
            .select("amount", count='exact') \
            .eq('status', 'paid') \
            .execute()
        
        total_donations = sum(d['amount'] for d in donations_response.data) / 100 if donations_response.data else 0
        
        # Get counts
        volunteers_response = supabase.table('volunteers').select("*", count='exact').execute()
        programs_response = supabase.table('programs').select("*", count='exact').eq('status', 'active').execute()
        try:
            grievances_response = supabase.table('grievances').select("*", count='exact').in_('status', ['open', 'in_progress']).execute()
        except Exception:
            grievances_response = supabase.table('grievances').select("*", count='exact').execute()
        try:
            fundraising_response = supabase.table('fundraisers').select("*", count='exact').eq('status', 'active').execute()
        except Exception:
            fundraising_response = supabase.table('fundraisers').select("*", count='exact').execute()
        
        return jsonify({
            'total_donations': total_donations,
            'donation_count': donations_response.count or 0,
            'volunteer_count': volunteers_response.count or 0,
            'program_count': programs_response.count or 0,
            'open_grievance_count': grievances_response.count or 0,
            'active_fundraising_count': fundraising_response.count or 0,
        })
    except Exception as e:
        app.logger.error(f"Analytics error: {e}")
        return jsonify({'error': str(e)}), 500
    
@app.route("/api/chart-donations")
@login_required
def chart_donations():
    """Get donation data for chart"""
    try:
        from datetime import datetime, timedelta
        
        # Get donations from last 7 days
        today = datetime.utcnow()
        days = []
        labels = []
        data = []
        
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            days.append(day.date())
            labels.append(day.strftime('%a'))  # Mon, Tue, etc.
        
        # Get all paid donations
        response = supabase.table('donations') \
            .select("amount, created_at") \
            .eq('status', 'paid') \
            .execute()
        
        # Group by day
        day_totals = {day: 0 for day in days}
        
        for donation in response.data:
            created_date = datetime.fromisoformat(donation['created_at'].replace('Z', '+00:00')).date()
            if created_date in day_totals:
                day_totals[created_date] += donation['amount'] / 100  # Convert to rupees
        
        # Convert to list for chart
        data = [day_totals[day] for day in days]
        
        return jsonify({
            "labels": labels,
            "data": data
        })
    except Exception as e:
        app.logger.error(f"Chart donations error: {e}")
        # Return empty data instead of error
        return jsonify({
            "labels": ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            "data": [0, 0, 0, 0, 0, 0, 0]
        })


@app.route("/api/chart-volunteers")
@login_required
def chart_volunteers():
    """Get volunteer status data for chart"""
    try:
        # Get volunteer counts by status
        response = supabase.table('volunteers').select("status").execute()
        
        statuses = {
            'approved': 0,
            'pending': 0,
            'rejected': 0
        }
        
        for volunteer in response.data:
            status = volunteer.get('status', 'pending').lower()
            if status in statuses:
                statuses[status] += 1
        
        return jsonify({
            "labels": ['Approved', 'Pending', 'Rejected'],
            "data": [statuses['approved'], statuses['pending'], statuses['rejected']]
        })
    except Exception as e:
        app.logger.error(f"Chart volunteers error: {e}")
        return jsonify({
            "labels": ['Approved', 'Pending', 'Rejected'],
            "data": [0, 0, 0]
        })


@app.route("/admin")
@login_required
def admin_dashboard():
    """Admin dashboard"""
    try:
        # Get recent donations
        donations_response = supabase.table('donations') \
            .select("*") \
            .eq('status', 'paid') \
            .order('created_at', desc=True) \
            .limit(10) \
            .execute()
        
        recent_donations = donations_response.data if donations_response.data else []
        
        # Calculate total
        total_donations = sum(d['amount'] for d in recent_donations) / 100
        
        volunteers_response = supabase.table('volunteers').select("*", count='exact').execute()
        
        return render_template(
            "admin/dashboard.html",
            total_donations=total_donations,
            donation_count=len(recent_donations),
            volunteer_count=volunteers_response.count or 0,
            recent_donations=recent_donations
        )
    except Exception as e:
        app.logger.error(f"Dashboard error: {e}")
        flash("Error loading dashboard", "error")
        return render_template("admin/dashboard.html", total_donations=0, donation_count=0, volunteer_count=0, recent_donations=[])

@app.route("/admin/donations")
@login_required
def admin_donations():
    """View all donations"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        offset = (page - 1) * per_page
        
        response = supabase.table('donations') \
            .select("*", count='exact') \
            .order('created_at', desc=True) \
            .range(offset, offset + per_page - 1) \
            .execute()
        
        # Mock pagination object
        class Pagination:
            def __init__(self, items, total, page, per_page):
                self.items = items
                self.total = total
                self.page = page
                self.per_page = per_page
                self.pages = (total + per_page - 1) // per_page
                self.has_prev = page > 1
                self.has_next = page < self.pages
                self.prev_num = page - 1 if self.has_prev else None
                self.next_num = page + 1 if self.has_next else None
        
        donations = Pagination(
            response.data if response.data else [],
            response.count or 0,
            page,
            per_page
        )
        
        return render_template("admin/donations.html", donations=donations)
    except Exception as e:
        app.logger.error(f"Donations page error: {e}")
        flash("Error loading donations", "error")
        return redirect('/admin')

@app.route("/admin/donations/export")
@login_required
def export_donations():
    """Export donations to CSV"""
    try:
        response = supabase.table('donations').select("*").eq('status', 'paid').execute()
        donations = response.data
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Amount (â‚¹)', 'Payment ID', 'Email', 'Date', 'Status'])
        
        for d in donations:
            writer.writerow([
                d['id'],
                f"{d['amount']/100:.2f}",
                d.get('razorpay_payment_id', ''),
                d.get('email', ''),
                d['created_at'],
                d['status']
            ])
        
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'donations_{datetime.now().strftime("%Y%m%d")}.csv'
        )
    except Exception as e:
        flash(f"Export failed: {str(e)}", "error")
        return redirect('/admin/donations')





@app.route("/admin/volunteers")
@login_required
def admin_volunteers():
    """View all volunteers"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        offset = (page - 1) * per_page
        
        response = supabase.table('volunteers') \
            .select("*", count='exact') \
            .order('created_at', desc=True) \
            .range(offset, offset + per_page - 1) \
            .execute()
        
        class Pagination:
            def __init__(self, items, total, page, per_page):
                self.items = items
                self.total = total
                self.page = page
                self.per_page = per_page
                self.pages = (total + per_page - 1) // per_page
                self.has_prev = page > 1
                self.has_next = page < self.pages
                self.prev_num = page - 1 if self.has_prev else None
                self.next_num = page + 1 if self.has_next else None
        
        volunteers = Pagination(
            response.data if response.data else [],
            response.count or 0,
            page,
            per_page
        )
        
        return render_template("admin/volunteers.html", volunteers=volunteers)
    except Exception as e:
        app.logger.error(f"Volunteers page error: {e}")
        flash("Error loading volunteers", "error")
        return redirect('/admin')
    
@app.route("/admin/volunteers/export")
@login_required
def export_volunteers():
    """Export volunteers to CSV"""
    try:
        response = supabase.table('volunteers').select("*").execute()
        volunteers = response.data
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Name', 'Email', 'Phone', 'Status', 'Date'])
        
        for v in volunteers:
            writer.writerow([
                v['id'],
                v['name'],
                v.get('email', ''),
                v.get('phone', ''),
                v['status'],
                v['created_at']
            ])
        
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'volunteers_{datetime.now().strftime("%Y%m%d")}.csv'
        )
    except Exception as e:
        flash(f"Export failed: {str(e)}", "error")
        return redirect('/admin/volunteers')

@app.route("/admin/volunteer/<int:vid>/action", methods=["POST"])
@login_required
def volunteer_action(vid):
    """Update volunteer status"""
    action = clean_text(request.form.get("action"), 20)
    
    try:
        if action not in {"approve", "reject"}:
            flash("Invalid action", "error")
            return redirect(url_for("admin_volunteers"))

        status = "approved" if action == "approve" else "rejected"
        
        response = supabase.table('volunteers') \
            .update({"status": status}) \
            .eq('id', vid) \
            .execute()
        
        if response.data:
            volunteer = response.data[0]
            recipient = volunteer.get("email")
            if recipient:
                status_label = "approved" if status == "approved" else "not approved"
                mail_html = f"""
                <div style='font-family: Arial, sans-serif; line-height: 1.6; color: #0f172a;'>
                    <h2 style='color:#0ea5e9;'>Think.4U Volunteer Update</h2>
                    <p>Hello {html.escape(volunteer.get('name', 'Volunteer'))},</p>
                    <p>Your volunteer registration has been <strong>{status_label}</strong> by our admin team.</p>
                    <p>Please log in to your Think.4U dashboard to view your latest status and opportunities.</p>
                </div>
                """
                send_email_async(
                    subject="Think.4U Volunteer Application Status",
                    recipients=[recipient],
                    html=mail_html
                )
                create_notification_for_email(
                    recipient,
                    "Volunteer application update",
                    f"Your volunteer application was marked as {status} by admin."
                )
            flash(f"Volunteer {volunteer['name']} {status}!", "success")
        
    except Exception as e:
        flash(f"Action failed: {str(e)}", "error")
    
    return redirect(url_for("admin_volunteers"))

# ===================================
# VOLUNTEER INFO ROUTE
# ===================================
@app.route("/admin/volunteer/<int:vid>/info")
@login_required
def volunteer_info(vid):
    """Get volunteer information as JSON"""
    try:
        response = supabase.table('volunteers').select('*').eq('id', vid).execute()
        
        if not response.data:
            return jsonify({"error": "Volunteer not found"}), 404
        
        return jsonify({"volunteer": response.data[0]})
    except Exception as e:
        app.logger.error(f"Error fetching volunteer info: {e}")
        return jsonify({"error": str(e)}), 500


# ===================================
# VOLUNTEER DONATIONS ROUTE
# ===================================
@app.route("/admin/volunteer/<int:vid>/donations")
@login_required
def volunteer_donations(vid):
    """View donations made by a volunteer"""
    try:
        # Get volunteer info
        volunteer_response = supabase.table('volunteers').select('*').eq('id', vid).execute()
        
        if not volunteer_response.data:
            flash('Volunteer not found', 'error')
            return redirect('/admin/volunteers')
        
        volunteer = volunteer_response.data[0]
        
        # Get donations by matching email
        donations_response = supabase.table('donations') \
            .select('*') \
            .eq('email', volunteer['email']) \
            .order('created_at', desc=True) \
            .execute()
        
        donations = donations_response.data if donations_response.data else []
        
        # Calculate total donated
        total_donated = sum(d.get('amount', 0) for d in donations) / 100  # Convert paise to rupees
        
        return render_template('admin/volunteer_donations.html',
                             volunteer=volunteer,
                             donations=donations,
                             total_donated=total_donated)
    except Exception as e:
        app.logger.error(f"Error fetching volunteer donations: {e}")
        flash('Error loading donations', 'error')
        return redirect('/admin/volunteers')


# ===================================
# DELETE VOLUNTEER ROUTE
# ===================================
@app.route("/admin/volunteer/<int:vid>/delete", methods=["DELETE"])
@login_required
def delete_volunteer(vid):
    """Delete a volunteer"""
    try:
        # Check if volunteer exists
        check_response = supabase.table('volunteers').select('id').eq('id', vid).execute()
        
        if not check_response.data:
            return jsonify({"error": "Volunteer not found"}), 404
        
        # Delete volunteer
        supabase.table('volunteers').delete().eq('id', vid).execute()
        
        app.logger.info(f"Volunteer {vid} deleted")
        
        return jsonify({"success": True, "message": "Volunteer removed successfully"})
    except Exception as e:
        app.logger.error(f"Error deleting volunteer: {e}")
        return jsonify({"error": str(e)}), 500


    

@app.route("/admin/certificates")
@login_required
def admin_certificates():
    participation_rows = []
    event_map = {}
    cert_map = {}
    user_map = {}
    rows = []

    try:
        participants_response = supabase.table("event_participants") \
            .select("*") \
            .order("created_at", desc=True) \
            .limit(300) \
            .execute()
        participation_rows = participants_response.data or []
    except Exception as e:
        app.logger.error(f"Admin certificates participant load failed: {e}")
        participation_rows = []

    event_ids = sorted({
        int(item.get("event_id"))
        for item in participation_rows
        if item.get("event_id") is not None
    })
    user_ids = sorted({
        int(item.get("user_id"))
        for item in participation_rows
        if item.get("user_id") is not None
    })

    if event_ids:
        try:
            events_response = supabase.table("volunteer_events") \
                .select("*") \
                .in_("id", event_ids) \
                .execute()
            event_map = {int(item["id"]): item for item in (events_response.data or [])}
        except Exception as e:
            app.logger.warning(f"Admin certificate events lookup failed: {e}")
            event_map = {}

    if user_ids:
        try:
            users_response = supabase.table("users") \
                .select("id,email,name") \
                .in_("id", user_ids) \
                .execute()
            user_map = {int(item["id"]): item for item in (users_response.data or [])}
        except Exception as e:
            app.logger.warning(f"Admin certificate users lookup failed: {e}")
            user_map = {}

    try:
        cert_response = supabase.table("event_certificates").select("*").execute()
        cert_map = {
            f"{int(item.get('event_id'))}:{int(item.get('user_id'))}": item
            for item in (cert_response.data or [])
            if item.get("event_id") is not None and item.get("user_id") is not None
        }
    except Exception as e:
        app.logger.warning(f"Admin certificate status lookup failed: {e}")
        cert_map = {}

    for item in participation_rows:
        event_id = item.get("event_id")
        user_id = item.get("user_id")
        if event_id is None or user_id is None:
            continue
        event_id = int(event_id)
        user_id = int(user_id)

        cert_key = f"{event_id}:{user_id}"
        cert_row = cert_map.get(cert_key, {})
        event_row = event_map.get(event_id, {})
        user_row = user_map.get(user_id, {})

        rows.append({
            "event_id": event_id,
            "user_id": user_id,
            "event_title": event_row.get("title", "Event"),
            "event_date": event_row.get("event_date") or event_row.get("date"),
            "participant_name": item.get("name") or user_row.get("name") or "Participant",
            "participant_email": item.get("email") or user_row.get("email"),
            "participation_status": item.get("status", "registered"),
            "certificate_status": cert_row.get("status", "pending"),
            "certificate_url": cert_row.get("certificate_url"),
            "review_note": cert_row.get("review_note"),
            "reviewed_at": cert_row.get("reviewed_at"),
        })

    return render_template("admin/certificates.html", items=rows)


@app.route("/admin/certificates/action", methods=["POST"])
@login_required
def admin_certificate_action():
    action = clean_text(request.form.get("action"), 20).lower()
    certificate_url = clean_text(request.form.get("certificate_url"), 500)
    review_note = clean_text(request.form.get("review_note"), 500, keep_new_lines=True)

    try:
        event_id = int(request.form.get("event_id", "0"))
        user_id = int(request.form.get("user_id", "0"))
    except (TypeError, ValueError):
        flash("Invalid certificate action payload.", "error")
        return redirect(url_for("admin_certificates"))

    if event_id <= 0 or user_id <= 0 or action not in {"approve", "reject"}:
        flash("Invalid certificate action request.", "error")
        return redirect(url_for("admin_certificates"))

    new_status = "approved" if action == "approve" else "rejected"

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        existing_response = supabase.table("event_certificates") \
            .select("*") \
            .eq("event_id", event_id) \
            .eq("user_id", user_id) \
            .limit(1) \
            .execute()
        existing_row = (existing_response.data or [None])[0]

        update_payload = {
            "event_id": event_id,
            "user_id": user_id,
            "status": new_status,
            "certificate_url": certificate_url or None,
            "review_note": review_note or None,
            "reviewed_by_user_id": int(current_user.id),
            "reviewed_at": now_iso,
            "created_at": now_iso,
        }

        if existing_row:
            update_payload.pop("created_at", None)
            supabase.table("event_certificates").update(update_payload) \
                .eq("event_id", event_id) \
                .eq("user_id", user_id) \
                .execute()
        else:
            supabase.table("event_certificates").insert(update_payload).execute()

        user_response = supabase.table("users").select("email,name").eq("id", user_id).limit(1).execute()
        user_row = (user_response.data or [None])[0]
        event_response = supabase.table("volunteer_events").select("title").eq("id", event_id).limit(1).execute()
        event_row = (event_response.data or [None])[0]

        event_title = (event_row or {}).get("title", "your event")
        participant_name = (user_row or {}).get("name", "Participant")
        recipient = (user_row or {}).get("email")

        create_notification_for_user(
            user_id,
            f"Certificate {new_status}",
            f"Your certificate status for {event_title} is now {new_status}."
        )

        if recipient:
            mail_html = f"""
            <div style='font-family: Arial, sans-serif; line-height: 1.6; color: #0f172a;'>
                <h2 style='color:#0ea5e9;'>Think.4U Certificate Update</h2>
                <p>Hello {html.escape(participant_name)},</p>
                <p>Your certificate request for <strong>{html.escape(event_title)}</strong> is now <strong>{new_status}</strong>.</p>
                <p>Please log in to your dashboard and open the Certificates section.</p>
            </div>
            """
            send_email_async(
                subject="Think.4U Event Certificate Status",
                recipients=[recipient],
                html=mail_html
            )

        flash(f"Certificate marked as {new_status}.", "success")
    except Exception as e:
        app.logger.error(f"Admin certificate action failed: {e}")
        flash("Unable to update certificate status right now.", "error")

    return redirect(url_for("admin_certificates"))


# ===================================
# ADMIN SUPPORT / FUNDRAISING
# ===================================
@app.route("/admin/grievances")
@login_required
def admin_grievances():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = 25
        offset = (page - 1) * per_page

        response = supabase.table("grievances") \
            .select("*", count="exact") \
            .order("created_at", desc=True) \
            .range(offset, offset + per_page - 1) \
            .execute()

        class Pagination:
            def __init__(self, items, total, page_num, page_size):
                self.items = items
                self.total = total
                self.page = page_num
                self.per_page = page_size
                self.pages = (total + page_size - 1) // page_size if total else 1
                self.has_prev = page_num > 1
                self.has_next = page_num < self.pages
                self.prev_num = page_num - 1 if self.has_prev else None
                self.next_num = page_num + 1 if self.has_next else None

        grievances = Pagination(response.data or [], response.count or 0, page, per_page)
        return render_template("admin/grievances.html", grievances=grievances)
    except Exception as e:
        app.logger.error(f"Grievances page load failed: {e}")
        flash("Unable to load grievance/support requests.", "error")
        return redirect(url_for("admin_dashboard"))


@app.route("/admin/grievance/<int:gid>/action", methods=["POST"])
@login_required
def admin_grievance_action(gid):
    new_status = clean_text(request.form.get("status"), 30).lower()
    admin_note = clean_text(request.form.get("admin_note"), 1000, keep_new_lines=True)
    if new_status not in {"open", "in_progress", "resolved", "closed"}:
        flash("Invalid grievance status.", "error")
        return redirect(url_for("admin_grievances"))

    try:
        updated_payload = {
            "status": new_status,
            "admin_note": admin_note,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            response = supabase.table("grievances").update(updated_payload).eq("id", gid).execute()
        except Exception:
            response = supabase.table("grievances").update({"status": new_status}).eq("id", gid).execute()
        grievance = (response.data or [None])[0]
        if grievance:
            user_id = grievance.get("user_id")
            if user_id:
                create_notification_for_user(
                    int(user_id),
                    "Support request updated",
                    f"Your grievance status is now {new_status.replace('_', ' ')}."
                )
            recipient = grievance.get("email")
            if recipient:
                send_email_async(
                    subject="Think.4U Support Request Update",
                    recipients=[recipient],
                    html=f"""
                    <div style='font-family: Arial, sans-serif; line-height: 1.6; color: #0f172a;'>
                        <h2 style='color:#0ea5e9;'>Support Request Update</h2>
                        <p>Your grievance/feedback status is now <strong>{new_status.replace('_', ' ')}</strong>.</p>
                        <p>Thank you for your patience.</p>
                    </div>
                    """
                )
        flash("Grievance updated successfully.", "success")
    except Exception as e:
        app.logger.error(f"Grievance update failed: {e}")
        flash("Unable to update grievance right now.", "error")
    return redirect(url_for("admin_grievances"))


@app.route("/admin/fundraising", methods=["GET", "POST"])
@login_required
def admin_fundraising():
    if request.method == "POST":
        title = clean_text(request.form.get("title"), 200)
        description = clean_text(request.form.get("description"), 2000, keep_new_lines=True)
        try:
            target_amount = float(request.form.get("target_amount", "0"))
        except (TypeError, ValueError):
            target_amount = 0

        if not title or target_amount <= 0:
            flash("Title and valid target amount are required.", "error")
            return redirect(url_for("admin_fundraising"))

        try:
            payload = {
                "title": title,
                "description": description,
                "target_amount": target_amount,
                "raised_amount": 0,
                "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                supabase.table("fundraisers").insert(payload).execute()
            except Exception:
                payload.pop("status", None)
                supabase.table("fundraisers").insert(payload).execute()
            flash("Fundraising campaign created.", "success")
        except Exception as e:
            app.logger.error(f"Fundraising create failed: {e}")
            flash("Unable to create fundraising campaign.", "error")

        return redirect(url_for("admin_fundraising"))

    campaigns = []
    try:
        response = supabase.table("fundraisers").select("*").order("created_at", desc=True).limit(100).execute()
        campaigns = response.data or []
    except Exception as e:
        app.logger.warning(f"Fundraising list load failed: {e}")

    return render_template("admin/fundraising.html", campaigns=campaigns)


@app.route("/admin/fundraising/<int:fid>/update", methods=["POST"])
@login_required
def admin_fundraising_update(fid):
    title = clean_text(request.form.get("title"), 200)
    description = clean_text(request.form.get("description"), 2000, keep_new_lines=True)
    status = clean_text(request.form.get("status"), 20).lower()
    try:
        target_amount = float(request.form.get("target_amount", "0"))
    except (TypeError, ValueError):
        target_amount = 0
    try:
        raised_amount = float(request.form.get("raised_amount", "0"))
    except (TypeError, ValueError):
        raised_amount = 0

    if status not in {"active", "closed", "paused"}:
        status = "active"

    if not title or target_amount <= 0:
        flash("Invalid campaign data.", "error")
        return redirect(url_for("admin_fundraising"))

    try:
        update_payload = {
            "title": title,
            "description": description,
            "target_amount": target_amount,
            "raised_amount": max(0, raised_amount),
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            supabase.table("fundraisers").update(update_payload).eq("id", fid).execute()
        except Exception:
            update_payload.pop("status", None)
            update_payload.pop("updated_at", None)
            supabase.table("fundraisers").update(update_payload).eq("id", fid).execute()
        flash("Fundraising campaign updated.", "success")
    except Exception as e:
        app.logger.error(f"Fundraising update failed: {e}")
        flash("Unable to update campaign.", "error")
    return redirect(url_for("admin_fundraising"))


@app.route("/admin/fundraising/<int:fid>/delete", methods=["POST"])
@login_required
def admin_fundraising_delete(fid):
    try:
        supabase.table("fundraisers").delete().eq("id", fid).execute()
        flash("Fundraising campaign deleted.", "success")
    except Exception as e:
        app.logger.error(f"Fundraising delete failed: {e}")
        flash("Unable to delete campaign.", "error")
    return redirect(url_for("admin_fundraising"))


# ===================================
# PROGRAMS ROUTES (Supabase)
# ===================================

@app.route("/program/<int:program_id>")
def program_detail(program_id):
    """Display program details from Supabase"""
    registration = None
    certificate = None
    linked_event = None

    try:
        response = supabase.table('programs').select('*').eq('id', program_id).execute()
        
        if not response.data:
            flash('Program not found', 'error')
            return redirect(url_for('index'))
        
        program = response.data[0]
        linked_event = ensure_event_for_program(program)

        if current_user.is_authenticated and linked_event and linked_event.get("id") is not None:
            event_id = int(linked_event["id"])
            try:
                reg_response = supabase.table("event_participants") \
                    .select("*") \
                    .eq("event_id", event_id) \
                    .eq("user_id", int(current_user.id)) \
                    .limit(1) \
                    .execute()
                registration = (reg_response.data or [None])[0]
                if not registration:
                    fallback_reg = supabase.table("event_participants") \
                        .select("*") \
                        .eq("event_id", event_id) \
                        .eq("email", current_user.email) \
                        .limit(1) \
                        .execute()
                    registration = (fallback_reg.data or [None])[0]
            except Exception:
                registration = None

            try:
                cert_response = supabase.table("event_certificates") \
                    .select("*") \
                    .eq("event_id", event_id) \
                    .eq("user_id", int(current_user.id)) \
                    .limit(1) \
                    .execute()
                certificate = (cert_response.data or [None])[0]
            except Exception:
                certificate = None

        return render_template(
            "program_detail.html",
            program=program,
            linked_event=linked_event,
            registration=registration,
            certificate=certificate
        )
    except Exception as e:
        app.logger.error(f"Error fetching program: {e}")
        flash('Error loading program', 'error')
        return redirect(url_for('index'))


@app.route("/program/<int:program_id>/register", methods=["POST"])
@login_required
def register_for_program(program_id):
    try:
        program_response = supabase.table("programs").select("*").eq("id", program_id).limit(1).execute()
        program_row = (program_response.data or [None])[0]
        if not program_row:
            flash("Program not found.", "error")
            return redirect(url_for("index"))

        linked_event = ensure_event_for_program(program_row)
        if not linked_event or linked_event.get("id") is None:
            flash("Unable to prepare event registration for this program.", "error")
            return redirect(url_for("program_detail", program_id=program_id))

        event_id = int(linked_event["id"])

        existing_response = supabase.table("event_participants") \
            .select("id") \
            .eq("event_id", event_id) \
            .eq("user_id", int(current_user.id)) \
            .limit(1) \
            .execute()
        existing_data = existing_response.data or []
        if not existing_data:
            email_existing_response = supabase.table("event_participants") \
                .select("id") \
                .eq("event_id", event_id) \
                .eq("email", current_user.email) \
                .limit(1) \
                .execute()
            existing_data = email_existing_response.data or []

        if existing_data:
            flash("You are already registered for this program event.", "info")
            return redirect(url_for("program_detail", program_id=program_id))

        supabase.table("event_participants").insert({
            "event_id": event_id,
            "user_id": int(current_user.id),
            "name": clean_text(current_user.name, 120),
            "email": current_user.email,
            "role": current_user.role if current_user.role in {"donor", "volunteer", "both", "admin"} else "donor",
            "status": "registered",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        try:
            supabase.table("event_certificates").upsert({
                "event_id": event_id,
                "user_id": int(current_user.id),
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="event_id,user_id").execute()
        except Exception as cert_error:
            app.logger.warning(f"Program certificate upsert skipped: {cert_error}")

        create_notification_for_user(
            int(current_user.id),
            "Program registration confirmed",
            f"You are registered for {program_row.get('title', 'this program')}."
        )
        flash("Program registration successful.", "success")
        return redirect(url_for("program_detail", program_id=program_id))
    except Exception as e:
        app.logger.error(f"Program registration failed: {e}")
        flash("Unable to register for this program right now.", "error")
        return redirect(url_for("program_detail", program_id=program_id))


@app.route("/admin/programs", methods=["GET", "POST"])
@login_required
def admin_programs():
    """Manage programs - supports URL and file upload to Supabase Storage"""
    
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()
        image_file = request.files.get("image")
        
        # Validation
        if not title or not description:
            flash("Title and description are required", "error")
            return redirect(url_for('admin_programs'))
        
        try:
            final_image_url = None
            
            # Handle file upload to Supabase Storage
            if image_file and image_file.filename:
                is_valid, validation_message = validate_image_upload(image_file)
                if not is_valid:
                    flash(validation_message, "error")
                    return redirect(url_for('admin_programs'))

                safe_filename = secure_filename(image_file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                name, ext = os.path.splitext(safe_filename)
                unique_filename = f"programs/{name}_{timestamp}{ext}"

                try:
                    file_data = image_file.read()

                    try:
                        supabase.storage.from_('program-images').list()
                    except Exception:
                        try:
                            supabase.storage.create_bucket('program-images', options={'public': True})
                        except Exception as create_error:
                            app.logger.error(f"Could not create storage bucket: {create_error}")
                            flash("Storage bucket not found. Please create 'program-images' bucket in Supabase Storage.", "error")
                            return redirect(url_for('admin_programs'))

                    supabase.storage.from_('program-images').upload(
                        unique_filename,
                        file_data,
                        file_options={"content-type": image_file.content_type}
                    )

                    final_image_url = supabase.storage.from_('program-images').get_public_url(unique_filename)

                except Exception as storage_error:
                    app.logger.error(f"Supabase storage error: {storage_error}")
                    flash(f"Error uploading image: {str(storage_error)}", "error")
                    return redirect(url_for('admin_programs'))
            
            # Use image URL if no file uploaded
            elif image_url:
                final_image_url = image_url
            
            # Insert into Supabase database
            program_data = {
                "title": title,
                "description": description,
                "image_url": final_image_url,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            response = supabase.table('programs').insert(program_data).execute()
            
            if response.data:
                created_program = response.data[0]
                ensure_event_for_program(created_program)
                app.logger.info(f"Program created: {title}")
                flash("Program created successfully!", "success")
            else:
                flash("Error: No data returned from Supabase", "error")
            
            return redirect(url_for('admin_programs'))
            
        except Exception as e:
            app.logger.error(f"Error creating program: {e}")
            import traceback
            traceback.print_exc()
            flash(f'Error creating program: {str(e)}', 'error')
    
    # GET request - Fetch all programs
    try:
        response = supabase.table('programs').select('*').order('created_at', desc=True).execute()
        programs = response.data if response.data else []
        app.logger.info(f"Loaded {len(programs)} programs")
    except Exception as e:
        app.logger.warning(f"Error fetching programs: {e}")
        programs = []
        flash('Error loading programs', 'error')
    
    return render_template("admin/programs.html", programs=programs)







@app.route("/admin/programs/edit/<int:pid>", methods=["GET", "POST"])
@login_required
def admin_program_edit(pid):
    """Edit program in Supabase"""
    if not current_user.is_admin:
        return redirect(url_for('index'))

    # Fetch program
    try:
        response = supabase.table('programs').select('*').eq('id', pid).execute()
        
        if not response.data:
            flash('Program not found', 'error')
            return redirect(url_for('admin_programs'))
        
        program = response.data[0]
    except Exception as e:
        app.logger.error(f"Error fetching program: {e}")
        flash('Error loading program', 'error')
        return redirect(url_for('admin_programs'))

    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        image_url = request.form.get("image_url")
        
        try:
            # Update in Supabase
            supabase.table('programs').update({
                "title": title,
                "description": description,
                "image_url": image_url,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).eq('id', pid).execute()

            linked_event = ensure_event_for_program({
                "id": pid,
                "title": title,
                "description": description,
                "created_at": program.get("created_at")
            })
            if linked_event and linked_event.get("id"):
                try:
                    supabase.table("volunteer_events").update({
                        "title": clean_text(title, 200),
                        "description": clean_text(description, 2000, keep_new_lines=True),
                        "program_id": int(pid)
                    }).eq("id", linked_event["id"]).execute()
                except Exception:
                    supabase.table("volunteer_events").update({
                        "title": clean_text(title, 200),
                        "description": clean_text(description, 2000, keep_new_lines=True)
                    }).eq("id", linked_event["id"]).execute()
             
            flash("Program updated successfully!", "success")
            return redirect(url_for("admin_programs"))
        except Exception as e:
            app.logger.error(f"Error updating program: {e}")
            flash(f'Error updating program: {str(e)}', 'error')

    return render_template("admin/program_edit.html", program=program)


@app.route("/admin/program/<int:pid>/delete", methods=["POST", "DELETE"])
@login_required
def admin_program_delete(pid):
    """Delete program from Supabase"""

    
    try:
        try:
            supabase.table('volunteer_events').delete().eq('program_id', pid).execute()
        except Exception:
            pass
        supabase.table('programs').delete().eq('id', pid).execute()
        flash("Program deleted successfully!", "success")
    except Exception as e:
        app.logger.error(f"Error deleting program: {e}")
        flash(f'Error deleting program: {str(e)}', 'error')
    
    return redirect(url_for('admin_programs'))



# ------------------------------
# CMS Content Management Routes
# ------------------------------

@app.route("/admin/cms", methods=["GET", "POST"])
@login_required
def admin_cms():
    """Manage website content"""

    
    if request.method == "POST":
        content_id = request.form.get("content_id")
        key = request.form.get("key", "").strip()
        value = request.form.get("value", "").strip()
        
        if not key or not value:
            flash("Key and value are required", "error")
            return redirect(url_for('admin_cms'))
        
        try:
            if content_id:  # Update existing
                response = supabase.table('cms_content').update({
                "key": key,
                "value": value
                }).eq('id', int(content_id)).execute()
                flash("Content updated successfully!", "success")
            else:  # Create new
                response = supabase.table('cms_content').insert({
                "key": key,
                "value": value
                }).execute()
                flash("Content added successfully!", "success")
            
            return redirect(url_for('admin_cms'))
        except Exception as e:
            app.logger.error(f"Error saving content: {e}")
            flash(f"Error: {str(e)}", "error")
    
    # GET - Fetch all content
    try:
        response = supabase.table('cms_content').select('*').order('created_at', desc=True).execute()
        content_items = response.data if response.data else []
    except Exception as e:
        app.logger.error(f"Error fetching content: {e}")
        content_items = []
        flash("Error loading content", "error")
    
    return render_template("admin/cms.html", content_items=content_items)


@app.route("/admin/cms/delete/<int:content_id>", methods=["DELETE"])
@login_required
def admin_cms_delete(content_id):
    """Delete CMS content"""
    
    try:
        supabase.table('cms_content').delete().eq('id', content_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        app.logger.error(f"Error deleting content: {e}")
        return jsonify({"error": str(e)}), 500
    
# ------------------------------
# CMS Helper Function
# ------------------------------

def get_cms_content(key, default=""):
    """Get CMS content by key"""
    global CMS_FAILURE_UNTIL
    now_ts = int(datetime.now(timezone.utc).timestamp())

    cached_expiry = CMS_CACHE_EXPIRY.get(key, 0)
    if cached_expiry > now_ts:
        return CMS_CACHE.get(key, default)

    if now_ts < CMS_FAILURE_UNTIL:
        return default

    try:
        response = supabase.table('cms_content').select('value').eq('key', key).execute()
        if response.data and len(response.data) > 0:
            value = response.data[0]['value']
            CMS_CACHE[key] = value
            CMS_CACHE_EXPIRY[key] = now_ts + CMS_CACHE_TTL_SECONDS
            return value
        CMS_CACHE[key] = default
        CMS_CACHE_EXPIRY[key] = now_ts + CMS_CACHE_TTL_SECONDS
    except Exception as e:
        app.logger.warning(f"Error fetching CMS content '{key}': {e}")
        CMS_FAILURE_UNTIL = now_ts + CMS_FAILURE_BACKOFF_SECONDS
    return default


# Make CMS helper available in all templates
@app.context_processor
def inject_cms():
    """Inject CMS helper and other utilities into templates"""
    return dict(
        get_cms=get_cms_content,
        csrf_token=generate_csrf_token,
        current_year=datetime.now(timezone.utc).year,
        inactivity_timeout_minutes=max(1, INACTIVITY_TIMEOUT_SECONDS // 60)
    )



@app.route("/admin/settings", methods=["GET", "POST"])
@login_required
def admin_settings():
    """Admin settings page"""
    
    if request.method == "POST":
        form_type = request.form.get('form_type')
        
        try:
            if form_type == 'organization':
                # Save organization settings to CMS
                org_data = {
                    'org_name': request.form.get('org_name'),
                    'reg_number': request.form.get('reg_number'),
                    'tax_id': request.form.get('tax_id'),
                    'cert_80g': request.form.get('cert_80g')
                }
                
                for key, value in org_data.items():
                    supabase.table('cms_content').upsert({
                        'key': key,
                        'value': value
                    }).execute()
                
                flash('Organization information updated successfully!', 'success')
            
            elif form_type == 'contact':
                # Save contact settings
                contact_data = {
                    'contact_email': request.form.get('contact_email'),
                    'contact_phone': request.form.get('contact_phone'),
                    'contact_whatsapp': request.form.get('whatsapp'),
                    'contact_address': request.form.get('contact_address')
                }
                
                for key, value in contact_data.items():
                    supabase.table('cms_content').upsert({
                        'key': key,
                        'value': value
                    }).execute()
                
                flash('Contact information updated successfully!', 'success')
            
            elif form_type == 'payment':
                # Save payment settings
                payment_data = {
                    'razorpay_key': request.form.get('razorpay_key'),
                    'razorpay_secret': request.form.get('razorpay_secret'),
                    'upi_id': request.form.get('upi_id')
                }
                
                for key, value in payment_data.items():
                    if value:  # Only save if provided
                        supabase.table('cms_content').upsert({
                            'key': key,
                            'value': value
                        }).execute()
                
                flash('Payment settings updated successfully!', 'success')
            
            elif form_type == 'social':
                # Save social media links
                social_data = {
                    'social_facebook': request.form.get('facebook'),
                    'social_twitter': request.form.get('twitter'),
                    'social_instagram': request.form.get('instagram'),
                    'social_linkedin': request.form.get('linkedin')
                }
                
                for key, value in social_data.items():
                    supabase.table('cms_content').upsert({
                        'key': key,
                        'value': value
                    }).execute()
                
                flash('Social media links updated successfully!', 'success')
            
            elif form_type == 'password':
                flash(
                    'For security reasons, admin passwords are not stored in CMS. Update credentials via environment variables.',
                    'warning'
                )
            elif form_type == "create_admin_user":
                admin_email = normalize_email(request.form.get("admin_email"))
                admin_name = clean_text(request.form.get("admin_name"), 120)
                admin_password = request.form.get("admin_password", "")

                if not admin_email:
                    flash("Please enter a valid admin email.", "error")
                    return redirect(url_for("admin_settings"))
                password_ok, password_error = validate_password_strength(admin_password)
                if not password_ok:
                    flash(password_error, "error")
                    return redirect(url_for("admin_settings"))

                existing_response = supabase.table("users") \
                    .select("id") \
                    .eq("email", admin_email) \
                    .limit(1) \
                    .execute()
                existing_row = (existing_response.data or [None])[0]

                payload = {
                    "email": admin_email,
                    "name": admin_name or "Admin",
                    "password_hash": generate_password_hash(admin_password),
                    "is_admin": True,
                    "role": "admin",
                    "email_verified": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

                if existing_row:
                    payload.pop("created_at", None)
                    supabase.table("users").update(payload).eq("id", existing_row["id"]).execute()
                    flash("Admin user updated successfully.", "success")
                else:
                    supabase.table("users").insert(payload).execute()
                    flash("Admin user created successfully.", "success")
             
        except Exception as e:
            app.logger.info(f"Error saving settings: {e}")
            flash(f'Error updating settings: {str(e)}', 'error')
        
        return redirect(url_for('admin_settings'))
    
    # GET request - Load settings
    try:
        # Fetch all settings from CMS
        response = supabase.table('cms_content').select('*').execute()
        settings_dict = {item['key']: item['value'] for item in response.data} if response.data else {}
        
        # Organize settings
        org_settings = {
            'name': settings_dict.get('org_name', ''),
            'reg_number': settings_dict.get('reg_number', ''),
            'tax_id': settings_dict.get('tax_id', ''),
            'cert_80g': settings_dict.get('cert_80g', '')
        }
        
        contact_settings = {
            'email': settings_dict.get('contact_email', ''),
            'phone': settings_dict.get('contact_phone', ''),
            'whatsapp': settings_dict.get('contact_whatsapp', ''),
            'address': settings_dict.get('contact_address', '')
        }
        
        payment_settings = {
            'razorpay_key': settings_dict.get('razorpay_key', ''),
            'razorpay_secret': settings_dict.get('razorpay_secret', ''),
            'upi_id': settings_dict.get('upi_id', '')
        }
        
        social_settings = {
            'facebook': settings_dict.get('social_facebook', ''),
            'twitter': settings_dict.get('social_twitter', ''),
            'instagram': settings_dict.get('social_instagram', ''),
            'linkedin': settings_dict.get('social_linkedin', '')
        }
        
    except Exception as e:
        app.logger.info(f"Error loading settings: {e}")
        org_settings = {}
        contact_settings = {}
        payment_settings = {}
        social_settings = {}
    
    return render_template("admin/settings.html",
                         org_settings=org_settings,
                         contact_settings=contact_settings,
                         payment_settings=payment_settings,
                         social_settings=social_settings)

def generate_qr(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return base64.b64encode(buf.read()).decode("utf-8")


@app.route("/create-admin-secret-123")
def create_admin_secret():
    """Create admin user in Supabase - REMOVE AFTER USE!"""
    if os.getenv("ENABLE_ADMIN_BOOTSTRAP", "false").lower() != "true":
        abort(404)
    bootstrap_token = os.getenv("ADMIN_BOOTSTRAP_TOKEN", "")
    if bootstrap_token and request.args.get("token") != bootstrap_token:
        abort(403)
    try:
        from datetime import datetime, timezone
        
        email = normalize_email(os.getenv("ADMIN_BOOTSTRAP_EMAIL", "admin@think4u.local")) or "admin@think4u.local"
        password = os.getenv("ADMIN_BOOTSTRAP_PASSWORD") or secrets.token_urlsafe(12)
        password_hash = generate_password_hash(password)
        
        # Check if admin exists
        response = supabase.table('users').select('*').eq('email', email).execute()
        
        if response.data:
            # Update existing user
            result = supabase.table('users').update({
                'password_hash': password_hash,
                'is_admin': True,
                'role': 'admin'
            }).eq('email', email).execute()
            message = "Admin user UPDATED!"
        else:
            # Create new admin user
            result = supabase.table('users').insert({
                'email': email,
                'password_hash': password_hash,
                'is_admin': True,
                'role': 'admin',
                'created_at': datetime.now(timezone.utc).isoformat()
            }).execute()
            message = "Admin user CREATED!"
        
        return f"""
        <html>
        <body style="font-family: Arial; padding: 50px; background: #f0f9ff;">
            <div style="background: white; padding: 30px; border-radius: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); max-width: 500px; margin: 0 auto;">
                <h1 style="color: #10b981;">{message}</h1>
                <p><strong>Email:</strong> {email}</p>
                <p><strong>Password:</strong> {password}</p>
                <hr>
                <p style="color: #666; font-size: 14px;"><strong>Important:</strong> Delete this route from app.py after use!
                </p>
                <a href="/login" style="display: inline-block; margin-top: 20px; padding: 10px 20px; background: #10b981; color: white; text-decoration: none; border-radius: 8px;">
                    Go to Login
                </a>
            </div>
        </body>
        </html>
        """
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return f"""
        <html>
        <body style="font-family: monospace; padding: 50px; background: #fee;">
            <h1 style="color: red;">Error Creating Admin</h1>
            <pre>{error_trace}</pre>
        </body>
        </html>
        """

def amount_to_words(amount):
    return num2words(amount, lang='en_IN').replace('-', ' ').title()

# ===================================
# RUN APP
# ===================================
if __name__ == "__main__":
    app.logger.info("App configured with Supabase!")
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", "5000")))
    app.run(debug=debug_mode, host=host, port=port)
