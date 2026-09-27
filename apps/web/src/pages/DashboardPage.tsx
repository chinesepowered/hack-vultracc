import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CalendarDaysIcon, CheckIcon, ChevronDownIcon, HistoryIcon, InfoIcon, Loader2Icon, OctagonAlertIcon, PlayIcon, UploadIcon } from "lucide-react";
import { api, ApiError } from "@/api";
import type { Batch, Client, RunSummary } from "@/api/types";
import { ClientTile, type TileClient } from "@/components/dashboard/ClientTile";
import { GroundTruthCard } from "@/components/dashboard/GroundTruthCard";
import { UploadDialog, UploadsCard } from "@/components/dashboard/UploadDialog";
import { Alert, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Hint } from "@/components/ui/tooltip";
import { qk, useBatchById, useBatches, useBatchLive, useGroundTruth, useLatestBatch, useMe, useSystem } from "@/hooks/queries";
import { formatCompact, formatDateTime, formatDuration, formatInt, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";

function StatCard({
  label,
  children,
  sub,
  className,
  testId,
  data,
}: {
  label: string;
  children: React.ReactNode;
  sub?: React.ReactNode;
  className?: string;
  testId?: string;
  data?: Record<string, string | number>;
}) {
  const dataAttrs = Object.fromEntries(Object.entries(data ?? {}).map(([k, v]) => [`data-${k}`, String(v)]));
  return (
    <Card className={cn("px-5 py-3.5", className)} data-testid={testId} {...dataAttrs}>
      <div className="text-[12px] font-medium text-gray-500">{label}</div>
      <div className="mt-1 flex items-baseline gap-2 text-[24px] leading-none font-semibold tracking-tight text-gray-900">{children}</div>
      {sub && <div className="mt-2 text-[12px] text-gray-500">{sub}</div>}
    </Card>
  );
}

function ProgressSegments({ runs, total }: { runs: RunSummary[]; total: number }) {
  const count = (fn: (r: RunSummary) => boolean) => runs.filter(fn).length;
  const segs = [
    { n: count((r) => r.status === "succeeded" && r.recon_status === "reconciled"), cls: "bg-emerald-500", label: "reconciled" },
    { n: count((r) => r.status === "succeeded" && r.recon_status !== "reconciled"), cls: "bg-amber-500", label: "need review" },
    { n: count((r) => r.status === "failed" || r.status === "stopped"), cls: "bg-red-500", label: "failed or stopped" },
    { n: count((r) => r.status === "running"), cls: "stripe-running", label: "running" },
  ];
  return (
    <div className="mt-1 flex h-1.5 w-full gap-0.5 overflow-hidden rounded-full bg-gray-100">
      {segs.map((s) =>
        s.n > 0 ? <div key={s.label} className={cn("h-full transition-[width] duration-700 ease-out first:rounded-l-full last:rounded-r-full", s.cls)} style={{ width: `${(s.n / total) * 100}%` }} /> : null,
      )}
    </div>
  );
}

const SELECTED_KEY = "tieout.dashboard.batch";

export function DashboardPage() {
  const me = useMe();
  const system = useSystem();
  const qc = useQueryClient();
  const clients = useQuery({ queryKey: qk.clients, queryFn: () => api.clients() });
  const latest = useLatestBatch();
  const batches = useBatches();
  const [selectedId, setSelectedIdState] = useState<string | null>(() => {
    try {
      return sessionStorage.getItem(SELECTED_KEY);
    } catch {
      return null;
    }
  });
  const setSelectedId = (id: string | null) => {
    setSelectedIdState(id);
    try {
      if (id) sessionStorage.setItem(SELECTED_KEY, id);
      else sessionStorage.removeItem(SELECTED_KEY);
    } catch {
      // per-viewer convenience only
    }
  };
  const viewingPast = !!selectedId && selectedId !== latest.data?.id;
  const selected = useBatchById(viewingPast ? selectedId : null);
  const batch = (viewingPast ? selected.data : latest.data) ?? null;
  const activity = useBatchLive(batch, viewingPast && selectedId ? qk.batch(selectedId) : qk.latestBatch);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);
  const groundTruth = useGroundTruth(batch?.id, !!batch && batch.status !== "running");

  useEffect(() => {
    // a stale selection (for example after a database reset) falls back to the latest close
    if (viewingPast && selected.isError) setSelectedId(null);
  }, [viewingPast, selected.isError]);

  const role = me.data?.role;
  const [uploadOpen, setUploadOpen] = useState(false);
  const running = batch?.status === "running";
  const killSwitch = !!system.data?.kill_switch;

  const start = useMutation({
    mutationFn: () => api.createBatch(system.data?.period ?? "2026-09"),
    onMutate: () => setError(null),
    onSuccess: (b: Batch) => {
      setSelectedId(null);
      qc.setQueryData(qk.latestBatch, b);
      void qc.invalidateQueries({ queryKey: qk.batches });
      toast.success("September close started", { description: `${b.runs.length} clients, each in its own sealed sandbox.` });
    },
    onError: (e: unknown) => {
      const status = e instanceof ApiError ? e.status : 0;
      const message = e instanceof Error ? e.message : String(e);
      const title =
        status === 409
          ? message.toLowerCase().includes("kill switch")
            ? "Kill switch is on"
            : "A close is already running"
          : status === 429
            ? "Rate limit reached"
            : status === 403
              ? "Not allowed"
              : "Could not start the close";
      setError({ title, message });
      void qc.invalidateQueries({ queryKey: qk.system });
      void qc.invalidateQueries({ queryKey: qk.latestBatch });
    },
  });

  const batchKey = viewingPast && selectedId ? qk.batch(selectedId) : qk.latestBatch;
  const rerun = useMutation({
    mutationFn: (r: RunSummary) => api.rerun(r.id),
    onSuccess: (fresh) => {
      qc.setQueryData<Batch | null>(batchKey, (old) =>
        old ? { ...old, status: "running", finished_at: null, runs: old.runs.map((r) => (r.client_id === fresh.client_id ? fresh : r)) } : old,
      );
      toast.success(`Re-running ${fresh.client_name}`, { description: "A fresh sandbox with the same inputs. The tile follows the new run." });
      void qc.invalidateQueries({ queryKey: batchKey });
      void qc.invalidateQueries({ queryKey: qk.batches });
    },
    onError: (e: unknown) => toast.error("Re-run refused", { description: e instanceof Error ? e.message : String(e) }),
  });

  const tiles = useMemo(() => {
    const cl: Client[] = clients.data ?? [];
    const byClient = new Map<string, RunSummary>((batch?.runs ?? []).map((r) => [r.client_id, r]));
    const base: TileClient[] = cl.length
      ? cl.map((c) => ({ id: c.id, name: c.name, industry: c.industry }))
      : (batch?.runs ?? []).map((r) => ({ id: r.client_id, name: r.client_name, industry: r.industry }));
    return base.sort((a, b) => a.id.localeCompare(b.id)).map((c) => ({ client: c, run: byClient.get(c.id) ?? null }));
  }, [clients.data, batch]);

  const runs = batch?.runs ?? [];
  const totalClients = tiles.length || 12;
  const reconciled = runs.filter((r) => r.status === "succeeded" && r.recon_status === "reconciled").length;
  const needsReview = runs.filter((r) => r.status === "succeeded" && r.recon_status === "needs_review").length;
  const finished = runs.filter((r) => r.status === "succeeded" || r.status === "failed" || r.status === "stopped").length;
  const exceptions = runs.reduce((a, r) => a + (r.exception_count ?? 0), 0);
  const flagged = runs.reduce((a, r) => a + (r.needs_review_count ?? 0), 0);
  const pendingAjes = runs.filter((r) => r.approval_status === "pending").reduce((a, r) => a + (r.aje_count ?? 0), 0);
  const pendingClients = runs.filter((r) => r.approval_status === "pending" && (r.aje_count ?? 0) > 0).length;
  const approved = runs.filter((r) => r.approval_status === "approved").length;
  const tokens = runs.reduce((a, r) => a + r.tokens_in + r.tokens_out, 0);

  const canStart = role === "preparer" || role === "admin";
  const disabledReason = !canStart
    ? "Reviewers approve the close; a preparer starts it (maker-checker)."
    : killSwitch
      ? "The kill switch is on. An admin must turn it off before new work can start."
      : running
        ? "A close is already running."
        : null;

  return (
    <div className="mx-auto max-w-[1560px] px-6 pt-5 pb-12">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-[24px] font-semibold tracking-tight text-gray-900">September 2026 close</h1>
          <p className="mt-0.5 text-[14px] text-gray-500">
            {system.data?.firm ?? "Harbor & Pine CPA"} · {totalClients} clients · each bank reconciliation runs in its own sealed sandbox on Vultr
          </p>
        </div>
        <div className="flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="lg" data-testid="previous-closes" className="text-gray-600">
                <HistoryIcon className="text-gray-500" /> Previous closes
                {(batches.data?.length ?? 0) > 0 && <span className="tnum rounded-full bg-gray-100 px-1.5 text-[11px] text-gray-600">{batches.data?.length}</span>}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-[380px]">
              <DropdownMenuLabel>Closes for September 2026</DropdownMenuLabel>
              {!batches.data?.length && <div className="px-2 py-3 text-[12.5px] text-gray-500">No closes yet.</div>}
              {(batches.data ?? []).slice(0, 12).map((b, i) => {
                const current = (batch?.id ?? null) === b.id;
                const t = b.totals;
                return (
                  <DropdownMenuItem
                    key={b.id}
                    data-testid={`previous-close-${b.id}`}
                    onSelect={() => setSelectedId(i === 0 ? null : b.id)}
                    className="items-start py-2"
                  >
                    <span className="mt-0.5 size-4 shrink-0">{current && <CheckIcon className="size-4 text-indigo-600" />}</span>
                    <span className="min-w-0 flex-1 leading-tight">
                      <span className="flex items-center gap-2 text-[13px] text-gray-900">
                        {formatDateTime(b.created_at)}
                        {i === 0 && <span className="rounded bg-indigo-50 px-1.5 py-px text-[10.5px] font-medium text-indigo-700">Latest</span>}
                      </span>
                      <span className="mt-0.5 block text-[11.5px] text-gray-500">
                        {b.status === "running"
                          ? `Running, ${t.succeeded + t.failed} of ${t.clients} done`
                          : `${t.reconciled} reconciled, ${t.needs_review} need review${t.failed ? `, ${t.failed} failed or stopped` : ""}`}
                        {" · "}
                        {b.created_by_name}
                      </span>
                    </span>
                    <span
                      className={cn(
                        "mt-0.5 shrink-0 rounded-full px-1.5 py-px text-[10.5px] font-medium",
                        b.status === "completed" ? "bg-emerald-50 text-emerald-700" : b.status === "running" ? "bg-indigo-50 text-indigo-700" : "bg-red-50 text-red-700",
                      )}
                    >
                      {b.status}
                    </span>
                  </DropdownMenuItem>
                );
              })}
              {viewingPast && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={() => setSelectedId(null)}>
                    <HistoryIcon /> Back to the latest close
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="lg" data-testid="period-selector">
                <CalendarDaysIcon className="text-gray-500" /> September 2026 <ChevronDownIcon className="text-gray-400" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-60">
              <DropdownMenuLabel>Period</DropdownMenuLabel>
              <DropdownMenuItem>
                <CheckIcon className="text-indigo-600" /> September 2026
                <span className="ml-auto text-[11px] text-gray-400">Open</span>
              </DropdownMenuItem>
              <DropdownMenuItem disabled>
                <span className="size-4" /> August 2026
                <span className="ml-auto text-[11px] text-gray-400">Closed</span>
              </DropdownMenuItem>
              <DropdownMenuItem disabled>
                <span className="size-4" /> October 2026
                <span className="ml-auto text-[11px] text-gray-400">Not started</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          {(role === "preparer" || role === "admin") && (
            <Hint label="Reconcile a bank export and ledger of your own, in a fresh sandbox, outside the monthly close.">
              <Button variant="outline" size="lg" data-testid="upload-open" onClick={() => setUploadOpen(true)}>
                <UploadIcon className="text-gray-500" /> Upload files
              </Button>
            </Hint>
          )}
          <Hint label={disabledReason} wrap={!!disabledReason}>
            <Button
              size="lg"
              data-testid="close-period-button"
              onClick={() => start.mutate()}
              disabled={!!disabledReason || start.isPending}
              className="min-w-[180px]"
            >
              {start.isPending || running ? <Loader2Icon className="animate-spin" /> : <PlayIcon className="fill-current" />}
              {running ? `Closing, ${finished} of ${totalClients} done` : start.isPending ? "Starting sandboxes" : "Close September"}
            </Button>
          </Hint>
        </div>
      </div>

      {error && (
        <Alert
          tone={error.title === "Kill switch is on" ? "danger" : "warning"}
          icon={<OctagonAlertIcon />}
          title={error.title}
          className="mt-5"
          data-testid="close-error"
          action={
            <Button variant="ghost" size="sm" onClick={() => setError(null)}>
              Dismiss
            </Button>
          }
        >
          {error.message}
        </Alert>
      )}

      {viewingPast && batch && (
        <Alert
          tone="info"
          icon={<HistoryIcon />}
          className="mt-5"
          data-testid="viewing-previous-close"
          action={
            <Button variant="outline" size="sm" onClick={() => setSelectedId(null)}>
              Back to the latest close
            </Button>
          }
        >
          Viewing a previous close started by {batch.created_by_name} on {formatDateTime(batch.created_at)}. Every run in it is a real, recorded run.
        </Alert>
      )}

      <div className="mt-5 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard
          label="September close"
          testId="batch-progress"
          data={{ reconciled, finished, total: totalClients, status: batch?.status ?? "none" }}
          sub={
            <>
              <ProgressSegments runs={runs} total={totalClients} />
              <div className="mt-2">
                {batch ? (
                  <span>
                    {needsReview > 0 && <span className="font-medium text-amber-700">{needsReview} need review · </span>}
                    {running ? `${runs.filter((r) => r.status === "running").length} running, ${finished} finished` : `${finished} of ${totalClients} finished`}
                    {batch.duration_ms ? ` in ${formatDuration(batch.duration_ms)}` : ""}
                  </span>
                ) : (
                  "Not started"
                )}
              </div>
            </>
          }
        >
          <span className="money" data-testid="reconciled-count">
            {reconciled}
          </span>
          <span className="text-[15px] font-medium text-gray-500">of {totalClients} reconciled</span>
        </StatCard>
        <StatCard
          label="Exceptions found"
          testId="stat-exceptions"
          sub={batch ? flagged ? <span className="font-medium text-amber-700">{flagged} flagged for a human to investigate</span> : "Every leftover explained" : "Timing items, errors and unknowns"}
        >
          <span className="money">{formatInt(exceptions)}</span>
        </StatCard>
        <StatCard
          label="AJEs pending approval"
          testId="stat-ajes"
          sub={batch ? `${pendingClients} client${pendingClients === 1 ? "" : "s"} awaiting review · ${approved} approved` : "Nothing posts without a reviewer"}
        >
          <span className="money">{formatInt(pendingAjes)}</span>
        </StatCard>
        <StatCard label="LLM tokens used" testId="stat-tokens" sub={`Vultr Serverless Inference · ${system.data?.models.main ?? "GLM 5.3"}`}>
          <Hint label={`${formatInt(tokens)} tokens in and out across this close`}>
            <span className="money">{formatCompact(tokens)}</span>
          </Hint>
        </StatCard>
      </div>

      {groundTruth.data && batch && batch.status !== "running" && (
        <GroundTruthCard
          gt={groundTruth.data}
          names={Object.fromEntries((batch.runs ?? []).map((r) => [r.client_id, r.client_name]))}
          className="mt-3"
        />
      )}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h2 className="text-[15px] font-semibold text-gray-900">Clients</h2>
          {batch && (
            <span className="text-[12px] text-gray-500">
              Close started by {batch.created_by_name} at {formatTime(batch.created_at)}
              {batch.finished_at && batch.duration_ms ? `, finished in ${formatDuration(batch.duration_ms)}` : ""}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 text-[12px] text-gray-500">
          <Legend cls="bg-emerald-500" label="Reconciled" />
          <Legend cls="bg-amber-500" label="Needs review" />
          <Legend cls="bg-indigo-500" label="Running" />
          <Legend cls="bg-red-500" label="Failed or stopped" />
          <Legend cls="bg-gray-300" label="Queued" />
        </div>
      </div>

      {!batch && !latest.isLoading && !viewingPast && (
        <Alert tone="info" icon={<InfoIcon />} className="mt-4" data-testid="empty-batch">
          No close has run for September yet. <span className="font-medium">Close September</span> starts one agent run per client, in parallel. Each run gets its own gVisor
          sandbox with no network, read-only inputs and no access to the ledger.
        </Alert>
      )}

      {clients.isError && latest.isError ? (
        <Card className="mt-4">
          <ErrorState
            message={(clients.error as Error)?.message}
            onRetry={() => {
              void clients.refetch();
              void latest.refetch();
            }}
          />
        </Card>
      ) : (
        <div className="mt-3 grid grid-cols-2 gap-3.5 lg:grid-cols-3 xl:grid-cols-4" data-testid="client-grid">
          {clients.isLoading && latest.isLoading
            ? Array.from({ length: 12 }).map((_, i) => <Skeleton key={i} className="h-[164px] rounded-xl" />)
            : tiles.map(({ client, run }) => (
                <ClientTile
                  key={client.id}
                  client={client}
                  run={run}
                  activity={activity[client.id]}
                  onRerun={canStart ? (r) => rerun.mutate(r) : undefined}
                  rerunning={rerun.isPending && rerun.variables?.id === run?.id}
                />
              ))}
        </div>
      )}
      <UploadsCard />
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
    </div>
  );
}

function Legend({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("size-2 rounded-full", cls)} /> {label}
    </span>
  );
}
