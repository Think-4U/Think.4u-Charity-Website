import os

import requests
from dotenv import load_dotenv


def main():
    load_dotenv()
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not service_key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY in environment")

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }

    response = requests.get(f"{supabase_url}/auth/v1/admin/users", headers=headers, timeout=30)
    print("Status:", response.status_code)
    print("Response:", response.json())


if __name__ == "__main__":
    main()
