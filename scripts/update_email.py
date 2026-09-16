import os, httpx
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SERVICE_KEY  = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

headers = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

url = f"{SUPABASE_URL}/rest/v1/cms_content?value=eq.hello@think4u.org"
res = httpx.patch(url, headers=headers, json={"value": "info@think4u.org"})
print("Status:", res.status_code)
print("Response:", res.text)
print("Done.")
