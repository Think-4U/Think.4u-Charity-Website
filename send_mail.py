import os
import smtplib
from dotenv import load_dotenv
from supabase import create_client
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"

loaded = load_dotenv(dotenv_path=env_path)

print("Loaded:", loaded)
print("ENV Path:", env_path)

print("MAIL_SERVER:", os.getenv("MAIL_SERVER"))
print("MAIL_PORT:", os.getenv("MAIL_PORT"))
print("MAIL_USERNAME:", os.getenv("MAIL_USERNAME"))
print("MAIL_PASSWORD:", os.getenv("MAIL_PASSWORD"))
# -----------------------------
# ENV VARIABLES
# -----------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

SMTP_SERVER = os.getenv("MAIL_SERVER")
SMTP_PORT = int(os.getenv("MAIL_PORT", "587"))
SMTP_EMAIL = os.getenv("MAIL_USERNAME")
SMTP_PASSWORD = os.getenv("MAIL_PASSWORD")


PRIMARY = "#2B1B14"      # Dark Brown
SECONDARY = "#F39C12"    # Orange
SUCCESS = "#2E7D32"
WARNING = "#C96A12"
BACKGROUND = "#F6F3EF"
CARD = "#FFFFFF"
TEXT = "#3E3E3E"
LIGHT = "#FFF7EF"
# -----------------------------
# CONNECT TO SUPABASE
# -----------------------------

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

def email_header(title, subtitle):

    return f"""
<!DOCTYPE html>
<html>

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width, initial-scale=1.0">

<title>{title}</title>

</head>

<body
style="
margin:0;
padding:0;
background:{BACKGROUND};
font-family:Arial,Helvetica,sans-serif;
">

<table
width="100%"
cellpadding="0"
cellspacing="0"
style="background:{BACKGROUND};">

<tr>

<td align="center">

<table
width="680"
cellpadding="0"
cellspacing="0"
style="
max-width:680px;
width:100%;
background:white;
border-radius:14px;
overflow:hidden;
box-shadow:0 10px 35px rgba(0,0,0,.08);
">

<tr>

<td
style="
background:{PRIMARY};
padding:45px;
text-align:center;
">

<img
src="cid:think4u_logo"
width="220"
style="
display:block;
margin:auto;
max-width:220px;
height:auto;
">

<div
style="
margin-top:25px;
font-size:30px;
color:white;
font-weight:bold;
">

Think4U Charity Foundation

</div>

<div
style="
margin-top:12px;
font-size:16px;
color:#FFE9D4;
">

Love in Action, Care with Compassion

</div>

</td>

</tr>

<tr>

<td style="padding:45px;">

<h1
style="
margin-top:0;
font-size:32px;
color:{PRIMARY};
">

{title}

</h1>

<p
style="
font-size:18px;
color:#666;
line-height:1.8;
">

{subtitle}

</p>
"""

def email_footer():

    return f"""

<hr
style="
margin:40px 0;
border:none;
border-top:1px solid #eee;
">

<table
width="100%"
cellpadding="10">

<tr>

<td align="center">

<a
href="https://think-4u-charity-website.vercel.app/"
style="
display:inline-block;
background:{PRIMARY};
padding:16px 36px;
color:white;
text-decoration:none;
border-radius:8px;
font-size:16px;
font-weight:bold;
">

Visit Think4U

</a>

</td>

</tr>

</table>

<br>

<table
width="100%"
style="
background:#F9F9F9;
border-radius:10px;
">

<tr>

<td
style="
padding:20px;
text-align:center;
">

<div
style="
font-size:17px;
font-weight:bold;
color:{PRIMARY};
">

CTO

</div>

<div
style="
margin-top:8px;
color:#555;
">

Think4U Tech

<br>

Think4U Charity Foundation

</div>

<br>

<div
style="
color:#777;
font-size:13px;
">

Registered Under Government of Telangana

</div>

<br>

<div
style="
color:#999;
font-size:13px;
">

© 2026 Think4U Charity Foundation

<br>

All Rights Reserved.

</div>

</td>

</tr>

</table>

</td>

</tr>

</table>

</td>

</tr>

</table>

</body>

</html>
"""



def service_restoration_template():

    subject = "✅ Think4U Charity Foundation - Service Restoration Notice"

    html = email_header(
        "✅ Service Restoration",
        "We are pleased to inform you that our scheduled maintenance has been completed successfully."
    )

    html += f"""

<table width="100%" cellpadding="0" cellspacing="0">

<tr>

<td>

<div
style="
background:#ECFDF5;
border-left:6px solid {SUCCESS};
padding:25px;
border-radius:10px;
">

<h2
style="
margin:0;
color:{SUCCESS};
font-size:24px;
">

All Services Are Back Online

</h2>

<p
style="
margin-top:15px;
font-size:16px;
color:#555;
line-height:1.8;
">

Dear User,

<br><br>

We are delighted to inform you that the scheduled maintenance of the
<b>Think4U Charity Foundation</b> website has been completed successfully.

All website services are now fully operational and available for use.

</p>

</div>

</td>

</tr>

</table>

<br>

<table
width="100%"
cellpadding="18"
style="
border:1px solid #E5E7EB;
border-radius:10px;
background:white;
">

<tr>

<td>

<h3
style="
margin-top:0;
color:{PRIMARY};
">

Available Services

</h3>

<table width="100%">

<tr>

<td width="50%" style="padding:8px;">

✅ Appointment Booking

</td>

<td width="50%" style="padding:8px;">

💝 Donations

</td>

</tr>

<tr>

<td style="padding:8px;">

🤝 Volunteer Requests

</td>

<td style="padding:8px;">

📝 Feedback

</td>

</tr>

<tr>

<td style="padding:8px;">

🌐 Website Portal

</td>

<td style="padding:8px;">

👤 User Dashboard

</td>

</tr>

</table>

</td>

</tr>

</table>

<br>

<table
width="100%"
cellpadding="18"
style="
background:#FFF8EC;
border-left:5px solid {SECONDARY};
border-radius:10px;
">

<tr>

<td>

<b
style="
font-size:18px;
color:{PRIMARY};
">

What's Improved?

</b>

<br><br>

• Improved website performance

<br>

• Enhanced security measures

<br>

• Faster response time

<br>

• Better reliability

<br>

• General bug fixes & optimizations

</td>

</tr>

</table>

<br>

<p
style="
font-size:16px;
line-height:1.8;
color:#555;
">

Thank you for your patience, trust, and continued support during the maintenance period.

Our team remains committed to providing a secure, reliable, and seamless experience for every user.

</p>

"""

    html += email_footer()

    return subject, html



def maintenance_template(date, start, end):

    subject = "📢 Think4U Charity Foundation - Scheduled Maintenance Notice"

    html = email_header(
        "📢 Scheduled Maintenance",
        "We are performing scheduled maintenance to improve our platform's performance, security, and reliability."
    )

    html += f"""

<table width="100%" cellpadding="0" cellspacing="0">

<tr>

<td>

<div
style="
background:#FFF7ED;
border-left:6px solid {WARNING};
padding:25px;
border-radius:10px;
">

<h2
style="
margin:0;
color:{WARNING};
font-size:24px;
">

Scheduled Maintenance

</h2>

<p
style="
margin-top:15px;
font-size:16px;
line-height:1.8;
color:#555;
">

Dear User,

<br><br>

To provide a faster, safer and more reliable experience,
the Think4U Charity Foundation website will undergo
scheduled maintenance.

</p>

</div>

</td>

</tr>

</table>

<br>

<table
width="100%"
cellpadding="16"
style="
background:#FFFFFF;
border:1px solid #E5E7EB;
border-radius:10px;
">

<tr>

<td colspan="2">

<h3
style="
margin:0;
color:{PRIMARY};
">

Maintenance Details

</h3>

</td>

</tr>

<tr>

<td
style="
font-weight:bold;
width:35%;
color:#555;
">

📅 Date

</td>

<td>

{date}

</td>

</tr>

<tr>

<td
style="
font-weight:bold;
color:#555;
">

🕘 Time

</td>

<td>

{start} - {end}

</td>

</tr>

<tr>

<td
style="
font-weight:bold;
color:#555;
">

🟠 Status

</td>

<td>

Scheduled

</td>

</tr>

<tr>

<td
style="
font-weight:bold;
color:#555;
">

🌐 Website

</td>

<td>

Think4U Charity Foundation

</td>

</tr>

</table>

<br>

<table
width="100%"
cellpadding="18"
style="
background:#F9FAFB;
border-radius:10px;
border:1px solid #ECECEC;
">

<tr>

<td>

<h3
style="
margin-top:0;
color:{PRIMARY};
">

Services That May Be Affected

</h3>

<table width="100%">

<tr>

<td width="50%" style="padding:8px;">

📝 Appointment Booking

</td>

<td width="50%" style="padding:8px;">

💝 Donations

</td>

</tr>

<tr>

<td style="padding:8px;">

🤝 Volunteer Requests

</td>

<td style="padding:8px;">

📝 Feedback

</td>

</tr>

<tr>

<td style="padding:8px;">

🌐 Website Access

</td>

<td style="padding:8px;">

👤 User Dashboard

</td>

</tr>

</table>

</td>

</tr>

</table>

<br>

<table
width="100%"
cellpadding="18"
style="
background:#FFF8EC;
border-left:5px solid {SECONDARY};
border-radius:10px;
">

<tr>

<td>

<b
style="
font-size:18px;
color:{PRIMARY};
">

Why are we performing maintenance?

</b>

<br><br>

✔ Security Improvements

<br>

✔ Faster Performance

<br>

✔ Infrastructure Upgrades

<br>

✔ Bug Fixes

<br>

✔ Better User Experience

</td>

</tr>

</table>

<br>

<p
style="
font-size:16px;
line-height:1.8;
color:#555;
">

We sincerely apologize for any inconvenience this may cause.
Our technical team will work diligently to complete the maintenance
within the scheduled window.

Thank you for your patience and continued support.

</p>

"""

    html += email_footer()

    return subject, html

def custom_template():

    subject = input("Subject : ")

    print("\nType your message.")
    print("Press ENTER twice to finish.\n")

    lines = []

    while True:

        line = input()

        if line == "":
            break

        lines.append(line)

    message = "<br>".join(lines)

    html = f"""
    <html>
    <body style="font-family:Arial;line-height:1.7">

    {message}

    <br><br>

    Regards,<br><br>

    <b>CTO</b><br>
    Think4U Tech<br>
    Think4U Charity Foundation

    </body>
    </html>
    """

    return subject, html



def fetch_emails():

    response = (
        supabase
        .table("users")
        .select("email")
        .execute()
    )

    emails = []

    for row in response.data:

        if row["email"]:

            emails.append(row["email"])

    return emails





def send_emails(email_list, subject, html):

    server = smtplib.SMTP(
        SMTP_SERVER,
        SMTP_PORT
    )

    server.starttls()

    server.login(
        SMTP_EMAIL,
        SMTP_PASSWORD
    )

    success = 0
    failed = 0

    for email in email_list:

        msg = MIMEMultipart()

        msg["From"] = SMTP_EMAIL
        msg["To"] = email
        msg["Subject"] = subject

        msg.attach(
            MIMEText(
                html,
                "html"
            )
        )

        try:

            server.sendmail(
                SMTP_EMAIL,
                email,
                msg.as_string()
            )

            print(f"✓ {email}")

            success += 1

        except Exception as e:

            print(f"✗ {email}")
            print(e)

            failed += 1

    server.quit()

    print("\nCompleted.")
    print("Successful :", success)
    print("Failed :", failed)



# -----------------------------------
# MAIN MENU
# -----------------------------------

def main():

    while True:

        print("\n" + "=" * 50)
        print("      THINK4U EMAIL SENDER")
        print("=" * 50)
        print("1. Test Email")
        print("2. Send Service Restoration Notice")
        print("3. Send Maintenance Notice")
        print("4. Send Custom Announcement")
        print("5. Exit")
        print("=" * 50)

        choice = input("Enter your choice (1-5): ").strip()

        # ---------------------------------
        # TEST EMAIL
        # ---------------------------------

        if choice == "1":

            print("\nSelect Template")
            print("1. Service Restoration")
            print("2. Maintenance Notice")
            print("3. Custom Announcement")

            template = input("Choice: ").strip()

            test_email = input("\nEnter your email: ").strip()

            if template == "1":

                subject, html = service_restoration_template()

            elif template == "2":

                date = input("Maintenance Date : ")
                start = input("Start Time : ")
                end = input("End Time : ")

                subject, html = maintenance_template(
                    date,
                    start,
                    end
                )

            elif template == "3":

                subject, html = custom_template()

            else:

                print("Invalid Template")
                continue

            send_emails(
                [test_email],
                subject,
                html
            )

        # ---------------------------------
        # SERVICE RESTORATION
        # ---------------------------------

        elif choice == "2":

            subject, html = service_restoration_template()

            emails = fetch_emails()

            print(f"\nFound {len(emails)} users.")

            confirm = input(
                "Send Service Restoration to ALL users? (yes/no): "
            )

            if confirm.lower() == "yes":

                send_emails(
                    emails,
                    subject,
                    html
                )

            else:

                print("Cancelled.")

        # ---------------------------------
        # MAINTENANCE NOTICE
        # ---------------------------------

        elif choice == "3":

            date = input("Maintenance Date : ")
            start = input("Start Time : ")
            end = input("End Time : ")

            subject, html = maintenance_template(
                date,
                start,
                end
            )

            emails = fetch_emails()

            print(f"\nFound {len(emails)} users.")

            confirm = input(
                "Send Maintenance Notice to ALL users? (yes/no): "
            )

            if confirm.lower() == "yes":

                send_emails(
                    emails,
                    subject,
                    html
                )

            else:

                print("Cancelled.")

        # ---------------------------------
        # CUSTOM MESSAGE
        # ---------------------------------

        elif choice == "4":

            subject, html = custom_template()

            emails = fetch_emails()

            print(f"\nFound {len(emails)} users.")

            confirm = input(
                "Send Custom Announcement to ALL users? (yes/no): "
            )

            if confirm.lower() == "yes":

                send_emails(
                    emails,
                    subject,
                    html
                )

            else:

                print("Cancelled.")

        # ---------------------------------
        # EXIT
        # ---------------------------------

        elif choice == "5":

            print("\nGoodbye!")
            break

        else:

            print("\nInvalid Choice.")


if __name__ == "__main__":
    main()