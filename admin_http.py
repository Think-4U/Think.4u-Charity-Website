import requests

SUPABASE_URL = "https://gutdnucusjhbimduscno.supabase.co"
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd1dGRudWN1c2poYmltZHVzY25vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTIwNTg4NSwiZXhwIjoyMDgwNzgxODg1fQ._ZxEkdjnKskMJrQ5FGiiwUnPsR1mKsV2yS71WbP3rBI"

headers = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json"
}

# List users
r = requests.get(f"{SUPABASE_URL}/auth/v1/admin/users", headers=headers)
print("Status:", r.status_code)
print("Response:", r.json())
