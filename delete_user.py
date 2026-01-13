import requests

SUPABASE_URL = "https://gutdnucusjhbimduscno.supabase.co"
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd1dGRudWN1c2poYmltZHVzY25vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTIwNTg4NSwiZXhwIjoyMDgwNzgxODg1fQ._ZxEkdjnKskMJrQ5FGiiwUnPsR1mKsV2yS71WbP3rBI"

headers = {
    "Authorization": f"Bearer {SERVICE_KEY}",
    "apikey": SERVICE_KEY,
    "Content-Type": "application/json"
}

EMAIL = "admin@think4u.com"

users = requests.get(f"{SUPABASE_URL}/auth/v1/admin/users", headers=headers).json()["users"]

for u in users:
    if u["email"] == EMAIL:
        r = requests.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{u['id']}", headers=headers)
        print("Deleted user:", r.status_code)
        break
