"""
ARCHIVED: Razorpay Payment Gateway Implementation
Extracted from: payment_gateways.py (RazorpayGateway class)
Archive Date: 2024-11-14

This file preserves the Razorpay gateway integration for future reuse.
The RazorpayGateway class implements the BasePaymentGateway interface.

Environment Variables Required:
  - RAZOR_KEY_ID
  - RAZOR_KEY_SECRET
  - RAZORPAY_WEBHOOK_SECRET (for webhook verification)

API Endpoint: https://api.razorpay.com/v1/orders

SDK/Frontend:
  - Razorpay Checkout JS SDK loaded from https://checkout.razorpay.com/v1/checkout.js
  - Checkout mode: "razorpay_modal"

Routes that used this gateway (in app.py):
  - POST /create-order (order creation)
  - GET/POST /payment-success (signature verification)
  - POST /payment-webhook (webhook signature verification)

Docs: https://razorpay.com/docs/payments/
"""

import os
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone
import httpx

logger = logging.getLogger("think4u.payments")


class RazorpayGateway:
    """
    Razorpay integration implementing the common gateway interface.
    """

    gateway_id = "razorpay"
    gateway_name = "Razorpay"

    def __init__(self):
        self.key_id = (os.getenv("RAZOR_KEY_ID") or "").strip()
        self.key_secret = (os.getenv("RAZOR_KEY_SECRET") or "").strip()
        self.webhook_secret = (os.getenv("RAZORPAY_WEBHOOK_SECRET") or "").strip()

    def is_configured(self) -> bool:
        return bool(self.key_id and self.key_secret)

    def create_order(self, amount_paise, currency="INR", donor_details=None, notes=None, return_url=None):
        if not self.is_configured():
            raise RuntimeError("Razorpay credentials (RAZOR_KEY_ID, RAZOR_KEY_SECRET) are missing.")

        receipt = (notes or {}).get("donation_ref", f"rcpt_{int(datetime.now(timezone.utc).timestamp())}")[:40]
        payload = {
            "amount": amount_paise,
            "currency": currency or "INR",
            "receipt": receipt,
            "payment_capture": 1,
        }
        if notes and isinstance(notes, dict):
            payload["notes"] = {k: str(v)[:60] for k, v in notes.items()}

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                "https://api.razorpay.com/v1/orders",
                auth=(self.key_id, self.key_secret),
                json=payload
            )

        if resp.status_code not in (200, 201):
            logger.error(f"Razorpay order creation failed: {resp.status_code} {resp.text}")
            raise RuntimeError(f"Razorpay order creation failed: {resp.status_code} {resp.text}")

        res_json = resp.json()
        return {
            "gateway": self.gateway_id,
            "gateway_name": self.gateway_name,
            "order_id": res_json["id"],
            "amount": res_json["amount"],
            "amount_rupees": round(res_json["amount"] / 100.0, 2),
            "currency": res_json["currency"],
            "key_id": self.key_id,
            "checkout_mode": "razorpay_modal",
            "raw_response": res_json
        }

    def verify_payment(self, payload):
        order_id = payload.get("order_token") or payload.get("razorpay_order_id") or payload.get("order_id")
        payment_id = payload.get("payment_token") or payload.get("razorpay_payment_id") or payload.get("payment_id")
        signature = payload.get("checkout_signature") or payload.get("razorpay_signature")

        if not all([order_id, payment_id, signature, self.key_secret]):
            return {"verified": False, "error": "Missing signature or payment token parameters"}

        message = f"{order_id}|{payment_id}".encode("utf-8")
        expected = hmac.new(self.key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

        if hmac.compare_digest(expected, signature):
            return {
                "verified": True,
                "status": "PAID",
                "order_id": order_id,
                "payment_id": payment_id,
                "payment_method": "Razorpay",
                "raw_response": payload,
                "error": None
            }
        return {"verified": False, "error": "Invalid Razorpay signature"}

    def verify_webhook(self, headers, raw_body):
        signature = headers.get("X-Razorpay-Signature") or headers.get("x-razorpay-signature")
        if not self.webhook_secret:
            return {"verified": False, "error": "RAZORPAY_WEBHOOK_SECRET not configured"}
        if not signature:
            return {"verified": False, "error": "Missing X-Razorpay-Signature header"}

        expected = hmac.new(self.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return {"verified": False, "error": "Invalid Razorpay webhook signature"}

        import json
        data = json.loads(raw_body.decode("utf-8"))
        entity = data.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = entity.get("order_id", "")
        payment_id = entity.get("id", "")
        status = entity.get("status", "")
        return {
            "verified": True,
            "order_id": order_id,
            "payment_id": payment_id,
            "status": "PAID" if status == "captured" else "FAILED",
            "event_type": data.get("event", ""),
            "raw_data": data,
            "error": None
        }
