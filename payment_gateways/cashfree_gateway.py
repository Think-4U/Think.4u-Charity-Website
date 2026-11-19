"""
ARCHIVED: Cashfree Payment Gateway Implementation
Extracted from: payment_gateways.py (CashfreeGateway class)
Archive Date: 2024-11-14

This file preserves the Cashfree gateway integration for future reuse.
The CashfreeGateway class implements the BasePaymentGateway interface.

Environment Variables Required:
  - CASHFREE_APP_ID (or CASHFREE_CLIENT_ID)
  - CASHFREE_SECRET_KEY (or CASHFREE_CLIENT_SECRET)
  - CASHFREE_API_VERSION (default: "2023-08-01")
  - CASHFREE_ENV (TEST or PROD, auto-detected if not set)

API Endpoints:
  - Sandbox: https://sandbox.cashfree.com/pg
  - Production: https://api.cashfree.com/pg

SDK/Frontend:
  - Cashfree Drop Checkout JS SDK loaded from https://sdk.cashfree.com
  - Checkout mode: "cashfree_drop"

Routes that used this gateway (in app.py):
  - POST /create-order (order creation via create_order())
  - GET/POST /payment-success (verification via verify_payment())
  - POST /payment-webhook (webhook verification via verify_webhook())
  - POST /api/payment/webhook (alias for webhook)

Docs: https://docs.cashfree.com/docs/core-concepts
"""

import os
import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone
import httpx

logger = logging.getLogger("think4u.payments")


class CashfreeGateway:
    """
    Cashfree Payment Gateway integration (Payment Gateway Orders API v2023-08-01 / v2022-09-01).
    Docs: https://docs.cashfree.com/docs/core-concepts
    """

    gateway_id = "cashfree"
    gateway_name = "Cashfree"

    def __init__(self):
        self.app_id = (os.getenv("CASHFREE_APP_ID") or os.getenv("CASHFREE_CLIENT_ID") or "").strip()
        self.secret_key = (os.getenv("CASHFREE_SECRET_KEY") or os.getenv("CASHFREE_CLIENT_SECRET") or "").strip()
        self.api_version = os.getenv("CASHFREE_API_VERSION", "2023-08-01").strip()
        
        # Determine environment: TEST (sandbox) or PROD (production)
        env = os.getenv("CASHFREE_ENV", "").upper()
        if not env:
            if "TEST" in self.app_id.upper() or not self.app_id:
                env = "TEST"
            else:
                env = "PROD"
        self.env = env

        if self.env == "PROD":
            self.base_url = "https://api.cashfree.com/pg"
            self.sdk_mode = "production"
        else:
            self.base_url = "https://sandbox.cashfree.com/pg"
            self.sdk_mode = "sandbox"

    def is_configured(self) -> bool:
        return bool(self.app_id and self.secret_key)

    def _get_headers(self) -> dict:
        return {
            "x-client-id": self.app_id,
            "x-client-secret": self.secret_key,
            "x-api-version": self.api_version,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def create_order(self, amount_paise, currency="INR", donor_details=None, notes=None, return_url=None):
        if not self.is_configured():
            raise RuntimeError("Cashfree credentials (CASHFREE_APP_ID, CASHFREE_SECRET_KEY) are not configured.")

        donor = donor_details or {}
        order_amount = round(amount_paise / 100.0, 2)
        
        timestamp_part = int(datetime.now(timezone.utc).timestamp())
        random_part = secrets.token_hex(4).upper()
        order_id = f"CF_{timestamp_part}_{random_part}"

        cust_id = str(donor.get("user_id") or secrets.token_hex(6))
        clean_cust_id = "".join(c for c in cust_id if c.isalnum() or c in "_-")[:40] or f"cust_{timestamp_part}"
        clean_phone = "".join(filter(str.isdigit, str(donor.get("phone") or "")))[-10:]
        if len(clean_phone) != 10:
            clean_phone = "9876543210"

        clean_name = (donor.get("name") or "Donor").strip()[:60]
        clean_email = (donor.get("email") or "donor@think4u.org").strip()

        order_meta = {}
        if return_url:
            separator = "&" if "?" in return_url else "?"
            formatted_return_url = f"{return_url}{separator}order_id={{order_id}}&gateway=cashfree"
            if formatted_return_url.startswith("http://"):
                if "127.0.0.1" in formatted_return_url or "localhost" in formatted_return_url:
                    formatted_return_url = "https://think4u.org/payment-success?order_id={order_id}&gateway=cashfree"
                else:
                    formatted_return_url = "https://" + formatted_return_url[len("http://"):]
            order_meta["return_url"] = formatted_return_url

        order_note = ""
        if notes and isinstance(notes, dict):
            order_note = notes.get("purpose") or notes.get("donation_ref") or ""
        order_note = (order_note or "Think.4U Charity Donation")[:80]

        payload = {
            "order_id": order_id,
            "order_amount": order_amount,
            "order_currency": currency or "INR",
            "customer_details": {
                "customer_id": clean_cust_id,
                "customer_email": clean_email,
                "customer_phone": clean_phone,
                "customer_name": clean_name
            },
            "order_meta": order_meta,
            "order_note": order_note
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    f"{self.base_url}/orders",
                    headers=self._get_headers(),
                    json=payload
                )
            
            if resp.status_code not in (200, 201):
                logger.error(f"Cashfree order creation error [{resp.status_code}]: {resp.text}")
                raise RuntimeError(f"Cashfree order creation failed ({resp.status_code}): {resp.text}")

            res_json = resp.json()
            payment_session_id = res_json.get("payment_session_id", "")

            return {
                "gateway": self.gateway_id,
                "gateway_name": self.gateway_name,
                "order_id": res_json.get("order_id", order_id),
                "payment_session_id": payment_session_id,
                "amount": amount_paise,
                "amount_rupees": order_amount,
                "currency": res_json.get("order_currency", "INR"),
                "checkout_mode": "cashfree_drop",
                "cashfree_mode": self.sdk_mode,
                "raw_response": res_json
            }
        except httpx.RequestError as exc:
            logger.error(f"Cashfree network request error: {exc}")
            raise RuntimeError(f"Unable to reach Cashfree gateway: {exc}")

    def verify_payment(self, payload):
        if not self.is_configured():
            return {"verified": False, "error": "Cashfree is not configured."}

        order_id = payload.get("order_id") or payload.get("cf_order_id")
        if not order_id:
            return {"verified": False, "error": "Missing order ID for Cashfree verification."}

        try:
            with httpx.Client(timeout=15.0) as client:
                order_resp = client.get(
                    f"{self.base_url}/orders/{order_id}",
                    headers=self._get_headers()
                )

            if order_resp.status_code != 200:
                return {"verified": False, "error": f"Failed to retrieve Cashfree order status: {order_resp.status_code}"}

            order_data = order_resp.json()
            order_status = (order_data.get("order_status") or "").upper()
            order_amount = float(order_data.get("order_amount", 0.0))
            amount_paise = int(round(order_amount * 100))

            if order_status == "PAID":
                payment_id = ""
                pay_method = "Cashfree"
                try:
                    with httpx.Client(timeout=10.0) as client:
                        pay_resp = client.get(
                            f"{self.base_url}/orders/{order_id}/payments",
                            headers=self._get_headers()
                        )
                    if pay_resp.status_code == 200:
                        payments_list = pay_resp.json()
                        for p in payments_list:
                            if p.get("payment_status") == "SUCCESS":
                                payment_id = str(p.get("cf_payment_id") or "")
                                pay_method = p.get("payment_group") or "Cashfree"
                                break
                except Exception as ex:
                    logger.warning(f"Could not fetch Cashfree payments detail for {order_id}: {ex}")

                return {
                    "verified": True,
                    "status": "PAID",
                    "order_id": order_id,
                    "payment_id": payment_id or f"cf_{order_id}",
                    "amount_paise": amount_paise,
                    "payment_method": f"Cashfree ({pay_method})",
                    "raw_response": order_data,
                    "error": None
                }
            else:
                return {
                    "verified": False,
                    "status": order_status or "FAILED",
                    "order_id": order_id,
                    "payment_id": "",
                    "amount_paise": amount_paise,
                    "payment_method": "Cashfree",
                    "raw_response": order_data,
                    "error": f"Order status is {order_status}"
                }
        except Exception as e:
            logger.error(f"Cashfree verification exception: {e}")
            return {"verified": False, "error": str(e)}

    def verify_webhook(self, headers, raw_body):
        signature = headers.get("x-webhook-signature") or headers.get("X-Webhook-Signature")
        timestamp = headers.get("x-webhook-timestamp") or headers.get("X-Webhook-Timestamp")

        if not self.secret_key:
            return {"verified": False, "error": "CASHFREE_SECRET_KEY not set"}
        if not signature or not timestamp:
            return {"verified": False, "error": "Missing signature or timestamp headers"}

        try:
            data_to_sign = timestamp.encode("utf-8") + raw_body
            computed = base64.b64encode(
                hmac.new(self.secret_key.encode("utf-8"), data_to_sign, hashlib.sha256).digest()
            ).decode("utf-8")

            if not hmac.compare_digest(computed, signature):
                return {"verified": False, "error": "Invalid webhook signature"}

            import json
            data = json.loads(raw_body.decode("utf-8"))
            order_data = data.get("data", {}).get("order", {})
            payment_data = data.get("data", {}).get("payment", {})
            event_type = data.get("type", "")

            order_id = order_data.get("order_id", "")
            payment_id = str(payment_data.get("cf_payment_id", ""))
            payment_status = (payment_data.get("payment_status") or "").upper()

            is_paid = payment_status == "SUCCESS" or event_type == "PAYMENT_SUCCESS_WEBHOOK"
            return {
                "verified": True,
                "order_id": order_id,
                "payment_id": payment_id,
                "status": "PAID" if is_paid else "FAILED",
                "event_type": event_type,
                "raw_data": data,
                "error": None
            }
        except Exception as e:
            return {"verified": False, "error": str(e)}
