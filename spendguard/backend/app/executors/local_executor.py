"""Local mock executor — the always-available fallback.

It stands in for the Daytona sandbox: an isolated, in-process execution of the
payment worker. The credential is brokered just-in-time, passed to the worker,
and discarded. This executor never returns the secret.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..credential_broker import resolve_payment_credential
from ..workers.payment_worker import run_payment


def execute_local(payload: dict[str, Any]) -> dict[str, Any]:
    sandbox_id = f"local-mock-{uuid.uuid4().hex[:10]}"

    # JIT: mint the credential only now (post-approval), use it, drop it.
    secret, meta = resolve_payment_credential()
    result = run_payment(payload, secret=secret)
    secret = ""  # discard
    revoked_at = datetime.now(timezone.utc).isoformat()

    return {
        "executed": True,
        "executor": "local-mock",
        "sandbox_created": True,
        "sandbox_id": sandbox_id,
        "credential_requested": True,
        "credential_name": payload.get("credential_name"),
        "credential_source": meta["source"],
        "secret_visible_to_model": False,
        "credential_live": meta["live"],
        "credential_broker": meta["broker"],
        "credential_reference": meta["reference"],
        "credential_issued_at": meta["issued_at"],
        "credential_revoked_at": revoked_at,
        "worker_status": result.get("status", "done"),
        "worker_result": result,
    }
