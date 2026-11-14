"""
ARCHIVED: UPI Payment Routes & QR Code Generation
Extracted from: app.py
Archive Date: 2024-11-14

These routes handled UPI-based donations (direct UPI payment + QR code).

Environment Variables Required:
  - UPI_VPA (e.g., "yourname@upi")

Templates Used:
  - templates/donate_upi.html (archived in this folder)

Routes:
  - GET  /donate-upi         -> UPI donation page (login required)
  - POST /donate-upi/verify  -> Submit UPI transaction for admin verification
  - GET  /upi-qr             -> Generate UPI QR code image

Dependencies (shared, NOT archived):
  - supabase/db client for saving donation records
  - current_user (Flask-Login) for donor identification
  - create_notification_for_user() for user notifications
  - send_email_async() for acknowledgment emails
  - clean_text(), normalize_phone() for input sanitization
"""


# --- Route: GET /donate-upi ---
# @app.route("/donate-upi")
# @login_required
# def donate_upi():
#     """UPI donation page"""
#     amount = request.args.get('amount', '')
#     return render_template("donate_upi.html", upi_vpa=UPI_VPA, amount=amount)


# --- Route: POST /donate-upi/verify ---
# @app.route("/donate-upi/verify", methods=["POST"])
# @login_required
# def donate_upi_verify():
#     """Create manual UPI donation entry for admin verification."""
#     amount_raw = clean_text(request.form.get("amount"), 20)
#     txn_ref = clean_text(request.form.get("txn_ref"), 80).upper()
#     phone = normalize_phone(request.form.get("phone", ""))
#
#     try:
#         amount_rupees = float(amount_raw)
#         amount_paise = int(round(amount_rupees * 100))
#     except Exception:
#         flash("Enter a valid donation amount.", "error")
#         return redirect(url_for("donate_upi", amount=amount_raw))
#
#     if amount_paise < 1000:
#         flash("Minimum donation is Rs 10.", "error")
#         return redirect(url_for("donate_upi", amount=amount_raw))
#
#     if not re.fullmatch(r"[A-Z0-9]{8,40}", txn_ref):
#         flash("Enter a valid UPI transaction reference (8-40 letters/numbers).", "error")
#         return redirect(url_for("donate_upi", amount=amount_raw))
#
#     if not phone:
#         flash("Enter a valid 10 digit phone number for verification.", "error")
#         return redirect(url_for("donate_upi", amount=amount_raw))
#
#     synthetic_order_id = f"upi_{int(datetime.now(timezone.utc).timestamp())}_{current_user.id}_{secrets.randbelow(10000)}"
#
#     try:
#         supabase.table("donations").insert({
#             "user_id": current_db_user_id(),
#             "name": clean_text(current_user.name or current_user.email.split("@")[0], 120),
#             "email": current_user.email,
#             "phone": phone,
#             "amount": amount_paise,
#             "razorpay_order_id": synthetic_order_id,
#             "razorpay_payment_id": txn_ref,
#             "payment_method": "UPI",
#             "status": "pending",
#             "created_at": datetime.now(timezone.utc).isoformat(),
#         }).execute()
#         ...
#     except Exception as e:
#         ...


# --- Route: GET /upi-qr ---
# @app.route("/upi-qr")
# def upi_qr():
#     """Generate UPI QR code"""
#     amount = request.args.get('amount', '')
#     upi_string = f"upi://pay?pa={UPI_VPA}&pn=Think.4U"
#     if amount:
#         upi_string += f"&am={amount}"
#     upi_string += "&cu=INR"
#     qr = qrcode.QRCode(...)
#     qr.add_data(upi_string)
#     ...
