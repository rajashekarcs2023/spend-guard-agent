"use client";

import type { Decision, SeedRequest } from "@/lib/types";

function OutcomePill({ decision }: { decision?: Decision }) {
  if (!decision) return null;
  const map: Record<Decision, string> = {
    allowed: "bg-ok/15 text-ok",
    blocked: "bg-bad/15 text-bad",
    needs_approval: "bg-warn/15 text-warn",
  };
  return <span className={`pill ${map[decision]}`}>{decision}</span>;
}

export default function RequestPanel({
  requests,
  decisions,
  runningId,
  busy,
  onRun,
  onReset,
}: {
  requests: SeedRequest[];
  decisions: Record<string, Decision>;
  runningId: string | null;
  busy: boolean;
  onRun: (id: string) => void;
  onReset: () => void;
}) {
  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
          Incoming requests
        </h2>
        <button
          onClick={onReset}
          disabled={busy}
          className="rounded-lg border border-edge px-3 py-1 text-xs text-slate-300 transition hover:bg-panel2 disabled:opacity-50"
        >
          Reset demo
        </button>
      </div>

      <div className="scroll flex flex-col gap-3 overflow-y-auto pr-1">
        {requests.map((r) => {
          const expectedAllowed = r.expected_demo_result === "allowed";
          return (
            <div key={r.id} className="card">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-semibold text-slate-100">{r.title}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    {r.source} · {r.from_address}
                  </div>
                </div>
                <OutcomePill decision={decisions[r.id]} />
              </div>

              <p className="mt-3 line-clamp-3 text-xs leading-relaxed text-slate-400">
                {r.body}
              </p>

              <div className="mt-3 flex items-center justify-between">
                <span
                  className={`pill ${
                    r.trusted_source
                      ? "bg-ok/10 text-ok"
                      : "bg-bad/10 text-bad"
                  }`}
                >
                  {r.trusted_source ? "trusted source" : "untrusted source"}
                </span>
                <button
                  onClick={() => onRun(r.id)}
                  disabled={busy}
                  className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white transition hover:brightness-110 disabled:opacity-50"
                >
                  {runningId === r.id ? "Running…" : "Run SpendGuard"}
                </button>
              </div>

              <div className="mt-2 text-[11px] text-muted">
                expected: {expectedAllowed ? "allowed" : "blocked"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
