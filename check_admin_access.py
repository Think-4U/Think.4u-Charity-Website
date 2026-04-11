import os

from dotenv import load_dotenv
from supabase import create_client


def main():
    load_dotenv()
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not service_key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_KEY in environment")

    supabase = create_client(supabase_url, service_key)
    users = supabase.auth.admin.list_users()
    user_list = users.users if hasattr(users, "users") else users
    print("Total users found:", len(user_list))


if __name__ == "__main__":
    main()
