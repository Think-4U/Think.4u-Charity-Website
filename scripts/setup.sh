#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "1) Create Python virtual environment (.venv)"
python3 -m venv .venv

echo "2) Activate and install Python dependencies"
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ -f package.json ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "3) Installing node deps and building Tailwind CSS"
    npm install
    npm run build:css
  else
    echo "npm not found — skip JS/CSS build. Install Node/npm to build Tailwind CSS." >&2
  fi
fi

echo
echo "Done. Next steps:"
echo "- Copy .env.example to .env and fill values (Supabase, Razorpay, MAIL credentials, SECRET_KEY)."
echo "  cp .env.example .env && edit .env"
echo "- To run locally:"
echo "  source .venv/bin/activate"
echo "  export FLASK_APP=app"
echo "  flask run --host=0.0.0.0 --port=5000"
echo
echo "Notes:" 
echo "- The production deployment uses Vercel serverless function at api/index.py and requires Vercel env vars (see README)."
echo "- Supabase setup: run sql_code.txt in Supabase SQL Editor as described in README.md."
