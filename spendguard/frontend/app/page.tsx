"use client";

import { useCallback, useEffect, useState } from "react";

import AuthorityPanel from "@/components/AuthorityPanel";
import RequestPanel from "@/components/RequestPanel";
import TracePanel from "@/components/TracePanel";
import { api } from "@/lib/api";
import type {
  AgentRunResponse,
  AuditEntry,
  Decision,
  SeedRequest,
} from "@/lib/types";

export default function Home() {
  const [requests, setRequests] = useState<SeedRequest[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [result, setResult] = useState<AgentRunResponse | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [runningId, setRunningId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [opLive, setOpLive] = useState<boolean>(false);

  const refreshAudit = useCallback(async () => {
    try {
      setAudit(await api.getAudit());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const h = await api.health();
        setOnline(true);
        setOpLive(!!h.onepassword_live);
        setRequests(await api.listRequests());
        await refreshAudit();
      } catch (e) {
        setOnline(false);
        setError(e instanceof Error ? e.message : "Cannot reach backend");
      }
    })();
  }, [refreshAudit]);

  const run = useCallback(
    async (id: string) => {
      setBusy(true);
      setRunningId(id);
      setError(null);
      try {
        const res = await api.runAgent(id);
        setResult(res);
        setDecisions((d) => ({ ...d, [id]: res.decision }));
        await refreshAudit();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Run failed");
      } finally {
        setBusy(false);
        setRunningId(null);
      }
    },
    [refreshAudit],
  );

  const reset = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await api.resetDemo();
      setResult(null);
      setDecisions({});
      await refreshAudit();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  }, [refreshAudit]);

  return (
    <main className="mx-auto flex h-screen max-w-[1500px] flex-col p-5">
      <header className="mb-4 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">
            Spend<span className="text-accent">Guard</span>
          </h1>
          <p className="text-sm text-muted">
            Let agents spend without holding the keys.
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="pill bg-ok/10 text-ok">Secret visible to model: No</span>
          <span
            className={`pill ${
              opLive ? "bg-ok/15 text-ok" : "bg-warn/15 text-warn"
            }`}
          >
            1Password: {opLive ? "live runtime broker" : "mock (no token)"}
          </span>
          <span
            className={`pill ${
              online === false
                ? "bg-bad/15 text-bad"
                : online
                  ? "bg-ok/15 text-ok"
                  : "bg-muted/15 text-muted"
            }`}
          >
            backend {online === false ? "offline" : online ? "online" : "…"}
          </span>
        </div>
      </header>

      {error && (
        <div className="mb-3 rounded-lg border border-bad/40 bg-bad/10 px-3 py-2 text-xs text-bad">
          {error}
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-12 gap-4">
        <section className="col-span-12 min-h-0 md:col-span-3">
          <RequestPanel
            requests={requests}
            decisions={decisions}
            runningId={runningId}
            busy={busy}
            onRun={run}
            onReset={reset}
          />
        </section>
        <section className="col-span-12 min-h-0 md:col-span-5">
          <TracePanel result={result} running={busy && !!runningId} />
        </section>
        <section className="col-span-12 min-h-0 md:col-span-4">
          <AuthorityPanel result={result} audit={audit} />
        </section>
      </div>
    </main>
  );
}
