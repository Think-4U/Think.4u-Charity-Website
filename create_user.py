import argparse
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client
from werkzeug.security import generate_password_hash
import re


def normalize_email(value):
    email = (value or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return None
    return email


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Create or update Think.4U users in public.users")
    parser.add_argument("--email", required=True, help="User email")
    parser.add_argument("--password", required=True, help="Plain-text password")
    parser.add_argument("--name", default="User", help="Display name")
    parser.add_argument("--role", default="donor", choices=["donor", "volunteer", "both", "admin"], help="User role")
    parser.add_argument("--admin", action="store_true", help="Force admin permissions")
    args = parser.parse_args()

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY in environment")

    email = normalize_email(args.email)
    if not email:
        raise ValueError("Invalid email format")
    if len(args.password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not re.search(r"[A-Z]", args.password):
        raise ValueError("Password must include an uppercase letter")
    if not re.search(r"[a-z]", args.password):
        raise ValueError("Password must include a lowercase letter")
    if not re.search(r"\d", args.password):
        raise ValueError("Password must include a number")
    if not re.search(r"[^A-Za-z0-9]", args.password):
        raise ValueError("Password must include a special character")

    is_admin = bool(args.admin or args.role == "admin")
    role = "admin" if is_admin else args.role

    supabase = create_client(supabase_url, supabase_key)
    now_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "email": email,
        "name": (args.name or "User").strip()[:120],
        "password_hash": generate_password_hash(args.password),
        "is_admin": is_admin,
        "role": role,
        "email_verified": True,
        "created_at": now_iso,
    }

    existing_response = supabase.table("users").select("id").eq("email", email).limit(1).execute()
    existing_row = (existing_response.data or [None])[0]

    if existing_row:
        payload.pop("created_at", None)
        supabase.table("users").update(payload).eq("id", existing_row["id"]).execute()
        print(f"Updated user: {email}")
    else:
        supabase.table("users").insert(payload).execute()
        print(f"Created user: {email}")

    print(f"is_admin={is_admin}, role={role}")


if __name__ == "__main__":
    main()
