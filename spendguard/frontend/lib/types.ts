// Mirrors the backend Pydantic models. No secret value is ever present.

export type Decision = "allowed" | "blocked" | "needs_approval";
export type TraceStatus = "ok" | "skipped" | "blocked" | "info";

export interface SeedRequest {
  id: string;
  title: string;
  source: string;
  from_address: string;
  trusted_source: boolean;
  body: string;
  expected_demo_result: string;
}

export interface Intent {
  vendor: string | null;
  amount_usd: number | null;
  action: string | null;
  description: string;
  extraction_method: "deterministic" | "llm";
}

export interface RiskFlag {
  flag: string;
  reason: string;
  evidence: string;
}

export interface TraceStep {
  step: string;
  status: TraceStatus;
  detail: string;
}

export interface ExecutionResult {
  executed: boolean;
  executor: string;
  sandbox_created: boolean;
  sandbox_id: string | null;
  credential_requested: boolean;
  credential_name: string | null;
  credential_source: string | null;
  secret_visible_to_model: boolean;
  credential_live: boolean;
  credential_broker: string | null;
  credential_reference: string | null;
  credential_issued_at: string | null;
  credential_revoked_at: string | null;
  worker_status: string;
  worker_result: Record<string, unknown> | null;
}

export interface AuthorityView {
  delegated_by: string;
  agent_id: string;
  task_intent: string;
  budget_limit_usd: number;
  approved_vendors: string[];
  allowed_actions: string[];
  action: string | null;
  vendor: string | null;
  amount_usd: number | null;
  credential_name: string;
  credential_source: string;
  secret_visible_to_model: boolean;
  credential_live: boolean;
  credential_broker: string | null;
  credential_issued_at: string | null;
  credential_revoked_at: string | null;
  executor: string;
  sandbox_id: string | null;
  decision: Decision;
  reasons: string[];
}

export interface AgentRunResponse {
  request_id: string;
  title: string;
  created_at: string;
  intent: Intent;
  risk_flags: RiskFlag[];
  decision: Decision;
  reasons: string[];
  trace: TraceStep[];
  execution: ExecutionResult;
  authority: AuthorityView;
  audit_id: string;
}

export interface AuditEntry {
  id: string;
  request_id: string;
  title: string;
  timestamp: string;
  decision: Decision;
  reasons: string[];
  risk_flags: string[];
  vendor: string | null;
  amount_usd: number | null;
  action: string | null;
  executor: string;
  sandbox_created: boolean;
  sandbox_id: string | null;
  credential_requested: boolean;
  credential_name: string | null;
  credential_source: string | null;
  secret_visible_to_model: boolean;
  credential_live: boolean;
  credential_broker: string | null;
  credential_issued_at: string | null;
  credential_revoked_at: string | null;
  worker_status: string;
  executed: boolean;
}
