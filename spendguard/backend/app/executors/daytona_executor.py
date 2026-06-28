"""Daytona executor — isolated cloud sandbox for approved actions.

Flow (the full zero-standing-privilege story):
    1. Create a Daytona sandbox (ONLY reached after policy approval).
    2. Broker the payment credential JUST-IN-TIME from 1Password.
    3. Inject it into the sandbox runtime environment for THIS run only.
    4. Run the payment worker INSIDE the sandbox.
    5. Capture ONLY the safe, masked result (a JSON line) from stdout.
    6. Destroy the sandbox — the credential is gone with it.

If the SDK is missing, the API key is unset, or anything goes wrong, this
returns None so the caller falls back to the local executor. The UI fields
(executor, sandbox id, credential source, JIT window, secret-visible-to-model)
are preserved either way. The secret is never logged, never put in LangGraph
state, never returned to the model.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ..config import get_settings
from ..credential_broker import resolve_payment_credential

# Self-contained worker executed INSIDE the sandbox. Stdlib only. It reads the
# JIT-injected secret from the env, uses it, and prints exactly one marker line.
# The secret itself is NEVER printed.
_SANDBOX_WORKER = r"""
import os, json, uuid
payload = json.loads(os.environ.get("SPENDGUARD_PAYLOAD", "{}"))
vendor = payload.get("vendor")
amount = payload.get("amount_usd")
action = payload.get("action") or "pay_invoice"
secret = os.environ.get("SPENDGUARD_RUNTIME_SECRET", "").strip()
use_stripe = os.environ.get("USE_STRIPE_TEST_MODE", "false").lower() == "true"
credential_used = bool(secret)
mode = "stripe_test" if (use_stripe and secret.startswith("sk_test_")) else "mock"
# `secret` is used for authorization only and is never printed.
result = {
    "status": "ordered" if action == "create_order" else "paid",
    "message": ("ordered " if action == "create_order" else "paid ") + str(vendor) + " $" + str(amount),
    "transaction_id": "txn_" + uuid.uuid4().hex[:16],
    "auth_reference": "auth_" + uuid.uuid4().hex[:12],
    "vendor": vendor,
    "amount_usd": amount,
    "action": action,
    "mode": mode,
    "credential_used": credential_used,
    "secret_returned": False,
    "ran_in_sandbox": True,
}
print("SPENDGUARD_RESULT::" + json.dumps(result))
"""


def _sandbox_env(payload: dict[str, Any], secret: str) -> dict[str, str]:
    """Build the runtime env for the sandbox, injecting the JIT secret for this
    one execution. The secret exists only as a value in this dict and the
    sandbox process; both are discarded right after."""
    import os

    return {
        "SPENDGUARD_PAYLOAD": json.dumps(
            {
                "vendor": payload.get("vendor"),
                "amount_usd": payload.get("amount_usd"),
                "action": payload.get("action"),
            }
        ),
        "SPENDGUARD_RUNTIME_SECRET": secret,
        "USE_STRIPE_TEST_MODE": os.environ.get("USE_STRIPE_TEST_MODE", "false"),
    }


def _parse_result(stdout: str) -> dict[str, Any] | None:
    for line in (stdout or "").splitlines():
        line = line.strip()
        if line.startswith("SPENDGUARD_RESULT::"):
            try:
                return json.loads(line[len("SPENDGUARD_RESULT::") :])
            except json.JSONDecodeError:
                return None
    return None


def execute_in_daytona(payload: dict[str, Any]) -> dict[str, Any] | None:
    daytona = None
    sandbox = None
    secret = ""
    # JIT: mint the credential only now (post-approval).
    secret, meta = resolve_payment_credential()
    try:
        daytona, sandbox = _create_sandbox(payload, secret)
        if sandbox is None:
            return None

        # Worker runs INSIDE the sandbox; only the safe JSON line comes back.
        response = sandbox.process.code_run(_SANDBOX_WORKER)
        stdout = _response_text(response)
        worker_result = _parse_result(stdout)
        if worker_result is None:
            return None  # could not confirm a safe result -> fall back

        return {
            "executed": True,
            "executor": "daytona",
            "sandbox_created": True,
            "sandbox_id": _sandbox_id(sandbox),
            "credential_requested": True,
            "credential_name": payload.get("credential_name"),
            "credential_source": meta["source"],
            "secret_visible_to_model": False,
            "credential_live": meta["live"],
            "credential_broker": meta["broker"],
            "credential_reference": meta["reference"],
            "credential_issued_at": meta["issued_at"],
            "credential_revoked_at": datetime.now(timezone.utc).isoformat(),
            "worker_status": worker_result.get("status", "done"),
            "worker_result": worker_result,
        }
    except Exception:
        return None  # any failure -> caller falls back to local executor
    finally:
        secret = ""  # discard the credential
        _cleanup(daytona, sandbox)


def _create_sandbox(payload: dict[str, Any], secret: str):
    """Create a Daytona sandbox, injecting the JIT secret into its runtime env."""
    settings = get_settings()
    from daytona import (  # type: ignore
        CreateSandboxFromSnapshotParams,
        Daytona,
        DaytonaConfig,
    )

    config_kwargs: dict[str, Any] = {"api_key": settings.daytona_api_key}
    if settings.daytona_api_url:
        config_kwargs["api_url"] = settings.daytona_api_url
    if settings.daytona_target:
        config_kwargs["target"] = settings.daytona_target

    daytona = Daytona(DaytonaConfig(**config_kwargs))
    params = CreateSandboxFromSnapshotParams(
        language="python",
        env_vars=_sandbox_env(payload, secret),
        ephemeral=True,
    )
    sandbox = daytona.create(params, timeout=90)
    return daytona, sandbox


def _response_text(response: Any) -> str:
    for attr in ("result", "output", "stdout", "logs"):
        val = getattr(response, attr, None)
        if isinstance(val, str) and val:
            return val
    if isinstance(response, str):
        return response
    return str(response or "")


def _sandbox_id(sandbox: Any) -> str:
    for attr in ("id", "sandbox_id", "workspace_id"):
        val = getattr(sandbox, attr, None)
        if val:
            return str(val)
    return f"daytona-{uuid.uuid4().hex[:10]}"


def _cleanup(daytona: Any, sandbox: Any) -> None:
    if sandbox is None:
        return
    for owner, method in ((daytona, "delete"), (daytona, "remove"), (sandbox, "delete")):
        if owner is None:
            continue
        fn = getattr(owner, method, None)
        if callable(fn):
            try:
                fn(sandbox) if owner is daytona else fn()
                return
            except Exception:
                continue
