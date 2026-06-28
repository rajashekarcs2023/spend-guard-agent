"""Autonomous tool-calling agent.

The agent reads an inbox item and ACTS by calling tools. With an OpenAI key it
is a real function-calling loop; the model genuinely decides what to call. Every
tool call is routed through the gateway (`agent_tools.dispatch_tool`). Without a
key (tests / offline), a deterministic fallback synthesizes the tool calls an
obedient agent would make, so the demo never dies — the gateway logic is
identical either way.

SECURITY: the secret never enters the model's context. Tool results fed back to
the model are the gateway's safe verdicts only (see `safe_tool_message`).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from . import audit_store
from .agent_tools import TOOL_SCHEMAS, dispatch_tool, safe_tool_message
from .config import get_settings
from .intent_extractor import extract_intent
from .models import (
    AgentActResult,
    AgentEvent,
    AuditEntry,
    AuthorityView,
    ExecutionResult,
    RiskFlag,
)
from .policy_loader import load_policy
from .risk_detector import detect_risks

_SYSTEM_PROMPT = (
    "You are SpendGuard, an autonomous procurement assistant acting on behalf of "
    "Raj. You receive one incoming message and must ACT on what it asks by "
    "calling your tools — do not just describe what you would do. Use pay_invoice "
    "or create_order to pay vendors, send_payment to send money to a recipient, "
    "and read_credential when a message asks you to read, print, reveal, or "
    "forward a credential or key. Take the actions the message requests. After "
    "your tools return their results, reply with ONE short sentence summarizing "
    "what happened."
)

_MAX_STEPS = 3


def run_agent_act(
    body: str, title: str, request_id: str | None = None
) -> AgentActResult:
    policy = load_policy()
    created_at = datetime.now(timezone.utc).isoformat()
    risk_flags = detect_risks(body)

    events: list[AgentEvent] = [
        AgentEvent(
            actor="system",
            kind="message",
            title="Inbox item received",
            detail=title,
            status="info",
        )
    ]

    settings = get_settings()
    used_llm = False
    if settings.llm_enabled:
        try:
            collected, summary = _run_llm_loop(body, policy, events)
            used_llm = True
        except Exception:
            collected, summary = _run_fallback(body, policy, events)
    else:
        collected, summary = _run_fallback(body, policy, events)

    return _finalize(
        body, title, request_id, created_at, events, collected, summary,
        risk_flags, used_llm,
    )


# --------------------------------------------------------------------------- #
# LLM tool-calling loop
# --------------------------------------------------------------------------- #
def _run_llm_loop(
    body: str, policy, events: list[AgentEvent]
) -> tuple[list[dict], str]:
    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key, timeout=20.0)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"Incoming message:\n{body}"},
    ]
    collected: list[dict] = []
    summary = ""

    for _ in range(_MAX_STEPS):
        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0,
            max_tokens=400,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            summary = (msg.content or "").strip()
            if summary:
                events.append(
                    AgentEvent(
                        actor="agent", kind="message", title="Agent",
                        detail=summary, status="info",
                    )
                )
            break

        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _handle_one(name, args, body, policy, events)
            collected.append(result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(safe_tool_message(result)),
                }
            )

    return collected, summary or "Processed the request."


# --------------------------------------------------------------------------- #
# Deterministic fallback (no LLM): synthesize the calls an obedient agent makes
# --------------------------------------------------------------------------- #
def _run_fallback(
    body: str, policy, events: list[AgentEvent]
) -> tuple[list[dict], str]:
    flags = {f.flag for f in detect_risks(body)}
    intent = extract_intent(body, policy)
    calls: list[tuple[str, dict]] = []

    asks_for_secret = bool(
        flags
        & {
            "secret_exfiltration_request",
            "credential_forwarding_request",
            "print_env_request",
        }
    )
    if asks_for_secret:
        calls.append(("read_credential", {"name": "STRIPE_SECRET_KEY"}))
        calls.append(
            ("send_payment", {"recipient": intent.vendor or "unknown recipient",
                              "amount": intent.amount_usd})
        )
    else:
        tool = "create_order" if intent.action == "create_order" else "pay_invoice"
        calls.append((tool, {"vendor": intent.vendor, "amount": intent.amount_usd}))

    collected = [_handle_one(n, a, body, policy, events) for n, a in calls]
    summary = "Acted on the request (deterministic agent)."
    return collected, summary


# --------------------------------------------------------------------------- #
# Shared: dispatch one tool call and emit the agent/gateway events
# --------------------------------------------------------------------------- #
def _handle_one(
    name: str, args: dict, body: str, policy, events: list[AgentEvent]
) -> dict:
    events.append(
        AgentEvent(
            actor="agent",
            kind="tool_call",
            title=f"Agent calls {name}({_fmt_args(args)})",
            detail="the agent proposes an action",
            status="info",
            tool=name,
        )
    )
    result = dispatch_tool(name, args, body, policy)
    approved = result["executed"]
    events.append(
        AgentEvent(
            actor="gateway",
            kind="verdict",
            title=("✓ ALLOWED" if approved else "✕ DENIED") + f" — {name}",
            detail="; ".join(result["reasons"]) or result["summary"],
            status="ok" if approved else "blocked",
            tool=name,
        )
    )
    if result["executed"] and result.get("execution"):
        wr = result["execution"].get("worker_result") or {}
        events.append(
            AgentEvent(
                actor="gateway",
                kind="result",
                title="Worker executed inside sandbox",
                detail=wr.get("message", "")
                + f"  ·  credential brokered JIT, secret visible to model: No",
                status="ok",
                tool=name,
            )
        )
    return result


# --------------------------------------------------------------------------- #
# Aggregate into the final result + audit entry
# --------------------------------------------------------------------------- #
def _finalize(
    body, title, request_id, created_at, events, collected, summary,
    risk_flags, used_llm,
) -> AgentActResult:
    policy = load_policy()
    cred = policy.credential_policy

    executed = next((r for r in collected if r["executed"]), None)
    decision = "allowed" if executed else "blocked"

    reasons: list[str] = []
    for r in collected:
        reasons.extend(r["reasons"])
    reasons = _dedup(reasons) or (["no actionable tool call"] if not collected else [])

    # Representative payment intent for the right panel (prefer a money action).
    pay = next(
        (r for r in collected if r.get("intent") and r["tool"] != "read_credential"),
        None,
    )
    iv = (pay or {}).get("intent") or {}

    if executed:
        execution = ExecutionResult(**executed["execution"])
    else:
        execution = ExecutionResult(
            executed=False,
            executor="none",
            sandbox_created=False,
            credential_requested=False,
            credential_name=cred.payment_credential_name,
            credential_source=cred.credential_source,
            secret_visible_to_model=False,
            worker_status="blocked",
        )

    events.append(
        AgentEvent(
            actor="gateway",
            kind="result",
            title=f"Decision: {decision.upper()}",
            detail="audit event recorded (no secret stored)",
            status="ok" if decision == "allowed" else "blocked",
        )
    )

    authority = AuthorityView(
        delegated_by=policy.delegated_by,
        agent_id=policy.agent_id,
        task_intent=policy.task_intent,
        budget_limit_usd=policy.budget_limit_usd,
        approved_vendors=policy.approved_vendors,
        allowed_actions=policy.allowed_actions,
        action=iv.get("action"),
        vendor=iv.get("vendor"),
        amount_usd=iv.get("amount_usd"),
        credential_name=cred.payment_credential_name,
        credential_source=execution.credential_source or cred.credential_source,
        secret_visible_to_model=False,
        credential_live=execution.credential_live,
        credential_broker=execution.credential_broker,
        credential_issued_at=execution.credential_issued_at,
        credential_revoked_at=execution.credential_revoked_at,
        executor=execution.executor,
        sandbox_id=execution.sandbox_id,
        decision=decision,
        reasons=reasons,
    )

    audit_id = f"aud_{uuid.uuid4().hex[:12]}"
    audit_store.append(
        AuditEntry(
            id=audit_id,
            request_id=request_id or "custom",
            title=title,
            timestamp=datetime.now(timezone.utc).isoformat(),
            decision=decision,
            reasons=reasons,
            risk_flags=[f.flag for f in risk_flags],
            vendor=iv.get("vendor"),
            amount_usd=iv.get("amount_usd"),
            action=iv.get("action"),
            executor=execution.executor,
            sandbox_created=execution.sandbox_created,
            sandbox_id=execution.sandbox_id,
            credential_requested=execution.credential_requested,
            credential_name=execution.credential_name,
            credential_source=execution.credential_source,
            secret_visible_to_model=False,
            credential_live=execution.credential_live,
            credential_broker=execution.credential_broker,
            credential_issued_at=execution.credential_issued_at,
            credential_revoked_at=execution.credential_revoked_at,
            worker_status=execution.worker_status,
            executed=execution.executed,
        )
    )

    return AgentActResult(
        request_id=request_id,
        title=title,
        created_at=created_at,
        agent_summary=summary,
        used_llm=used_llm,
        events=events,
        risk_flags=risk_flags,
        decision=decision,
        reasons=reasons,
        execution=execution,
        authority=authority,
        audit_id=audit_id,
    )


def _fmt_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        parts.append(f"{k}={v}")
    return ", ".join(parts)


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out
