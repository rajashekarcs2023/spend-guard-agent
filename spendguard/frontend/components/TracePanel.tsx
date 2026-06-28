"use client";

import type { AgentRunResponse, TraceStatus } from "@/lib/types";

const STATUS_STYLE: Record<TraceStatus, { dot: string; text: string }> = {
  ok: { dot: "bg-ok", text: "text-ok" },
  info: { dot: "bg-accent", text: "text-accent" },
  skipped: { dot: "bg-muted", text: "text-muted" },
  blocked: { dot: "bg-bad", text: "text-bad" },
};

export default function TracePanel({
  result,
  running,
}: {
  result: AgentRunResponse | null;
  running: boolean;
}) {
  return (
    <div className="flex h-full flex-col gap-3">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
        Agent trace
      </h2>

      {!result && !running && (
        <div className="card flex flex-1 items-center justify-center text-center text-sm text-muted">
          Select a request and click <span className="mx-1 font-semibold text-slate-300">Run SpendGuard</span> to see the agent workflow.
        </div>
      )}

      {running && !result && (
        <div className="card flex flex-1 items-center justify-center text-sm text-muted">
          Running workflow…
        </div>
      )}

      {result && (
        <div className="scroll flex flex-1 flex-col gap-3 overflow-y-auto pr-1">
          <div className="card">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-100">
                {result.title}
              </span>
              <DecisionPill decision={result.decision} />
            </div>
            <div className="mt-1 text-xs text-muted">
              intent: {result.intent.description} ·{" "}
              <span className="text-slate-400">
                {result.intent.extraction_method} extraction
              </span>
            </div>
          </div>

          <ol className="relative ml-2 border-l border-edge">
            {result.trace.map((step, i) => {
              const s = STATUS_STYLE[step.status];
              return (
                <li key={i} className="mb-4 ml-4">
                  <span
                    className={`absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full ${s.dot}`}
                  />
                  <div className={`text-sm font-medium ${s.text}`}>
                    {step.step}
                  </div>
                  <div className="mt-0.5 text-xs leading-relaxed text-slate-400">
                    {step.detail}
                  </div>
                </li>
              );
            })}
          </ol>

          {result.risk_flags.length > 0 && (
            <div className="card border-bad/40">
              <div className="text-xs font-semibold uppercase tracking-wider text-bad">
                Risk flags
              </div>
              <ul className="mt-2 space-y-1.5">
                {result.risk_flags.map((f) => (
                  <li key={f.flag} className="text-xs">
                    <span className="font-mono text-bad">{f.flag}</span>
                    <span className="text-slate-400"> — {f.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DecisionPill({ decision }: { decision: string }) {
  const map: Record<string, string> = {
    allowed: "bg-ok/15 text-ok",
    blocked: "bg-bad/15 text-bad",
    needs_approval: "bg-warn/15 text-warn",
  };
  return (
    <span className={`pill ${map[decision] || "bg-muted/15 text-muted"}`}>
      {decision}
    </span>
  );
}
