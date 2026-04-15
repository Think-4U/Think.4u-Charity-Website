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

## 4) Add Vercel Environment Variables
Set these in Vercel Project Settings -> Environment Variables:

- `SECRET_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY` (service_role key for backend)
- `RAZOR_KEY_ID`
- `RAZOR_KEY_SECRET`
- `RAZORPAY_WEBHOOK_SECRET`
- `UPI_VPA`
- `MAIL_USERNAME`
- `MAIL_PASSWORD`
- `ENFORCE_HTTPS=true`
- `SESSION_COOKIE_SECURE=true`
- `ALLOW_DEV_OTP_FALLBACK=false`
- `ENABLE_ADMIN_BOOTSTRAP=false`

Optional:
- `ADMIN_BOOTSTRAP_TOKEN`
- `ADMIN_BOOTSTRAP_EMAIL`
- `ADMIN_BOOTSTRAP_PASSWORD`

## 5) Verify Deployment
- Open:
  - `/healthz`
  - `/`
  - `/login`

If `/healthz` is not `status: ok`, check Vercel function logs and env variables.
