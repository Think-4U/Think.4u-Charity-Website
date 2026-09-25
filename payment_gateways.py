"""
Think.4U Common Payment Gateway Architecture
Supports interchangeable payment providers (Cashfree, Razorpay, etc.)
using a clean Adapter/Provider pattern.
"""
import os
import base64
import hashlib
import hmac
import logging
import secrets
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import httpx

logger = logging.getLogger("think4u.payments")


class BasePaymentGateway(ABC):
    """Abstract base class for all payment gateways."""

    gateway_id: str = "base"
    gateway_name: str = "Base Gateway"

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if required API credentials are present."""
        pass

    @abstractmethod
    def create_order(
        self,
        amount_paise: int,
        currency: str,
        donor_details: dict,
        notes: dict = None,
        return_url: str = None
    ) -> dict:
        """
        Create a payment order at the gateway.
        Returns a dictionary with standardized keys:
        {
            "gateway": str,
            "order_id": str,
            "amount": int (paise),
            "amount_rupees": float,
            "currency": str,
            "payment_session_id": str (if applicable),
            "key_id": str (if applicable),
            "checkout_mode": "cashfree_drop" | "razorpay_modal" | "redirect",
            "cashfree_mode": "sandbox" | "production",
            "raw_response": dict
        }
        """
        pass

    @abstractmethod
    def verify_payment(self, payload: dict) -> dict:
        """
        Verify payment return/callback.
        Returns:
        {
            "verified": bool,
            "status": "PAID" | "FAILED" | "PENDING",
            "order_id": str,
            "payment_id": str,
            "amount_paise": int,
            "payment_method": str,
            "raw_response": dict,
            "error": str or None
        }
        """
        pass

    @abstractmethod
    def verify_webhook(self, headers: dict, raw_body: bytes) -> dict:
        """
        Verify incoming webhook signature and parse event data.
        Returns:
        {
            "verified": bool,
            "order_id": str,
            "payment_id": str,
            "status": "PAID" | "FAILED",
            "event_type": str,
            "raw_data": dict,
            "error": str or None
        }
        """
        pass


class CashfreeGateway(BasePaymentGateway):
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

    def create_order(
        self,
        amount_paise: int,
        currency: str = "INR",
        donor_details: dict = None,
        notes: dict = None,
        return_url: str = None
    ) -> dict:
        if not self.is_configured():
            raise RuntimeError("Cashfree credentials (CASHFREE_APP_ID, CASHFREE_SECRET_KEY) are not configured.")

        donor = donor_details or {}
        order_amount = round(amount_paise / 100.0, 2)
        
        # Cashfree requires alphanumeric order_id (max 45 chars)
        timestamp_part = int(datetime.now(timezone.utc).timestamp())
        random_part = secrets.token_hex(4).upper()
        order_id = f"CF_{timestamp_part}_{random_part}"

        # Clean customer details
        cust_id = str(donor.get("user_id") or secrets.token_hex(6))
        clean_cust_id = "".join(c for c in cust_id if c.isalnum() or c in "_-")[:40] or f"cust_{timestamp_part}"
        clean_phone = "".join(filter(str.isdigit, str(donor.get("phone") or "")))[-10:]
        if len(clean_phone) != 10:
            clean_phone = "9876543210"

        clean_name = (donor.get("name") or "Donor").strip()[:60]
        clean_email = (donor.get("email") or "donor@think4u.org").strip()

        # Build order meta
        order_meta = {}
        if return_url:
            separator = "&" if "?" in return_url else "?"
            # Cashfree replaces {order_id} placeholder in return_url
            order_meta["return_url"] = f"{return_url}{separator}order_id={{order_id}}&gateway=cashfree"

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

    def verify_payment(self, payload: dict) -> dict:
        """
        Verify Cashfree payment by querying the Cashfree Orders and Payments API.
        """
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
                logger.error(f"Failed to fetch Cashfree order {order_id}: {order_resp.text}")
                return {"verified": False, "error": f"Failed to retrieve Cashfree order status: {order_resp.status_code}"}

            order_data = order_resp.json()
            order_status = (order_data.get("order_status") or "").upper()
            order_amount = float(order_data.get("order_amount", 0.0))
            amount_paise = int(round(order_amount * 100))

            if order_status == "PAID":
                # Fetch payment details to obtain cf_payment_id and method
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

    def verify_webhook(self, headers: dict, raw_body: bytes) -> dict:
        """
        Verify Cashfree Webhook signature using HMAC-SHA256.
        Docs: https://docs.cashfree.com/docs/pg-webhook-verification
        """
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


class RazorpayGateway(BasePaymentGateway):
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

    def create_order(
        self,
        amount_paise: int,
        currency: str = "INR",
        donor_details: dict = None,
        notes: dict = None,
        return_url: str = None
    ) -> dict:
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

    def verify_payment(self, payload: dict) -> dict:
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

    def verify_webhook(self, headers: dict, raw_body: bytes) -> dict:
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


# ==============================================================================
# Payment Gateway Manager & Factory
# ==============================================================================
class PaymentGatewayManager:
    """
    Central manager for payment gateways. Allows dynamically swapping,
    registering, and selecting payment gateways.
    """

    def __init__(self):
        self._gateways = {}
        self.register(CashfreeGateway())
        self.register(RazorpayGateway())

    def register(self, gateway: BasePaymentGateway):
        """Register a new payment gateway provider instance."""
        self._gateways[gateway.gateway_id.lower()] = gateway

    def get_gateway(self, gateway_id: str = None) -> BasePaymentGateway:
        """
        Get gateway by id. If None, resolves the active gateway based on
        PAYMENT_GATEWAY env var (default: 'cashfree'). Falls back gracefully if
        the preferred gateway is not configured.
        """
        preferred = (gateway_id or os.getenv("PAYMENT_GATEWAY") or "cashfree").strip().lower()
        gw = self._gateways.get(preferred)

        # If explicitly requested or configured, return it
        if gw and (gateway_id or gw.is_configured()):
            return gw

        # If preferred is not configured, fall back to any configured gateway
        for candidate_id, candidate in self._gateways.items():
            if candidate.is_configured():
                logger.info(f"Preferred gateway '{preferred}' not configured; falling back to '{candidate_id}'")
                return candidate

        # Return default gateway even if not yet configured
        return self._gateways.get("cashfree") or list(self._gateways.values())[0]

    def list_gateways(self) -> dict:
        """List all registered gateways and their configuration status."""
        return {
            gid: {
                "name": gw.gateway_name,
                "configured": gw.is_configured()
            }
            for gid, gw in self._gateways.items()
        }


# Global singleton instance
payment_manager = PaymentGatewayManager()


def get_active_payment_gateway(gateway_id: str = None) -> BasePaymentGateway:
    """Convenience getter for the active payment gateway."""
    return payment_manager.get_gateway(gateway_id)
