# Archive Payments

## Purpose
This folder preserves the complete Think.4U payment gateway implementation (Cashfree, Razorpay, UPI) for future reuse. The payment functionality has been temporarily disabled in the active application while donation services are under maintenance.

**Archive Date:** 2024-11-14  
**Archived By:** Payment Archival Process  
**Status:** INACTIVE — These files are not imported or executed by the active application.

---

## Folder Structure

```
Archive Payments/
├── README.md                          ← This file
├── Cashfree/
│   ├── cashfree_gateway.py            ← Full CashfreeGateway class implementation
│   ├── donate.html                    ← Original donation template (Cashfree checkout JS)
│   └── frontend_integration_notes.py  ← Cashfree Drop SDK integration documentation
├── Razorpay/
│   ├── razorpay_gateway.py            ← Full RazorpayGateway class implementation
│   ├── donate.html                    ← Original donation template (Razorpay modal JS)
│   └── frontend_integration_notes.py  ← Razorpay Checkout SDK integration documentation
├── UPI/
│   ├── upi_payment_routes.py          ← UPI donation routes (/donate-upi, /upi-qr)
│   └── donate_upi.html               ← Original UPI donation template
├── Shared Payment Gateway/
│   ├── payment_gateways.py            ← Complete gateway module (BasePaymentGateway, Manager, Factory)
│   └── payment_routes_archived.py     ← All payment route handlers from app.py
└── Documentation/
    └── environment_variables.md       ← All required environment variables
```

---

## Original Architecture

### Gateway Pattern
The payment system used an **Adapter/Provider pattern** via `BasePaymentGateway` (abstract base class):

```
BasePaymentGateway (ABC)
├── CashfreeGateway  → Cashfree Payment Gateway API v2023-08-01
└── RazorpayGateway  → Razorpay Orders API v1
```

A `PaymentGatewayManager` singleton managed gateway registration, selection, and fallback. The active gateway was determined by the `PAYMENT_GATEWAY` environment variable (default: `cashfree`).

### Route Flow
1. **Donor visits** `/donate` → sees donation form with gateway checkout
2. **Anonymous donors** verify identity via OTP (`/donation/start`, `/donation/verify`)
3. **Order creation** → `POST /create-order` → calls `gateway.create_order()`
4. **Checkout** → Cashfree Drop SDK or Razorpay Modal opens in browser
5. **Payment verification** → `GET/POST /payment-success` → calls `gateway.verify_payment()`
6. **Webhook backup** → `POST /payment-webhook` → calls `gateway.verify_webhook()`
7. **Receipt** → donation record updated, PDF receipt generated + emailed

### UPI Flow (Separate)
1. **Donor visits** `/donate-upi` → sees UPI VPA + QR code
2. **Donor pays** externally via UPI app
3. **Donor submits** transaction reference → `POST /donate-upi/verify`
4. **Admin verifies** manually from admin dashboard

---

## Environment Variables Required

### Cashfree
| Variable | Description |
|---|---|
| `CASHFREE_APP_ID` (or `CASHFREE_CLIENT_ID`) | Cashfree Application ID |
| `CASHFREE_SECRET_KEY` (or `CASHFREE_CLIENT_SECRET`) | Cashfree Secret Key |
| `CASHFREE_API_VERSION` | API version (default: `2023-08-01`) |
| `CASHFREE_ENV` | `TEST` or `PROD` (auto-detected if not set) |

### Razorpay
| Variable | Description |
|---|---|
| `RAZOR_KEY_ID` | Razorpay Key ID (public) |
| `RAZOR_KEY_SECRET` | Razorpay Key Secret |
| `RAZORPAY_WEBHOOK_SECRET` | Webhook verification secret |

### UPI
| Variable | Description |
|---|---|
| `UPI_VPA` | UPI Virtual Payment Address (e.g., `name@upi`) |

### General
| Variable | Description |
|---|---|
| `PAYMENT_GATEWAY` | Active gateway: `cashfree` or `razorpay` (default: `cashfree`) |
| `PAYMENT_PENDING_TIMEOUT_MINUTES` | Timeout for pending payments (default: 15) |

> **⚠️ IMPORTANT:** No live credentials or secrets are stored in this archive. Only environment variable names and configuration documentation are preserved.

---

## Dependencies on Active Application (Shared, NOT archived)

These functions/modules remain in the active `app.py` because they serve non-payment features:

| Function | Why Retained |
|---|---|
| `normalize_donation_purpose()` | Used by donation history display |
| `donation_context_from_args()` | Used by donation context resolution |
| `make_donation_ref()` | Used by donation record creation |
| `get_or_create_public_donor()` | Used by donor account management |
| `apply_paid_donation_effects()` | Used by admin donation status updates |
| `send_donation_receipt_email_if_needed()` | Used by existing receipts |
| `create_notification_for_user()` | Used across entire application |
| `generate_receipt_pdf()` | Used by existing receipt downloads |
| `generate_qr()` | Used by receipts |
| `send_otp_email()` / `set_pending_otp()` | Used by signup, login, profile update |

---

## Restoration Process

To restore payment functionality:

### Step 1: Restore `payment_gateways.py`
Copy `Shared Payment Gateway/payment_gateways.py` back to the project root (or verify the stub in the active app still provides the import interface).

### Step 2: Re-enable Imports in `app.py`
Uncomment or restore the import block at the top of `app.py`:
```python
from payment_gateways import (
    get_active_payment_gateway,
    payment_manager,
    CashfreeGateway,
    RazorpayGateway,
    BasePaymentGateway
)
```

### Step 3: Re-enable Gateway Configuration Block
Uncomment the gateway initialization section (~lines 414-460 in original app.py):
```python
RAZOR_KEY = os.getenv('RAZOR_KEY_ID')
RAZOR_SECRET = os.getenv('RAZOR_KEY_SECRET')
# ... etc.
```

### Step 4: Restore Payment Routes
Remove the maintenance redirects from the donation routes and restore the original route implementations. Reference `Shared Payment Gateway/payment_routes_archived.py` for the full route code.

### Step 5: Restore Frontend Templates
Copy `Cashfree/donate.html` or `Razorpay/donate.html` back to `templates/donate.html` and `UPI/donate_upi.html` back to `templates/donate_upi.html`.

### Step 6: Restore CSP Headers
Re-add payment gateway domains to the Content-Security-Policy header in the `after_request` handler.

### Step 7: Configure Environment Variables
Ensure all required environment variables listed above are set in the deployment environment.

### Step 8: Test
- Test order creation for each gateway
- Test payment verification flow
- Test webhook processing
- Test UPI QR generation
- Test receipt generation for new payments

---

## Files Previously in Active Application

| Original Location | Archived To |
|---|---|
| `payment_gateways.py` | `Shared Payment Gateway/payment_gateways.py` |
| `templates/donate.html` | `Cashfree/donate.html` + `Razorpay/donate.html` |
| `templates/donate_upi.html` | `UPI/donate_upi.html` |
| Payment routes in `app.py` | `Shared Payment Gateway/payment_routes_archived.py` |
| UPI routes in `app.py` | `UPI/upi_payment_routes.py` |

---

## Important Notes

1. **Database schema is unchanged.** The `donations` table and all records remain intact.
2. **Admin donation management continues to work.** Admins can still view, filter, export, and update donation statuses.
3. **Existing donation receipts continue to work.** The `/donation-receipt/<id>` and PDF download routes remain active.
4. **Donation history remains accessible.** Users can still view their past donations from the dashboard.
5. **Webhooks are preserved temporarily.** The `/payment-webhook` endpoint still processes callbacks for any pending transactions initiated before the archival.
