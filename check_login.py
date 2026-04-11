import argparse
import os

from dotenv import load_dotenv
from supabase import create_client


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Validate user login against Supabase auth")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY in environment")

    supabase = create_client(supabase_url, supabase_key)

    try:
        supabase.auth.sign_in_with_password({
            "email": args.email,
            "password": args.password,
        })
        print("Password correct")
    except Exception as exc:
        print("Login failed", exc)


if __name__ == "__main__":
    main()
