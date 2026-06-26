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
    print("Connecting to database...")
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    
    print("Altering public.appointment_slots to add registration_limit and meeting_settings...")
    cursor.execute("""
        ALTER TABLE public.appointment_slots 
        ADD COLUMN IF NOT EXISTS registration_limit INTEGER DEFAULT 1,
        ADD COLUMN IF NOT EXISTS meeting_settings JSONB DEFAULT '{"show_chat": true, "show_screen_share": true, "show_raise_hand": true, "show_participants": true}'::jsonb;
    """)
    
    print("Altering public.appointments to add meeting_settings...")
    cursor.execute("""
        ALTER TABLE public.appointments 
        ADD COLUMN IF NOT EXISTS meeting_settings JSONB DEFAULT '{"show_chat": true, "show_screen_share": true, "show_raise_hand": true, "show_participants": true}'::jsonb;
    """)
    
    conn.commit()
    cursor.close()
    conn.close()
    print("Database altered successfully!")
except Exception as e:
    print(f"Error altering database: {e}")
    exit(1)
