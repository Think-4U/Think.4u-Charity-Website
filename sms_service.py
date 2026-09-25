"""
Think.4U SMS OTP Service & Mobile Verification
Supports Fast2SMS, Twilio, MSG91, Webhooks, and secure local dev simulation.
"""
import os
import re
import secrets
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
import httpx
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger("think4u.sms")

# Configuration
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "fast2sms").strip().lower()
FAST2SMS_API_KEY = (os.getenv("FAST2SMS_API_KEY") or "").strip()
TWILIO_ACCOUNT_SID = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
TWILIO_AUTH_TOKEN = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
TWILIO_PHONE_NUMBER = (os.getenv("TWILIO_PHONE_NUMBER") or "").strip()
MSG91_AUTH_KEY = (os.getenv("MSG91_AUTH_KEY") or "").strip()
SMS_WEBHOOK_URL = (os.getenv("SMS_WEBHOOK_URL") or "").strip()

SMS_OTP_EXPIRY_SECONDS = int(os.getenv("SMS_OTP_EXPIRY_SECONDS", "300"))  # 5 minutes
SMS_MAX_ATTEMPTS = int(os.getenv("SMS_MAX_ATTEMPTS", "3"))

# Rate limiting state (Thread-safe in single process / small scale)
_PHONE_RATE_STATE = defaultdict(deque)
_IP_RATE_STATE = defaultdict(deque)

# In-memory storage for active OTPs: key = f"{purpose}:{phone}"
_ACTIVE_OTPS = {}


def normalize_phone(phone_input: str) -> str:
    """
    Normalize phone number to 10-digit Indian mobile number or E.164.
    Returns 10-digit string if valid Indian mobile, else empty string.
    """
    if not phone_input or not isinstance(phone_input, str):
        return ""
    digits = re.sub(r"\D", "", phone_input)
    # Handle +91 or 91 prefix
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    
    # Valid Indian mobile numbers are 10 digits starting with 6, 7, 8, or 9
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return ""


def check_sms_rate_limit(phone: str, ip: str = None) -> (bool, str):
    """
    Rate limit checking:
    - Max 3 SMS OTP requests per phone per 10 minutes
    - Max 8 SMS OTP requests per IP per 10 minutes
    """
    now = datetime.now(timezone.utc).timestamp()
    window = 600  # 10 minutes

    # Check phone limit
    phone_q = _PHONE_RATE_STATE[phone]
    while phone_q and (now - phone_q[0]) > window:
        phone_q.popleft()
    if len(phone_q) >= 3:
        wait_seconds = int(window - (now - phone_q[0]))
        return False, f"Too many OTP requests for this phone. Please retry in {wait_seconds // 60 + 1} minute(s)."

    # Check IP limit
    if ip:
        ip_q = _IP_RATE_STATE[ip]
        while ip_q and (now - ip_q[0]) > window:
            ip_q.popleft()
        if len(ip_q) >= 8:
            return False, "Too many OTP requests from your network. Please try again later."

    return True, ""


def record_sms_request(phone: str, ip: str = None):
    now = datetime.now(timezone.utc).timestamp()
    _PHONE_RATE_STATE[phone].append(now)
    if ip:
        _IP_RATE_STATE[ip].append(now)


def send_sms_via_provider(phone: str, otp: str, message: str) -> (bool, str):
    """
    Send SMS via the configured gateway.
    """
    # 1. Fast2SMS
    if FAST2SMS_API_KEY:
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    "https://www.fast2sms.com/dev/bulkV2",
                    headers={"authorization": FAST2SMS_API_KEY},
                    json={
                        "variables_values": otp,
                        "route": "otp",
                        "numbers": phone
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    if data.get("return") is True or "successful" in str(data.get("message", "")).lower():
                        return True, "SMS sent successfully."
                    return False, f"Fast2SMS error: {data.get('message', 'Delivery failed')}"
                return False, f"Fast2SMS HTTP {res.status_code}"
        except Exception as e:
            logger.error(f"Fast2SMS error: {e}")
            return False, str(e)

    # 2. Twilio
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER:
        try:
            with httpx.Client(timeout=10.0) as client:
                url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
                formatted_phone = f"+91{phone}" if not phone.startswith("+") else phone
                res = client.post(
                    url,
                    auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                    data={
                        "From": TWILIO_PHONE_NUMBER,
                        "To": formatted_phone,
                        "Body": message
                    }
                )
                if res.status_code in (200, 201):
                    return True, "SMS sent via Twilio."
                return False, f"Twilio HTTP {res.status_code}: {res.text}"
        except Exception as e:
            logger.error(f"Twilio error: {e}")
            return False, str(e)

    # 3. MSG91
    if MSG91_AUTH_KEY:
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    "https://control.msg91.com/api/v5/otp",
                    headers={"authkey": MSG91_AUTH_KEY, "Content-Type": "application/json"},
                    json={
                        "template_id": os.getenv("MSG91_TEMPLATE_ID", ""),
                        "mobile": f"91{phone}",
                        "otp": otp
                    }
                )
                if res.status_code in (200, 201):
                    return True, "SMS sent via MSG91."
                return False, f"MSG91 HTTP {res.status_code}"
        except Exception as e:
            logger.error(f"MSG91 error: {e}")
            return False, str(e)

    # 4. Generic SMS Webhook
    if SMS_WEBHOOK_URL:
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    SMS_WEBHOOK_URL,
                    json={"phone": phone, "otp": otp, "message": message}
                )
                if res.status_code in (200, 201):
                    return True, "SMS sent via webhook."
        except Exception as e:
            logger.error(f"SMS webhook error: {e}")

    # Fallback to dev/sandbox simulator
    logger.warning(
        f"\n======================================================\n"
        f"[SMS OTP SIMULATOR] Mobile: +91-{phone}\n"
        f"OTP Code: >>> {otp} <<<\n"
        f"Message: {message}\n"
        f"======================================================"
    )
    return True, "SMS sent (sandbox mode)."


def generate_and_send_mobile_otp(
    phone_input: str,
    purpose: str = "login",
    ip: str = None,
    metadata: dict = None
) -> (bool, str, str):
    """
    Generate, hash, store, and dispatch SMS OTP to the mobile number.
    Returns (success, message, phone)
    """
    phone = normalize_phone(phone_input)
    if not phone:
        return False, "Please enter a valid 10-digit Indian mobile number.", ""

    # Rate limit check
    allowed, rate_msg = check_sms_rate_limit(phone, ip)
    if not allowed:
        return False, rate_msg, phone

    # Cryptographically secure 6-digit OTP
    otp = f"{secrets.randbelow(900000) + 100000}"
    expires_at = int(datetime.now(timezone.utc).timestamp()) + SMS_OTP_EXPIRY_SECONDS

    otp_key = f"{purpose}:{phone}"
    _ACTIVE_OTPS[otp_key] = {
        "otp_hash": generate_password_hash(otp),
        "expires_at": expires_at,
        "attempts": 0,
        "phone": phone,
        "purpose": purpose,
        "metadata": metadata or {}
    }

    message = f"Your Think.4U verification code is {otp}. Valid for 5 minutes. Do not share this OTP with anyone."
    success, send_msg = send_sms_via_provider(phone, otp, message)
    if success:
        record_sms_request(phone, ip)
        return True, "Verification code sent to your mobile number.", phone
    else:
        _ACTIVE_OTPS.pop(otp_key, None)
        return False, f"Could not dispatch SMS: {send_msg}", phone


def verify_mobile_otp(phone_input: str, otp_code: str, purpose: str = "login") -> (bool, str, dict):
    """
    Verify incoming mobile OTP against stored hash.
    Checks expiry, brute-force attempt counts, and clears on success.
    Returns (verified: bool, message: str, metadata: dict)
    """
    phone = normalize_phone(phone_input)
    if not phone:
        return False, "Invalid mobile number format.", {}

    cleaned_otp = (otp_code or "").strip()
    if not re.fullmatch(r"\d{6}", cleaned_otp):
        return False, "OTP must be a 6-digit number.", {}

    otp_key = f"{purpose}:{phone}"
    entry = _ACTIVE_OTPS.get(otp_key)
    if not entry:
        return False, "No active OTP found for this number or OTP has expired. Please request a new one.", {}

    now = int(datetime.now(timezone.utc).timestamp())
    if now > entry["expires_at"]:
        _ACTIVE_OTPS.pop(otp_key, None)
        return False, "This OTP has expired. Please request a new one.", {}

    entry["attempts"] += 1
    if entry["attempts"] > SMS_MAX_ATTEMPTS:
        _ACTIVE_OTPS.pop(otp_key, None)
        return False, "Too many failed OTP attempts. This code is invalidated. Please request a new OTP.", {}

    if not check_password_hash(entry["otp_hash"], cleaned_otp):
        remaining = SMS_MAX_ATTEMPTS - entry["attempts"]
        if remaining > 0:
            return False, f"Invalid OTP. {remaining} attempt(s) remaining.", {}
        else:
            _ACTIVE_OTPS.pop(otp_key, None)
            return False, "Invalid OTP. Maximum attempts reached. Please request a new OTP.", {}

    # Verified successfully! Remove used OTP to prevent replay attacks
    metadata = entry.get("metadata", {})
    _ACTIVE_OTPS.pop(otp_key, None)
    return True, "Mobile number verified successfully.", metadata
