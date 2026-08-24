import app
from flask_mail import Message
with app.app.app_context():
    m=Message(sender='test@example.com')
    m.attach('invite.ics', 'text/calendar; method=REQUEST', 'data', disposition='inline', headers={'Content-Class': 'urn:content-classes:calendarmessage'})
    print('Attached!')