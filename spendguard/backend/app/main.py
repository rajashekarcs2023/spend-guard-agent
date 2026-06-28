"""SpendGuard FastAPI application.

Endpoints:
    GET  /health
    GET  /requests
    POST /agent/run
    GET  /audit
    POST /audit/reset
    POST /demo/reset
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import audit_store
from .agent_runtime import run_agent_act
from .config import get_settings
from .graph import run_agent
from .models import (
    AgentActResult,
    AgentRunResponse,
    AuditEntry,
    RunAgentActRequest,
    RunAgentRequest,
    SeedRequest,
)
from .policy_loader import get_seed_request, load_policy, load_seed_requests

app = FastAPI(title="SpendGuard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo: any local frontend origin
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "spendguard",
        "llm_extraction": settings.llm_enabled,
        "daytona_configured": bool(settings.use_daytona and settings.daytona_api_key),
        "onepassword_live": settings.op_enabled,
        "credential_reference": settings.op_payment_credential_reference,
        "local_fallback": settings.use_local_executor_fallback,
    }


@app.get("/requests", response_model=list[SeedRequest])
def list_requests() -> list[SeedRequest]:
    return list(load_seed_requests())


@app.post("/agent/run", response_model=AgentRunResponse)
def agent_run(payload: RunAgentRequest) -> AgentRunResponse:
    request = get_seed_request(payload.request_id)
    if request is None:
        raise HTTPException(status_code=404, detail=f"unknown request_id: {payload.request_id}")
    return run_agent(request)


@app.post("/agent/act", response_model=AgentActResult)
def agent_act(payload: RunAgentActRequest) -> AgentActResult:
    """Autonomous tool-calling agent. Either runs a seeded request by id, or a
    custom body (the attack arena). The agent calls tools; the gateway decides."""
    if payload.request_id:
        seed = get_seed_request(payload.request_id)
        if seed is None:
            raise HTTPException(status_code=404, detail=f"unknown request_id: {payload.request_id}")
        return run_agent_act(seed.body, seed.title, request_id=seed.id)

    if not payload.body or not payload.body.strip():
        raise HTTPException(status_code=400, detail="provide a request_id or a non-empty body")
    title = payload.title or "Custom request (attack arena)"
    return run_agent_act(payload.body, title, request_id=None)


@app.get("/audit", response_model=list[AuditEntry])
def get_audit() -> list[AuditEntry]:
    # Newest first.
    return list(reversed(audit_store.all_entries()))


@app.post("/audit/reset")
def reset_audit() -> dict:
    audit_store.reset()
    return {"status": "ok", "message": "audit log cleared"}


@app.post("/demo/reset")
def reset_demo() -> dict:
    """Reset the demo: clear the audit log and reload policy/seed caches."""
    audit_store.reset()
    load_policy.cache_clear()
    load_seed_requests.cache_clear()
    return {
        "status": "ok",
        "message": "demo reset — audit cleared, requests reloaded",
        "requests": [r.id for r in load_seed_requests()],
    }
