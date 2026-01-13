from supabase import create_client

SUPABASE_URL = "https://gutdnucusjhbimduscno.supabase.co"
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd1dGRudWN1c2poYmltZHVzY25vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTIwNTg4NSwiZXhwIjoyMDgwNzgxODg1fQ._ZxEkdjnKskMJrQ5FGiiwUnPsR1mKsV2yS71WbP3rBI"

supabase = create_client(SUPABASE_URL, ANON_KEY)

email = "admin@think4u.com"
password = input("Enter password: ")

try:
    supabase.auth.sign_in_with_password({
        "email": email,
        "password": password
    })
    print("Password correct ✅")
except Exception as e:
    print("Login failed ❌", e)
