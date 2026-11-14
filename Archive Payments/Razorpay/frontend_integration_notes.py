"""
ARCHIVED: Razorpay-specific Frontend Integration
Extracted from: templates/donate.html
Archive Date: 2024-11-14

The donate.html template contained Razorpay Modal Checkout JS SDK integration.

Key Frontend Integration Points:
  - Razorpay SDK loaded from: https://checkout.razorpay.com/v1/checkout.js
  - Checkout mode: "razorpay_modal" (uses new Razorpay(options).open())
  - Uses key_id (public key) and order_id from /create-order response

JavaScript Flow (from donate.html):
  1. User submits donation form
  2. POST /create-order returns {checkout_mode: "razorpay_modal", key_id, order_id, ...}
  3. If checkout_mode == "razorpay_modal":
     - const rzp = new Razorpay({key: order.key_id, order_id: order.order_id, ...})
     - rzp.open()
  4. On success callback: POST /payment-success with razorpay_order_id, razorpay_payment_id, razorpay_signature
  5. Server verifies via RazorpayGateway.verify_payment() (HMAC-SHA256 signature check)

Template Variables (passed from donate() route):
  - razor_key: public key ID (RAZOR_KEY_ID env var)
  - active_gateway: "razorpay"
  - active_gateway_name: "Razorpay"
  - is_payment_enabled: bool
"""
