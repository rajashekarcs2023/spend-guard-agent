import type { AgentRunResponse, AuditEntry, SeedRequest } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () =>
    http<{
      status: string;
      onepassword_live: boolean;
      daytona_configured: boolean;
      credential_reference: string;
    }>("/health"),
  listRequests: () => http<SeedRequest[]>("/requests"),
  runAgent: (request_id: string) =>
    http<AgentRunResponse>("/agent/run", {
      method: "POST",
      body: JSON.stringify({ request_id }),
    }),
  getAudit: () => http<AuditEntry[]>("/audit"),
  resetDemo: () => http<{ status: string }>("/demo/reset", { method: "POST" }),
};

export { API_BASE };
