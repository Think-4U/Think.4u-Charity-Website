"""
ARCHIVED: Payment Gateway Route Handlers (Cashfree + Razorpay)
Extracted from: app.py (lines ~2934-3285)
Archive Date: 2024-11-14

These routes handled the core payment flow:
  1. Order creation (POST /create-order)
  2. Payment status updates (POST /payment-status)
  3. Payment success redirect verification (GET/POST /payment-success)
  4. Server-to-server webhook processing (POST /payment-webhook, /api/payment/webhook)

All routes worked with any gateway registered in PaymentGatewayManager
via the get_active_gateway() function.

Dependencies (shared, NOT archived - remain in app.py):
  - supabase/db client
  - Flask-Login current_user
  - make_donation_ref()
  - normalize_donation_purpose()
  - apply_paid_donation_effects()
  - send_donation_receipt_email_if_needed()
  - create_notification_for_user()
  - clean_text(), normalize_phone(), db_id()
  - RAZOR_KEY, PAYMENT_PENDING_TIMEOUT_MINUTES

CSP Headers that were required (in after_request handler):
  - script-src: https://*.razorpay.com https://sdk.cashfree.com https://*.cashfree.com
  - connect-src: https://*.razorpay.com https://api.cashfree.com https://sandbox.cashfree.com https://*.cashfree.com
  - frame-src: https://*.razorpay.com https://*.cashfree.com
  - form-action: https://*.cashfree.com https://*.razorpay.com
"""


# =============================================================================
# POST /create-order
# =============================================================================
# @app.route("/create-order", methods=["POST"])
# @login_required
# def create_order():
#     """Create payment gateway order for logged-in donor (Cashfree, Razorpay, or pluggable gateway)."""
#     active_gw = get_active_gateway()
#     if not active_gw.is_configured():
#         return jsonify({"error": "Payment gateway temporarily unavailable"}), 503
#     ...
#     order = active_gw.create_order(amount_paise=amount, ...)
#     supabase.table("donations").insert(donation_payload).execute()
#     return jsonify({...})


# =============================================================================
# POST /payment-status
# =============================================================================
# @app.route("/payment-status", methods=["POST"])
# @login_required
# def payment_status_update():
#     """Mark interrupted payment attempt as failed/cancelled."""
#     ...


# =============================================================================
# GET/POST /payment-success
# =============================================================================
# @app.route("/payment-success", methods=["GET", "POST"])
# def payment_success_redirect():
#     """Handle payment success redirect for Cashfree, Razorpay, or pluggable gateway."""
#     # Auto-detects gateway from parameters (CF_ prefix → Cashfree, razorpay_signature → Razorpay)
#     # Calls gw.verify_payment(verify_payload) for cryptographic verification
#     # Checks amount tampering (verified amount vs expected amount)
#     # Updates donation record and triggers side effects
#     ...


# =============================================================================
# POST /payment-webhook, /api/payment/webhook
# =============================================================================
# @app.route("/payment-webhook", methods=["GET", "POST"])
# @app.route("/api/payment/webhook", methods=["GET", "POST"])
# def payment_webhook():
#     """Server-to-server webhook for Cashfree & Razorpay confirmations."""
#     # Detects gateway from headers (x-webhook-signature → Cashfree, X-Razorpay-Signature → Razorpay)
#     # Calls gw.verify_webhook(headers, raw_body)
#     # Updates donation status to "paid" and triggers side effects
#     ...


# =============================================================================
# Donation verification (OTP) routes for anonymous donors
# =============================================================================
# @app.route("/donation/start", methods=["POST"])
# def start_public_donation_verification():
#     """Send OTP for anonymous/public donation checkout (SMS or Email)."""
#     ...

# @app.route("/donation/verify", methods=["POST"])
# def verify_public_donation():
#     """Verify OTP and create/login donor account."""
#     ...
