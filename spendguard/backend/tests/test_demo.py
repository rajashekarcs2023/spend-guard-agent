"""SpendGuard demo acceptance tests.

Covers exactly the required scenarios:
    * valid SnackHub allowed (req_001)
    * valid EventSuppliesCo allowed (req_002)
    * malicious request blocked (req_003)
    * blocked request does not execute
    * no secret leakage in responses / audit logs
"""

from __future__ import annotations

import json

from .conftest import CANARY_SECRET


def _run(client, request_id: str) -> dict:
    resp = client.post("/agent/run", json={"request_id": request_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


# --------------------------------------------------------------------------- #
# Allowed requests
# --------------------------------------------------------------------------- #
def test_snackhub_allowed_and_executes(client):
    data = _run(client, "req_001")
    assert data["decision"] == "allowed"
    assert data["intent"]["vendor"] == "SnackHub"
    assert data["intent"]["amount_usd"] == 42
    assert data["intent"]["action"] == "pay_invoice"

    ex = data["execution"]
    assert ex["executed"] is True
    assert ex["sandbox_created"] is True
    assert ex["sandbox_id"]
    assert ex["credential_requested"] is True
    assert ex["secret_visible_to_model"] is False
    assert ex["worker_result"]["secret_returned"] is False
    assert ex["worker_result"]["credential_used"] is True


def test_eventsupplies_allowed_and_executes(client):
    data = _run(client, "req_002")
    assert data["decision"] == "allowed"
    assert data["intent"]["vendor"] == "EventSuppliesCo"
    assert data["intent"]["amount_usd"] == 76
    assert data["intent"]["action"] == "create_order"
    assert data["execution"]["executed"] is True
    assert data["execution"]["worker_result"]["status"] == "ordered"


# --------------------------------------------------------------------------- #
# Credential broker (1Password runtime brokering)
# --------------------------------------------------------------------------- #
def test_allowed_request_brokers_jit_credential(client):
    ex = _run(client, "req_001")["execution"]
    # Credential was issued just-in-time (post-approval) and then revoked.
    assert ex["credential_requested"] is True
    assert ex["credential_issued_at"]
    assert ex["credential_revoked_at"]
    assert ex["credential_revoked_at"] >= ex["credential_issued_at"]
    # No token in the test env -> honest mock fallback, never claims "live".
    assert ex["credential_live"] is False
    assert ex["credential_broker"] == "local-mock"
    assert ex["secret_visible_to_model"] is False


def test_blocked_request_brokers_nothing(client):
    ex = _run(client, "req_003")["execution"]
    assert ex["credential_requested"] is False
    assert ex["credential_issued_at"] is None
    assert ex["credential_revoked_at"] is None
    assert ex["credential_live"] is False


def test_authority_view_reports_credential_provenance(client):
    a = _run(client, "req_001")["authority"]
    assert a["credential_name"] == "STRIPE_SECRET_KEY"
    assert a["secret_visible_to_model"] is False
    assert a["credential_live"] is False  # mock in tests, reported honestly
    assert a["credential_issued_at"]


# --------------------------------------------------------------------------- #
# Malicious request
# --------------------------------------------------------------------------- #
def test_malicious_blocked_with_reasons(client):
    data = _run(client, "req_003")
    assert data["decision"] == "blocked"

    reasons = " | ".join(data["reasons"]).lower()
    # At least four blocking reasons (CLAUDE.md requires >= 4).
    assert len(data["reasons"]) >= 4, data["reasons"]
    assert "prompt injection" in reasons
    assert "secret exfiltration" in reasons
    assert "credential forwarding" in reasons
    assert "unknown vendor" in reasons
    assert "budget" in reasons

    flags = {f["flag"] for f in data["risk_flags"]}
    assert "prompt_injection" in flags
    assert "secret_exfiltration_request" in flags
    assert "credential_forwarding_request" in flags


def test_blocked_request_does_not_execute(client):
    data = _run(client, "req_003")
    ex = data["execution"]
    assert ex["executed"] is False
    assert ex["sandbox_created"] is False  # no Daytona sandbox
    assert ex["sandbox_id"] is None
    assert ex["credential_requested"] is False  # no credential requested
    assert ex["worker_result"] is None  # worker never ran
    assert ex["worker_status"] == "blocked"


# --------------------------------------------------------------------------- #
# Secret leakage
# --------------------------------------------------------------------------- #
def test_no_secret_leak_in_responses(client):
    for rid in ("req_001", "req_002", "req_003"):
        data = _run(client, rid)
        assert CANARY_SECRET not in json.dumps(data)


def test_no_secret_leak_in_audit(client, audit_file):
    for rid in ("req_001", "req_002", "req_003"):
        _run(client, rid)

    audit_resp = client.get("/audit")
    assert audit_resp.status_code == 200
    assert CANARY_SECRET not in json.dumps(audit_resp.json())

    # And not on disk either.
    with open(audit_file, "r", encoding="utf-8") as f:
        raw = f.read()
    assert CANARY_SECRET not in raw

    # Audit invariants: never stores a secret, marks it not visible.
    for entry in audit_resp.json():
        assert entry["secret_visible_to_model"] is False
        assert "secret" not in {k.lower() for k in entry if k.endswith("_value")}


# --------------------------------------------------------------------------- #
# Audit updates after every run
# --------------------------------------------------------------------------- #
def test_audit_updates_after_each_run(client):
    assert client.get("/audit").json() == []
    _run(client, "req_001")
    assert len(client.get("/audit").json()) == 1
    _run(client, "req_002")
    assert len(client.get("/audit").json()) == 2
    _run(client, "req_003")
    assert len(client.get("/audit").json()) == 3

    # Reset clears it.
    client.post("/audit/reset")
    assert client.get("/audit").json() == []


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
def test_health(client):
    data = client.get("/health").json()
    assert data["status"] == "ok"


def test_requests_listed(client):
    data = client.get("/requests").json()
    ids = {r["id"] for r in data}
    assert ids == {"req_001", "req_002", "req_003"}


def test_demo_reset(client):
    _run(client, "req_001")
    resp = client.post("/demo/reset")
    assert resp.status_code == 200
    assert client.get("/audit").json() == []
