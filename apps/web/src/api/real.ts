import type {
  AdminOverview,
  Api,
  Approval,
  Batch,
  BatchRunEvent,
  BatchStreamHandlers,
  BatchWithoutRuns,
  Client,
  DemoAccount,
  DownloadName,
  GroundTruth,
  Health,
  KillSwitchResult,
  Lines,
  RunDetail,
  RunEvent,
  RunStreamHandlers,
  RunSummary,
  RunVerify,
  SystemInfo,
  Unsubscribe,
  User,
  WarmupResult,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

function detailMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      const msgs = d.map((x) => (x && typeof x === "object" && "msg" in x ? String((x as { msg: unknown }).msg) : String(x)));
      return msgs.join("; ");
    }
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      credentials: "include",
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the Tieout API. Check your connection and try again.");
  }
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    const fallback =
      res.status === 401
        ? "Sign in required"
        : res.status === 403
          ? "You do not have permission to do that."
          : res.status === 429
            ? "Rate limit reached. Try again shortly."
            : `Request failed (${res.status})`;
    throw new ApiError(res.status, detailMessage(body, fallback));
  }
  return body as T;
}

const post = <T>(path: string, data?: unknown) =>
  request<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });

type Listener = (data: unknown) => void;

/** Open an SSE stream with named event listeners. Returns a function that closes it. */
function openStream(url: string, listeners: Record<string, Listener | undefined>, onError?: () => void): Unsubscribe {
  if (typeof EventSource === "undefined") {
    onError?.();
    return () => {};
  }
  const es = new EventSource(url, { withCredentials: true });
  for (const [name, fn] of Object.entries(listeners)) {
    if (!fn) continue;
    es.addEventListener(name, (e) => {
      try {
        fn(JSON.parse((e as MessageEvent<string>).data));
      } catch {
        // ignore malformed frames
      }
    });
  }
  es.onerror = () => onError?.();
  return () => es.close();
}

function clickDownload(href: string, filename: string) {
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export const realApi: Api = {
  demoAccounts: () => request<DemoAccount[]>("/demo-accounts"),
  login: (email, password) => post<User>("/auth/login", { email, password }),
  logout: async () => {
    await post<{ ok: boolean }>("/auth/logout");
  },
  me: async () => {
    try {
      return await request<User>("/me");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return null;
      throw e;
    }
  },
  system: () => request<SystemInfo>("/system"),
  health: () => request<Health>("/health"),
  clients: () => request<Client[]>("/clients"),
  createBatch: (period) => post<Batch>("/batches", { period }),
  latestBatch: () => request<Batch | null>("/batches/latest"),
  batches: () => request<BatchWithoutRuns[]>("/batches"),
  batch: (id) => request<Batch>(`/batches/${encodeURIComponent(id)}`),
  groundTruth: (batchId) => request<GroundTruth>(`/batches/${encodeURIComponent(batchId)}/ground-truth`),
  streamBatch: (id, h: BatchStreamHandlers) =>
    openStream(
      `/api/batches/${encodeURIComponent(id)}/stream`,
      {
        run_update: h.onRunUpdate && ((d) => h.onRunUpdate?.(d as RunSummary)),
        run_event: h.onRunEvent && ((d) => h.onRunEvent?.(d as BatchRunEvent)),
        batch_update: h.onBatchUpdate && ((d) => h.onBatchUpdate?.(d as BatchWithoutRuns)),
      },
      h.onError,
    ),
  run: (id) => request<RunDetail>(`/runs/${encodeURIComponent(id)}`),
  runEvents: (id, after = 0) => request<RunEvent[]>(`/runs/${encodeURIComponent(id)}/events?after=${after}`),
  streamRun: (id, after, h: RunStreamHandlers) =>
    openStream(
      `/api/runs/${encodeURIComponent(id)}/stream?after=${after}`,
      {
        run_event: h.onRunEvent && ((d) => h.onRunEvent?.(d as RunEvent)),
        run_update: h.onRunUpdate && ((d) => h.onRunUpdate?.(d as RunSummary)),
        replay_update: h.onReplayUpdate && ((d) => h.onReplayUpdate?.(d as RunSummary)),
      },
      h.onError,
    ),
  lines: (id) => request<Lines>(`/runs/${encodeURIComponent(id)}/lines`),
  verifyRun: (id) => request<RunVerify>(`/runs/${encodeURIComponent(id)}/verify`),
  replay: (id) => post<RunSummary>(`/runs/${encodeURIComponent(id)}/replay`),
  rerun: (id) => post<RunSummary>(`/runs/${encodeURIComponent(id)}/rerun`),
  approve: (id, decision, comment) => post<Approval>(`/runs/${encodeURIComponent(id)}/approve`, { decision, comment }),
  adminOverview: () => request<AdminOverview>("/admin/overview"),
  killSwitch: (enabled) => post<KillSwitchResult>("/admin/kill-switch", { enabled }),
  warmup: () => post<WarmupResult>("/admin/warmup"),
  downloadUrl: (runId, name: DownloadName) =>
    name === "ajes.csv" || name === "evidence.zip"
      ? `/api/runs/${encodeURIComponent(runId)}/${name}`
      : `/api/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(name)}`,
  download: async (runId, name, filename) => {
    if (name === "ajes.csv" || name === "evidence.zip") {
      // Same-origin responses: fetch them so a refusal shows as a clear error instead of a broken download.
      let res: Response;
      try {
        res = await fetch(realApi.downloadUrl(runId, name), { credentials: "include" });
      } catch {
        throw new ApiError(0, "Cannot reach the Tieout API.");
      }
      if (!res.ok) {
        let body: unknown = null;
        try {
          body = await res.json();
        } catch {
          body = null;
        }
        throw new ApiError(res.status, detailMessage(body, name === "ajes.csv" ? "The AJE export is not available." : "The evidence pack is not available."));
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      clickDownload(url, filename);
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
      return;
    }
    // Artifacts redirect to a short-lived presigned Object Storage URL; let the browser follow it.
    clickDownload(realApi.downloadUrl(runId, name), filename);
  },
  uploads: () => request<RunSummary[]>("/uploads"),
  upload: (req) => post<RunSummary>("/uploads", req),
  sampleUrl: (name) => `/api/samples/${encodeURIComponent(name)}`,
};
