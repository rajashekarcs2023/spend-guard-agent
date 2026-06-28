"""Payment / order worker.

Contract:
    * receives a SAFE transaction payload (vendor, amount, action) — no secrets
    * receives the payment credential that the broker minted JUST-IN-TIME
    * executes a mock payment (or a Stripe *test-mode* charge if configured)
    * returns ONLY a safe, masked result

SECURITY INVARIANT: this worker NEVER prints, logs, or returns the secret value,
nor any reversible derivative of it. The most it ever reports is
`credential_used: true`.

The credential is passed in by the executor (which got it from the 1Password
runtime broker). The worker uses it for authorization and lets it go out of
scope. This module is dependency-light so the same logic also runs inside a
Daytona sandbox (see executors/daytona_executor.py).
"""

from __future__ import annotations

import os
import uuid
from typing import Any


def run_payment(payload: dict[str, Any], *, secret: str) -> dict[str, Any]:
    """Execute the transaction described by `payload` using the runtime
    `secret`, and return a safe result. `secret` is never returned."""
    vendor = payload.get("vendor")
    amount = payload.get("amount_usd")
    action = payload.get("action") or "pay_invoice"

    credential_used = bool(secret)
    use_stripe = os.environ.get("USE_STRIPE_TEST_MODE", "false").lower() == "true"

    if use_stripe and secret.startswith("sk_test_"):
        result = _try_stripe_test(secret, vendor, amount, action)
        if result is not None:
            return result
        # Fall back to mock if the Stripe call could not be made.

    # `secret` is intentionally not referenced again after authorization.
    return _mock_result(vendor, amount, action, credential_used)


def _mock_result(
    vendor: Any, amount: Any, action: Any, credential_used: bool
) -> dict[str, Any]:
    verb = "ordered" if action == "create_order" else "paid"
    return {
        "status": "ordered" if action == "create_order" else "paid",
        "message": f"{verb} {vendor} ${amount}",
        "transaction_id": f"txn_{uuid.uuid4().hex[:16]}",
        # An opaque, NON-secret authorization reference (unrelated to the key).
        "auth_reference": f"auth_{uuid.uuid4().hex[:12]}",
        "vendor": vendor,
        "amount_usd": amount,
        "action": action,
        "mode": "mock",
        "credential_used": credential_used,
        "secret_returned": False,  # explicit, audited invariant
    }


def _try_stripe_test(
    secret: str, vendor: Any, amount: Any, action: Any
) -> dict[str, Any] | None:
    """Attempt a Stripe TEST-mode PaymentIntent. Returns None on any failure so
    the caller falls back to the mock path. The secret is never returned."""
    try:
        import stripe  # optional dependency
    except Exception:
        return None
    if not secret.startswith("sk_test_"):
        return None  # refuse anything that isn't an explicit test key
    try:
        stripe.api_key = secret
        intent = stripe.PaymentIntent.create(
            amount=int(round(float(amount) * 100)),
            currency="usd",
            description=f"SpendGuard {action} {vendor}",
            payment_method_types=["card"],
        )
        return {
            "status": "requires_payment_method",
            "message": f"created Stripe test PaymentIntent for {vendor} ${amount}",
            "transaction_id": intent.id,
            "auth_reference": f"auth_{uuid.uuid4().hex[:12]}",
            "vendor": vendor,
            "amount_usd": amount,
            "action": action,
            "mode": "stripe_test",
            "credential_used": True,
            "secret_returned": False,
        }
    except Exception:
        return None
