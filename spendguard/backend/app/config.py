"""Configuration and environment loading for SpendGuard.

Secrets are read from the environment at runtime. They are NEVER stored in
LangGraph state, returned to the frontend, written to the audit log, or logged.

`op run` (1Password) compatibility: when the backend is launched via
`op run --env-file=op.env -- uvicorn ...`, 1Password resolves the `op://`
references into real environment variables for this process. The payment worker
reads them at runtime; nothing else touches them.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# macOS' python.org build ships without a wired-up CA bundle, which makes the
# Daytona/OpenAI HTTPS calls fail with CERTIFICATE_VERIFY_FAILED. Point TLS at
# certifi's bundle if the user hasn't configured one. This does NOT disable
# verification — it supplies a valid root store.
try:  # pragma: no cover - environment dependent
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except Exception:
    pass

# spendguard/backend/app/config.py -> parents: [0]=app [1]=backend [2]=spendguard [3]=repo root
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent  # the `spendguard/` directory
REPO_ROOT = PROJECT_ROOT.parent

# Load .env from the most likely locations (first found wins per key).
for _candidate in (
    BACKEND_DIR / ".env",
    PROJECT_ROOT / ".env",
    REPO_ROOT / ".env",
):
    if _candidate.exists():
        load_dotenv(_candidate, override=False)


def _resolve(path_str: str) -> Path:
    """Resolve a configured path relative to the spendguard project root."""
    p = Path(path_str)
    if p.is_absolute():
        return p
    return (PROJECT_ROOT / p).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    # --- LLM (intent extraction only; never used for policy decisions) ---
    llm_provider: str = "openai"
    use_llm_extraction: bool = True
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # --- Executor ---
    use_daytona: bool = True
    use_local_executor_fallback: bool = True
    daytona_api_key: str = ""
    daytona_api_url: str = "https://app.daytona.io/api"
    daytona_target: str = ""

    # --- Payment / credential ---
    use_stripe_test_mode: bool = False
    # The payment credential value is read at runtime by the worker ONLY.
    stripe_secret_key: str = ""
    mock_payment_secret: str = "demo_mock_secret"

    # --- 1Password runtime credential broker ---
    # The Service Account token is the BROKER identity (a trusted issuer). It is
    # used to mint a task-scoped payment credential just-in-time. The token and
    # the resolved secret never enter model context, trace, frontend, or audit.
    op_service_account_token: str = ""
    op_payment_credential_reference: str = "op://SpendGuard/Stripe/secret_key"
    op_integration_name: str = "SpendGuard"
    op_integration_version: str = "1.0.0"

    # --- Paths ---
    spendguard_policy_path: str = "backend/config/policy.json"
    spendguard_seed_requests_path: str = "backend/data/seed_requests.json"
    audit_log_path: str = "backend/data/audit_log.json"

    @property
    def policy_path(self) -> Path:
        return _resolve(self.spendguard_policy_path)

    @property
    def seed_requests_path(self) -> Path:
        return _resolve(self.spendguard_seed_requests_path)

    @property
    def audit_path(self) -> Path:
        return _resolve(self.audit_log_path)

    @property
    def llm_enabled(self) -> bool:
        """LLM extraction is only attempted when explicitly enabled AND a key
        is present. Policy decisions never depend on this."""
        return bool(self.use_llm_extraction and self.openai_api_key)

    @property
    def op_enabled(self) -> bool:
        """Live 1Password brokering requires a Service Account token and a
        secret reference. Without them the broker uses the mock fallback."""
        return bool(self.op_service_account_token and self.op_payment_credential_reference)


@lru_cache
def get_settings() -> Settings:
    return Settings()
