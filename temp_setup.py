import os
from dotenv import load_dotenv
load_dotenv()
import psycopg2

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

try:
    cur.execute('''INSERT INTO storage.buckets (id, name, public) VALUES ('think4u-media', 'think4u-media', true) ON CONFLICT (id) DO NOTHING;''')
    cur.execute('''CREATE POLICY "Public Access" ON storage.objects FOR SELECT USING (bucket_id = 'think4u-media');''')
    cur.execute('''CREATE POLICY "Anon Upload" ON storage.objects FOR INSERT WITH CHECK (bucket_id = 'think4u-media');''')
    cur.execute('''CREATE POLICY "Anon Update" ON storage.objects FOR UPDATE USING (bucket_id = 'think4u-media');''')
    cur.execute('''CREATE POLICY "Anon Delete" ON storage.objects FOR DELETE USING (bucket_id = 'think4u-media');''')
    conn.commit()
    print('Bucket and policies created successfully!')
except Exception as e:
    print('Error:', e)
finally:
    cur.close()
    conn.close()
