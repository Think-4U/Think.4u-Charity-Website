# Payment Gateway Environment Variables

## Overview
This document lists all environment variables required by the payment gateway integrations.
No live credentials or secrets are stored in this archive.

---

## Cashfree Payment Gateway

| Variable | Required | Default | Description |
|---|---|---|---|
| `CASHFREE_APP_ID` | Yes | — | Cashfree Application/Client ID |
| `CASHFREE_CLIENT_ID` | Alt | — | Alternative name for CASHFREE_APP_ID |
| `CASHFREE_SECRET_KEY` | Yes | — | Cashfree Secret Key |
| `CASHFREE_CLIENT_SECRET` | Alt | — | Alternative name for CASHFREE_SECRET_KEY |
| `CASHFREE_API_VERSION` | No | `2023-08-01` | Cashfree API version string |
| `CASHFREE_ENV` | No | Auto-detected | `TEST` (sandbox) or `PROD` (production) |

### Cashfree API Endpoints
- **Sandbox:** `https://sandbox.cashfree.com/pg`
- **Production:** `https://api.cashfree.com/pg`

### Cashfree Frontend SDK
- URL: `https://sdk.cashfree.com/js/v3/cashfree.js`

---

## Razorpay Payment Gateway

| Variable | Required | Default | Description |
|---|---|---|---|
| `RAZOR_KEY_ID` | Yes | — | Razorpay Key ID (public, safe for frontend) |
| `RAZOR_KEY_SECRET` | Yes | — | Razorpay Key Secret (server-side only) |
| `RAZORPAY_WEBHOOK_SECRET` | For webhooks | — | Webhook signature verification secret |

### Razorpay API Endpoint
- `https://api.razorpay.com/v1/orders`

### Razorpay Frontend SDK
- URL: `https://checkout.razorpay.com/v1/checkout.js`

---

## UPI Direct Payment

| Variable | Required | Default | Description |
|---|---|---|---|
| `UPI_VPA` | Yes | — | UPI Virtual Payment Address (e.g., `name@upi`) |

---

## General Payment Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `PAYMENT_GATEWAY` | No | `cashfree` | Active gateway selector: `cashfree` or `razorpay` |
| `PAYMENT_PENDING_TIMEOUT_MINUTES` | No | `15` | Minutes before a pending payment is considered stale |

---

## Content Security Policy Domains (were required)

These domains were included in the CSP headers when payment gateways were active:

```
script-src: https://*.razorpay.com https://sdk.cashfree.com https://*.cashfree.com
connect-src: https://*.razorpay.com https://api.cashfree.com https://sandbox.cashfree.com https://*.cashfree.com
frame-src: https://*.razorpay.com https://*.cashfree.com
form-action: https://*.cashfree.com https://*.razorpay.com
```

---

## Log Redaction
The application redacted these sensitive values from log output:
- `RAZOR_KEY_SECRET`
- `RAZORPAY_WEBHOOK_SECRET`
