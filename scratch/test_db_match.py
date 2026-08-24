import os
import sys
# Add root folder to sys.path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app import get_db_connection
from psycopg2.extras import RealDictCursor

conn = get_db_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

# Let's insert a test slot
try:
    cur.execute("SELECT id, slot_date, slot_time FROM public.appointment_slots LIMIT 1;")
    row = cur.fetchone()
    if row:
        date_val = str(row['slot_date'])
        time_val = str(row['slot_time'])[:5] # e.g. "09:00"
        print(f"Database values - Date: {row['slot_date']} (type: {type(row['slot_date'])}), Time: {row['slot_time']} (type: {type(row['slot_time'])})")
        print(f"Querying with parameter - Date: '{date_val}', Time: '{time_val}'")
        
        cur.execute("""
            SELECT id FROM public.appointment_slots 
            WHERE slot_date = %s AND slot_time = %s;
        """, (date_val, time_val))
        res = cur.fetchone()
        print(f"Result: {res}")
    else:
        print("No slots in database to test.")
except Exception as e:
    print(f"Error: {e}")
finally:
    cur.close()
    conn.close()
