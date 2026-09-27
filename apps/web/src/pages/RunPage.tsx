import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeftIcon,
  CircleAlertIcon,
  DownloadIcon,
  FileArchiveIcon,
  FileSpreadsheetIcon,
  GitCompareArrowsIcon,
  Loader2Icon,
  LinkIcon,
  OctagonAlertIcon,
  RotateCwIcon,
  SearchXIcon,
  UnlinkIcon,
} from "lucide-react";
import { api, ApiError } from "@/api";
import type { Attestation, DockerSummary, RunDetail, RunEvent, SandboxLimits } from "@/api/types";
import { Difference } from "@/components/money";
import { BlastRadius } from "@/components/run/BlastRadius";
import { MatchingView } from "@/components/run/MatchingView";
import { ReconSummary } from "@/components/run/ReconSummary";
import { filesFromHashes, ReplayComparison, ReplayDialog, type CompareFile } from "@/components/run/Replay";
import { ReviewPanel, useDownloadAjes } from "@/components/run/ReviewPanel";
import { RunTabs } from "@/components/run/RunTabs";
import { Timeline } from "@/components/run/Timeline";
import { Hash } from "@/components/hash";
import { Alert, EmptyState, ErrorState } from "@/components/states";
import { StatusPill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Hint } from "@/components/ui/tooltip";
import { isTerminal, qk, useLines, useMe, useRun, useRunEvents, useRunLive, useRunVerify } from "@/hooks/queries";
import { formatDuration, formatInt, shortId } from "@/lib/format";
import { approvalDisplay, runStatusDisplay } from "@/lib/labels";
import { cn } from "@/lib/utils";

function useViewportHeight() {
  const [h, setH] = useState(() => (typeof window === "undefined" ? 900 : window.innerHeight));
  useEffect(() => {
    const on = () => setH(window.innerHeight);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return h;
}

function Stat({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0 px-4 first:pl-0", className)}>
      <div className="text-[11px] font-medium whitespace-nowrap text-gray-500">{label}</div>
      <div className="mt-0.5 truncate text-[14px] font-semibold text-gray-900">{children}</div>
    </div>
  );
}

function periodLabel(p: string | undefined) {
  if (p === "2026-09") return "September 2026";
  return p ?? "";
}

function RunHeader({ run, onReplay, replayPending }: { run: RunDetail; onReplay: () => void; replayPending: boolean }) {
  const me = useMe();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const canRerun =
    run.kind === "original" && !!run.batch_id && (run.status === "failed" || run.status === "stopped") && (me.data?.role === "preparer" || me.data?.role === "admin");
  const rerun = useMutation({
    mutationFn: () => api.rerun(run.id),
    onSuccess: (fresh) => {
      toast.success(`Re-running ${fresh.client_name}`, { description: "A fresh sandbox with the same inputs." });
      void qc.invalidateQueries({ queryKey: qk.latestBatch });
      navigate(`/runs/${fresh.id}`);
    },
    onError: (e: unknown) => toast.error("Re-run refused", { description: e instanceof Error ? e.message : String(e) }),
  });
  const display = runStatusDisplay(run.status, run.recon_status, run.sandbox_state, run.kind, run.replay_match);
  const approval = approvalDisplay(run.approval_status);
  const running = run.status === "running" || run.status === "queued";
  const ajes = useDownloadAjes(run);
  const workpaper = useMutation({
    mutationFn: () => api.download(run.id, "workpaper.xlsx", `${run.client_id}-${run.period}-workpaper.xlsx`),
    onError: (e: unknown) => toast.error("Download failed", { description: e instanceof Error ? e.message : String(e) }),
  });
  const evidence = useMutation({
    mutationFn: () => api.download(run.id, "evidence.zip", `${run.client_id}-${run.period}-${run.id}-evidence.zip`),
    onSuccess: () => toast.success("Evidence pack downloaded", { description: "Input hashes, every step's code, the event log, attestation, approvals and manifest." }),
    onError: (e: unknown) => toast.error("Evidence pack unavailable", { description: e instanceof Error ? e.message : String(e) }),
  });
  const hasResult = run.status === "succeeded" && !!run.result;
  const finished = isTerminal(run.status);
  const ajeReason = run.can.download_ajes
    ? null
    : run.kind === "replay"
      ? "AJEs export from the approved original run."
      : run.approval_status === "rejected"
        ? "The reviewer rejected this run, so there is nothing to export."
        : run.status !== "succeeded"
          ? "Available once the run finishes and a reviewer approves it."
          : "Available after a reviewer approves the adjusting entries. The agent never posts.";
  const replayReason = run.can.replay
    ? null
    : run.kind === "replay"
      ? "This is already a replay. Replay the original run."
      : "Replay is available once the run has succeeded.";

  return (
    <Card className="px-5 py-4" data-testid="run-header" data-run-id={run.id} data-kind={run.kind}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link to={run.kind === "replay" && run.replay_of ? `/runs/${run.replay_of}` : "/"} className="inline-flex items-center gap-1 text-[12px] font-medium text-gray-500 hover:text-gray-900">
            <ArrowLeftIcon className="size-3.5" /> {run.kind === "replay" ? "Back to the original run" : "September close"}
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-2.5">
            <h1 className="text-[22px] font-semibold tracking-tight text-gray-900">
              {run.kind === "replay" ? `Replay: ${run.client_name}` : run.client_name}
            </h1>
            <StatusPill tone={display.tone} spinning={running} size="lg" data-testid="run-status" data-status={run.status} data-recon={run.recon_status ?? ""}>
              {display.label}
            </StatusPill>
            {approval && run.kind === "original" && (
              <StatusPill tone={approval.tone} size="lg" data-testid="run-approval" data-approval={run.approval_status ?? ""}>
                {approval.label}
              </StatusPill>
            )}
          </div>
          <div className="mt-1 text-[13px] text-gray-500">
            {run.industry} · {periodLabel(run.period)} · <span className="mono text-[12px]">{run.id}</span>
            {run.created_by_name ? ` · started by ${run.created_by_name}` : ""}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canRerun && (
            <Button onClick={() => rerun.mutate()} disabled={rerun.isPending} data-testid="rerun-button">
              {rerun.isPending ? <Loader2Icon className="animate-spin" /> : <RotateCwIcon />}
              Re-run
            </Button>
          )}
          <Hint label={replayReason} wrap={!!replayReason}>
            <Button variant="outline" onClick={onReplay} disabled={!run.can.replay || replayPending} data-testid="replay-button">
              {replayPending ? <Loader2Icon className="animate-spin" /> : <GitCompareArrowsIcon />}
              Replay
            </Button>
          </Hint>
          <Hint label={hasResult ? "The workpaper written by the sandbox: Summary with live formulas, Matches, Exceptions, AJEs, Inputs." : "Available once the run finishes."} wrap={!hasResult}>
            <Button variant="outline" onClick={() => workpaper.mutate()} disabled={!hasResult || workpaper.isPending} data-testid="download-workpaper">
              {workpaper.isPending ? <Loader2Icon className="animate-spin" /> : <FileSpreadsheetIcon />}
              Workpaper .xlsx
            </Button>
          </Hint>
          <Hint
            label={finished ? "Zip for auditors: input hashes, every step's code, the hash-chained event log, attestation, approvals and a manifest." : "Available once the run finishes."}
            wrap={!finished}
          >
            <Button variant="outline" onClick={() => evidence.mutate()} disabled={!finished || evidence.isPending} data-testid="download-evidence">
              {evidence.isPending ? <Loader2Icon className="animate-spin" /> : <FileArchiveIcon />}
              Evidence pack
            </Button>
          </Hint>
          <Hint label={ajeReason} wrap={!!ajeReason}>
            <Button onClick={() => ajes.mutate()} disabled={!run.can.download_ajes || ajes.isPending} data-testid="download-ajes" data-enabled={String(run.can.download_ajes)}>
              {ajes.isPending ? <Loader2Icon className="animate-spin" /> : <DownloadIcon />}
              AJE CSV
            </Button>
          </Hint>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-stretch divide-x divide-gray-200 border-t border-gray-100 pt-3.5">
        <Stat label="Difference">{run.difference !== null ? <Difference value={run.difference} /> : <span className="font-normal text-gray-400">Pending</span>}</Stat>
        <Stat label="Matched">
          {run.matched_count !== null && run.bank_line_count ? (
            <span className="money">
              {formatInt(run.matched_count)} <span className="font-normal text-gray-400">of {formatInt(run.bank_line_count)}</span>
            </span>
          ) : (
            <span className="font-normal text-gray-400">{running ? "Matching" : "n/a"}</span>
          )}
        </Stat>
        <Stat label="Exceptions">
          {run.exception_count !== null ? (
            <span className="money">
              {run.exception_count}
              {!!run.needs_review_count && <span className="ml-1.5 text-[12px] font-medium text-amber-700">{run.needs_review_count} for review</span>}
            </span>
          ) : (
            <span className="font-normal text-gray-400">{running ? "..." : "n/a"}</span>
          )}
        </Stat>
        <Stat label="Proposed AJEs">{run.aje_count !== null ? <span className="money">{run.aje_count}</span> : <span className="font-normal text-gray-400">{running ? "..." : "n/a"}</span>}</Stat>
        <Stat label="Duration">
          {run.duration_ms ? <span className="money">{formatDuration(run.duration_ms)}</span> : <span className="font-normal text-gray-400">{running ? `Step ${run.step_count}` : "n/a"}</span>}
        </Stat>
        <Stat label="Model">
          <span className="mono text-[13px]">{run.model_id ?? (run.kind === "replay" ? "none (replay)" : isTerminal(run.status) ? "none" : "pending")}</span>
        </Stat>
        <Stat label="Sandbox" className="flex-1 max-sm:mt-2 max-sm:basis-full max-sm:border-l-0 max-sm:pl-0">
          {run.sandbox_id ? (
            <Hint label={<span className="mono">{run.sandbox_id}</span>}>
              <span className="mono text-[13px]">
                {shortId(run.sandbox_id, 12)} <span className="font-normal text-gray-500">on {run.sandbox_host}</span>
                <span className={cn("ml-2 text-[11px] font-medium", run.sandbox_state === "running" ? "text-indigo-700" : "text-gray-400")}>{run.sandbox_state}</span>
              </span>
            </Hint>
          ) : (
            <span className="font-normal text-gray-400">{running ? "Starting" : "none"}</span>
          )}
        </Stat>
      </div>
    </Card>
  );
}

function fromEvents(events: RunEvent[]) {
  const sb = events.find((e) => e.type === "sandbox_created")?.payload;
  const stored = events.find((e) => e.type === "stored")?.payload;
  const compared = events.find((e) => e.type === "replay_compared")?.payload;
  return {
    attestation: (sb?.attestation ?? null) as Attestation | null,
    docker: (sb?.docker ?? null) as DockerSummary | null,
    limits: (sb?.limits ?? null) as SandboxLimits | null,
    inputs: sb?.inputs ?? events.find((e) => e.type === "run_started")?.payload?.inputs ?? [],
    stored: stored?.artifacts ?? [],
    compared: compared ? { match: !!compared.match, files: compared.files as CompareFile[] } : null,
  };
}

/** Backend reasons arrive as fragments ("stopped by the admin kill switch"); show them as sentences. */
function asSentence(text: string | null | undefined, fallback: string): string {
  const t = (text ?? "").trim();
  if (!t) return fallback;
  const s = t[0].toUpperCase() + t.slice(1);
  return /[.!?]$/.test(s) ? s : `${s}.`;
}

export function RunPage() {
  const { id } = useParams();
  const run = useRun(id);
  const events = useRunEvents(id);
  const detail = run.data;
  useRunLive(id, detail?.status, events.isSuccess);
  const ready = detail?.status === "succeeded";
  const lines = useLines(id, ready);
  const vh = useViewportHeight();
  const [replayId, setReplayId] = useState<string | null>(null);
  const [replayOpen, setReplayOpen] = useState(false);

  const replay = useMutation({
    mutationFn: () => api.replay(id as string),
    onMutate: () => {
      setReplayId(null);
      setReplayOpen(true);
    },
    onSuccess: (s) => setReplayId(s.id),
    onError: (e: unknown) => {
      setReplayOpen(false);
      toast.error("Replay could not start", { description: e instanceof Error ? e.message : String(e) });
    },
  });

  const evs = useMemo(() => events.data ?? [], [events.data]);
  const derived = useMemo(() => fromEvents(evs), [evs]);
  const verify = useRunVerify(id, !!detail && isTerminal(detail.status), evs.length);

  if (run.isLoading) {
    return (
      <div className="mx-auto max-w-[1560px] space-y-4 px-4 sm:px-6 pt-5">
        <Skeleton className="h-[132px] rounded-xl" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[360px_1fr_340px]">
          <Skeleton className="h-[560px] rounded-xl" />
          <Skeleton className="h-[560px] rounded-xl" />
          <Skeleton className="h-[560px] rounded-xl" />
        </div>
      </div>
    );
  }
  if (run.isError || !detail) {
    const notFound = run.error instanceof ApiError && run.error.status === 404;
    return (
      <div className="mx-auto max-w-[1560px] px-4 sm:px-6 pt-10">
        <Card>
          {notFound ? (
            <EmptyState
              icon={<SearchXIcon />}
              title="Run not found"
              action={
                <Button asChild variant="outline">
                  <Link to="/">Back to the September close</Link>
                </Button>
              }
            >
              There is no run with the id <span className="mono">{id}</span>. It may belong to an earlier demo database.
            </EmptyState>
          ) : (
            <ErrorState message={(run.error as Error)?.message} onRetry={() => void run.refetch()} />
          )}
        </Card>
      </div>
    );
  }

  const live = !isTerminal(detail.status);

  const ended = !!detail && isTerminal(detail.status) && !detail.result; // stopped or failed without a result
  const attestation = detail.attestation ?? derived.attestation;
  const docker = detail.docker ?? derived.docker;
  const limits = detail.limits ?? derived.limits;
  const inputs = detail.inputs.length ? detail.inputs : derived.inputs;
  const outputs = detail.outputs.length ? detail.outputs : derived.stored;
  const listHeight = Math.max(360, Math.min(660, vh - 330));

  const replayFiles: CompareFile[] | null =
    detail.kind === "replay"
      ? (derived.compared?.files ?? (detail.original && Object.keys(detail.hashes).length ? filesFromHashes(detail.original.hashes, detail.hashes) : null))
      : null;

  return (
    <div className="mx-auto max-w-[1560px] px-4 sm:px-6 pt-5 pb-12">
      <RunHeader run={detail} onReplay={() => replay.mutate()} replayPending={replay.isPending} />

      {detail.status === "failed" && (
        <Alert tone="danger" icon={<CircleAlertIcon />} title="The run failed" className="mt-4">
          {asSentence(detail.error, "The agent did not produce a valid result.")} The sandbox was destroyed; nothing was exported.
        </Alert>
      )}
      {detail.status === "stopped" && (
        <Alert tone="danger" icon={<OctagonAlertIcon />} title="Stopped" className="mt-4">
          {asSentence(detail.error, "Stopped by the admin kill switch.")} Its sandbox was destroyed; nothing was exported.
        </Alert>
      )}

      {detail.kind === "replay" && (
        <div className="mt-4">
          {replayFiles ? (
            <ReplayComparison files={replayFiles} match={derived.compared?.match ?? !!detail.replay_match} originalId={detail.original?.id ?? detail.replay_of ?? undefined} replayId={detail.id} />
          ) : (
            <Card className="flex items-center gap-2 px-5 py-4 text-[13px] text-gray-600">
              <Loader2Icon className="size-4 animate-spin text-indigo-600" /> Re-running the recorded steps in a fresh sandbox. The hash comparison appears when it finishes.
            </Card>
          )}
        </div>
      )}

      {detail.kind === "original" && detail.replays.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[12.5px] text-gray-600" data-testid="replays-list">
          <GitCompareArrowsIcon className="size-3.5 text-gray-400" />
          Replayed {detail.replays.length} time{detail.replays.length > 1 ? "s" : ""}:
          {detail.replays.slice(0, 4).map((r) => (
            <Link
              key={r.id}
              to={`/runs/${r.id}`}
              className={cn(
                "mono rounded-md border px-1.5 py-0.5 text-[11.5px]",
                r.replay_match === true ? "border-emerald-200 bg-emerald-50 text-emerald-800" : r.replay_match === false ? "border-red-200 bg-red-50 text-red-700" : "border-gray-200 bg-white text-gray-600",
              )}
            >
              {r.id} {r.replay_match === true ? "reproducible" : r.replay_match === false ? "differs" : r.status}
            </Link>
          ))}
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 items-start gap-4 lg:grid-cols-[clamp(280px,24vw,340px)_minmax(0,1fr)_clamp(290px,23vw,330px)]">
        <Card className="p-4">
          <Timeline events={evs} live={live} loading={events.isLoading} />
          {verify.data && (
            <div
              className={cn(
                "mt-1 rounded-lg border px-3 py-2.5 text-[12px]",
                verify.data.chain_ok ? "border-emerald-200 bg-emerald-50/60 text-emerald-900" : "border-red-200 bg-red-50 text-red-800",
              )}
              data-testid="event-chain"
              data-ok={String(verify.data.chain_ok)}
            >
              <div className="flex items-center gap-1.5 font-semibold">
                {verify.data.chain_ok ? <LinkIcon className="size-3.5" /> : <UnlinkIcon className="size-3.5" />}
                {verify.data.chain_ok ? "Event log hash chain verified" : "Event log hash chain is broken"}
              </div>
              <div className="mt-1 flex items-center justify-between gap-2 text-[11.5px] opacity-90">
                <span>{verify.data.events} events, each hash covers the previous one</span>
                <Hash value={verify.data.head} head={8} tail={6} />
              </div>
            </div>
          )}
        </Card>
        <div className="lg:sticky lg:top-[72px]">
          <Card className="p-4">
            <MatchingView
              lines={lines.data}
              result={detail.result}
              loading={lines.isLoading && ready}
              height={listHeight}
              pendingText={
                live ? (
                  <>
                    Lines connect as soon as the run finishes.
                    {detail.matched_count !== null && detail.bank_line_count ? ` Matched so far: ${formatInt(detail.matched_count)} of ${formatInt(detail.bank_line_count)}.` : ""}
                  </>
                ) : ended ? (
                  "No matching view: the run ended before its outputs left the sandbox."
                ) : lines.isError ? (
                  "lines.json is not available for this run."
                ) : undefined
              }
            />
          </Card>
        </div>
        <div className="space-y-4">
          <ReviewPanel run={detail} />
          <ReconSummary result={detail.result} loading={live} ended={ended} />
          <BlastRadius
            attestation={attestation}
            docker={docker}
            limits={limits}
            inputs={inputs}
            outputs={outputs}
            tenant={detail.client_id}
            sandboxId={detail.sandbox_id}
            host={detail.sandbox_host}
            imageDigest={detail.image_digest}
            untrusted={detail.untrusted_text ?? []}
            running={live}
            ended={ended}
          />
        </div>
      </div>

      <div className="mt-4">
        <RunTabs run={detail} />
      </div>

      <ReplayDialog replayId={replayId} original={detail} open={replayOpen} onOpenChange={setReplayOpen} />
    </div>
  );
}
