# Think.4U Deployment Guide (GitHub + Vercel)

## 1) Push to GitHub
- Ensure `.env` is **not** committed.
- Commit and push this project to your GitHub repository.

## 2) Configure Supabase
- Open Supabase SQL Editor.
- Run the full SQL from `sql_code.txt`.

## 3) Deploy on Vercel
- Import the GitHub repo in Vercel.
- Framework: `Other`.
- Python version: `3.12` (from `.python-version`)
- Vercel uses:
  - `vercel.json`
  - `api/index.py` (Python serverless function)

### Frontend CSS Build (Tailwind)
- This project uses compiled Tailwind CSS (no CDN in production).
- After template/class changes, run:
  - `npm install`
  - `npm run build:css`
- Ensure [static/css/tailwind.css](E:\LAPTOP\think4u\static\css\tailwind.css) is committed.

## 4) Add Vercel Environment Variables
Set these in Vercel Project Settings -> Environment Variables:

- `SECRET_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY` (service_role key for backend)
- `SUPABASE_TIMEOUT_SECONDS=4`
- `RAZOR_KEY_ID`
- `RAZOR_KEY_SECRET`
- `RAZORPAY_WEBHOOK_SECRET`
- `UPI_VPA`
- `MAIL_USERNAME`
- `MAIL_PASSWORD`
- `SITE_MEDIA_BUCKET=site-media`
- `JITSI_MEET_DOMAIN=meet.yourdomain.com`
- `JITSI_JWT_KID`
- `JITSI_JWT_PRIVATE_KEY` or `JITSI_JWT_PRIVATE_KEY_FILE`
- `JITSI_JWT_SUBJECT`
- `JITSI_REQUIRE_JWT=true`
- `JITSI_JWT_TTL_SECONDS=900` (or less)
- `ENFORCE_HTTPS=true`
- `SESSION_COOKIE_SECURE=true`
- `ALLOW_DEV_OTP_FALLBACK=false`

## 5) Verify Deployment
- Open:
  - `/healthz`
  - `/`
  - `/login`

If `/healthz` is not `status: ok`, check Vercel function logs and env variables.

## Jitsi security deployment

This site is linked to Jitsi through `JITSI_MEET_DOMAIN`. It issues a short-lived,
room-scoped JWT only after Think4u authorization succeeds. On the AWS Jitsi host,
copy `E:\LAPTOP\think4u meet\docker-jitsi-meet\think4u.secure.env.example` to the
deployment `.env`, fill in unique secrets and the real domain/IP, then restart the
stack. Do not enable guest access: guests bypass the application authorization
boundary. Jitsi's lobby is useful only for authenticated users and does not replace
JWT validation.

For the supplied self-hosted Docker configuration, set `JITSI_JWT_SECRET` to the
same secret as the host's `JWT_APP_SECRET` and set `JITSI_JWT_ALGORITHM=HS256` in
the Think4u deployment. The supplied RSA variables are for a JaaS/asymmetric JWT
setup and are not interchangeable with the Docker shared secret.
