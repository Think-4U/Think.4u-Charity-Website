import os
import psycopg2
from dotenv import load_dotenv

# Load env variables from .env
load_dotenv()

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("DATABASE_URL is not set in .env")
    exit(1)

try:
    print(f"Connecting to database...")
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    
    print("Altering table volunteer_events to add column max_registrations...")
    cursor.execute("""
        ALTER TABLE public.volunteer_events 
        ADD COLUMN IF NOT EXISTS max_registrations INTEGER DEFAULT NULL;
    """)
    
    conn.commit()
    cursor.close()
    conn.close()
    print("Database altered successfully!")
except Exception as e:
    print(f"Error altering database: {e}")
    exit(1)
