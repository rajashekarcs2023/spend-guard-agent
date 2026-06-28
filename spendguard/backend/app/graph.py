"""LangGraph workflow — the harness that wires the deterministic components.

LangGraph is ONLY an orchestrator here. The security-critical work (risk
detection, policy decision, execution) happens in pure Python nodes the LLM
cannot influence. No secret value ever enters this graph's state.

Flow:
    load_request -> extract_intent -> detect_risk -> evaluate_policy
        -> (allowed)  execute      -> write_audit -> END
        -> (blocked)  skip_execute -> write_audit -> END
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from . import audit_store
from .executors import run_execution
from .intent_extractor import extract_intent
from .models import (
    AgentRunResponse,
    AuditEntry,
    AuthorityView,
    ExecutionResult,
    Intent,
    PolicyDecision,
    RiskFlag,
    SeedRequest,
    TraceStep,
)
from .policy_engine import evaluate_policy
from .policy_loader import load_policy
from .risk_detector import detect_risks


class GraphState(TypedDict, total=False):
    request: dict
    intent: dict
    risk_flags: list[dict]
    decision: str
    reasons: list[str]
    trace: list[dict]
    execution: dict
    audit_id: str
    created_at: str


def _append(state: GraphState, **step: Any) -> list[dict]:
    return list(state.get("trace", [])) + [TraceStep(**step).model_dump()]


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
def _load_request(state: GraphState) -> GraphState:
    req = state["request"]
    return {
        "trace": _append(
            state,
            step="Request loaded",
            status="ok",
            detail=f"{req['title']} (from {req['from_address']}, "
            f"trusted_source={req['trusted_source']})",
        )
    }


def _extract_intent(state: GraphState) -> GraphState:
    policy = load_policy()
    intent = extract_intent(state["request"]["body"], policy)
    return {
        "intent": intent.model_dump(),
        "trace": _append(
            state,
            step="Intent extracted",
            status="ok",
            detail=f"{intent.description} "
            f"(via {intent.extraction_method} extraction)",
        ),
    }


def _detect_risk(state: GraphState) -> GraphState:
    flags = detect_risks(state["request"]["body"])
    if flags:
        detail = ", ".join(f.reason for f in flags)
        status = "blocked"
    else:
        detail = "no risk flags detected"
        status = "ok"
    return {
        "risk_flags": [f.model_dump() for f in flags],
        "trace": _append(
            state, step="Risk flags detected", status=status, detail=detail
        ),
    }


def _evaluate_policy(state: GraphState) -> GraphState:
    policy = load_policy()
    intent = Intent(**state["intent"])
    risk_flags = [RiskFlag(**f) for f in state.get("risk_flags", [])]
    decision: PolicyDecision = evaluate_policy(intent, risk_flags, policy)
    return {
        "decision": decision.decision,
        "reasons": decision.reasons,
        "trace": _append(
            state,
            step="Policy evaluated",
            status="ok" if decision.decision == "allowed" else "blocked",
            detail=f"decision = {decision.decision.upper()} — "
            + "; ".join(decision.reasons),
        ),
    }


def _route(state: GraphState) -> str:
    return "execute" if state.get("decision") == "allowed" else "skip_execute"


def _execute(state: GraphState) -> GraphState:
    policy = load_policy()
    intent = state["intent"]
    cred = policy.credential_policy
    payload = {
        "vendor": intent.get("vendor"),
        "amount_usd": intent.get("amount_usd"),
        "action": intent.get("action"),
        "credential_name": cred.payment_credential_name,
        "credential_source": cred.credential_source,
    }
    # Sandbox is created ONLY here, after policy approval.
    result = run_execution(payload)
    execution = ExecutionResult(**result).model_dump()

    trace = state.get("trace", [])
    sandbox_label = (
        f"{execution['executor']} sandbox {execution['sandbox_id']}"
        if execution["sandbox_created"]
        else "no sandbox"
    )
    fallback_note = (
        " (Daytona unavailable — local fallback)"
        if execution["executor"] == "local-mock"
        else ""
    )
    trace = trace + [
        TraceStep(
            step="Daytona sandbox created",
            status="ok" if execution["sandbox_created"] else "skipped",
            detail=sandbox_label + fallback_note,
        ).model_dump(),
        TraceStep(
            step="Credential brokered (just-in-time)",
            status="ok" if execution["credential_requested"] else "skipped",
            detail=_credential_detail(execution),
        ).model_dump(),
        TraceStep(
            step="Worker executed",
            status="ok" if execution["executed"] else "blocked",
            detail=_worker_detail(execution),
        ).model_dump(),
    ]
    return {"execution": execution, "trace": trace}


def _skip_execute(state: GraphState) -> GraphState:
    policy = load_policy()
    cred = policy.credential_policy
    execution = ExecutionResult(
        executed=False,
        executor="none",
        sandbox_created=False,
        sandbox_id=None,
        credential_requested=False,
        credential_name=cred.payment_credential_name,
        credential_source=cred.credential_source,
        secret_visible_to_model=False,
        worker_status="blocked",
        worker_result=None,
    ).model_dump()

    trace = state.get("trace", []) + [
        TraceStep(
            step="Daytona sandbox created",
            status="skipped",
            detail="No — blocked before execution, no sandbox created",
        ).model_dump(),
        TraceStep(
            step="Credential brokered (just-in-time)",
            status="skipped",
            detail="No — no credential requested or issued for a blocked request",
        ).model_dump(),
        TraceStep(
            step="Worker executed",
            status="blocked",
            detail="No — payment worker not executed",
        ).model_dump(),
    ]
    return {"execution": execution, "trace": trace}


def _write_audit(state: GraphState) -> GraphState:
    intent = state.get("intent", {})
    execution = state.get("execution", {})
    audit_id = f"aud_{uuid.uuid4().hex[:12]}"
    entry = AuditEntry(
        id=audit_id,
        request_id=state["request"]["id"],
        title=state["request"]["title"],
        timestamp=datetime.now(timezone.utc).isoformat(),
        decision=state["decision"],  # type: ignore[arg-type]
        reasons=state.get("reasons", []),
        risk_flags=[f["flag"] for f in state.get("risk_flags", [])],
        vendor=intent.get("vendor"),
        amount_usd=intent.get("amount_usd"),
        action=intent.get("action"),
        executor=execution.get("executor", "none"),
        sandbox_created=execution.get("sandbox_created", False),
        sandbox_id=execution.get("sandbox_id"),
        credential_requested=execution.get("credential_requested", False),
        credential_name=execution.get("credential_name"),
        credential_source=execution.get("credential_source"),
        secret_visible_to_model=False,
        credential_live=execution.get("credential_live", False),
        credential_broker=execution.get("credential_broker"),
        credential_issued_at=execution.get("credential_issued_at"),
        credential_revoked_at=execution.get("credential_revoked_at"),
        worker_status=execution.get("worker_status", "not_executed"),
        executed=execution.get("executed", False),
    )
    audit_store.append(entry)
    return {
        "audit_id": audit_id,
        "trace": _append(
            state,
            step="Audit written",
            status="ok",
            detail=f"audit event {audit_id} recorded (no secret stored)",
        ),
    }


def _worker_detail(execution: dict) -> str:
    result = execution.get("worker_result") or {}
    msg = result.get("message", "")
    mode = result.get("mode", "")
    return f"{execution.get('worker_status', 'done')}: {msg} [{mode}]".strip()


def _credential_detail(execution: dict) -> str:
    name = execution.get("credential_name")
    source = execution.get("credential_source")
    broker = execution.get("credential_broker")
    live = execution.get("credential_live")
    tag = "1Password live" if live else "mock fallback"
    return (
        f"{name} issued JIT via {source} ({broker}, {tag}) — "
        "secret visible to model: No"
    )


# --------------------------------------------------------------------------- #
# Graph assembly
# --------------------------------------------------------------------------- #
def build_graph():
    g = StateGraph(GraphState)
    g.add_node("load_request", _load_request)
    g.add_node("extract_intent", _extract_intent)
    g.add_node("detect_risk", _detect_risk)
    g.add_node("evaluate_policy", _evaluate_policy)
    g.add_node("execute", _execute)
    g.add_node("skip_execute", _skip_execute)
    g.add_node("write_audit", _write_audit)

    g.set_entry_point("load_request")
    g.add_edge("load_request", "extract_intent")
    g.add_edge("extract_intent", "detect_risk")
    g.add_edge("detect_risk", "evaluate_policy")
    g.add_conditional_edges(
        "evaluate_policy",
        _route,
        {"execute": "execute", "skip_execute": "skip_execute"},
    )
    g.add_edge("execute", "write_audit")
    g.add_edge("skip_execute", "write_audit")
    g.add_edge("write_audit", END)
    return g.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def run_agent(request: SeedRequest) -> AgentRunResponse:
    created_at = datetime.now(timezone.utc).isoformat()
    final: GraphState = _graph().invoke(
        {"request": request.model_dump(), "trace": [], "created_at": created_at}
    )

    policy = load_policy()
    intent = Intent(**final["intent"])
    execution = ExecutionResult(**final["execution"])
    risk_flags = [RiskFlag(**f) for f in final.get("risk_flags", [])]
    cred = policy.credential_policy

    authority = AuthorityView(
        delegated_by=policy.delegated_by,
        agent_id=policy.agent_id,
        task_intent=policy.task_intent,
        budget_limit_usd=policy.budget_limit_usd,
        approved_vendors=policy.approved_vendors,
        allowed_actions=policy.allowed_actions,
        action=intent.action,
        vendor=intent.vendor,
        amount_usd=intent.amount_usd,
        credential_name=cred.payment_credential_name,
        credential_source=execution.credential_source or cred.credential_source,
        secret_visible_to_model=False,
        credential_live=execution.credential_live,
        credential_broker=execution.credential_broker,
        credential_issued_at=execution.credential_issued_at,
        credential_revoked_at=execution.credential_revoked_at,
        executor=execution.executor,
        sandbox_id=execution.sandbox_id,
        decision=final["decision"],  # type: ignore[arg-type]
        reasons=final.get("reasons", []),
    )

    return AgentRunResponse(
        request_id=request.id,
        title=request.title,
        created_at=created_at,
        intent=intent,
        risk_flags=risk_flags,
        decision=final["decision"],  # type: ignore[arg-type]
        reasons=final.get("reasons", []),
        trace=[TraceStep(**t) for t in final.get("trace", [])],
        execution=execution,
        authority=authority,
        audit_id=final["audit_id"],
    )
