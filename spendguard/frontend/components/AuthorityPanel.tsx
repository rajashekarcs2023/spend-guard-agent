"use client";

import type {
  AuditEntry,
  AuthorityView,
  ExecutionResult,
} from "@/lib/types";

type AuthorityResult = { authority: AuthorityView; execution: ExecutionResult };

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleTimeString();
}

function Row({
  label,
  children,
  emphasis,
}: {
  label: string;
  children: React.ReactNode;
  emphasis?: "good" | "bad" | "warn";
}) {
  const valClass =
    emphasis === "good"
      ? "text-ok"
      : emphasis === "bad"
        ? "text-bad"
        : emphasis === "warn"
          ? "text-warn"
          : "text-slate-100";
  return (
    <div className="kv">
      <span className="kv-label">{label}</span>
      <span className={`kv-val ${valClass}`}>{children}</span>
    </div>
  );
}

export default function AuthorityPanel({
  result,
  audit,
}: {
  result: AuthorityResult | null;
  audit: AuditEntry[];
}) {
  const a = result?.authority;
  const ex = result?.execution;
  const sandboxCreated = !!ex?.sandbox_created;
  const isDaytona = ex?.executor === "daytona";

  return (
    <div className="flex h-full flex-col gap-3">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
        Authority &amp; audit
      </h2>

      <div className="scroll flex flex-1 flex-col gap-3 overflow-y-auto pr-1">
        {/* Authority card */}
        <div className="card">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">
            Delegated authority
          </div>
          {a ? (
            <div>
              <Row label="Human delegator">{a.delegated_by}</Row>
              <Row label="Agent identity">{a.agent_id}</Row>
              <Row label="Task intent">{a.task_intent}</Row>
              <Row label="Budget">${a.budget_limit_usd.toFixed(0)}</Row>
              <Row label="Approved vendors">
                {a.approved_vendors.join(", ")}
              </Row>
              <Row label="Action">{a.action ?? "—"}</Row>
              <Row label="Vendor">{a.vendor ?? "—"}</Row>
              <Row label="Amount">
                {a.amount_usd != null ? `$${a.amount_usd.toFixed(0)}` : "—"}
              </Row>
              <Row label="Credential name">{a.credential_name}</Row>
              <Row
                label="Credential source"
                emphasis={a.credential_live ? "good" : "warn"}
              >
                {a.credential_source}{" "}
                <span
                  className={`pill ml-1 ${
                    a.credential_live
                      ? "bg-ok/15 text-ok"
                      : "bg-warn/15 text-warn"
                  }`}
                >
                  {a.credential_live ? "1Password live" : "mock"}
                </span>
              </Row>
              <Row label="Issued → revoked (JIT)">
                {a.credential_issued_at ? (
                  <span className="font-mono text-xs">
                    {fmtTime(a.credential_issued_at)} →{" "}
                    {fmtTime(a.credential_revoked_at)}
                  </span>
                ) : (
                  "— (none issued)"
                )}
              </Row>
              <Row label="Secret visible to model" emphasis="good">
                No
              </Row>
              <Row label="Executor">{a.executor}</Row>
              <Row
                label="Daytona sandbox"
                emphasis={!sandboxCreated ? "bad" : isDaytona ? "good" : "warn"}
              >
                {!sandboxCreated
                  ? "skipped"
                  : isDaytona
                    ? "created"
                    : "created (local fallback)"}
              </Row>
              <Row label="Sandbox id">
                <span className="font-mono text-xs">{a.sandbox_id ?? "—"}</span>
              </Row>
              <Row
                label="Decision"
                emphasis={a.decision === "allowed" ? "good" : "bad"}
              >
                {a.decision}
              </Row>
              <div className="kv flex-col items-start">
                <span className="kv-label mb-1">Reasons</span>
                <ul className="w-full space-y-1">
                  {a.reasons.map((r, i) => (
                    <li
                      key={i}
                      className="text-left text-xs leading-relaxed text-slate-300"
                    >
                      • {r}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <div className="py-6 text-center text-sm text-muted">
              Run a request to populate the authority view.
            </div>
          )}
        </div>

        {/* Audit log */}
        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              Audit log
            </span>
            <span className="pill bg-panel2 text-muted">{audit.length}</span>
          </div>
          {audit.length === 0 ? (
            <div className="py-4 text-center text-xs text-muted">
              No audit events yet.
            </div>
          ) : (
            <ul className="space-y-2">
              {audit.map((e) => (
                <li
                  key={e.id}
                  className="rounded-lg border border-edge/70 bg-panel2 p-2.5 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-slate-200">
                      {e.title}
                    </span>
                    <span
                      className={`pill ${
                        e.decision === "allowed"
                          ? "bg-ok/15 text-ok"
                          : "bg-bad/15 text-bad"
                      }`}
                    >
                      {e.decision}
                    </span>
                  </div>
                  <div className="mt-1 text-muted">
                    {e.executed
                      ? `executed via ${e.executor}`
                      : "not executed"}
                    {" · "}
                    sandbox: {e.sandbox_created ? "yes" : "no"}
                    {" · "}
                    secret to model: No
                  </div>
                  <div className="mt-0.5 font-mono text-[10px] text-muted/70">
                    {e.id} · {new Date(e.timestamp).toLocaleTimeString()}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
