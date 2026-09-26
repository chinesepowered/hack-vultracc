// Types for the Tieout API. Source of truth: docs/API.md.
// A few optional fields the server also sends are marked as optional extras.

export type Role = "preparer" | "reviewer" | "admin";

export interface User {
  id: string;
  email: string;
  name: string;
  role: Role;
  title: string;
}

export interface DemoAccount {
  email: string;
  password: string;
  name: string;
  role: Role;
  title: string;
  blurb: string;
}

export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "stopped";
export type ReconStatus = "reconciled" | "needs_review" | "unreconciled" | null;
export type ApprovalStatus = "pending" | "approved" | "rejected" | null;
export type SandboxState = "none" | "starting" | "running" | "destroyed";

export interface Badges {
  runtime: string | null; // "runsc" means gVisor
  network: string | null; // "none"
  readonly_rootfs: boolean | null;
  cpus: number | null;
  memory_mb: number | null;
  attestation_ok: boolean | null;
}

export interface RunSummary {
  id: string;
  batch_id: string | null;
  client_id: string;
  client_name: string;
  industry: string;
  kind: "original" | "replay";
  replay_of: string | null;
  status: RunStatus;
  recon_status: ReconStatus;
  approval_status: ApprovalStatus;
  step_count: number;
  matched_count: number | null;
  bank_line_count: number | null;
  exception_count: number | null;
  needs_review_count: number | null;
  aje_count: number | null;
  difference: string | null;
  sandbox_id: string | null;
  sandbox_host: string | null;
  sandbox_state: SandboxState;
  badges: Badges;
  summary: string | null;
  error: string | null;
  tokens_in: number;
  tokens_out: number;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  created_by_name: string | null;
  replay_match: boolean | null;
}

export interface BatchTotals {
  clients: number;
  queued: number;
  running: number;
  succeeded: number;
  failed: number;
  reconciled: number;
  needs_review: number;
  exceptions: number;
  ajes: number;
  approved: number;
}

export interface Batch {
  id: string;
  period: string;
  status: "running" | "completed" | "stopped";
  created_by_name: string;
  created_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  totals: BatchTotals;
  runs: RunSummary[];
}

export type BatchWithoutRuns = Omit<Batch, "runs">;

export interface Client {
  id: string;
  name: string;
  industry: string;
  materiality: string;
  gl_cash_account: string;
  latest_run: RunSummary | null;
}

export interface RunEvent {
  seq: number;
  ts: string;
  type: string;
  payload: any; // eslint-disable-line @typescript-eslint/no-explicit-any
  sha256?: string;
  prev_sha256?: string | null;
  run_id?: string;
}

export interface BatchRunEvent {
  run_id: string;
  client_id: string;
  seq: number;
  ts: string;
  type: string;
  payload: any; // eslint-disable-line @typescript-eslint/no-explicit-any
}

export interface AttestationCheck {
  id: string;
  ok: boolean;
  label: string;
  detail: string;
}

export interface Attestation {
  schema: string;
  ok: boolean;
  checks: AttestationCheck[];
  facts: {
    uid: number;
    gid: number;
    cap_eff: string;
    interfaces: string[];
    env_names: string[];
    kernel: string;
    cgroup: Record<string, string>;
    mounts: { target: string; fstype: string; mode: "ro" | "rw" }[];
    in_files: string[];
    image_build: { image: string; version: string; git_sha: string } | null;
    hostname: string;
    platform?: string;
    python?: string;
    cpu_count_visible?: number;
  };
}

export interface DockerSummary {
  Runtime: string;
  NetworkMode: string;
  ReadonlyRootfs: boolean;
  CapDrop: string[];
  CapAdd?: string[] | null;
  SecurityOpt: string[];
  Privileged: boolean;
  Memory: number;
  NanoCpus: number;
  PidsLimit: number;
  User: string;
  Image: string;
  ImageId?: string;
  ImageDigest: string;
  Mounts: { Destination: string; RW: boolean; Type: string }[];
  Tmpfs?: Record<string, string>;
  Env: string[];
  Host: string;
}

export interface SandboxLimits {
  cpus: number;
  memory_mb: number;
  pids: number;
  exec_timeout_s: number;
  ttl_s: number;
}

export interface FileRef {
  name: string;
  sha256: string;
  bytes: number;
  content_type?: string;
}

export interface Approval {
  id: string;
  decision: "approved" | "rejected";
  comment: string;
  reviewer_name: string;
  reviewer_email: string;
  ts: string;
  signed_sha256: string;
}

export interface UntrustedText {
  file: string;
  row: number;
  preview: string;
  reason: string;
  /** Second opinion from Nemotron 3.5 Content Safety on Vultr Serverless Inference. */
  classifier?: { model: string; verdict: "unsafe" | "safe" | "unknown" | "error"; raw: string };
}

export interface ReplayRef {
  id: string;
  status: RunStatus;
  replay_match: boolean | null;
  finished_at: string | null;
}

export interface RunDetail extends RunSummary {
  period: string;
  model_id: string | null;
  image_digest: string | null;
  attestation: Attestation | null;
  docker: DockerSummary | null;
  limits: SandboxLimits | null;
  inputs: FileRef[];
  outputs: FileRef[];
  result: ReconResult | null;
  memo_md: string | null;
  hashes: Record<string, string>;
  approvals: Approval[];
  replays: ReplayRef[];
  original: { id: string; hashes: Record<string, string> } | null;
  untrusted_text: UntrustedText[];
  can: {
    approve: boolean;
    replay: boolean;
    download_ajes: boolean;
    reason_cannot_approve: string | null;
  };
}

export type MatchMethod = "check_number" | "exact" | "fuzzy" | "prior_outstanding" | "manual";

export interface ReconMatch {
  bank_ref: string;
  gl_ref: string;
  method: MatchMethod;
  score: number;
  amount: string;
  bank_date: string;
  gl_date: string;
}

export interface ReconResult {
  client_id: string;
  client_name: string;
  period: string;
  period_end: string;
  run_id: string;
  prepared_by?: string;
  schema_version?: string;
  bank_opening_balance: string;
  bank_ending_balance: string;
  gl_opening_balance: string;
  gl_ending_balance: string;
  deposits_in_transit: OutstandingItem[];
  outstanding_checks: OutstandingItem[];
  adjusted_bank_balance: string;
  adjustments_total: string;
  unresolved_total: string;
  adjusted_book_balance: string;
  difference: string;
  bank_line_count: number;
  gl_line_count: number;
  matched_count: number;
  matches: ReconMatch[];
  exceptions: ReconException[];
  ajes: AJE[];
  inputs: FileRef[];
  status: "reconciled" | "needs_review" | "unreconciled";
}

export interface OutstandingItem {
  ref: string;
  date: string;
  description: string;
  amount: string;
  check_no: string | null;
  carried_from_prior: boolean;
}

export type ExceptionKind =
  | "outstanding_check"
  | "deposit_in_transit"
  | "bank_fee_unrecorded"
  | "interest_unrecorded"
  | "nsf_check"
  | "transposition"
  | "duplicate_entry"
  | "unidentified";

export interface ReconException {
  kind: ExceptionKind;
  amount: string;
  effect: string;
  side: "bank" | "book";
  bank_ref: string | null;
  gl_ref: string | null;
  check_no: string | null;
  date: string | null;
  description: string;
  aje_id: string | null;
  offset_account: string | null;
  related_bank_ref: string | null;
  needs_review: boolean;
  note: string;
}

export interface AJE {
  id: string;
  date: string;
  debit_account: string;
  debit_account_name: string;
  credit_account: string;
  credit_account_name: string;
  amount: string;
  memo: string;
  exception_kind: ExceptionKind;
  bank_ref: string | null;
  gl_ref: string | null;
}

export interface Lines {
  bank: BankLine[];
  gl: GlLine[];
}

export interface BankLine {
  ref: string;
  date: string;
  description: string;
  amount: string;
  check_no: string | null;
  row: number;
  match: string | null; // GL ref, or a prior-period ref (AUG-xxxx)
  method: string | null;
  exception: ExceptionKind | null;
}

export interface GlLine {
  ref: string;
  date: string;
  description: string;
  amount: string;
  check_no: string | null;
  row: number;
  counterparty: string | null;
  offset_account: string | null;
  match: string | null;
  method: string | null;
  exception: ExceptionKind | null;
}

export interface HealthCheck {
  ok: boolean;
  ms: number;
  detail: string;
  label?: string;
}

export interface Health {
  ok: boolean;
  checks: {
    inference: HealthCheck;
    database: HealthCheck;
    object_storage: HealthCheck;
    runner: HealthCheck;
  };
  version?: string;
  kill_switch?: boolean;
}

export interface AuditEntry {
  seq: number;
  ts: string;
  actor: string;
  action: string;
  target: string;
  detail: any; // eslint-disable-line @typescript-eslint/no-explicit-any
  sha256: string;
  prev_sha256: string | null;
}

export interface SystemInfo {
  firm: string;
  period: string;
  period_label: string;
  region: string;
  version: string;
  git_sha: string;
  models: { main: string; fast: string };
  kill_switch: boolean;
  /** Public deployment safeguard: the kill switch releases itself at this time. */
  kill_switch_auto_resume_at?: string | null;
  storage_backend?: string;
  limits: {
    max_concurrent_sandboxes: number;
    max_concurrent_runs: number;
    daily_token_budget: number;
    sandbox: SandboxLimits;
  };
}

export interface RunnerSandbox {
  id: string;
  status: string;
  labels: Record<string, string>;
  limits: SandboxLimits;
  created_at: string | number; // runner sends epoch seconds
  expires_at: string | number;
  exec_count: number;
  host: string;
  image?: string;
}

export interface AdminOverview {
  kill_switch: boolean;
  kill_switch_auto_resume_at?: string | null;
  runner: {
    host: string | null;
    max: number | null;
    accepting: boolean | null;
    sandboxes: RunnerSandbox[];
    error?: string;
  };
  usage: {
    tokens_today: number;
    budget: number;
    cost_today_usd: number;
    runs_today: number;
    by_model: { model: string; tokens_in: number; tokens_out: number; cost_usd: number; runs?: number }[];
  };
  health: Health;
  audit: AuditEntry[];
  audit_chain_ok: boolean;
}

export interface GroundTruthClient {
  client_id: string;
  run_id: string | null;
  status: string | null;
  planted: number;
  found: number;
  missing: string[];
  extra: string[];
  difference: string | null;
  exact: boolean;
}

/** GET /api/batches/{id}/ground-truth: the run's exceptions vs the generator's answer key (never shown to the model). */
export interface GroundTruth {
  batch_id: string;
  planted: number;
  found: number;
  all_exact?: boolean;
  clients: GroundTruthClient[];
}

/** GET /api/runs/{id}/verify */
export interface RunVerify {
  events: number;
  chain_ok: boolean;
  head: string | null;
}

export interface KillSwitchResult {
  kill_switch: boolean;
  destroyed: number;
  cancelled_runs: number;
  auto_resume_at?: string | null;
}

export interface WarmupResult {
  ok: boolean;
  ms: number;
  attestation_ok: boolean | null;
}

// ---------------------------------------------------------------- streams

export interface BatchStreamHandlers {
  onRunUpdate?: (run: RunSummary) => void;
  onRunEvent?: (ev: BatchRunEvent) => void;
  onBatchUpdate?: (batch: BatchWithoutRuns) => void;
  onError?: () => void;
}

export interface RunStreamHandlers {
  onRunEvent?: (ev: RunEvent) => void;
  onRunUpdate?: (run: RunSummary) => void;
  onReplayUpdate?: (run: RunSummary) => void;
  onError?: () => void;
}

export type Unsubscribe = () => void;

export type DownloadName = "workpaper.xlsx" | "result.json" | "lines.json" | "ajes.csv" | "evidence.zip";

export interface Api {
  demoAccounts(): Promise<DemoAccount[]>;
  login(email: string, password: string): Promise<User>;
  logout(): Promise<void>;
  me(): Promise<User | null>;
  system(): Promise<SystemInfo>;
  health(): Promise<Health>;
  clients(): Promise<Client[]>;
  createBatch(period: string): Promise<Batch>;
  latestBatch(): Promise<Batch | null>;
  batches(): Promise<BatchWithoutRuns[]>;
  batch(id: string): Promise<Batch>;
  groundTruth(batchId: string): Promise<GroundTruth>;
  streamBatch(id: string, handlers: BatchStreamHandlers): Unsubscribe;
  run(id: string): Promise<RunDetail>;
  runEvents(id: string, after?: number): Promise<RunEvent[]>;
  streamRun(id: string, after: number, handlers: RunStreamHandlers): Unsubscribe;
  lines(id: string): Promise<Lines>;
  verifyRun(id: string): Promise<RunVerify>;
  replay(id: string): Promise<RunSummary>;
  /** Start a fresh run for this client in the same batch (failed or stopped runs only). */
  rerun(id: string): Promise<RunSummary>;
  approve(id: string, decision: "approved" | "rejected", comment: string): Promise<Approval>;
  adminOverview(): Promise<AdminOverview>;
  killSwitch(enabled: boolean): Promise<KillSwitchResult>;
  warmup(): Promise<WarmupResult>;
  /** Start a browser download of a run file. */
  download(runId: string, name: DownloadName, filename: string): Promise<void>;
  /** A plain URL for the file (used as the href of download links). */
  downloadUrl(runId: string, name: DownloadName): string;
}
