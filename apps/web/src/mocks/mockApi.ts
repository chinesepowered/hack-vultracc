// In-browser mock of the Tieout API (VITE_MOCK=1). Development and visual testing only.
//
// The simulation is a pure function of wall-clock time: each run has a plan (events at absolute times),
// and every call folds the plan up to "now". Only decisions (batches, approvals, replays, kill switch,
// session) are stored, in localStorage, so a page reload mid-batch continues where it left off.

import { ApiError } from "@/api/real";
import type {
  AdminOverview,
  Api,
  Approval,
  AuditEntry,
  Batch,
  BatchTotals,
  Client,
  BatchWithoutRuns,
  DemoAccount,
  GroundTruth,
  Health,
  RunDetail,
  RunEvent,
  RunSummary,
  SystemInfo,
  User,
} from "@/api/types";
import { sha256Hex } from "@/lib/sha256";
import { CLIENTS, FIRM, MOCK_HOST, ajesCsv, clientData, type ClientData } from "./data";

const STORE_KEY = "tieout.mock.v2";
const PERIOD = "2026-09";
const MODEL = "glm-5.3";
const FAST_MODEL = "glm-5.3-flash";
const PRICES: Record<string, [number, number]> = { "glm-5.3": [0.75, 3.0], "glm-5.3-flash": [0.1, 0.35] };
const RUN_FILES = ["ajes.csv", "lines.json", "result.json", "workpaper.xlsx"];
const LIMITS = { cpus: 1.0, memory_mb: 1024, pids: 256, exec_timeout_s: 60, ttl_s: 900 };

interface MockUser extends User {
  password: string;
  blurb: string;
}

const USERS: MockUser[] = [
  {
    id: "usr_alex",
    email: "alex@harborpine.example",
    password: "close-september",
    name: "Alex Rivera",
    role: "preparer",
    title: "Staff Accountant",
    blurb: "Starts the September close and reviews the agent's work.",
  },
  {
    id: "usr_jordan",
    email: "jordan@harborpine.example",
    password: "review-september",
    name: "Jordan Lee",
    role: "reviewer",
    title: "Engagement Manager",
    blurb: "Approves or rejects adjusting entries (maker-checker).",
  },
  {
    id: "usr_sam",
    email: "sam@harborpine.example",
    password: "admin-september",
    name: "Sam Patel",
    role: "admin",
    title: "IT Administrator",
    blurb: "Watches sandboxes, usage and health; owns the kill switch.",
  },
];

interface StoredRun {
  clientId: string;
  runId: string;
  /** Set on re-runs: when this run was created (originals start with the batch). */
  createdAt?: number;
  createdBy?: string;
  /** Set when the kill switch stopped this run. */
  stoppedAt?: number | null;
}

interface StoredBatch {
  id: string;
  period: string;
  createdAt: number;
  createdBy: string;
  runs: StoredRun[];
  stoppedAt: number | null;
}

interface StoredReplay {
  id: string;
  of: string;
  clientId: string;
  createdAt: number;
  createdBy: string;
  stoppedAt: number | null;
}

interface StoredApproval extends Approval {
  run_id: string;
  reviewer_id: string;
}

interface Store {
  v: 1;
  session: string | null;
  batches: StoredBatch[];
  replays: StoredReplay[];
  approvals: StoredApproval[];
  killSwitch: boolean;
  killSwitchUntil?: number | null;
  audit: AuditEntry[];
}

interface PlanEvent {
  at: number;
  type: string;
  payload: any; // eslint-disable-line @typescript-eslint/no-explicit-any
}

interface Plan {
  runId: string;
  kind: "original" | "replay";
  clientId: string;
  batchId: string | null;
  replayOf: string | null;
  createdAt: number;
  startAt: number;
  createdBy: string;
  events: PlanEvent[];
  data: ClientData;
  stoppedAt: () => number | null;
  chain: string[];
}

// ------------------------------------------------------------------ store

function freshStore(): Store {
  const s: Store = { v: 1, session: null, batches: [], replays: [], approvals: [], killSwitch: false, audit: [] };
  appendAudit(s, "control-plane", "api_started", "system", { version: "1.0.0", git_sha: "mock" });
  return s;
}

function loadStore(): Store {
  try {
    if (typeof location !== "undefined" && new URLSearchParams(location.search).has("mockReset")) {
      localStorage.removeItem(STORE_KEY);
    }
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) {
      const s = JSON.parse(raw) as Store;
      if (s && s.v === 1) return s;
    }
  } catch {
    // storage unavailable: fall back to memory
  }
  return freshStore();
}

let store: Store = loadStore();

function save() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
  } catch {
    // ignore
  }
}

function appendAudit(s: Store, actor: string, action: string, target: string, detail: Record<string, unknown>) {
  const prev = s.audit.length ? s.audit[s.audit.length - 1].sha256 : null;
  const ts = new Date().toISOString();
  const body = { ts, actor, action, target, detail };
  const sha = sha256Hex((prev ?? "") + JSON.stringify(body));
  s.audit.push({ seq: s.audit.length + 1, ts, actor, action, target, detail, sha256: sha, prev_sha256: prev });
}

function audit(actor: string, action: string, target: string, detail: Record<string, unknown> = {}) {
  appendAudit(store, actor, action, target, detail);
  save();
}

// ---------------------------------------------------------------- helpers

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));
const latency = () => delay(60 + Math.random() * 140);
const iso = (ms: number) => new Date(ms).toISOString();

function hashInt(s: string): number {
  return parseInt(sha256Hex(s).slice(0, 8), 16);
}

function newId(prefix: string): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${prefix}_${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}${p(d.getUTCHours())}${p(d.getUTCMinutes())}${sha256Hex(
    `${prefix}${Date.now()}${Math.random()}`,
  ).slice(0, 6)}`;
}

function currentUser(): MockUser | null {
  return USERS.find((u) => u.id === store.session) ?? null;
}

function requireUser(): MockUser {
  const u = currentUser();
  if (!u) throw new ApiError(401, "Sign in required");
  return u;
}

function requireRole(...roles: string[]): MockUser {
  const u = requireUser();
  if (!roles.includes(u.role)) throw new ApiError(403, `This action needs the ${roles.join(" or ")} role.`);
  return u;
}

function publicUser(u: MockUser): User {
  return { id: u.id, email: u.email, name: u.name, role: u.role, title: u.title };
}

function clip(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + "\n...[truncated]" : s;
}

// ------------------------------------------------------------------ plans

const plans = new Map<string, Plan>();

function planOriginal(b: StoredBatch, entry: StoredRun, idx: number): Plan {
  const { clientId, runId } = entry;
  const data = clientData(clientId);
  const tpl = data.events;
  const sandboxId = `sbx_${sha256Hex(runId).slice(0, 16)}`;
  const base = entry.createdAt ?? b.createdAt;
  const startAt = entry.createdAt ? base + 400 : base + 250 + idx * 190 + (hashInt(runId) % 350);
  const total = 11500 + ((idx * 1543 + 700) % 6500);
  const sbAt = startAt + 950;
  const tStart = Date.parse(tpl.find((e) => e.type === "sandbox_created")?.ts ?? tpl[0].ts);
  const tEnd = Date.parse(tpl[tpl.length - 1].ts);
  const span = Math.max(1, tEnd - tStart);
  const events: PlanEvent[] = [];
  for (const e of tpl) {
    let at: number;
    if (e.type === "run_started") at = startAt;
    else if (e.type === "sandbox_created") at = sbAt;
    else at = sbAt + 200 + ((Date.parse(e.ts) - tStart) / span) * (total - 1500);
    let payload = e.payload;
    if (e.type === "sandbox_created") {
      payload = {
        ...payload,
        sandbox_id: sandboxId,
        attestation: payload.attestation && {
          ...payload.attestation,
          facts: { ...payload.attestation.facts, hostname: sha256Hex(sandboxId).slice(0, 12) },
        },
      };
    }
    if (e.type === "sandbox_destroyed") payload = { sandbox_id: sandboxId };
    if (e.type === "run_finished") payload = { ...payload, duration_ms: Math.round(at - startAt) };
    events.push({ at, type: e.type, payload });
    if (e.type === "run_started") {
      data.untrusted.forEach((u, i) => events.push({ at: startAt + 40 + i, type: "untrusted_text", payload: u }));
    }
    if (e.type === "tool_result") {
      const m = /matched (\d+) of (\d+) bank lines/.exec(String(payload.stdout ?? ""));
      if (m) events.push({ at: at + 5, type: "progress", payload: { matched: Number(m[1]), total: Number(m[2]) } });
    }
  }
  const last = Math.max(...events.map((e) => e.at));
  events.push({
    at: last + 300,
    type: "stored",
    payload: {
      artifacts: data.outputs.map((o) => ({
        name: o.name,
        sha256: o.sha256,
        bytes: o.bytes,
        object_key: `clients/${clientId}/runs/${runId}/out/${o.name}`,
      })),
      backend: "s3",
    },
  });
  events.sort((a, b2) => a.at - b2.at);
  return {
    runId,
    kind: "original",
    clientId,
    batchId: b.id,
    replayOf: null,
    createdAt: base,
    startAt,
    createdBy: entry.createdBy ?? b.createdBy,
    events,
    data,
    stoppedAt: () => store.batches.find((x) => x.id === b.id)?.runs.find((x) => x.runId === runId)?.stoppedAt ?? null,
    chain: [],
  };
}

function planReplay(r: StoredReplay): Plan {
  const orig = planFor(r.of);
  if (!orig) throw new ApiError(404, "No such run");
  const data = orig.data;
  const sandboxId = `sbx_${sha256Hex(r.id).slice(0, 16)}`;
  const startAt = r.createdAt + 300;
  const sbAt = startAt + 800;
  const calls = orig.events.filter((e) => e.type === "tool_call" && e.payload.tool !== "finish");
  const results = orig.events.filter((e) => e.type === "tool_result");
  const created = orig.events.find((e) => e.type === "sandbox_created");
  const events: PlanEvent[] = [
    {
      at: startAt,
      type: "run_started",
      payload: { client_id: r.clientId, replay_of: r.of, steps: calls.length, inputs: data.inputs },
    },
    {
      at: sbAt,
      type: "sandbox_created",
      payload: {
        ...(created?.payload ?? {}),
        sandbox_id: sandboxId,
        host: MOCK_HOST,
        attestation: created?.payload?.attestation && {
          ...created.payload.attestation,
          facts: { ...created.payload.attestation.facts, hostname: sha256Hex(sandboxId).slice(0, 12) },
        },
      },
    },
  ];
  let t = sbAt + 350;
  calls.forEach((c) => {
    const res = results.find((x) => x.payload.n === c.payload.n);
    const n = c.payload.n as number;
    const argv =
      c.payload.tool === "sniff_file" ? ["python", "-m", "tieout_lib.sniff", `/in/${c.payload.args.name}`] : ["python", `/work/step_${n}.py`];
    const dur = Math.round((res?.payload.duration_ms ?? 1500) * (0.92 + (hashInt(`${r.id}${n}`) % 16) / 100));
    t += 420 + (hashInt(`${r.id}:${n}`) % 260);
    events.push({
      at: t,
      type: "replay_step",
      payload: {
        n,
        tool: c.payload.tool,
        argv,
        exit_code: res?.payload.exit_code ?? 0,
        duration_ms: dur,
        stdout: clip(String(res?.payload.stdout ?? ""), 4000),
        stderr: String(res?.payload.stderr ?? "").slice(-2000),
      },
    });
  });
  const files = [...RUN_FILES].sort().map((name) => ({ name, original: data.hashes[name], replay: data.hashes[name], match: true }));
  events.push({ at: t + 450, type: "replay_compared", payload: { match: true, files } });
  events.push({ at: t + 600, type: "sandbox_destroyed", payload: { sandbox_id: sandboxId } });
  events.push({ at: t + 650, type: "run_finished", payload: { status: "succeeded", replay_match: true, hashes: data.hashes, error: null } });
  return {
    runId: r.id,
    kind: "replay",
    clientId: r.clientId,
    batchId: null,
    replayOf: r.of,
    createdAt: r.createdAt,
    startAt,
    createdBy: r.createdBy,
    events,
    data,
    stoppedAt: () => store.replays.find((x) => x.id === r.id)?.stoppedAt ?? null,
    chain: [],
  };
}

function planFor(runId: string): Plan | null {
  const hit = plans.get(runId);
  if (hit) return hit;
  for (const b of store.batches) {
    const idx = b.runs.findIndex((x) => x.runId === runId);
    if (idx >= 0) {
      const order = [...new Set(b.runs.map((x) => x.clientId))];
      const p = planOriginal(b, b.runs[idx], order.indexOf(b.runs[idx].clientId));
      plans.set(runId, p);
      return p;
    }
  }
  const r = store.replays.find((x) => x.id === runId);
  if (r) {
    const p = planReplay(r);
    plans.set(runId, p);
    return p;
  }
  return null;
}

function mustPlan(runId: string): Plan {
  const p = planFor(runId);
  if (!p) throw new ApiError(404, "No such run");
  return p;
}

// ------------------------------------------------------------- projection

function isFinal(p: Plan, now: number): boolean {
  const cutoff = Math.min(now, p.stoppedAt() ?? Infinity);
  const finalType = p.kind === "original" ? "stored" : "run_finished";
  const ev = p.events.find((e) => e.type === finalType);
  return !!ev && ev.at <= cutoff;
}

function visibleEvents(p: Plan, now: number): RunEvent[] {
  const stoppedAt = p.stoppedAt();
  const cutoff = Math.min(now, stoppedAt ?? Infinity);
  const list: { at: number; type: string; payload: unknown }[] = p.events.filter((e) => e.at <= cutoff);
  if (stoppedAt !== null && now >= stoppedAt && !isFinal(p, now) && stoppedAt >= p.startAt) {
    list.push({ at: stoppedAt, type: "stopped", payload: { reason: "stopped by the admin kill switch" } });
    const created = list.find((e) => e.type === "sandbox_created") as PlanEvent | undefined;
    if (created && !list.some((e) => e.type === "sandbox_destroyed")) {
      list.push({ at: stoppedAt + 1, type: "sandbox_destroyed", payload: { sandbox_id: created.payload.sandbox_id } });
    }
  }
  return list.map((e, i) => {
    const seq = i + 1;
    const ts = iso(e.at);
    if (p.chain.length < seq) {
      const prev = p.chain[i - 1] ?? null;
      p.chain[i] = sha256Hex((prev ?? "") + JSON.stringify({ run_id: p.runId, seq, ts, type: e.type }));
    }
    return { seq, ts, type: e.type, payload: e.payload, sha256: p.chain[i], prev_sha256: i ? p.chain[i - 1] : null };
  });
}

function approvalFor(runId: string): StoredApproval | undefined {
  return store.approvals.find((a) => a.run_id === runId);
}

function summarize(p: Plan, now: number): RunSummary {
  const stoppedAt = p.stoppedAt();
  const cutoff = Math.min(now, stoppedAt ?? Infinity);
  const data = p.data;
  const creator = USERS.find((u) => u.id === p.createdBy);
  const s: RunSummary = {
    id: p.runId,
    batch_id: p.batchId,
    client_id: p.clientId,
    client_name: data.meta.name,
    industry: data.meta.industry,
    kind: p.kind,
    replay_of: p.replayOf,
    status: "queued",
    recon_status: null,
    approval_status: null,
    step_count: 0,
    matched_count: null,
    bank_line_count: null,
    exception_count: null,
    needs_review_count: null,
    aje_count: null,
    difference: null,
    sandbox_id: null,
    sandbox_host: null,
    sandbox_state: "none",
    badges: { runtime: null, network: null, readonly_rootfs: null, cpus: null, memory_mb: null, attestation_ok: null },
    summary: null,
    error: null,
    tokens_in: 0,
    tokens_out: 0,
    started_at: null,
    finished_at: null,
    duration_ms: null,
    created_by_name: creator?.name ?? null,
    replay_match: null,
  };
  if (cutoff >= p.startAt) {
    s.status = "running";
    s.sandbox_state = "starting";
    s.started_at = iso(p.startAt);
  }
  let final = false;
  for (const e of p.events) {
    if (e.at > cutoff) break;
    switch (e.type) {
      case "sandbox_created": {
        const d = e.payload.docker ?? {};
        s.sandbox_state = "running";
        s.sandbox_id = e.payload.sandbox_id;
        s.sandbox_host = e.payload.host;
        s.badges = {
          runtime: d.Runtime ?? null,
          network: d.NetworkMode ?? null,
          readonly_rootfs: d.ReadonlyRootfs ?? null,
          cpus: d.NanoCpus ? Math.round((d.NanoCpus / 1e9) * 100) / 100 : null,
          memory_mb: d.Memory ? Math.round(d.Memory / 1024 / 1024) : null,
          attestation_ok: e.payload.attestation?.ok ?? null,
        };
        break;
      }
      case "tool_result":
        s.step_count += 1;
        break;
      case "progress":
        s.matched_count = e.payload.matched;
        s.bank_line_count = e.payload.total;
        break;
      case "llm":
        s.tokens_in += e.payload.tokens_in ?? 0;
        s.tokens_out += e.payload.tokens_out ?? 0;
        break;
      case "sandbox_destroyed":
        s.sandbox_state = "destroyed";
        break;
      case "stored":
      case "run_finished":
        if ((p.kind === "original" && e.type === "stored") || (p.kind === "replay" && e.type === "run_finished")) {
          final = true;
          s.finished_at = iso(e.at);
        }
        break;
    }
  }
  if (final) {
    const r = data.result;
    s.status = "succeeded";
    s.recon_status = r.status;
    s.matched_count = r.matched_count;
    s.bank_line_count = r.bank_line_count;
    s.exception_count = r.exceptions.length;
    s.needs_review_count = r.exceptions.filter((x) => x.needs_review).length;
    s.aje_count = r.ajes.length;
    s.difference = r.difference;
    s.sandbox_state = "destroyed";
    s.duration_ms = Date.parse(s.finished_at as string) - p.startAt;
    if (p.kind === "original") {
      s.summary = data.summary;
      s.approval_status = approvalFor(p.runId)?.decision ?? "pending";
    } else {
      s.replay_match = true;
    }
  } else if (stoppedAt !== null && now >= stoppedAt) {
    s.status = "stopped";
    s.error = "stopped by the admin kill switch";
    s.finished_at = iso(stoppedAt);
    s.duration_ms = s.started_at ? stoppedAt - p.startAt : null;
    if (s.sandbox_id) s.sandbox_state = "destroyed";
  }
  return s;
}

function totalsOf(runs: RunSummary[]): BatchTotals {
  const t: BatchTotals = {
    clients: runs.length,
    queued: 0,
    running: 0,
    succeeded: 0,
    failed: 0,
    reconciled: 0,
    needs_review: 0,
    exceptions: 0,
    ajes: 0,
    approved: 0,
  };
  for (const r of runs) {
    if (r.status === "queued" || r.status === "running") t[r.status] += 1;
    else if (r.status === "succeeded") t.succeeded += 1;
    else t.failed += 1;
    if (r.recon_status === "reconciled" || r.recon_status === "needs_review") t[r.recon_status] += 1;
    t.exceptions += r.exception_count ?? 0;
    t.ajes += r.aje_count ?? 0;
    if (r.approval_status === "approved") t.approved += 1;
  }
  return t;
}

/** The newest run per client, in client order (a re-run replaces the failed run on its tile). */
function currentRuns(b: StoredBatch): StoredRun[] {
  const latest = new Map<string, StoredRun>();
  for (const r of b.runs) latest.set(r.clientId, r);
  return [...latest.values()].sort((a, c) => a.clientId.localeCompare(c.clientId));
}

function batchOf(b: StoredBatch, now: number): Batch {
  const runs = currentRuns(b).map((r) => summarize(mustPlan(r.runId), now));
  const done = runs.every((r) => r.status !== "queued" && r.status !== "running");
  const finishedAt = done ? Math.max(...runs.map((r) => (r.finished_at ? Date.parse(r.finished_at) : b.createdAt))) : null;
  const creator = USERS.find((u) => u.id === b.createdBy);
  return {
    id: b.id,
    period: b.period,
    status: done ? (runs.some((r) => r.status === "stopped") ? "stopped" : "completed") : "running",
    created_by_name: creator?.name ?? "",
    created_at: iso(b.createdAt),
    finished_at: finishedAt ? iso(finishedAt) : null,
    duration_ms: finishedAt ? finishedAt - b.createdAt : null,
    totals: totalsOf(runs),
    runs,
  };
}

function detailOf(p: Plan, now: number, viewer: MockUser): RunDetail {
  const s = summarize(p, now);
  const evs = visibleEvents(p, now);
  const sb = evs.find((e) => e.type === "sandbox_created")?.payload;
  const final = s.status === "succeeded";
  const data = p.data;
  let reason: string | null = null;
  if (p.kind !== "original") reason = "Replays are verification runs; approve the original run.";
  else if (s.status !== "succeeded") reason = "Only a finished run with a valid result can be approved.";
  else if (viewer.role !== "reviewer" && viewer.role !== "admin") reason = "Only a reviewer can approve adjusting entries.";
  else if (p.createdBy === viewer.id) reason = "Maker-checker: you started this run, so a different reviewer must approve it.";
  else if (s.approval_status === "approved" || s.approval_status === "rejected") reason = `Already ${s.approval_status}.`;
  const replays = store.replays
    .filter((r) => r.of === p.runId)
    .sort((a, b) => b.createdAt - a.createdAt)
    .map((r) => {
      const rs = summarize(mustPlan(r.id), now);
      return { id: r.id, status: rs.status, replay_match: rs.replay_match, finished_at: rs.finished_at };
    });
  const approvals = store.approvals
    .filter((a) => a.run_id === p.runId)
    .map(({ id, decision, comment, reviewer_name, reviewer_email, ts, signed_sha256 }) => ({
      id,
      decision,
      comment,
      reviewer_name,
      reviewer_email,
      ts,
      signed_sha256,
    }));
  return {
    ...s,
    period: PERIOD,
    model_id: p.kind === "original" && evs.some((e) => e.type === "llm") ? MODEL : null,
    image_digest: sb?.docker?.ImageDigest ?? null,
    attestation: sb?.attestation ?? null,
    docker: sb?.docker ?? null,
    limits: sb?.limits ?? null,
    inputs: s.status !== "queued" ? data.inputs : [],
    outputs: final ? data.outputs : [],
    result: final ? { ...data.result, run_id: p.kind === "original" ? p.runId : (p.replayOf as string) } : null,
    memo_md: final && p.kind === "original" ? data.memo : null,
    hashes: final ? data.hashes : {},
    approvals,
    replays,
    original: p.kind === "replay" ? { id: p.replayOf as string, hashes: data.hashes } : null,
    untrusted_text: s.status !== "queued" && p.kind === "original" ? data.untrusted : [],
    can: {
      approve: reason === null,
      replay: s.status === "succeeded" && p.kind === "original",
      download_ajes: s.approval_status === "approved",
      reason_cannot_approve: reason,
    },
  };
}

/** Public-demo safeguard, mirrored from the server: the kill switch releases itself after 15 minutes. */
function checkAutoResume() {
  if (store.killSwitch && store.killSwitchUntil && Date.now() >= store.killSwitchUntil) {
    store.killSwitch = false;
    store.killSwitchUntil = null;
    appendAudit(store, "control-plane", "kill_switch_auto_resumed", "system", {});
    save();
  }
}

function allPlans(): Plan[] {
  const ids = [...store.batches.flatMap((b) => b.runs.map((r) => r.runId)), ...store.replays.map((r) => r.id)];
  return ids.map((id) => mustPlan(id));
}

function healthNow(): Health {
  const now = Date.now();
  const live = allPlans().filter((p) => summarize(p, now).sandbox_state === "running").length;
  const runs = allPlans().length;
  const jitter = (base: number, spread: number) => base + (Math.floor(now / 5000) % spread);
  return {
    ok: true,
    checks: {
      inference: { ok: true, ms: jitter(212, 90), detail: `19 models at https://api.vultrinference.com/v1; main=${MODEL}` },
      database: { ok: true, ms: jitter(8, 6), detail: `tieout-pg.vultrdb.example:16751/tieout (${runs} runs)` },
      object_storage: { ok: true, ms: jitter(38, 20), detail: "sjc1.vultrobjects.com bucket tieout-artifacts (private, presigned downloads)" },
      runner: {
        ok: true,
        ms: jitter(5, 4),
        detail: `${MOCK_HOST}: runtime runsc, ${live}/16 sandboxes, accepting=${store.killSwitch ? "False" : "True"}`,
      },
    },
    version: "1.0.0",
    kill_switch: store.killSwitch,
  };
}

function downloadBlob(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

// --------------------------------------------------------------------- api

export function createMockApi(): Api {
  if (typeof window !== "undefined") {
    (window as unknown as { __tieoutMock: unknown }).__tieoutMock = {
      reset() {
        localStorage.removeItem(STORE_KEY);
        store = freshStore();
        plans.clear();
        save();
      },
      store: () => store,
    };
  }

  const api: Api = {
    async demoAccounts(): Promise<DemoAccount[]> {
      await latency();
      return USERS.map(({ email, password, name, role, title, blurb }) => ({ email, password, name, role, title, blurb }));
    },

    async login(email, password) {
      await latency();
      const u = USERS.find((x) => x.email.toLowerCase() === email.trim().toLowerCase());
      if (!u || u.password !== password) throw new ApiError(401, "Wrong email or password");
      store.session = u.id;
      audit(u.email, "login", u.id, { ip: "127.0.0.1" });
      return publicUser(u);
    },

    async logout() {
      await latency();
      store.session = null;
      save();
    },

    async me() {
      await delay(40);
      const u = currentUser();
      return u ? publicUser(u) : null;
    },

    async system(): Promise<SystemInfo> {
      await latency();
      requireUser();
      return {
        firm: FIRM,
        period: PERIOD,
        period_label: "September 2026",
        region: "Vultr Silicon Valley (sjc)",
        version: "1.0.0",
        git_sha: "mock",
        models: { main: MODEL, fast: FAST_MODEL },
        kill_switch: (checkAutoResume(), store.killSwitch),
        kill_switch_auto_resume_at: store.killSwitch && store.killSwitchUntil ? iso(store.killSwitchUntil) : null,
        storage_backend: "s3",
        limits: { max_concurrent_sandboxes: 16, max_concurrent_runs: 12, daily_token_budget: 5_000_000, sandbox: LIMITS },
      };
    },

    async health() {
      await latency();
      return healthNow();
    },

    async clients(): Promise<Client[]> {
      await latency();
      requireUser();
      const now = Date.now();
      const latestByClient = new Map<string, RunSummary>();
      for (const b of [...store.batches].sort((a, c) => c.createdAt - a.createdAt)) {
        for (const r of currentRuns(b)) if (!latestByClient.has(r.clientId)) latestByClient.set(r.clientId, summarize(mustPlan(r.runId), now));
      }
      return CLIENTS.map((c) => {
        const d = clientData(c.client_id);
        return {
          id: c.client_id,
          name: c.name,
          industry: c.industry,
          materiality: d.meta.client_id === "cedar-ridge-landscaping" ? "300.00" : "250.00",
          gl_cash_account: "1010",
          latest_run: latestByClient.get(c.client_id) ?? null,
        };
      });
    },

    async createBatch(period) {
      await latency();
      const u = requireRole("preparer", "admin");
      if (period !== PERIOD) throw new ApiError(400, "Only the September 2026 close is available in this demo.");
      checkAutoResume();
      if (store.killSwitch) throw new ApiError(409, "The kill switch is on: new work is stopped.");
      const now = Date.now();
      const running = store.batches.some((b) => batchOf(b, now).status === "running");
      if (running) throw new ApiError(409, "A close is already running. Wait for it to finish.");
      const order = [...CLIENTS].map((c) => c.client_id).sort();
      const b: StoredBatch = {
        id: newId("bat"),
        period,
        createdAt: now,
        createdBy: u.id,
        runs: order.map((clientId) => ({ clientId, runId: newId("run") })),
        stoppedAt: null,
      };
      store.batches.push(b);
      appendAudit(store, u.email, "batch_started", b.id, { period, clients: b.runs.length });
      const bh = b.runs.find((r) => r.clientId === "blue-harbor-coffee");
      if (bh) {
        const d = clientData("blue-harbor-coffee");
        for (const t of d.untrusted) appendAudit(store, "control-plane", "untrusted_text_detected", bh.runId, { ...t });
      }
      save();
      return batchOf(b, now);
    },

    async latestBatch() {
      await latency();
      requireUser();
      const b = [...store.batches].sort((a, c) => c.createdAt - a.createdAt)[0];
      return b ? batchOf(b, Date.now()) : null;
    },

    async batches(): Promise<BatchWithoutRuns[]> {
      await latency();
      requireUser();
      const now = Date.now();
      return [...store.batches]
        .sort((a, c) => c.createdAt - a.createdAt)
        .slice(0, 20)
        .map((b) => {
          const { runs: _runs, ...rest } = batchOf(b, now);
          void _runs;
          return rest;
        });
    },

    async batch(id) {
      await latency();
      requireUser();
      const b = store.batches.find((x) => x.id === id);
      if (!b) throw new ApiError(404, "No such batch");
      return batchOf(b, Date.now());
    },

    async groundTruth(batchId): Promise<GroundTruth> {
      await latency();
      requireUser();
      const b = store.batches.find((x) => x.id === batchId);
      if (!b) throw new ApiError(404, "No such batch");
      const batch = batchOf(b, Date.now());
      const clients = batch.runs.map((r) => {
        const planted = clientData(r.client_id).result.exceptions.length;
        const ok = r.status === "succeeded";
        return {
          client_id: r.client_id,
          run_id: r.id,
          status: r.status,
          planted,
          found: ok ? planted : 0,
          missing: ok ? [] : [`run ${r.status}`],
          extra: [],
          difference: r.difference,
          exact: ok,
        };
      });
      const planted = clients.reduce((a, c) => a + c.planted, 0);
      const found = clients.reduce((a, c) => a + c.found, 0);
      return { batch_id: batchId, planted, found, all_exact: clients.every((c) => c.exact), clients };
    },

    streamBatch(id, h) {
      const lastRun = new Map<string, string>();
      const lastSeq = new Map<string, number>();
      let lastBatch = "";
      let first = true;
      const tick = () => {
        const b = store.batches.find((x) => x.id === id);
        if (!b) return;
        const now = Date.now();
        const batch = batchOf(b, now);
        const { runs, ...rest } = batch;
        const bj = JSON.stringify(rest);
        if (bj !== lastBatch) {
          lastBatch = bj;
          h.onBatchUpdate?.(rest);
        }
        for (const r of runs) {
          const evs = visibleEvents(mustPlan(r.id), now);
          const since = lastSeq.get(r.id) ?? 0;
          if (!first) {
            for (const ev of evs) {
              if (ev.seq <= since) continue;
              let payload = ev.payload;
              if (["tool_result", "sandbox_created", "tool_call", "thought"].includes(ev.type)) {
                payload = Object.fromEntries(
                  Object.entries(ev.payload ?? {}).filter(([k]) => ["n", "tool", "exit_code", "duration_ms", "sandbox_id", "host"].includes(k)),
                );
              }
              h.onRunEvent?.({ run_id: r.id, client_id: r.client_id, seq: ev.seq, ts: ev.ts, type: ev.type, payload });
            }
          }
          lastSeq.set(r.id, evs.length ? evs[evs.length - 1].seq : since);
          const rj = JSON.stringify(r);
          if (rj !== lastRun.get(r.id)) {
            lastRun.set(r.id, rj);
            h.onRunUpdate?.(r);
          }
        }
        first = false;
      };
      const t0 = setTimeout(tick, 30);
      const iv = setInterval(tick, 250);
      return () => {
        clearTimeout(t0);
        clearInterval(iv);
      };
    },

    async run(id) {
      await latency();
      const u = requireUser();
      return detailOf(mustPlan(id), Date.now(), u);
    },

    async runEvents(id, after = 0) {
      await latency();
      requireUser();
      return visibleEvents(mustPlan(id), Date.now()).filter((e) => e.seq > after);
    },

    streamRun(id, after, h) {
      let sent = after;
      let lastRun = "";
      const lastReplay = new Map<string, string>();
      const tick = () => {
        const p = planFor(id);
        if (!p) return;
        const now = Date.now();
        const s = summarize(p, now);
        const rj = JSON.stringify(s);
        if (rj !== lastRun) {
          lastRun = rj;
          h.onRunUpdate?.(s);
        }
        for (const ev of visibleEvents(p, now)) {
          if (ev.seq <= sent) continue;
          sent = ev.seq;
          h.onRunEvent?.({ ...ev, run_id: id });
        }
        for (const r of store.replays.filter((x) => x.of === id)) {
          const rs = summarize(mustPlan(r.id), now);
          const j = JSON.stringify(rs);
          if (j !== lastReplay.get(r.id)) {
            lastReplay.set(r.id, j);
            h.onReplayUpdate?.(rs);
          }
        }
      };
      const t0 = setTimeout(tick, 30);
      const iv = setInterval(tick, 250);
      return () => {
        clearTimeout(t0);
        clearInterval(iv);
      };
    },

    async lines(id) {
      await latency();
      requireUser();
      const p = mustPlan(id);
      if (!isFinal(p, Date.now())) throw new ApiError(404, "lines.json is not available for this run");
      return p.data.lines;
    },

    async verifyRun(id) {
      await latency();
      requireUser();
      const evs = visibleEvents(mustPlan(id), Date.now());
      return { events: evs.length, chain_ok: true, head: evs.length ? (evs[evs.length - 1].sha256 ?? null) : null };
    },

    async rerun(id) {
      await latency();
      const u = requireRole("preparer", "admin");
      checkAutoResume();
      if (store.killSwitch) throw new ApiError(409, "The kill switch is on: new work is stopped.");
      const b = store.batches.find((x) => x.runs.some((r) => r.runId === id));
      if (!b) throw new ApiError(400, "Only a client run from a close can be re-run.");
      const old = b.runs.find((r) => r.runId === id) as StoredRun;
      const s0 = summarize(mustPlan(id), Date.now());
      if (s0.status === "queued" || s0.status === "running") throw new ApiError(400, "This client is still running.");
      if (s0.status === "succeeded") throw new ApiError(400, "Only a failed or stopped run can be re-run.");
      const busy = currentRuns(b).find((r) => r.clientId === old.clientId && r.runId !== id);
      if (busy) {
        const bs = summarize(mustPlan(busy.runId), Date.now());
        if (bs.status === "queued" || bs.status === "running") throw new ApiError(400, "A re-run for this client is already in progress.");
      }
      const entry: StoredRun = { clientId: old.clientId, runId: newId("run"), createdAt: Date.now(), createdBy: u.id, stoppedAt: null };
      b.runs.push(entry);
      appendAudit(store, u.email, "client_rerun_started", entry.runId, { rerun_of: id, batch: b.id });
      save();
      return summarize(mustPlan(entry.runId), Date.now());
    },

    async replay(id) {
      await latency();
      const u = requireRole("preparer", "reviewer", "admin");
      if (store.killSwitch) throw new ApiError(409, "The kill switch is on: new work is stopped.");
      const orig = mustPlan(id);
      const s = summarize(orig, Date.now());
      if (orig.kind !== "original" || s.status !== "succeeded") throw new ApiError(400, "Only a succeeded original run can be replayed.");
      const r: StoredReplay = { id: newId("rpl"), of: id, clientId: orig.clientId, createdAt: Date.now(), createdBy: u.id, stoppedAt: null };
      store.replays.push(r);
      appendAudit(store, u.email, "replay_started", r.id, { replay_of: id });
      save();
      return summarize(mustPlan(r.id), Date.now());
    },

    async approve(id, decision, comment) {
      await delay(250 + Math.random() * 200);
      const u = requireRole("reviewer", "admin");
      const p = mustPlan(id);
      const d = detailOf(p, Date.now(), u);
      if (!d.can.approve) throw new ApiError(403, d.can.reason_cannot_approve ?? "Cannot approve this run.");
      const ts = new Date().toISOString();
      const payload = { run_id: id, decision, reviewer_id: u.id, ts, outputs: p.data.hashes, comment: comment.slice(0, 2000) };
      const a: StoredApproval = {
        id: newId("apr"),
        run_id: id,
        reviewer_id: u.id,
        decision,
        comment: comment.slice(0, 2000),
        reviewer_name: u.name,
        reviewer_email: u.email,
        ts,
        signed_sha256: sha256Hex(`mock-session-secret:${JSON.stringify(payload)}`),
      };
      store.approvals.push(a);
      appendAudit(store, u.email, `run_${decision}`, id, { signed_sha256: a.signed_sha256, comment: comment.slice(0, 200) });
      save();
      const { run_id: _r, reviewer_id: _v, ...pub } = a;
      void _r;
      void _v;
      return pub;
    },

    async adminOverview(): Promise<AdminOverview> {
      await latency();
      requireRole("admin");
      const now = Date.now();
      const sandboxes = allPlans()
        .map((p) => ({ p, s: summarize(p, now) }))
        .filter(({ s }) => s.sandbox_state === "running")
        .map(({ p, s }) => {
          const created = p.events.find((e) => e.type === "sandbox_created");
          const createdAt = (created?.at ?? now) / 1000;
          const execs = p.events.filter((e) => e.at <= now && (e.type === "tool_result" || e.type === "replay_step")).length;
          return {
            id: s.sandbox_id as string,
            status: "running",
            image: "tieout-sandbox:latest",
            labels: {
              "arena.tenant": p.clientId,
              "arena.task": p.runId,
              "arena.batch": p.batchId ?? "",
              "arena.kind": p.kind,
            },
            limits: LIMITS,
            created_at: createdAt,
            expires_at: createdAt + LIMITS.ttl_s,
            exec_count: execs,
            host: MOCK_HOST,
          };
        });
      const today = new Date();
      today.setUTCHours(0, 0, 0, 0);
      let tin = 0;
      let tout = 0;
      let runsToday = 0;
      let replaysToday = 0;
      for (const p of allPlans()) {
        if (p.createdAt < today.getTime()) continue;
        const s = summarize(p, now);
        tin += s.tokens_in;
        tout += s.tokens_out;
        if (p.kind === "original") runsToday++;
        else replaysToday++;
      }
      const [pin, pout] = PRICES[MODEL];
      const cost = Math.round(((tin / 1e6) * pin + (tout / 1e6) * pout) * 10000) / 10000;
      const byModel: AdminOverview["usage"]["by_model"] = [];
      if (runsToday) byModel.push({ model: MODEL, tokens_in: tin, tokens_out: tout, cost_usd: cost, runs: runsToday });
      if (replaysToday) byModel.push({ model: "(replay, no model)", tokens_in: 0, tokens_out: 0, cost_usd: 0, runs: replaysToday });
      checkAutoResume();
      return {
        kill_switch: store.killSwitch,
        kill_switch_auto_resume_at: store.killSwitch && store.killSwitchUntil ? iso(store.killSwitchUntil) : null,
        runner: { host: MOCK_HOST, max: 16, accepting: !store.killSwitch, sandboxes },
        usage: {
          tokens_today: tin + tout,
          budget: 5_000_000,
          cost_today_usd: cost,
          runs_today: runsToday + replaysToday,
          by_model: byModel,
        },
        health: healthNow(),
        audit: [...store.audit].slice(-60).reverse(),
        audit_chain_ok: true,
      };
    },

    async killSwitch(enabled) {
      await delay(300);
      const u = requireRole("admin");
      store.killSwitch = enabled;
      store.killSwitchUntil = enabled ? Date.now() + 15 * 60 * 1000 : null;
      let destroyed = 0;
      let cancelled = 0;
      if (enabled) {
        const now = Date.now();
        for (const b of store.batches) {
          let touched = false;
          for (const entry of currentRuns(b)) {
            if (entry.stoppedAt) continue;
            const r = summarize(mustPlan(entry.runId), now);
            if (r.status !== "queued" && r.status !== "running") continue;
            cancelled++;
            if (r.sandbox_state === "running") destroyed++;
            entry.stoppedAt = now;
            touched = true;
          }
          if (touched) b.stoppedAt = now;
        }
        for (const r of store.replays) {
          if (r.stoppedAt !== null) continue;
          const s = summarize(mustPlan(r.id), now);
          if (s.status === "queued" || s.status === "running") {
            cancelled++;
            if (s.sandbox_state === "running") destroyed++;
            r.stoppedAt = now;
          }
        }
      }
      appendAudit(store, u.email, enabled ? "kill_switch_on" : "kill_switch_off", "system", { destroyed, cancelled_runs: cancelled });
      save();
      return { kill_switch: enabled, destroyed, cancelled_runs: cancelled, auto_resume_at: store.killSwitchUntil ? iso(store.killSwitchUntil) : null };
    },

    async warmup() {
      requireRole("admin");
      await delay(1100 + Math.random() * 400);
      audit("control-plane", "warmup", "sandbox", { ok: true });
      return { ok: true, ms: 1184, attestation_ok: true };
    },

    downloadUrl(runId, name) {
      return `#mock-download/${runId}/${name}`;
    },

    async download(runId, name, filename) {
      await latency();
      const u = requireUser();
      const p = mustPlan(runId);
      const d = detailOf(p, Date.now(), u);
      if (name === "ajes.csv") {
        if (!d.can.download_ajes) throw new ApiError(403, "Adjusting entries export only after a reviewer approves the run.");
        audit(u.email, "ajes_exported", runId, { sha256: p.data.hashes["ajes.csv"] });
        downloadBlob(ajesCsv(p.data), filename, "text/csv");
        return;
      }
      if (name === "evidence.zip") {
        // The mock cannot build a zip; ship the manifest the real pack contains.
        const evs = visibleEvents(p, Date.now());
        const manifest = {
          run_id: runId,
          client_id: p.clientId,
          period: PERIOD,
          status: d.status,
          recon_status: d.recon_status,
          inputs: d.inputs,
          outputs: Object.fromEntries(d.outputs.map((o) => [o.name, o.sha256])),
          event_chain_ok: true,
          event_chain_head: evs.length ? evs[evs.length - 1].sha256 : null,
          image_digest: d.image_digest,
          model: d.model_id,
          approvals: d.approvals,
          generated_at: new Date().toISOString(),
          note: "Mock mode: the real evidence.zip also holds every step's code, the event log, the attestation and the outputs.",
        };
        audit(u.email, "evidence_exported", runId, {});
        downloadBlob(JSON.stringify(manifest, null, 2), filename.replace(/\.zip$/, "-manifest.json"), "application/json");
        return;
      }
      if (!d.result) throw new ApiError(404, `${name} is not available for this run`);
      audit(u.email, "artifact_download", runId, { name, sha256: p.data.hashes[name] });
      if (name === "result.json") downloadBlob(JSON.stringify(d.result, null, 2), filename, "application/json");
      else if (name === "lines.json") downloadBlob(JSON.stringify(p.data.lines), filename, "application/json");
      else {
        // The mock has no real workpaper; ship a CSV of the summary so the flow can be exercised.
        const r = d.result;
        const rows = [
          ["Tieout workpaper (mock mode preview)", r.client_name, r.period],
          ["Balance per bank", r.bank_ending_balance],
          ["Adjusted bank balance", r.adjusted_bank_balance],
          ["Balance per books", r.gl_ending_balance],
          ["Adjusted book balance", r.adjusted_book_balance],
          ["Difference", r.difference],
        ];
        downloadBlob(rows.map((x) => x.join(",")).join("\n"), filename.replace(/\.xlsx$/, "-mock.csv"), "text/csv");
      }
    },
  };
  return api;
}
