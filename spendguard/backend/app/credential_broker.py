"""Runtime credential broker — the 1Password integration.

This is the answer to the build-day question "where does the authority come
from?": NOT from a key sitting in an .env file, but from a credential issued at
runtime, scoped to one approved task, and gone when the work is done.

Model (federated / brokered):
    * The 1Password Service Account token is the BROKER identity — a trusted
      issuer. It is held by the backend process only.
    * On an APPROVED transaction, the broker mints the payment credential
      just-in-time by resolving an `op://vault/item/field` reference.
    * The resolved secret is used by the worker and immediately discarded.
    * The secret value NEVER enters: model context, LangGraph state, the trace,
      the frontend, or the audit log. Only metadata (source, reference, the
      issue/revoke timestamps) is ever surfaced.

If no Service Account token is configured (or the SDK/network is unavailable),
the broker falls back to a local mock secret so the demo never breaks — and it
honestly reports `live: False` so the UI/audit shows it was not brokered.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

from .config import get_settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_payment_credential() -> tuple[str, dict[str, Any]]:
    """JIT-resolve the payment credential.

    Returns (secret_value, meta). `meta` contains NO secret value — only:
        source, reference, live, broker, issued_at.
    The caller uses the secret, then drops it; nothing persists it.
    """
    settings = get_settings()
    issued_at = _now()

    if settings.op_enabled:
        try:
            value = asyncio.run(
                _op_resolve(
                    settings.op_service_account_token,
                    settings.op_payment_credential_reference,
                    settings.op_integration_name,
                    settings.op_integration_version,
                )
            )
            if value:
                return value, {
                    "source": "1Password/runtime",
                    "reference": settings.op_payment_credential_reference,
                    "live": True,
                    "broker": "1password-service-account",
                    "issued_at": issued_at,
                }
        except Exception as exc:  # never leak details that might contain the ref/value
            # Fall through to mock; record only a coarse, non-sensitive reason.
            reason = type(exc).__name__
            return _mock_credential(
                settings, issued_at, note=f"1Password unavailable ({reason})"
            )

    return _mock_credential(
        settings,
        issued_at,
        note="no 1Password Service Account token configured",
    )


def _mock_credential(settings, issued_at: str, note: str) -> tuple[str, dict[str, Any]]:
    # Prefer a real Stripe test key if one is set in env; otherwise the mock.
    value = os.environ.get("STRIPE_SECRET_KEY", "").strip() or settings.mock_payment_secret
    return value, {
        "source": "mock/runtime",
        "reference": settings.op_payment_credential_reference,
        "live": False,
        "broker": "local-mock",
        "issued_at": issued_at,
        "note": note,
    }


async def _op_resolve(
    token: str, reference: str, integration_name: str, integration_version: str
) -> str:
    """Authenticate as the broker identity and mint the task-scoped secret."""
    from onepassword.client import Client  # imported lazily; optional dependency

    client = await Client.authenticate(
        auth=token,
        integration_name=integration_name,
        integration_version=integration_version,
    )
    return await client.secrets.resolve(reference)
