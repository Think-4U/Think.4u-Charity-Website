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
- `JITSI_MEET_DOMAIN=8x8.vc`
- `JITSI_APP_ID`
- `JITSI_JWT_KID`
- `JITSI_JWT_PRIVATE_KEY` or `JITSI_JWT_PRIVATE_KEY_FILE`
- `JITSI_JWT_SUBJECT` (usually the same as `JITSI_APP_ID` for JaaS)
- `ENFORCE_HTTPS=true`
- `SESSION_COOKIE_SECURE=true`
- `ALLOW_DEV_OTP_FALLBACK=false`

## 5) Verify Deployment
- Open:
  - `/healthz`
  - `/`
  - `/login`

If `/healthz` is not `status: ok`, check Vercel function logs and env variables.
