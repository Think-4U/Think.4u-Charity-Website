import argparse
import os
import re

from dotenv import load_dotenv
from supabase import create_client
from werkzeug.security import generate_password_hash


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Reset password in public.users table")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

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

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY in environment")

    supabase = create_client(supabase_url, supabase_key)
    supabase.table("users").update({
        "password_hash": generate_password_hash(args.password),
    }).eq("email", args.email.lower()).execute()

    print("Password updated for:", args.email.lower())


if __name__ == "__main__":
    main()
