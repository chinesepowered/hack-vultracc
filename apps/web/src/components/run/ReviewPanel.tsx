import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2Icon, ClockIcon, DownloadIcon, Loader2Icon, RepeatIcon, ScaleIcon, UserCheckIcon, XCircleIcon } from "lucide-react";
import { api } from "@/api";
import type { RunDetail } from "@/api/types";
import { Hash } from "@/components/hash";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { qk, useAuthActions, useDemoAccounts, useMe } from "@/hooks/queries";
import { firstName, formatDateTime, formatMoney, sumMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

export function useDownloadAjes(run: RunDetail) {
  return useMutation({
    mutationFn: () => api.download(run.id, "ajes.csv", `${run.client_id}-${run.period}-ajes.csv`),
    onSuccess: () => toast.success("AJE CSV downloaded", { description: "Ready to import into QuickBooks, Xero, or NetSuite." }),
    onError: (e: unknown) => toast.error("AJE export refused", { description: e instanceof Error ? e.message : String(e) }),
  });
}

export function ApprovalBanner({ run }: { run: RunDetail }) {
  const approval = run.approvals[run.approvals.length - 1];
  const download = useDownloadAjes(run);
  if (!approval) return null;
  const approved = approval.decision === "approved";
  return (
    <Card
      className={cn("overflow-hidden border", approved ? "border-emerald-200" : "border-red-200")}
      data-testid="approval-banner"
      data-decision={approval.decision}
    >
      <div className={cn("flex items-start gap-3 px-5 py-4", approved ? "bg-emerald-50" : "bg-red-50")}>
        {approved ? <CheckCircle2Icon className="mt-0.5 size-5 shrink-0 text-emerald-600" /> : <XCircleIcon className="mt-0.5 size-5 shrink-0 text-red-600" />}
        <div className="min-w-0">
          <div className={cn("text-[14px] font-semibold", approved ? "text-emerald-900" : "text-red-900")}>
            {approved ? "Approved" : "Rejected"} by {approval.reviewer_name}
          </div>
          <div className={cn("text-[12px]", approved ? "text-emerald-800/80" : "text-red-800/80")}>{formatDateTime(approval.ts)}</div>
          {approval.comment && <div className={cn("mt-1 text-[13px] leading-relaxed", approved ? "text-emerald-900/80" : "text-red-900/80")}>"{approval.comment}"</div>}
        </div>
      </div>
      <div className="space-y-3 px-5 py-4">
        <div>
          <div className="text-[11px] font-semibold tracking-wide text-gray-500 uppercase">Signed approval</div>
          <div className="mt-1 rounded-md border border-gray-200 bg-gray-50 px-2.5 py-2">
            <Hash value={approval.signed_sha256} full className="w-full" />
          </div>
          <div className="mt-1 text-[11px] leading-relaxed text-gray-500">
            HMAC over the run id, decision, reviewer, time, comment and the SHA-256 of every output. Recorded in the hash-chained audit log.
          </div>
        </div>
        {approved && (
          <div className="rounded-lg border border-gray-200 p-3">
            <Button className="w-full" onClick={() => download.mutate()} disabled={download.isPending} data-testid="approval-download-ajes">
              {download.isPending ? <Loader2Icon className="animate-spin" /> : <DownloadIcon />}
              Download AJE CSV
            </Button>
            <div className="mt-2 text-center text-[11.5px] text-gray-500">Import into QuickBooks, Xero, or NetSuite. The agent never posts.</div>
          </div>
        )}
      </div>
    </Card>
  );
}

export function ReviewPanel({ run }: { run: RunDetail }) {
  const me = useMe();
  const qc = useQueryClient();
  const accounts = useDemoAccounts();
  const { switchTo } = useAuthActions();
  const [comment, setComment] = useState("");
  const [switching, setSwitching] = useState(false);

  const decide = useMutation({
    mutationFn: (decision: "approved" | "rejected") => api.approve(run.id, decision, comment.trim()),
    onSuccess: (a) => {
      toast.success(a.decision === "approved" ? "Adjusting entries approved" : "Run rejected", {
        description: a.decision === "approved" ? "The AJE CSV is now available for import." : "The preparer will see your comment.",
      });
      setComment("");
      void qc.invalidateQueries({ queryKey: qk.run(run.id), exact: true });
      void qc.invalidateQueries({ queryKey: qk.latestBatch });
    },
    onError: (e: unknown) => {
      toast.error("Could not record the decision", { description: e instanceof Error ? e.message : String(e) });
      void qc.invalidateQueries({ queryKey: qk.run(run.id), exact: true });
    },
  });

  if (run.kind === "replay") return null;
  if (run.approvals.length) return <ApprovalBanner run={run} />;

  const result = run.result;
  const ajeTotal = result ? sumMoney(result.ajes.map((a) => a.amount)) : "0.00";
  const flagged = result?.exceptions.filter((e) => e.needs_review).length ?? 0;
  const role = me.data?.role;
  const reviewer = accounts.data?.find((a) => a.role === "reviewer");

  if (run.status !== "succeeded") {
    return (
      <Card className="px-5 py-4" data-testid="review-panel" data-state="waiting">
        <div className="flex items-center gap-2 text-[14px] font-semibold text-gray-900">
          <ScaleIcon className="size-4 text-gray-400" /> Review
        </div>
        <div className="mt-1 text-[12.5px] text-gray-500">
          {run.status === "failed" || run.status === "stopped"
            ? "This run did not produce a valid result, so there is nothing to approve."
            : "Review opens when the run finishes and result.json validates."}
        </div>
      </Card>
    );
  }

  const header = (
    <div className="flex items-start justify-between gap-3">
      <div>
        <div className="flex items-center gap-2 text-[14px] font-semibold text-gray-900">
          <UserCheckIcon className="size-4 text-indigo-600" /> Reviewer approval
        </div>
        <div className="mt-0.5 text-[12px] text-gray-500">Nothing is exported until a reviewer signs off.</div>
      </div>
      <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800">
        <ClockIcon className="size-3" /> Pending
      </span>
    </div>
  );

  const facts = (
    <div className="mt-3 grid grid-cols-3 gap-2 rounded-lg bg-gray-50 px-3 py-2.5 text-center">
      <div>
        <div className="text-[11px] text-gray-500">Proposed AJEs</div>
        <div className="money text-[15px] font-semibold text-gray-900">{result?.ajes.length ?? 0}</div>
      </div>
      <div>
        <div className="text-[11px] text-gray-500">Total</div>
        <div className="money text-[15px] font-semibold text-gray-900">{formatMoney(ajeTotal)}</div>
      </div>
      <div>
        <div className="text-[11px] text-gray-500">Flagged</div>
        <div className={cn("money text-[15px] font-semibold", flagged ? "text-amber-700" : "text-gray-900")}>{flagged}</div>
      </div>
    </div>
  );

  if (!run.can.approve) {
    const makerChecker = (run.can.reason_cannot_approve ?? "").toLowerCase().includes("maker-checker");
    return (
      <Card className="px-5 py-4" data-testid="review-panel" data-state="blocked">
        {header}
        {facts}
        <div
          className={cn("mt-3 rounded-lg border px-3 py-2.5 text-[12.5px] leading-relaxed", makerChecker ? "border-indigo-200 bg-indigo-50/60 text-indigo-950" : "border-gray-200 bg-white text-gray-600")}
          data-testid="cannot-approve-reason"
        >
          {makerChecker && <div className="mb-0.5 font-semibold">Maker-checker</div>}
          {run.can.reason_cannot_approve ?? "Waiting for a reviewer."}
        </div>
        {role === "preparer" && reviewer && (
          <Button
            variant="outline"
            className="mt-3 w-full"
            disabled={switching}
            data-testid="review-switch-reviewer"
            onClick={async () => {
              setSwitching(true);
              try {
                const u = await switchTo(reviewer);
                toast.success(`Signed in as ${u.name}`, { description: "Reviewer role" });
              } catch (e) {
                toast.error("Could not switch accounts", { description: e instanceof Error ? e.message : String(e) });
              } finally {
                setSwitching(false);
              }
            }}
          >
            {switching ? <Loader2Icon className="animate-spin" /> : <RepeatIcon />} Switch to {firstName(reviewer.name)} (Reviewer)
          </Button>
        )}
      </Card>
    );
  }

  return (
    <Card className="px-5 py-4" data-testid="review-panel" data-state="open">
      {header}
      {facts}
      <div className="mt-3 space-y-1.5">
        <Label htmlFor="approve-comment">Comment</Label>
        <Textarea
          id="approve-comment"
          data-testid="approve-comment"
          placeholder="What did you check? For example: NSF and transposition entries agree to the bank detail."
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={3}
          maxLength={2000}
        />
      </div>
      <div className="mt-3 grid grid-cols-[1fr_auto] gap-2">
        <Button variant="success" size="lg" onClick={() => decide.mutate("approved")} disabled={decide.isPending} data-testid="approve-button">
          {decide.isPending && decide.variables === "approved" ? <Loader2Icon className="animate-spin" /> : <CheckCircle2Icon />}
          Approve {result?.ajes.length ? `${result.ajes.length} entries` : "reconciliation"}
        </Button>
        <Button variant="outline" size="lg" onClick={() => decide.mutate("rejected")} disabled={decide.isPending} data-testid="reject-button">
          {decide.isPending && decide.variables === "rejected" ? <Loader2Icon className="animate-spin" /> : <XCircleIcon />}
          Reject
        </Button>
      </div>
      {flagged > 0 && (
        <div className="mt-2 text-[11.5px] leading-relaxed text-amber-800">
          {flagged} item{flagged > 1 ? "s are" : " is"} flagged for investigation. Approving signs off the proposed entries; the flagged item stays open.
        </div>
      )}
    </Card>
  );
}
