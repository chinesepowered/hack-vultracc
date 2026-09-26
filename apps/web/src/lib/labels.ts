import type { ApprovalStatus, ExceptionKind, ReconException, ReconStatus, RunStatus, SandboxState } from "@/api/types";

export const EXCEPTION_LABEL: Record<ExceptionKind, string> = {
  outstanding_check: "Outstanding check",
  deposit_in_transit: "Deposit in transit",
  bank_fee_unrecorded: "Bank fee",
  interest_unrecorded: "Interest",
  nsf_check: "NSF check",
  transposition: "Transposition",
  duplicate_entry: "Duplicate entry",
  unidentified: "Unidentified",
};

/** Compact labels for dense views such as the matching view. */
export const EXCEPTION_SHORT: Record<ExceptionKind, string> = {
  outstanding_check: "Outstanding",
  deposit_in_transit: "In transit",
  bank_fee_unrecorded: "Bank fee",
  interest_unrecorded: "Interest",
  nsf_check: "NSF",
  transposition: "Transposed",
  duplicate_entry: "Duplicate",
  unidentified: "Unidentified",
};

export const EXCEPTION_DESCRIPTION: Record<ExceptionKind, string> = {
  outstanding_check: "Check in the ledger that the bank had not cleared by period end. Timing item, no entry.",
  deposit_in_transit: "Deposit recorded in the ledger at month end that the bank posts next period. Timing item, no entry.",
  bank_fee_unrecorded: "Bank service charge not yet in the ledger. Entry: Dr Bank Fees, Cr Cash.",
  interest_unrecorded: "Interest earned not yet in the ledger. Entry: Dr Cash, Cr Interest Income.",
  nsf_check: "Customer check returned unpaid. Entry: Dr Accounts Receivable, Cr Cash.",
  transposition: "Ledger amount has swapped digits; the difference is divisible by 9. Correcting entry for the difference.",
  duplicate_entry: "The same ledger entry was posted twice. Reversing entry.",
  unidentified: "Bank item with no ledger match and no obvious cause. Flagged for a human to investigate.",
};

/** Timing items explain the bank side; errors need an adjusting entry; unidentified needs a human. */
export type ExceptionTone = "timing" | "error" | "review";

export function exceptionTone(kind: ExceptionKind | null | undefined): ExceptionTone {
  if (kind === "outstanding_check" || kind === "deposit_in_transit") return "timing";
  if (kind === "unidentified") return "review";
  return "error";
}

export function treatmentLabel(e: ReconException): string {
  if (e.needs_review || e.kind === "unidentified") return "Flagged for review";
  if (e.aje_id) return `Adjusting entry ${e.aje_id}`;
  if (exceptionTone(e.kind) === "timing") return e.kind === "outstanding_check" ? "Timing: clears next period" : "Timing: bank posts next period";
  return "No entry";
}

export type Tone = "neutral" | "running" | "success" | "warning" | "danger" | "muted";

export interface StatusDisplay {
  label: string;
  tone: Tone;
}

export function runStatusDisplay(
  status: RunStatus,
  recon: ReconStatus,
  sandbox?: SandboxState,
  kind: "original" | "replay" = "original",
  replayMatch: boolean | null = null,
): StatusDisplay {
  if (status === "queued") return { label: "Queued", tone: "muted" };
  if (status === "running") {
    if (sandbox === "starting" || sandbox === "none") return { label: "Starting sandbox", tone: "running" };
    return { label: kind === "replay" ? "Replaying" : "Running", tone: "running" };
  }
  if (status === "failed") return { label: "Failed", tone: "danger" };
  if (status === "stopped") return { label: "Stopped", tone: "danger" };
  // succeeded
  if (kind === "replay") {
    if (replayMatch === true) return { label: "Reproducible", tone: "success" };
    if (replayMatch === false) return { label: "Hashes differ", tone: "danger" };
    return { label: "Replayed", tone: "success" };
  }
  if (recon === "reconciled") return { label: "Reconciled", tone: "success" };
  if (recon === "needs_review") return { label: "Needs review", tone: "warning" };
  if (recon === "unreconciled") return { label: "Unreconciled", tone: "danger" };
  return { label: "Finished", tone: "neutral" };
}

export function approvalDisplay(a: ApprovalStatus): StatusDisplay | null {
  if (a === "approved") return { label: "Approved", tone: "success" };
  if (a === "rejected") return { label: "Rejected", tone: "danger" };
  if (a === "pending") return { label: "Awaiting approval", tone: "warning" };
  return null;
}

export const TOOL_LABEL: Record<string, string> = {
  sniff_file: "Inspect file",
  run_python: "Run Python",
  finish: "Finish",
};

export const ROLE_LABEL: Record<string, string> = {
  preparer: "Preparer",
  reviewer: "Reviewer",
  admin: "Admin",
};

export const HEALTH_LABEL: Record<string, string> = {
  inference: "Vultr Serverless Inference",
  database: "Vultr Managed PostgreSQL",
  object_storage: "Vultr Object Storage",
  runner: "Sandbox runner (gVisor host)",
};

export const RUN_FILE_ORDER = ["result.json", "workpaper.xlsx", "ajes.csv", "lines.json"];

/** Friendly names for model ids shown in the UI. */
export function modelName(id: string | null | undefined): string {
  if (!id) return "";
  const m = id.toLowerCase();
  if (m.includes("nemotron") && m.includes("safety")) return "Nemotron 3.5 Content Safety";
  if (m === "glm-5.3") return "GLM 5.3";
  if (m === "glm-5.3-flash") return "GLM 5.3 Flash";
  return id;
}
