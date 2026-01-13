from supabase import create_client
from werkzeug.security import generate_password_hash

SUPABASE_URL = "https://gutdnucusjhbimduscno.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd1dGRudWN1c2poYmltZHVzY25vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTIwNTg4NSwiZXhwIjoyMDgwNzgxODg1fQ._ZxEkdjnKskMJrQ5FGiiwUnPsR1mKsV2yS71WbP3rBI"

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

email = "admin@think4u.com"
new_password = "adminpass"

hash_pw = generate_password_hash(new_password)

sb.table("users").update({
    "password_hash": hash_pw
}).eq("email", email).execute()

print("✅ Password updated for:", email)
