"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import AgentTracePanel from "@/components/AgentTracePanel";
import AuthorityPanel from "@/components/AuthorityPanel";
import RequestPanel from "@/components/RequestPanel";
import { api } from "@/lib/api";
import type { AgentActResult, AuditEntry, Decision, SeedRequest } from "@/lib/types";

const EVENT_DELAY = 480; // ms between revealed trace events

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function Home() {
  const [requests, setRequests] = useState<SeedRequest[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [result, setResult] = useState<AgentActResult | null>(null);
  const [visibleCount, setVisibleCount] = useState(0);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [runningId, setRunningId] = useState<string | null>(null);
  const [thinking, setThinking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [opLive, setOpLive] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

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

  // Animate the revealed events whenever a new result lands.
  useEffect(() => {
    if (timer.current) clearInterval(timer.current);
    if (!result) {
      setVisibleCount(0);
      return;
    }
    setVisibleCount(0);
    let n = 0;
    timer.current = setInterval(() => {
      n += 1;
      setVisibleCount(n);
      if (n >= result.events.length && timer.current) clearInterval(timer.current);
    }, EVENT_DELAY);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [result]);

  const playOne = useCallback(
    async (res: AgentActResult) => {
      setThinking(false);
      setResult(res);
      // Wait for the reveal animation to finish before moving on.
      await sleep(res.events.length * EVENT_DELAY + 700);
    },
    [],
  );

  const autopilot = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await api.resetDemo();
      setResult(null);
      setDecisions({});
      await refreshAudit();
      for (const r of requests) {
        setRunningId(r.id);
        setThinking(true);
        const res = await api.actAgent(r.id);
        await playOne(res);
        setDecisions((d) => ({ ...d, [r.id]: res.decision }));
        await refreshAudit();
        await sleep(600);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Autopilot failed");
    } finally {
      setThinking(false);
      setRunningId(null);
      setBusy(false);
    }
  }, [requests, refreshAudit, playOne]);

  const runOne = useCallback(
    async (id: string) => {
      setBusy(true);
      setRunningId(id);
      setThinking(true);
      setError(null);
      try {
        const res = await api.actAgent(id);
        await playOne(res);
        setDecisions((d) => ({ ...d, [id]: res.decision }));
        await refreshAudit();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Run failed");
      } finally {
        setThinking(false);
        setRunningId(null);
        setBusy(false);
      }
    },
    [refreshAudit, playOne],
  );

  const sendAttack = useCallback(
    async (body: string) => {
      setBusy(true);
      setRunningId(null);
      setThinking(true);
      setError(null);
      try {
        const res = await api.actAgentBody(body, "Attack arena");
        await playOne(res);
        await refreshAudit();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Attack run failed");
      } finally {
        setThinking(false);
        setBusy(false);
      }
    },
    [refreshAudit, playOne],
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
            An autonomous agent that can spend — but never holds the keys.
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span className="pill bg-ok/10 text-ok">Secret visible to model: No</span>
          <span
            className={`pill ${opLive ? "bg-ok/15 text-ok" : "bg-warn/15 text-warn"}`}
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
            onRun={runOne}
            onAutopilot={autopilot}
            onAttack={sendAttack}
            onReset={reset}
          />
        </section>
        <section className="col-span-12 min-h-0 md:col-span-5">
          <AgentTracePanel
            result={result}
            visibleCount={visibleCount}
            running={thinking}
            runningTitle={
              runningId
                ? requests.find((r) => r.id === runningId)?.title
                : thinking
                  ? "attack arena"
                  : null
            }
          />
        </section>
        <section className="col-span-12 min-h-0 md:col-span-4">
          <AuthorityPanel result={result} audit={audit} />
        </section>
      </div>
    </main>
  );
}
