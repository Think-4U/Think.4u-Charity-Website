"""
ARCHIVED: Cashfree-specific Frontend Integration
Extracted from: templates/donate.html
Archive Date: 2024-11-14

The donate.html template contained Cashfree Drop Checkout JS SDK integration.

Key Frontend Integration Points:
  - Cashfree SDK loaded from: https://sdk.cashfree.com/js/v3/cashfree.js
  - Checkout mode: "cashfree_drop" (uses Cashfree.load() + checkout.open())
  - Uses payment_session_id from /create-order response
  - Sandbox mode controlled by cashfree_mode template variable

JavaScript Flow (from donate.html):
  1. User submits donation form
  2. POST /create-order returns {checkout_mode: "cashfree_drop", payment_session_id, cashfree_mode, ...}
  3. If checkout_mode == "cashfree_drop":
     - const cashfree = await Cashfree.load({mode: order.cashfree_mode});
     - cashfree.checkout({paymentSessionId: order.payment_session_id, ...})
  4. On success: redirect to /payment-success?order_id=...&gateway=cashfree
  5. Server verifies via CashfreeGateway.verify_payment()

Template Variables (passed from donate() route):
  - cashfree_mode: "sandbox" or "production"
  - active_gateway: "cashfree"
  - active_gateway_name: "Cashfree"
  - is_payment_enabled: bool
"""
