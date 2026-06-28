"""Deterministic policy engine — the SpendGuard gateway.

This is the authority. It is pure, deterministic Python. The LLM cannot reach
it, cannot influence it, and cannot override it. It evaluates the extracted
intent and the deterministically-detected risk flags against the policy.

Decision rules (in order; any single failing check blocks the request):
    1. Any detected risk flag listed in policy.blocked_risk_flags  -> block
    2. Vendor not in policy.approved_vendors                       -> block
    3. Amount over policy.budget_limit_usd                         -> block
    4. Action not in policy.allowed_actions                        -> block
    otherwise                                                      -> allowed
"""

from __future__ import annotations

from .models import Intent, Policy, PolicyDecision, RiskFlag


def evaluate_policy(
    intent: Intent,
    risk_flags: list[RiskFlag],
    policy: Policy,
) -> PolicyDecision:
    reasons: list[str] = []
    blocked = False
    detected = [f.flag for f in risk_flags]

    # 1. Hard-blocking risk flags (prompt injection, secret exfiltration, ...)
    for flag in risk_flags:
        if flag.flag in policy.blocked_risk_flags:
            reasons.append(flag.reason)
            blocked = True

    # 2. Vendor must be on the approved list.
    approved = {v.strip().lower() for v in policy.approved_vendors}
    vendor_known = bool(intent.vendor) and intent.vendor.strip().lower() in approved
    if not vendor_known:
        reasons.append(f"unknown vendor ({intent.vendor or 'unrecognized'})")
        blocked = True

    # 3. Amount must be within budget.
    if intent.amount_usd is not None and intent.amount_usd > policy.budget_limit_usd:
        reasons.append(
            f"amount ${intent.amount_usd:.0f} exceeds "
            f"${policy.budget_limit_usd:.0f} budget"
        )
        blocked = True

    # 4. Action must be allowed.
    if intent.action and intent.action not in policy.allowed_actions:
        reasons.append(f"action '{intent.action}' is not a permitted action")
        blocked = True

    if blocked:
        return PolicyDecision(decision="blocked", reasons=reasons, risk_flags=detected)

    # Allowed — record the affirmative reasons so the UI/audit can show why.
    allowed_reasons = [
        f"vendor '{intent.vendor}' is on the approved list",
        f"amount ${intent.amount_usd:.0f} is within the ${policy.budget_limit_usd:.0f} budget"
        if intent.amount_usd is not None
        else "amount is within budget",
        f"action '{intent.action}' is permitted",
        "no blocking risk flags detected",
    ]
    return PolicyDecision(decision="allowed", reasons=allowed_reasons, risk_flags=[])
