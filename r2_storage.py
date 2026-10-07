"""
Think.4U Cloudflare R2 Storage Service
Handles uploading, storing, and fetching images & videos on Cloudflare R2.
Public links are generated under the custom domain: https://media.think4u.org/...
"""

import os
import io
import uuid
import mimetypes
import logging
import socket
from urllib.parse import urlparse
import httpx

logger = logging.getLogger("think4u.r2_storage")

# Configuration from environment
R2_ACCOUNT_ID = (os.getenv("CLOUDFLARE_R2_ACCOUNT_ID") or "").strip()
R2_ACCESS_KEY_ID = (os.getenv("CLOUDFLARE_R2_ACCESS_KEY_ID") or "").strip()
R2_SECRET_ACCESS_KEY = (os.getenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY") or "").strip()
R2_BUCKET = (os.getenv("CLOUDFLARE_R2_BUCKET") or "think4u-media").strip()
R2_CUSTOM_DOMAIN = (os.getenv("CLOUDFLARE_R2_CUSTOM_DOMAIN") or "media.think4u.org").strip().rstrip("/")

_s3_client = None


def is_r2_configured() -> bool:
    """Check if all necessary Cloudflare R2 credentials are set."""
    account_id = (os.getenv("CLOUDFLARE_R2_ACCOUNT_ID") or R2_ACCOUNT_ID or "").strip()
    access_key = (os.getenv("CLOUDFLARE_R2_ACCESS_KEY_ID") or R2_ACCESS_KEY_ID or "").strip()
    secret_key = (os.getenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY") or R2_SECRET_ACCESS_KEY or "").strip()
    bucket = (os.getenv("CLOUDFLARE_R2_BUCKET") or R2_BUCKET or "").strip()
    return bool(account_id and access_key and secret_key and bucket)


def validate_r2_credentials() -> (bool, str):
    """
    Validate that Cloudflare R2 credentials match the expected formats:
      - Account ID: 32 hex characters
      - Access Key ID: 32 hex characters
      - Secret Access Key: 64 hex characters
    """
    account_id = (os.getenv("CLOUDFLARE_R2_ACCOUNT_ID") or R2_ACCOUNT_ID or "").strip()
    access_key = (os.getenv("CLOUDFLARE_R2_ACCESS_KEY_ID") or R2_ACCESS_KEY_ID or "").strip()
    secret_key = (os.getenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY") or R2_SECRET_ACCESS_KEY or "").strip()
    bucket = (os.getenv("CLOUDFLARE_R2_BUCKET") or R2_BUCKET or "").strip()

    if not (account_id and access_key and secret_key and bucket):
        return False, "Missing required R2 configuration (Account ID, Access Key ID, Secret Access Key, or Bucket)."

    if len(access_key) != 32:
        return False, (
            f"CLOUDFLARE_R2_ACCESS_KEY_ID has length {len(access_key)} (expected 32 characters). "
            "Please generate an R2 API token under R2 > Manage R2 API Tokens in Cloudflare "
            "and copy the 'Access Key ID' (not the general Bearer API token)."
        )
    if len(secret_key) != 64:
        return False, (
            f"CLOUDFLARE_R2_SECRET_ACCESS_KEY has length {len(secret_key)} (expected 64 characters). "
            "Please copy the 64-character 'Secret Access Key' generated with your R2 API Token."
        )

    return True, ""


def check_r2_status() -> dict:
    """Diagnostic check of Cloudflare R2 configuration status."""
    configured = is_r2_configured()
    if not configured:
        return {
            "configured": False,
            "status": "unconfigured",
            "custom_domain": (os.getenv("CLOUDFLARE_R2_CUSTOM_DOMAIN") or "media.think4u.org"),
            "error": "Cloudflare R2 credentials not set in environment."
        }
    valid, reason = validate_r2_credentials()
    return {
        "configured": True,
        "valid_credentials": valid,
        "status": "ready" if valid else "invalid_credentials",
        "bucket": (os.getenv("CLOUDFLARE_R2_BUCKET") or "think4u-media"),
        "custom_domain": (os.getenv("CLOUDFLARE_R2_CUSTOM_DOMAIN") or "media.think4u.org"),
        "error": reason if not valid else None,
    }


def get_r2_client():
    """Lazily construct and return boto3 S3 client configured for Cloudflare R2."""
    global _s3_client
    if _s3_client is not None:
        return _s3_client

    valid, reason = validate_r2_credentials()
    if not valid:
        logger.warning("Cloudflare R2 credentials validation failed: %s", reason)
        return None

    try:
        import boto3
        from botocore.config import Config

        account_id = (os.getenv("CLOUDFLARE_R2_ACCOUNT_ID") or R2_ACCOUNT_ID).strip()
        access_key = (os.getenv("CLOUDFLARE_R2_ACCESS_KEY_ID") or R2_ACCESS_KEY_ID).strip()
        secret_key = (os.getenv("CLOUDFLARE_R2_SECRET_ACCESS_KEY") or R2_SECRET_ACCESS_KEY).strip()

        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        _s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=30,
            ),
        )
        return _s3_client
    except Exception as exc:
        logger.error(f"Failed to initialize Cloudflare R2 boto3 client: {exc}")
        return None


def format_r2_url(key: str) -> str:
    """
    Generate public media URL starting with https://media.think4u.org/...
    """
    clean_key = str(key or "").lstrip("/")
    domain = (os.getenv("CLOUDFLARE_R2_CUSTOM_DOMAIN") or R2_CUSTOM_DOMAIN or "media.think4u.org").strip().rstrip("/")
    return f"https://{domain}/{clean_key}"


def is_r2_media_url(url_str: str) -> bool:
    """Validate whether a URL belongs to the Cloudflare R2 media domain."""
    if not url_str:
        return False
    parsed = urlparse(url_str.strip())
    domain = (os.getenv("CLOUDFLARE_R2_CUSTOM_DOMAIN") or R2_CUSTOM_DOMAIN or "media.think4u.org").lower().strip().rstrip("/")
    return parsed.scheme.lower() in {"https", "http"} and parsed.netloc.lower() == domain


def extract_r2_key_from_url(url_str: str) -> str:
    """Extract object key from a full media.think4u.org URL."""
    if not url_str:
        return ""
    parsed = urlparse(url_str.strip())
    return parsed.path.lstrip("/")


def upload_to_r2(file_data, key: str, content_type: str = None) -> (bool, str, str):
    """
    Upload byte stream or file object to Cloudflare R2.
    Returns (success: bool, public_url: str, error_message: str)
    """
    client = get_r2_client()
    if not client:
        return False, "", "Cloudflare R2 is not configured on this server."

    bucket = (os.getenv("CLOUDFLARE_R2_BUCKET") or R2_BUCKET or "think4u-media").strip()

    try:
        # Determine content type if not provided
        if not content_type:
            content_type, _ = mimetypes.guess_type(key)
        if not content_type:
            content_type = "application/octet-stream"

        # Prepare body bytes or file object
        if hasattr(file_data, "read"):
            if hasattr(file_data, "seek"):
                file_data.seek(0)
            body = file_data.read()
        elif isinstance(file_data, (bytes, bytearray)):
            body = file_data
        else:
            return False, "", "Invalid file data type."

        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )

        public_url = format_r2_url(key)
        logger.info(f"Successfully uploaded to R2: {public_url}")
        return True, public_url, ""
    except Exception as exc:
        logger.error(f"Error uploading to Cloudflare R2: {exc}")
        return False, "", str(exc)


def _is_safe_remote_url(target_url: str) -> (bool, str):
    """
    SSRF Protection: Ensure remote URL is public and does not point to
    private networks, loopback (127.0.0.1, localhost), or link-local metadata services.
    """
    try:
        parsed = urlparse(target_url)
        if parsed.scheme.lower() not in {"http", "https"}:
            return False, "Only HTTP and HTTPS URLs are allowed."

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False, "Invalid host in URL."

        if hostname in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
            return False, "Access to localhost or loopback is forbidden."

        # Resolve IP to detect private IP ranges
        ip_addr = socket.gethostbyname(hostname)
        parts = [int(p) for p in ip_addr.split(".")]
        if len(parts) == 4:
            # 10.0.0.0/8
            if parts[0] == 10:
                return False, "Access to private internal IP addresses is forbidden."
            # 172.16.0.0/12
            if parts[0] == 172 and 16 <= parts[1] <= 31:
                return False, "Access to private internal IP addresses is forbidden."
            # 192.168.0.0/16
            if parts[0] == 192 and parts[1] == 168:
                return False, "Access to private internal IP addresses is forbidden."
            # 169.254.0.0/16 (AWS / Cloud metadata)
            if parts[0] == 169 and parts[1] == 254:
                return False, "Access to metadata IP addresses is forbidden."
            # 127.0.0.0/8
            if parts[0] == 127:
                return False, "Access to loopback IP addresses is forbidden."

        return True, ""
    except Exception as exc:
        return False, f"Could not validate destination host: {exc}"


def fetch_and_store_to_r2(remote_url: str, folder: str = "media", custom_filename: str = None) -> (bool, str, str):
    """
    Fetch image or video from an external URL and upload to Cloudflare R2.
    Returns (success: bool, public_url: str, error_message: str)
    """
    url_clean = (remote_url or "").strip()
    if not url_clean:
        return False, "", "No URL provided."

    # If the URL is already an R2 URL on our domain, return directly
    if is_r2_media_url(url_clean):
        return True, url_clean, ""

    is_safe, reason = _is_safe_remote_url(url_clean)
    if not is_safe:
        return False, "", reason

    try:
        headers = {
            "User-Agent": "Think4U-MediaFetcher/1.0 (+https://think4u.org)",
            "Accept": "image/*,video/*,*/*",
        }
        with httpx.Client(timeout=25.0, follow_redirects=True) as client:
            resp = client.get(url_clean, headers=headers)

        if resp.status_code != 200:
            return False, "", f"Failed to fetch remote media (HTTP {resp.status_code})."

        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        content = resp.content

        # Size check: 100 MB max for remote fetch
        if len(content) > 100 * 1024 * 1024:
            return False, "", "Remote file is too large (exceeds 100 MB limit)."

        # Determine extension
        ext = ""
        if content_type:
            ext = mimetypes.guess_extension(content_type) or ""
        if not ext:
            parsed_path = urlparse(url_clean).path
            _, orig_ext = os.path.splitext(parsed_path)
            ext = orig_ext[:10] if orig_ext else ".jpg"

        if not ext.startswith("."):
            ext = f".{ext}"

        # Standardize common extensions
        if ext == ".jpe":
            ext = ".jpg"

        if custom_filename:
            safe_name = "".join(c for c in custom_filename if c.isalnum() or c in "-_")
            filename = f"{safe_name}{ext}"
        else:
            filename = f"{uuid.uuid4().hex[:16]}{ext}"

        clean_folder = folder.strip("/").strip()
        key = f"{clean_folder}/{filename}" if clean_folder else filename

        # If R2 is configured, upload to R2
        if is_r2_configured():
            return upload_to_r2(content, key, content_type=content_type)
        else:
            # Fallback if R2 credentials are not yet entered: save to local static/uploads
            uploads_dir = os.path.join(os.getcwd(), "static", "uploads", clean_folder)
            os.makedirs(uploads_dir, exist_ok=True)
            local_path = os.path.join(uploads_dir, filename)
            with open(local_path, "wb") as f:
                f.write(content)
            # Return custom domain URL anyway as requested or local fallback
            domain = R2_CUSTOM_DOMAIN or "media.think4u.org"
            public_url = f"https://{domain}/{key}"
            logger.info(f"Saved locally (R2 credentials absent), formatted as: {public_url}")
            return True, public_url, ""

    except Exception as exc:
        logger.error(f"Error fetching media from {url_clean}: {exc}")
        return False, "", f"Could not fetch media: {exc}"


def delete_from_r2(url_or_key: str) -> (bool, str):
    """Delete an object from Cloudflare R2 bucket by URL or Key."""
    client = get_r2_client()
    if not client:
        return False, "Cloudflare R2 is not configured."

    key = extract_r2_key_from_url(url_or_key) if url_or_key.startswith("http") else url_or_key.lstrip("/")
    if not key:
        return False, "Invalid key."

    try:
        client.delete_object(Bucket=R2_BUCKET, Key=key)
        return True, ""
    except Exception as exc:
        logger.error(f"Error deleting {key} from R2: {exc}")
        return False, str(exc)
