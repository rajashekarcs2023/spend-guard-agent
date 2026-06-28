"""Execution backends for approved transactions.

`run_execution` is the single entry point. It tries Daytona first (isolated
cloud sandbox) and falls back to the local mock executor. Either way, the secret
never enters LangGraph state, the API response, or the audit log.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from .daytona_executor import execute_in_daytona
from .local_executor import execute_local


def run_execution(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute an APPROVED transaction. Must only be called after policy approval.

    `payload` is the safe transaction payload (vendor, amount_usd, action,
    credential_name, credential_source). It contains no secret.
    """
    settings = get_settings()

    if settings.use_daytona and settings.daytona_api_key:
        result = execute_in_daytona(payload)
        if result is not None:
            return result
        # Daytona unavailable/failed -> fall back if allowed.
        if not settings.use_local_executor_fallback:
            return {
                "executed": False,
                "executor": "daytona",
                "sandbox_created": False,
                "sandbox_id": None,
                "credential_requested": False,
                "credential_name": payload.get("credential_name"),
                "credential_source": payload.get("credential_source"),
                "secret_visible_to_model": False,
                "worker_status": "executor_unavailable",
                "worker_result": None,
            }

    return execute_local(payload)
