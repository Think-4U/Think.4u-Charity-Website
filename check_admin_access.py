from supabase import create_client

SUPABASE_URL = "https://gutdnucusjhbimduscno.supabase.co"
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd1dGRudWN1c2poYmltZHVzY25vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTIwNTg4NSwiZXhwIjoyMDgwNzgxODg1fQ._ZxEkdjnKskMJrQ5FGiiwUnPsR1mKsV2yS71WbP3rBI"

supabase = create_client(SUPABASE_URL, SERVICE_KEY)

users = supabase.auth.admin.list_users()
print("Total users found:", len(users))
