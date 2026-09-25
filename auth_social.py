"""
Think.4U Social Authentication Module
Handles Google OAuth 2.0 / OpenID Connect and Google Identity Services.
"""
import os
import json
import secrets
import logging
import urllib.parse
from datetime import datetime, timezone
import httpx

logger = logging.getLogger("think4u.social_auth")

GOOGLE_CLIENT_ID = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
GOOGLE_CLIENT_SECRET = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()

# OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


def is_google_auth_configured() -> bool:
    """Check if Google OAuth credentials are configured."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def get_google_auth_url(redirect_uri: str, state: str) -> str:
    """
    Generate Google OAuth 2.0 authorization redirect URL.
    """
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account"
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_google_user(code: str, redirect_uri: str) -> (bool, dict, str):
    """
    Exchange authorization code for user info.
    Returns (success: bool, user_info: dict, error_message: str)
    """
    if not is_google_auth_configured():
        return False, {}, "Google OAuth is not configured on the server."

    try:
        with httpx.Client(timeout=12.0) as client:
            token_resp = client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"}
            )

        if token_resp.status_code != 200:
            logger.error(f"Google token exchange failed ({token_resp.status_code}): {token_resp.text}")
            return False, {}, f"Google token exchange failed: {token_resp.status_code}"

        tokens = token_resp.json()
        access_token = tokens.get("access_token")
        id_token = tokens.get("id_token")

        # Fetch user info using access token or verify id_token
        user_info = {}
        if access_token:
            with httpx.Client(timeout=10.0) as client:
                info_resp = client.get(
                    GOOGLE_USERINFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
            if info_resp.status_code == 200:
                user_info = info_resp.json()

        if not user_info and id_token:
            with httpx.Client(timeout=10.0) as client:
                id_resp = client.get(f"{GOOGLE_TOKENINFO_URL}?id_token={id_token}")
            if id_resp.status_code == 200:
                user_info = id_resp.json()

        if not user_info or not user_info.get("email"):
            return False, {}, "Could not retrieve user email from Google."

        email = user_info.get("email", "").strip().lower()
        name = user_info.get("name") or user_info.get("given_name") or email.split("@")[0]
        google_id = user_info.get("sub", "")
        picture = user_info.get("picture", "")

        return True, {
            "email": email,
            "name": name,
            "provider_user_id": google_id,
            "picture": picture,
            "provider": "google"
        }, ""

    except Exception as e:
        logger.error(f"Google OAuth exchange error: {e}")
        return False, {}, str(e)


def verify_google_credential_token(credential_token: str) -> (bool, dict, str):
    """
    Verify Google One Tap / Sign-In with Google ID token from frontend.
    """
    if not credential_token:
        return False, {}, "Missing credential token."

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{GOOGLE_TOKENINFO_URL}?id_token={credential_token}")

        if resp.status_code != 200:
            return False, {}, "Invalid Google credential token."

        data = resp.json()
        if GOOGLE_CLIENT_ID and data.get("aud") != GOOGLE_CLIENT_ID:
            logger.warning(f"Google token aud mismatch: expected {GOOGLE_CLIENT_ID}, got {data.get('aud')}")
            return False, {}, "Token audience mismatch."

        email = data.get("email", "").strip().lower()
        if not email:
            return False, {}, "Google token did not contain an email address."

        name = data.get("name") or email.split("@")[0]
        return True, {
            "email": email,
            "name": name,
            "provider_user_id": data.get("sub", ""),
            "picture": data.get("picture", ""),
            "provider": "google"
        }, ""
    except Exception as e:
        logger.error(f"Google token verification error: {e}")
        return False, {}, str(e)
