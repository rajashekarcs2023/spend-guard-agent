"""Test configuration.

These env vars are set BEFORE any app module is imported so that the cached
Settings pick them up. They force a fully local, offline, deterministic run:
    * no LLM calls (deterministic extraction only)
    * no Daytona calls (local executor)
    * a recognizable mock secret + isolated audit log so we can prove the secret
      never leaks into responses or the audit file.
"""

from __future__ import annotations

import os
import tempfile

# The canary secret. If this string ever appears in a response, trace, or audit
# entry, the secret-leakage test fails.
CANARY_SECRET = "SUPER_SECRET_CANARY_VALUE_DO_NOT_LEAK"

_AUDIT_FILE = os.path.join(tempfile.mkdtemp(prefix="spendguard_test_"), "audit_log.json")

os.environ["USE_LLM_EXTRACTION"] = "false"
os.environ["OPENAI_API_KEY"] = ""
os.environ["USE_DAYTONA"] = "false"
os.environ["USE_LOCAL_EXECUTOR_FALLBACK"] = "true"
os.environ["USE_STRIPE_TEST_MODE"] = "false"
os.environ["STRIPE_SECRET_KEY"] = ""
os.environ["MOCK_PAYMENT_SECRET"] = CANARY_SECRET
# Keep tests hermetic: never hit live 1Password even if a token is in .env.
os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = ""
os.environ["AUDIT_LOG_PATH"] = _AUDIT_FILE

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import audit_store  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    audit_store.reset()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def audit_file() -> str:
    return _AUDIT_FILE
