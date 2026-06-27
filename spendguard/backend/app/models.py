"""Pydantic models for SpendGuard.

SECURITY INVARIANT: none of these models contain a secret value. Credentials
are referenced by *name* and *source* only (e.g. "STRIPE_SECRET_KEY",
"1Password/runtime"). `secret_visible_to_model` is hard-coded False.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Decision = Literal["allowed", "blocked", "needs_approval"]
TraceStatus = Literal["ok", "skipped", "blocked", "info"]


class SeedRequest(BaseModel):
    id: str
    title: str
    source: str
    from_address: str
    trusted_source: bool
    body: str
    expected_demo_result: str


class CredentialPolicy(BaseModel):
    payment_credential_name: str
    credential_source: str
    visible_to_model: bool = False
    visible_to_frontend: bool = False
    visible_to_audit_logs: bool = False


class RuntimePolicy(BaseModel):
    executor: str = "daytona"
    create_sandbox_only_after_policy_approval: bool = True
    destroy_sandbox_after_execution: bool = True


class Policy(BaseModel):
    delegated_by: str
    agent_id: str
    task_intent: str
    budget_limit_usd: float
    approved_vendors: list[str]
    allowed_actions: list[str]
    requires_approval: list[str] = Field(default_factory=list)
    blocked_risk_flags: list[str] = Field(default_factory=list)
    credential_policy: CredentialPolicy
    runtime_policy: RuntimePolicy


class Intent(BaseModel):
    """Extracted purchase intent. Used for *display*; the policy engine
    re-derives the authoritative amount/vendor/action deterministically."""

    vendor: Optional[str] = None
    amount_usd: Optional[float] = None
    action: Optional[str] = None
    description: str = ""
    extraction_method: Literal["deterministic", "llm"] = "deterministic"


class RiskFlag(BaseModel):
    flag: str
    reason: str
    evidence: str = ""


class PolicyDecision(BaseModel):
    decision: Decision
    reasons: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class TraceStep(BaseModel):
    step: str
    status: TraceStatus = "ok"
    detail: str = ""


class ExecutionResult(BaseModel):
    executed: bool = False
    executor: str = "none"
    sandbox_created: bool = False
    sandbox_id: Optional[str] = None
    credential_requested: bool = False
    credential_name: Optional[str] = None
    credential_source: Optional[str] = None
    secret_visible_to_model: bool = False  # always False — invariant
    # Runtime credential brokering (1Password) — JIT, zero standing privilege.
    credential_live: bool = False  # True = brokered from 1Password at runtime
    credential_broker: Optional[str] = None
    credential_reference: Optional[str] = None
    credential_issued_at: Optional[str] = None
    credential_revoked_at: Optional[str] = None
    worker_status: str = "not_executed"
    worker_result: Optional[dict[str, Any]] = None


class AuthorityView(BaseModel):
    """The right-panel "authority and audit" view. No secret values."""

    delegated_by: str
    agent_id: str
    task_intent: str
    budget_limit_usd: float
    approved_vendors: list[str]
    allowed_actions: list[str]
    action: Optional[str] = None
    vendor: Optional[str] = None
    amount_usd: Optional[float] = None
    credential_name: str
    credential_source: str
    secret_visible_to_model: bool = False  # always False — invariant
    credential_live: bool = False
    credential_broker: Optional[str] = None
    credential_issued_at: Optional[str] = None
    credential_revoked_at: Optional[str] = None
    executor: str
    sandbox_id: Optional[str] = None
    decision: Decision
    reasons: list[str] = Field(default_factory=list)


class AuditEntry(BaseModel):
    """One audit record. NEVER contains a secret value."""

    id: str
    request_id: str
    title: str
    timestamp: str
    decision: Decision
    reasons: list[str]
    risk_flags: list[str]
    vendor: Optional[str] = None
    amount_usd: Optional[float] = None
    action: Optional[str] = None
    executor: str
    sandbox_created: bool
    sandbox_id: Optional[str] = None
    credential_requested: bool
    credential_name: Optional[str] = None
    credential_source: Optional[str] = None
    secret_visible_to_model: bool = False  # always False — invariant
    credential_live: bool = False
    credential_broker: Optional[str] = None
    credential_issued_at: Optional[str] = None
    credential_revoked_at: Optional[str] = None
    worker_status: str
    executed: bool


class AgentRunResponse(BaseModel):
    request_id: str
    title: str
    created_at: str
    intent: Intent
    risk_flags: list[RiskFlag]
    decision: Decision
    reasons: list[str]
    trace: list[TraceStep]
    execution: ExecutionResult
    authority: AuthorityView
    audit_id: str


class RunAgentRequest(BaseModel):
    request_id: str
