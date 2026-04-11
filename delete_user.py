import argparse
import os

import requests
from dotenv import load_dotenv


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Delete a Supabase auth user by email")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not service_key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY in environment")

    headers = {
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "Content-Type": "application/json",
    }

    users_resp = requests.get(f"{supabase_url}/auth/v1/admin/users", headers=headers, timeout=30)
    users_resp.raise_for_status()
    users = users_resp.json().get("users", [])

    for user in users:
        if (user.get("email") or "").lower() == args.email.lower():
            delete_resp = requests.delete(
                f"{supabase_url}/auth/v1/admin/users/{user['id']}",
                headers=headers,
                timeout=30,
            )
            print("Deleted user status:", delete_resp.status_code)
            return

    print("User not found")


if __name__ == "__main__":
    main()
