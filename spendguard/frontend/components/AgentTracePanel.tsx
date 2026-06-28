"use client";

import type { AgentActResult, AgentEvent } from "@/lib/types";

const ACTOR = {
  system: { icon: "📥", label: "inbox", color: "text-muted", ring: "border-edge" },
  agent: { icon: "🤖", label: "agent", color: "text-accent", ring: "border-accent/50" },
  gateway: { icon: "🛡️", label: "gateway", color: "text-slate-200", ring: "border-edge" },
} as const;

function statusColor(e: AgentEvent): string {
  if (e.status === "ok") return "text-ok";
  if (e.status === "blocked") return "text-bad";
  if (e.status === "skipped") return "text-muted";
  return e.actor === "agent" ? "text-accent" : "text-slate-200";
}

export default function AgentTracePanel({
  result,
  visibleCount,
  running,
  runningTitle,
}: {
  result: AgentActResult | null;
  visibleCount: number;
  running: boolean;
  runningTitle?: string | null;
}) {
  const events = result?.events ?? [];
  const shown = events.slice(0, visibleCount);
  const done = result && visibleCount >= events.length;

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
          Agent trace
        </h2>
        {result && (
          <span className="flex items-center gap-2 text-xs">
            <span
              className={`pill ${
                result.used_llm ? "bg-accent/15 text-accent" : "bg-muted/15 text-muted"
              }`}
            >
              {result.used_llm ? "real LLM agent" : "deterministic agent"}
            </span>
            <DecisionPill decision={result.decision} />
          </span>
        )}
      </div>

      {!result && !running && (
        <div className="card flex flex-1 items-center justify-center text-center text-sm text-muted">
          Hit <span className="mx-1 font-semibold text-accent">▶ Run agent</span>{" "}
          and watch it work the inbox on its own.
        </div>
      )}

      {running && (!result || runningTitle) && (
        <div className="card flex items-center gap-3 text-sm text-accent">
          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-accent" />
          Agent reasoning{runningTitle ? ` — ${runningTitle}` : ""}…
        </div>
      )}

      {result && (
        <div className="scroll flex flex-1 flex-col gap-2 overflow-y-auto pr-1">
          {shown.map((e, i) => {
            const a = ACTOR[e.actor];
            return (
              <div
                key={i}
                className={`rounded-lg border bg-panel px-3 py-2 ${a.ring} ${
                  e.status === "blocked" ? "border-bad/40" : ""
                }`}
              >
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 text-base leading-none">{a.icon}</span>
                  <div className="min-w-0 flex-1">
                    <div className={`text-sm font-medium ${statusColor(e)}`}>
                      {e.title}
                    </div>
                    {e.detail && (
                      <div className="mt-0.5 break-words text-xs leading-relaxed text-slate-400">
                        {e.detail}
                      </div>
                    )}
                  </div>
                  <span className="shrink-0 text-[10px] uppercase tracking-wider text-muted">
                    {a.label}
                  </span>
                </div>
              </div>
            );
          })}

          {done && result.agent_summary && (
            <div className="card mt-1 border-accent/30">
              <div className="text-xs font-semibold uppercase tracking-wider text-accent">
                Agent summary
              </div>
              <p className="mt-1 text-sm text-slate-200">{result.agent_summary}</p>
            </div>
          )}

          {done && result.risk_flags.length > 0 && (
            <div className="card border-bad/40">
              <div className="text-xs font-semibold uppercase tracking-wider text-bad">
                Risk flags (detected on the raw message)
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
