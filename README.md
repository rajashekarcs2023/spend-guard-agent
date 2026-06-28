# SpendGuard

**Let agents spend without holding the keys.**

SpendGuard is a delegated spending runtime for AI agents. It lets an AI agent
pay approved vendors within a fixed budget using runtime-scoped credentials,
while preventing secret leakage, over-budget payments, unknown-vendor payments,
and prompt-injection-driven misuse.

> Our agent can pay a $42 approved invoice, but it **cannot see the Stripe key**,
> **cannot exceed its $100 budget**, **cannot pay unknown vendors**, and
> **cannot obey malicious instructions from an email**.

---

## Why

Agents are starting to do real work — including payments and procurement. If you
put a Stripe key or company-card credential in an env file, tool config, prompt,
or model context, one malicious email can become a real financial incident.

SpendGuard gives the agent **delegated authority** instead of **custody of the
credential**. The model proposes an action; a deterministic policy gateway
decides; an isolated worker executes using a credential the model never sees.

---

## Architecture

```
Inbox request (seeded)
  → FastAPI backend
  → LangGraph workflow (orchestration only)
     → intent extraction        (LLM optional; deterministic is authoritative)
     → deterministic risk detection   (runs on RAW text — injection can't disable it)
     → deterministic policy engine     (the authority; LLM cannot override it)
     → if allowed:  Daytona sandbox
                      → 1Password broker mints the payment key JUST-IN-TIME
                      → payment/order worker uses it inside the sandbox
                      → credential discarded, sandbox destroyed → safe result
        if blocked: NO sandbox, NO credential brokered, NO worker
  → JSON audit log (attributes every action; never stores the secret)
  → three-panel dashboard (request / trace / authority+audit)
```

This is the build-day thesis made concrete: the agent receives **delegated
authority**, the payment credential is **issued at runtime and gone when the
task ends** (zero standing privilege), and every action is **attributable**.

**The LLM may** extract intent and describe decisions.
**The LLM never** sees secrets, calls Stripe/Daytona directly, or overrides policy.

### Sponsors

- **1Password** — runtime credential **broker**. A Service Account (the trusted
  issuer) mints the Stripe key **just-in-time** on an approved transaction via
  the 1Password SDK (`op://vault/item/field`); it's used inside the sandbox and
  discarded. The model, trace, frontend, and audit log never see it. (`op run`
  is also supported as an alternative — see below.)
- **Daytona** — isolated cloud sandbox. A sandbox is created *only after* policy
  approval; the worker runs *inside* it and returns only a safe, masked result;
  the sandbox is then destroyed.

---

## Repository layout

```
spendguard/
  backend/
    app/
      main.py            FastAPI app + endpoints
      config.py          settings / env loading (+ macOS TLS fix)
      models.py          Pydantic models (no field can hold a secret)
      policy_loader.py   loads policy.json + seed_requests.json
      risk_detector.py   deterministic prompt-injection / exfiltration detection
      policy_engine.py   deterministic allow/block decision (the gateway)
      intent_extractor.py deterministic parser (+ optional LLM description)
      credential_broker.py 1Password runtime broker — JIT credential issuance
      audit_store.py     append-only JSON audit log
      graph.py           LangGraph workflow wiring it all together
      executors/
        local_executor.py    always-available mock sandbox
        daytona_executor.py  real Daytona cloud sandbox (falls back to local)
      workers/
        payment_worker.py    uses the brokered secret; never prints/returns it
    config/policy.json   the delegated authority
    data/seed_requests.json   the 3 demo requests
    tests/test_demo.py   acceptance tests
    requirements.txt          core deps
    requirements-daytona.txt  optional Daytona SDK
    op.env.example            1Password runtime references
    run-dev.sh / run-with-op.sh
  frontend/              Next.js + TypeScript + Tailwind dashboard
  docs/                  PRODUCT_SPEC.md, DEMO_SCRIPT.md
```

---

## Setup & run

### 1. Backend

```bash
cd spendguard/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# optional — enables the real Daytona cloud sandbox:
pip install -r requirements-daytona.txt
# optional — enables the real 1Password runtime credential broker:
pip install -r requirements-1password.txt
```

Create `spendguard/backend/.env` (or place `.env` at the repo root — both are
detected). Use `backend/.env.example` as a template:

```ini
LLM_PROVIDER=openai
USE_LLM_EXTRACTION=true
OPENAI_API_KEY=sk-...            # optional — deterministic fallback if absent

USE_DAYTONA=true
USE_LOCAL_EXECUTOR_FALLBACK=true
DAYTONA_API_KEY=dtn_...          # optional — local fallback if absent
DAYTONA_API_URL=https://app.daytona.io/api

USE_STRIPE_TEST_MODE=false
STRIPE_SECRET_KEY=               # leave empty to use the mock secret
MOCK_PAYMENT_SECRET=demo_mock_secret

# 1Password runtime broker — the rubric integration.
OP_SERVICE_ACCOUNT_TOKEN=        # ops_... ; empty = honest mock fallback
OP_PAYMENT_CREDENTIAL_REFERENCE=op://SpendGuard/Stripe/secret_key
```

Run it:

```bash
./run-dev.sh          # http://localhost:8000  (credentials from .env)
```

### 2. Frontend

```bash
cd spendguard/frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                         # http://localhost:3000
```

Open **http://localhost:3000**.

> **macOS note:** the python.org build can throw `CERTIFICATE_VERIFY_FAILED` on
> outbound HTTPS. SpendGuard auto-points TLS at `certifi`'s CA bundle on startup,
> so Daytona/OpenAI calls work without any manual step.

---

## 1Password runtime credentials

The whole point: the secret is **issued at runtime, scoped to one approved task,
and the model never sees it.** Two supported paths — the SDK broker is primary
because it gives true *just-in-time, per-transaction* issuance.

### Primary — Service Account broker (just-in-time)

1. Create a 1Password vault `SpendGuard` with an item `Stripe` that has a field
   `secret_key` (your `sk_test_…`, or any value for a pure demo).
2. Create a **Service Account** with read access to that vault — either in the
   web app (Developer → Service Accounts) or via CLI:
   ```bash
   op service-account create "SpendGuard" --expires-in 24h --vault "SpendGuard:read_items"
   ```
   Copy the `ops_…` token (shown once).
3. Put it in `.env`:
   ```ini
   OP_SERVICE_ACCOUNT_TOKEN=ops_...
   OP_PAYMENT_CREDENTIAL_REFERENCE=op://SpendGuard/Stripe/secret_key
   ```
4. `pip install -r requirements-1password.txt` and run normally.

On every **approved** transaction, `credential_broker.py` authenticates as the
Service Account (the trusted issuer) and calls `client.secrets.resolve("op://…")`
to mint the payment key **just-in-time**, hands it to the worker *inside the
Daytona sandbox*, then discards it. The UI shows the **issued → revoked** window
and a green **1Password: live runtime broker** badge. With no token, the broker
falls back to a mock and honestly reports `credential_live: false`.

### Alternative — `op run` (process-level injection)

```bash
cd spendguard/backend
cp op.env.example op.env       # edit the op:// references
op signin
./run-with-op.sh               # op run --env-file=op.env -- uvicorn app.main:app ...
```

`op run` resolves the references into the uvicorn process environment for its
lifetime (mounted via a UNIX pipe, never written to disk, untrackable by Git).

---

## How this answers the build-day question

> *When your agent acts, is it acting as itself or as you? Where does its
> authority come from, and who answers for what it does?*

| Principle (from the brief) | How SpendGuard implements it |
| --- | --- |
| **Minimize standing access** (just-enough + just-in-time) | The payment key is never standing — it's brokered per transaction from 1Password and discarded. Authority is scoped to approved vendor + budget + action. |
| **Authority proven at runtime, not stored** | A 1Password Service Account (trusted issuer) mints the credential at the moment of use; the secret never sits in `.env`, prompt, or model context. |
| **Delegated authority + accountability** | The agent carries its own identity (`spendguard-agent-001`) and acts under authority a human delegated (`delegated_by`). The audit log binds every action to the agent, the delegator, the decision, and the JIT credential window. |
| **Containment of prompt injection** | The deterministic gateway sits between the agent and any action. Even a fully manipulated agent cannot exceed budget, pay an unknown vendor, or extract the key — the malicious request is blocked before a sandbox or credential exists. |

---

## API

| Method | Path           | Purpose                                  |
| ------ | -------------- | ---------------------------------------- |
| GET    | `/health`      | service + config status                  |
| GET    | `/requests`    | the seeded demo requests                 |
| POST   | `/agent/run`   | run the workflow for `{request_id}`      |
| GET    | `/audit`       | the audit log (newest first)             |
| POST   | `/audit/reset` | clear the audit log                      |
| POST   | `/demo/reset`  | clear audit + reload policy/seed caches  |

---

## Security invariants (enforced + tested)

1. The model never sees the payment secret.
2. The frontend never sees the payment secret.
3. The audit log never stores the payment secret.
4. Blocked requests do not create Daytona sandboxes.
5. Blocked requests do not request credentials.
6. Blocked requests do not execute workers.
7. The LLM cannot override policy (policy engine is pure, deterministic Python).
8. The LLM cannot call payment directly.
9. The LLM cannot call Daytona directly.
10. Every decision is auditable.
11. The malicious request is blocked every time.
12. The payment credential is issued just-in-time and is never standing.
13. The 1Password Service Account token (broker identity) never enters model
    context, trace, frontend, or audit.

Run the acceptance tests:

```bash
cd spendguard/backend
.venv/bin/python -m pytest        # 10 passed
```

Covers: SnackHub allowed, EventSuppliesCo allowed, malicious blocked, blocked
request does not execute, and no secret leakage in responses or the audit log.
