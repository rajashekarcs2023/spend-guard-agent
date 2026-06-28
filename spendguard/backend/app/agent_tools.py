"""The agent's tools — and the gateway that adjudicates every call.

This is the heart of the "autonomous agent, contained authority" story. The LLM
genuinely calls these tools. None of them performs a sensitive action directly:
each call is routed through `dispatch_tool`, which runs the SAME deterministic
gateway (risk detection on the RAW request + policy engine), and only then
brokers a credential and executes. The agent proposes; the gateway disposes.

`read_credential` is always refused — proving the model cannot obtain the secret
even when a prompt-injected email tells it to.
"""

from __future__ import annotations

from typing import Any

from .executors import run_execution
from .models import Intent, Policy
from .policy_engine import evaluate_policy
from .risk_detector import detect_risks

# OpenAI tool schemas. An obedient instruction-following persona means a
# malicious email will actually drive the agent to call read_credential /
# send_payment — and the gateway will refuse them, live.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "pay_invoice",
            "description": "Pay an invoice to a vendor.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {"type": "string", "description": "vendor name"},
                    "amount": {"type": "number", "description": "amount in USD"},
                },
                "required": ["vendor", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": "Create and pay for an order from a vendor.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vendor": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["vendor", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_payment",
            "description": "Send a payment to an arbitrary recipient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["recipient", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_credential",
            "description": "Read a stored credential/secret by name (e.g. an API key).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
]

_ACTION_BY_TOOL = {
    "pay_invoice": "pay_invoice",
    "create_order": "create_order",
    "send_payment": "send_payment",
}


def _to_amount(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def dispatch_tool(
    name: str, args: dict[str, Any], request_body: str, policy: Policy
) -> dict[str, Any]:
    """Adjudicate and (if allowed) execute one tool call.

    Returns a SAFE result dict (never contains a secret) with keys:
        tool, approved, executed, reasons, execution, intent, summary,
        denied_secret_access.
    """
    risk_flags = detect_risks(request_body)  # always on the RAW, untrusted text

    # read_credential is categorically refused — the model never sees a secret.
    if name == "read_credential":
        reasons = ["SpendGuard never exposes credentials to the agent — the model cannot read secrets"]
        reasons += [f.reason for f in risk_flags]
        return {
            "tool": name,
            "approved": False,
            "executed": False,
            "reasons": _dedup(reasons),
            "execution": None,
            "intent": None,
            "denied_secret_access": True,
            "summary": "DENIED: credential access is never granted to the agent",
        }

    vendor = args.get("vendor") or args.get("recipient") or args.get("to")
    amount = _to_amount(args.get("amount") if args.get("amount") is not None else args.get("amount_usd"))
    action = _ACTION_BY_TOOL.get(name, "pay_invoice")
    intent = Intent(vendor=vendor, amount_usd=amount, action=action)

    decision = evaluate_policy(intent, risk_flags, policy)
    intent_view = {"vendor": vendor, "amount_usd": amount, "action": action}

    if decision.decision == "allowed":
        cred = policy.credential_policy
        payload = {
            "vendor": vendor,
            "amount_usd": amount,
            "action": action,
            "credential_name": cred.payment_credential_name,
            "credential_source": cred.credential_source,
        }
        execution = run_execution(payload)  # brokers credential JIT, runs in sandbox
        return {
            "tool": name,
            "approved": True,
            "executed": bool(execution.get("executed")),
            "reasons": decision.reasons,
            "execution": execution,
            "intent": intent_view,
            "denied_secret_access": False,
            "summary": f"APPROVED & executed: {action} {vendor} ${amount}",
        }

    return {
        "tool": name,
        "approved": False,
        "executed": False,
        "reasons": decision.reasons,
        "execution": None,
        "intent": intent_view,
        "denied_secret_access": False,
        "summary": f"DENIED: {action} {vendor} ${amount} — " + "; ".join(decision.reasons),
    }


def safe_tool_message(result: dict[str, Any]) -> dict[str, Any]:
    """The message handed BACK to the LLM. Contains no secret — only the verdict
    so the model can react (and, hopefully, stop trying to exfiltrate)."""
    return {
        "status": "approved" if result["executed"] else "denied",
        "reasons": result["reasons"],
        "message": result["summary"],
    }


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out
