# Tieout API contract

All endpoints are under `/api`, JSON unless noted. Auth is an HttpOnly session cookie set by `POST /api/auth/login`. Money values are strings with two decimals (`"1250.00"`), dates are ISO strings. Timestamps are ISO 8601 UTC.

Real sample payloads captured from live runs are in `docs/fixtures/` (`*.events.json`, `*.result.json`, `*.lines.json`, `*.memo.md`).

## Types (TypeScript)

```ts
type Role = "preparer" | "reviewer" | "admin";
interface User { id: string; email: string; name: string; role: Role; title: string }
interface DemoAccount { email: string; password: string; name: string; role: Role; title: string; blurb: string }

type RunStatus = "queued" | "running" | "succeeded" | "failed" | "stopped";
type ReconStatus = "reconciled" | "needs_review" | "unreconciled" | null;
type ApprovalStatus = "pending" | "approved" | "rejected" | null;

interface Badges {
  runtime: string | null;          // "runsc" means gVisor
  network: string | null;          // "none"
  readonly_rootfs: boolean | null;
  cpus: number | null;             // 1
  memory_mb: number | null;        // 1024
  attestation_ok: boolean | null;
}

interface RunSummary {
  id: string; batch_id: string | null; client_id: string; client_name: string; industry: string;
  kind: "original" | "replay"; replay_of: string | null;
  status: RunStatus; recon_status: ReconStatus; approval_status: ApprovalStatus;
  step_count: number;                      // sandbox steps executed so far (sniff + python)
  matched_count: number | null;            // live (parsed from step output) then final
  bank_line_count: number | null;
  exception_count: number | null; needs_review_count: number | null; aje_count: number | null;
  difference: string | null;
  sandbox_id: string | null; sandbox_host: string | null;
  sandbox_state: "none" | "starting" | "running" | "destroyed";
  badges: Badges;
  summary: string | null; error: string | null;
  tokens_in: number; tokens_out: number;
  started_at: string | null; finished_at: string | null; duration_ms: number | null;
  created_by_name: string | null;
  replay_match: boolean | null;            // replays only
  source?: "close" | "upload";             // "upload": started from uploaded files, outside the monthly close
}

interface BatchTotals { clients: number; queued: number; running: number; succeeded: number; failed: number;
  reconciled: number; needs_review: number; exceptions: number; ajes: number; approved: number }
interface Batch { id: string; period: string; status: "running" | "completed" | "stopped";
  created_by_name: string; created_at: string; finished_at: string | null; duration_ms: number | null;
  totals: BatchTotals; runs: RunSummary[] }

interface Client { id: string; name: string; industry: string; materiality: string; gl_cash_account: string;
  latest_run: RunSummary | null }

interface RunEvent { seq: number; ts: string; type: string; payload: any; sha256: string; prev_sha256: string | null }

interface AttestationCheck { id: string; ok: boolean; label: string; detail: string }
interface Attestation { schema: string; ok: boolean; checks: AttestationCheck[];
  facts: { uid: number; gid: number; cap_eff: string; interfaces: string[]; env_names: string[]; kernel: string;
           cgroup: Record<string, string>; mounts: {target: string; fstype: string; mode: "ro" | "rw"}[];
           in_files: string[]; image_build: {image: string; version: string; git_sha: string} | null; hostname: string } }
interface DockerSummary { Runtime: string; NetworkMode: string; ReadonlyRootfs: boolean; CapDrop: string[];
  SecurityOpt: string[]; Privileged: boolean; Memory: number; NanoCpus: number; PidsLimit: number; User: string;
  Image: string; ImageDigest: string; Mounts: {Destination: string; RW: boolean; Type: string}[]; Env: string[]; Host: string }

interface FileRef { name: string; sha256: string; bytes: number; content_type?: string }
interface Approval { id: string; decision: "approved" | "rejected"; comment: string; reviewer_name: string;
  reviewer_email: string; ts: string; signed_sha256: string }
interface UntrustedText { file: string; row: number; preview: string; reason: string;
  classifier?: { model: string; verdict: "unsafe" | "safe" | "unknown" | "error"; raw: string } }   // Nemotron 3.5 Content Safety second opinion

interface RunDetail extends RunSummary {
  period: string; model_id: string | null; image_digest: string | null;
  attestation: Attestation | null; docker: DockerSummary | null;
  limits: { cpus: number; memory_mb: number; pids: number; exec_timeout_s: number; ttl_s: number } | null;
  inputs: FileRef[];                 // files the sandbox could read (in /in, read-only)
  outputs: FileRef[];                // files that left the sandbox (validated, hashed, stored in Object Storage)
  result: ReconResult | null;        // result.json, see below
  memo_md: string | null;
  hashes: Record<string, string>;
  approvals: Approval[];
  replays: { id: string; status: RunStatus; replay_match: boolean | null; finished_at: string | null }[];
  original: { id: string; hashes: Record<string, string> } | null;   // set on replay runs
  untrusted_text: UntrustedText[];
  can: { approve: boolean; replay: boolean; download_ajes: boolean; reason_cannot_approve: string | null };
}

// result.json written by tieout_lib.write_outputs inside the sandbox (validated by the control plane)
interface ReconResult {
  client_id: string; client_name: string; period: string; period_end: string; run_id: string;
  bank_opening_balance: string; bank_ending_balance: string; gl_opening_balance: string; gl_ending_balance: string;
  deposits_in_transit: OutstandingItem[]; outstanding_checks: OutstandingItem[];
  adjusted_bank_balance: string; adjustments_total: string; unresolved_total: string;
  adjusted_book_balance: string; difference: string;
  bank_line_count: number; gl_line_count: number; matched_count: number;
  matches: { bank_ref: string; gl_ref: string; method: "check_number" | "exact" | "fuzzy" | "prior_outstanding" | "manual";
             score: number; amount: string; bank_date: string; gl_date: string }[];
  exceptions: ReconException[]; ajes: AJE[]; inputs: FileRef[];
  status: "reconciled" | "needs_review" | "unreconciled";
}
interface OutstandingItem { ref: string; date: string; description: string; amount: string; check_no: string | null; carried_from_prior: boolean }
type ExceptionKind = "outstanding_check" | "deposit_in_transit" | "bank_fee_unrecorded" | "interest_unrecorded"
                   | "nsf_check" | "transposition" | "duplicate_entry" | "unidentified";
interface ReconException { kind: ExceptionKind; amount: string; effect: string; side: "bank" | "book";
  bank_ref: string | null; gl_ref: string | null; check_no: string | null; date: string | null; description: string;
  aje_id: string | null; offset_account: string | null; related_bank_ref: string | null; needs_review: boolean; note: string }
interface AJE { id: string; date: string; debit_account: string; debit_account_name: string; credit_account: string;
  credit_account_name: string; amount: string; memo: string; exception_kind: ExceptionKind; bank_ref: string | null; gl_ref: string | null }

// lines.json (for the matching view)
interface Lines { bank: BankLine[]; gl: GlLine[] }
interface BankLine { ref: string; date: string; description: string; amount: string; check_no: string | null; row: number;
  match: string | null; method: string | null; exception: ExceptionKind | null }   // match = GL ref, or prior-period ref (AUG-xxxx)
interface GlLine { ref: string; date: string; description: string; amount: string; check_no: string | null; row: number;
  counterparty: string | null; offset_account: string | null; match: string | null; method: string | null; exception: ExceptionKind | null }

interface HealthCheck { ok: boolean; ms: number; detail: string }
interface Health { ok: boolean; checks: { inference: HealthCheck; database: HealthCheck; object_storage: HealthCheck; runner: HealthCheck } }
interface AuditEntry { seq: number; ts: string; actor: string; action: string; target: string; detail: any; sha256: string; prev_sha256: string | null }
```

## Run event types (`RunEvent.type` and payload)

| type | payload |
|---|---|
| `run_started` | `{client_id, model, fallback_model, max_tool_calls, inputs: FileRef[]}` |
| `untrusted_text` | `UntrustedText` (control plane scanned the inputs and found instruction-like text) |
| `sandbox_created` | `{sandbox_id, host, attestation: Attestation, docker: DockerSummary, limits, inputs: FileRef[]}` |
| `llm` | `{call, model, tokens_in, tokens_out, latency_ms, finish_reason}` |
| `thought` | `{text, reasoning}` (the model's short note before a tool call) |
| `tool_call` | `{n, tool: "sniff_file" | "run_python" | "finish", args}`; args is `{name}` for sniff_file, `{purpose, code}` for run_python, `{summary, memo_markdown}` for finish (n is null for finish) |
| `tool_result` | `{n, tool, exit_code, duration_ms, timed_out, stdout, stderr, out_files: {path, size, sha256}[], rejected_out_files}` |
| `progress` | `{matched, total}` (parsed from step output, for live tiles) |
| `validation` | `{ok, errors: string[]}` (control plane checked result.json) |
| `stored` | `{artifacts: FileRef[]}` (outputs uploaded to Vultr Object Storage) |
| `sandbox_destroyed` | `{sandbox_id}` |
| `run_finished` | `{status, recon_status, error, duration_ms, tool_calls, llm_calls, tokens_in, tokens_out, hashes, difference, summary}` |
| `replay_step` | `{n, tool, argv, exit_code, duration_ms, stdout, stderr}` (replay runs) |
| `replay_compared` | `{match: boolean, files: {name, original, replay, match}[]}` (replay runs) |
| `stopped` | `{reason}` (kill switch or budget) |

## Endpoints

Auth
- `GET /api/demo-accounts` -> `DemoAccount[]` (public; shown on the login page)
- `POST /api/auth/login` `{email, password}` -> `User` (sets cookie)
- `POST /api/auth/logout` -> `{ok}`
- `GET /api/me` -> `User` (401 when signed out)

Firm and clients
- `GET /api/system` -> `{firm, period, period_label, region, version, git_sha, models: {main, fast}, kill_switch, limits: {max_concurrent_sandboxes, max_concurrent_runs, daily_token_budget, sandbox: {cpus, memory_mb, pids, exec_timeout_s, ttl_s}}}`
- `GET /api/clients` -> `Client[]`
- `GET /api/clients/{id}` -> `Client & {runs: RunSummary[]}`

Batches ("Close September")
- `POST /api/batches` `{period: "2026-09"}` -> `Batch` (preparer or admin; rate limited; 409 if the kill switch is on; 429 on limits)
- `GET /api/batches/latest` -> `Batch | null` (most recent batch)
- `GET /api/batches` -> recent batches (without runs)
- `GET /api/batches/{id}` -> `Batch` (newest run per client)
- `GET /api/batches/{id}/ground-truth` -> planted vs found per client (answer key never shown to the model)
- `GET /api/batches/{id}/stream` -> SSE (never compressed by the proxy: compression buffers small event writes). Events: `run_update` (data: `RunSummary`), `run_event` (data: `{run_id, client_id, seq, ts, type, payload}` with large fields trimmed), `batch_update` (data: `Batch` without runs). Comment heartbeats every 15 s.

Runs
- `GET /api/runs/{id}` -> `RunDetail`
- `GET /api/runs/{id}/events?after=0` -> `RunEvent[]`
- `GET /api/runs/{id}/stream?after=<seq>` -> SSE. Events: `run_event` (data: `RunEvent`), `run_update` (data: `RunSummary`)
- `GET /api/runs/{id}/lines` -> `Lines`
- `GET /api/runs/{id}/inputs/{name}` -> the exact input file the sandbox could read (hash-verified), e.g. `bank_statement.csv`
- `GET /api/runs/{id}/artifacts/{name}` -> file download (redirect to a short-lived presigned Object Storage URL). Names: `workpaper.xlsx`, `result.json`, `lines.json`. `ajes.csv` is refused here.
- `GET /api/runs/{id}/ajes.csv` -> CSV download, only after a reviewer approved the run (403 before)
- `POST /api/runs/{id}/replay` -> `RunSummary` of the new replay run (fresh sandbox, same code, same inputs, no LLM)
- `POST /api/runs/{id}/rerun` -> `RunSummary` of a new run for the same client in the same batch (preparer or admin; for failed or stopped runs; the batch then shows the newest run per client)
- `POST /api/runs/{id}/approve` `{decision: "approved" | "rejected", comment}` -> `Approval` (reviewer or admin; the approver must not be the user who started the batch: maker-checker, 403 with a clear message)
- `GET /api/runs/{id}/evidence.zip` -> zip (P1)

Reconcile your own files
- `POST /api/uploads` `{name, period_end: "2026-09-30", files: {bank_statement, gl_cash_detail, prior_outstanding?}}` (base64 file contents) -> `RunSummary` of a new run with `batch_id: null` and `source: "upload"` (preparer or admin). Each file at most 512 KB and 5,000 lines, text, delimited; Windows-1252 is converted to UTF-8. 400 with a clear message on bad input, 409 if the kill switch is on or 3 uploads are already running, 429 past 6 per hour per network or per user. Upload clients get ids `upload-<hex>` and never join a close or `GET /api/clients`.
- `GET /api/uploads` -> `RunSummary[]` (the 20 most recent upload runs)
- `GET /api/samples/{name}` -> a demo client's input file to edit and upload back: `bank_statement.csv`, `gl_cash_detail.csv`, `prior_outstanding.csv` (signed in; the answer key is never served)

Admin (admin role)
- `GET /api/admin/overview` -> `{kill_switch, runner: {host, max, accepting, sandboxes: {id, status, labels, limits, created_at, expires_at, exec_count, host}[]}, usage: {tokens_today, budget, cost_today_usd, runs_today, by_model: {model, tokens_in, tokens_out, cost_usd}[]}, health: Health, audit: AuditEntry[], audit_chain_ok: boolean}`
- `POST /api/admin/kill-switch` `{enabled: boolean}` -> `{kill_switch, destroyed, cancelled_runs}`
- `POST /api/admin/warmup` -> `{ok, ms, attestation_ok, hosts, failed_hosts}` (warms every sandbox host; succeeds while at least one host works)

Health
- `GET /api/health` -> `Health` (public)
