import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/api";
import type { Batch, BatchRunEvent, DemoAccount, RunDetail, RunEvent, RunStatus, RunSummary, User } from "@/api/types";

export const qk = {
  me: ["me"] as const,
  demoAccounts: ["demo-accounts"] as const,
  system: ["system"] as const,
  health: ["health"] as const,
  clients: ["clients"] as const,
  latestBatch: ["batch", "latest"] as const,
  batch: (id: string) => ["batch", "id", id] as const,
  batches: ["batches"] as const,
  groundTruth: (id: string) => ["batch", "ground-truth", id] as const,
  verify: (id: string) => ["run", id, "verify"] as const,
  run: (id: string) => ["run", id] as const,
  runEvents: (id: string) => ["run", id, "events"] as const,
  lines: (id: string) => ["run", id, "lines"] as const,
  admin: ["admin", "overview"] as const,
};

export const isTerminal = (s: RunStatus | undefined | null) => s === "succeeded" || s === "failed" || s === "stopped";

// ------------------------------------------------------------------ basic

export function useMe() {
  return useQuery({ queryKey: qk.me, queryFn: () => api.me(), staleTime: 60_000 });
}

export function useDemoAccounts() {
  return useQuery({ queryKey: qk.demoAccounts, queryFn: () => api.demoAccounts(), staleTime: Infinity });
}

export function useSystem(enabled = true) {
  return useQuery({ queryKey: qk.system, queryFn: () => api.system(), staleTime: 15_000, enabled });
}

export function useHealth() {
  return useQuery({ queryKey: qk.health, queryFn: () => api.health(), refetchInterval: 30_000, retry: 0, staleTime: 10_000 });
}

// ------------------------------------------------------------------- auth

export function useAuthActions() {
  const qc = useQueryClient();
  const login = useCallback(
    async (email: string, password: string): Promise<User> => {
      const user = await api.login(email, password);
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "demo-accounts" && q.queryKey[0] !== "me" });
      qc.setQueryData(qk.me, user);
      return user;
    },
    [qc],
  );
  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      qc.setQueryData(qk.me, null);
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "demo-accounts" && q.queryKey[0] !== "me" });
    }
  }, [qc]);
  /** One-click role switch for the demo: sign out, then sign in as another demo account. Keeps the current page. */
  const switchTo = useCallback(
    async (account: DemoAccount): Promise<User> => {
      try {
        await api.logout();
      } catch {
        // already signed out
      }
      const user = await api.login(account.email, account.password);
      qc.setQueryData(qk.me, user);
      await qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "demo-accounts" && q.queryKey[0] !== "me" });
      return user;
    },
    [qc],
  );
  return { login, logout, switchTo };
}

// --------------------------------------------------------------- batches

const STATUS_RANK: Record<RunStatus, number> = { queued: 0, running: 1, succeeded: 2, failed: 2, stopped: 2 };

/** Pick the more advanced of two snapshots of the same run (a slow poll must not undo a newer stream update). */
export function newerRun(a: RunSummary | undefined, b: RunSummary): RunSummary {
  if (!a) return b;
  if (STATUS_RANK[a.status] !== STATUS_RANK[b.status]) return STATUS_RANK[a.status] > STATUS_RANK[b.status] ? a : b;
  if (isTerminal(b.status)) return b; // approval changes arrive on finished runs
  if (a.step_count > b.step_count) return a;
  if (a.sandbox_state === "running" && b.sandbox_state === "starting") return a;
  return b;
}

function mergeBatch(prev: Batch | null | undefined, fresh: Batch | null): Batch | null {
  if (!fresh || !prev || prev.id !== fresh.id) return fresh;
  const byId = new Map(prev.runs.map((r) => [r.id, r]));
  const runs = fresh.runs.map((r) => newerRun(byId.get(r.id), r));
  const status = prev.status !== "running" && fresh.status === "running" ? prev.status : fresh.status;
  return { ...fresh, status, runs };
}

export function useLatestBatch() {
  const qc = useQueryClient();
  return useQuery({
    queryKey: qk.latestBatch,
    queryFn: async () => {
      const fresh = await api.latestBatch();
      return mergeBatch(qc.getQueryData<Batch | null>(qk.latestBatch), fresh);
    },
    staleTime: 3_000,
  });
}

export function useBatchById(id: string | null) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: qk.batch(id ?? ""),
    queryFn: async () => {
      const fresh = await api.batch(id as string);
      return mergeBatch(qc.getQueryData<Batch | null>(qk.batch(id as string)), fresh);
    },
    enabled: !!id,
    staleTime: 3_000,
  });
}

export function useBatches(enabled = true) {
  return useQuery({ queryKey: qk.batches, queryFn: () => api.batches(), enabled, staleTime: 10_000 });
}

export function useGroundTruth(batchId: string | null | undefined, enabled: boolean) {
  return useQuery({
    queryKey: qk.groundTruth(batchId ?? ""),
    queryFn: () => api.groundTruth(batchId as string),
    enabled: !!batchId && enabled,
    staleTime: 30_000,
    retry: (count, err) => !(err instanceof ApiError && [401, 403, 404].includes(err.status)) && count < 1,
  });
}

export function useRunVerify(id: string | undefined, enabled: boolean, eventCount: number) {
  return useQuery({
    queryKey: [...qk.verify(id ?? ""), eventCount],
    queryFn: () => api.verifyRun(id as string),
    enabled: !!id && enabled,
    staleTime: Infinity,
    retry: 0,
  });
}

export interface TileActivity {
  text: string;
  /** Step number the activity refers to, when it refers to one. */
  n?: number;
  ts: number;
}

function describeEvent(ev: BatchRunEvent): { text: string; n?: number } | null {
  const p = ev.payload ?? {};
  switch (ev.type) {
    case "run_started":
      return { text: "loading inputs" };
    case "untrusted_text":
      return { text: "flagged instruction-like text" };
    case "sandbox_created":
      return { text: "sandbox up, attestation passed" };
    case "llm":
    case "thought":
      return { text: "planning the next step" };
    case "tool_call":
      if (p.tool === "sniff_file") return { text: "inspecting a file", n: p.n };
      if (p.tool === "run_python") return { text: "running Python", n: p.n };
      if (p.tool === "finish") return { text: "validating result.json" };
      return null;
    case "tool_result":
      return p.n ? { text: `finished, exit ${p.exit_code}`, n: p.n } : null;
    case "progress":
      return { text: `matched ${p.matched} of ${p.total}` };
    case "validation":
      return { text: p.ok ? "result.json validated" : "fixing validation errors" };
    case "stored":
      return { text: "outputs stored" };
    case "sandbox_destroyed":
      return { text: "sandbox destroyed" };
    case "stopped":
      return { text: "stopped" };
    default:
      return null;
  }
}

/** Subscribe to the batch stream while it runs; keeps the given batch cache entry current. */
export function useBatchLive(batch: Batch | null | undefined, cacheKey: readonly unknown[] = qk.latestBatch) {
  const qc = useQueryClient();
  const keyRef = useRef(cacheKey);
  keyRef.current = cacheKey;
  const [activity, setActivity] = useState<Record<string, TileActivity>>({});
  const id = batch?.id;
  const running = batch?.status === "running";

  useEffect(() => {
    if (!id || !running) return;
    let pollMs = 5000;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    const apply = (fn: (b: Batch) => Batch) =>
      qc.setQueryData<Batch | null>(keyRef.current, (old) => (old && old.id === id ? fn(old) : old));

    const poll = () => {
      if (stopped) return;
      void qc.invalidateQueries({ queryKey: keyRef.current });
      timer = setTimeout(poll, pollMs);
    };
    timer = setTimeout(poll, pollMs);

    const unsub = api.streamBatch(id, {
      onRunUpdate: (run) =>
        apply((b) => {
          const exists = b.runs.some((r) => r.id === run.id);
          if (exists) return { ...b, runs: b.runs.map((r) => (r.id === run.id ? newerRun(r, run) : r)) };
          // a re-run: the batch shows the newest run per client, so it takes the old run's place
          const replaced = b.runs.some((r) => r.client_id === run.client_id);
          return { ...b, runs: replaced ? b.runs.map((r) => (r.client_id === run.client_id ? run : r)) : [...b.runs, run] };
        }),
      onBatchUpdate: (bu) => {
        apply((b) => ({ ...b, ...bu, runs: b.runs }));
        if (bu.status !== "running") {
          void qc.invalidateQueries({ queryKey: keyRef.current });
          void qc.invalidateQueries({ queryKey: qk.clients });
          void qc.invalidateQueries({ queryKey: qk.batches });
        }
      },
      onRunEvent: (ev) => {
        const d = describeEvent(ev);
        if (d) setActivity((a) => ({ ...a, [ev.client_id]: { text: d.text, n: d.n ?? a[ev.client_id]?.n, ts: Date.now() } }));
      },
      onError: () => {
        pollMs = 2000; // stream hiccup: lean on polling until it reconnects
      },
    });
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      unsub();
    };
  }, [id, running, qc]);

  return activity;
}

// ------------------------------------------------------------------- runs

export function useRun(id: string | undefined) {
  return useQuery({
    queryKey: qk.run(id ?? ""),
    queryFn: () => api.run(id as string),
    enabled: !!id,
    retry: (count, err) => !(err instanceof ApiError && [401, 403, 404].includes(err.status)) && count < 2,
  });
}

function appendEvents(old: RunEvent[] | undefined, incoming: RunEvent[]): RunEvent[] {
  const map = new Map<number, RunEvent>();
  for (const e of old ?? []) map.set(e.seq, e);
  for (const e of incoming) map.set(e.seq, e);
  return [...map.values()].sort((a, b) => a.seq - b.seq);
}

export function useRunEvents(id: string | undefined) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: qk.runEvents(id ?? ""),
    queryFn: async () => {
      const fresh = await api.runEvents(id as string, 0);
      return appendEvents(qc.getQueryData<RunEvent[]>(qk.runEvents(id as string)), fresh);
    },
    enabled: !!id,
  });
}

export function useLines(id: string | undefined, ready: boolean) {
  return useQuery({
    queryKey: qk.lines(id ?? ""),
    queryFn: () => api.lines(id as string),
    enabled: !!id && ready,
    staleTime: Infinity,
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });
}

function refreshRun(qc: QueryClient, id: string) {
  void qc.invalidateQueries({ queryKey: qk.run(id), exact: true });
  void qc.invalidateQueries({ queryKey: qk.runEvents(id) });
  void qc.invalidateQueries({ queryKey: qk.lines(id) });
}

/** Stream a run while it is queued or running; merge summaries and append events into the cache. */
export function useRunLive(id: string | undefined, status: RunStatus | undefined, eventsLoaded: boolean) {
  const qc = useQueryClient();
  const live = !!id && eventsLoaded && (status === "queued" || status === "running");
  const lastStatus = useRef<RunStatus | undefined>(status);

  useEffect(() => {
    if (!live || !id) return;
    const events = qc.getQueryData<RunEvent[]>(qk.runEvents(id)) ?? [];
    const after = events.length ? events[events.length - 1].seq : 0;
    let finishedTimer: ReturnType<typeof setTimeout> | undefined;
    const unsub = api.streamRun(id, after, {
      onRunEvent: (ev) => {
        qc.setQueryData<RunEvent[]>(qk.runEvents(id), (old) => appendEvents(old, [ev]));
        if (ev.type === "run_finished" || ev.type === "stopped") {
          // the final summary lands right after this event; refetch shortly as a safety net
          finishedTimer = setTimeout(() => refreshRun(qc, id), 1500);
        }
        if (ev.type === "sandbox_created") void qc.invalidateQueries({ queryKey: qk.run(id), exact: true });
      },
      onRunUpdate: (s) => {
        qc.setQueryData<RunDetail>(qk.run(id), (old) => (old ? { ...old, ...s } : old));
        if (isTerminal(s.status) && !isTerminal(lastStatus.current)) refreshRun(qc, id);
        lastStatus.current = s.status;
      },
    });
    const iv = setInterval(() => void qc.invalidateQueries({ queryKey: qk.run(id), exact: true }), 6000);
    return () => {
      unsub();
      clearInterval(iv);
      if (finishedTimer) clearTimeout(finishedTimer);
    };
  }, [id, live, qc]);
}

export function useAdminOverview(enabled: boolean) {
  return useQuery({
    queryKey: qk.admin,
    queryFn: () => api.adminOverview(),
    enabled,
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
  });
}
