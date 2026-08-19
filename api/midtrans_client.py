import base64
import hashlib
import os

import httpx

MIDTRANS_SERVER_KEY = os.getenv("MIDTRANS_SERVER_KEY", "")
MIDTRANS_IS_PRODUCTION = os.getenv("MIDTRANS_IS_PRODUCTION", "false").lower() == "true"

_BASE_URL = (
    "https://app.midtrans.com"
    if MIDTRANS_IS_PRODUCTION
    else "https://app.sandbox.midtrans.com"
)


def _auth_header() -> str:
    encoded = base64.b64encode(f"{MIDTRANS_SERVER_KEY}:".encode()).decode()
    return f"Basic {encoded}"


def create_snap_transaction(
    order_id: str,
    amount: int,
    first_name: str,
    phone: str,
    item_name: str,
) -> dict:
    """Create Midtrans Snap transaction. Returns {'token': ..., 'redirect_url': ...}."""
    payload = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": amount,
        },
        "customer_details": {
            "first_name": first_name,
            "phone": phone,
        },
        "item_details": [
            {
                "id": "subscription",
                "price": amount,
                "quantity": 1,
                "name": item_name,
            }
        ],
    }
    resp = httpx.post(
        f"{_BASE_URL}/snap/v1/transactions",
        json=payload,
        headers={
            "Authorization": _auth_header(),
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def verify_notification(notif: dict) -> bool:
    """Verify Midtrans webhook signature."""
    raw = (
        f"{notif.get('order_id', '')}"
        f"{notif.get('status_code', '')}"
        f"{notif.get('gross_amount', '')}"
        f"{MIDTRANS_SERVER_KEY}"
    )
    expected = hashlib.sha512(raw.encode()).hexdigest()
    return expected == notif.get("signature_key", "")


def is_payment_success(notif: dict) -> bool:
    """True when Midtrans confirms full settlement."""
    status = notif.get("transaction_status", "")
    fraud = notif.get("fraud_status", "accept")
    return status in ("settlement", "capture") and fraud == "accept"
