import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { CheckCircle2Icon, CircleAlertIcon, ClockIcon, Loader2Icon, RotateCwIcon, XCircleIcon } from "lucide-react";
import type { RunSummary } from "@/api/types";
import { Difference } from "@/components/money";
import { SandboxBadges } from "@/components/sandbox-badges";
import { Button } from "@/components/ui/button";
import { StatusPill } from "@/components/status";
import type { TileActivity } from "@/hooks/queries";
import { formatDuration, formatInt, formatPercent } from "@/lib/format";
import { runStatusDisplay, type Tone } from "@/lib/labels";
import { cn } from "@/lib/utils";

const STRIPE: Record<Tone | "idle", string> = {
  idle: "bg-gray-100",
  muted: "bg-gray-200",
  neutral: "bg-gray-300",
  running: "stripe-running",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
};

function useFlash(value: string) {
  const prev = useRef(value);
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (prev.current !== value) {
      prev.current = value;
      setFlash(true);
      const t = setTimeout(() => setFlash(false), 750);
      return () => clearTimeout(t);
    }
  }, [value]);
  return flash;
}

function Metric({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <div className="text-[11px] font-medium text-gray-500">{label}</div>
      <div className="mt-0.5 truncate text-[14px] font-semibold text-gray-900">{children}</div>
    </div>
  );
}

function Pending({ children = "..." }: { children?: React.ReactNode }) {
  return <span className="font-normal text-gray-400">{children}</span>;
}

export interface TileClient {
  id: string;
  name: string;
  industry: string;
}

export function ClientTile({
  client,
  run,
  activity,
  onRerun,
  rerunning,
}: {
  client: TileClient;
  run: RunSummary | null;
  activity?: TileActivity;
  /** Present when the viewer may re-run failed or stopped clients (preparer or admin). */
  onRerun?: (run: RunSummary) => void;
  rerunning?: boolean;
}) {
  const display = run ? runStatusDisplay(run.status, run.recon_status, run.sandbox_state) : { label: "Ready to close", tone: "muted" as Tone };
  const settled = run ? run.status === "succeeded" || run.status === "failed" || run.status === "stopped" : false;
  const flash = useFlash(`${run?.status ?? "idle"}:${run?.recon_status ?? ""}`);
  const running = run?.status === "running";
  const hasBadges = !!run?.badges?.runtime;
  const matched = run?.matched_count ?? null;
  const total = run?.bank_line_count ?? null;
  const pct = matched !== null && total ? Math.min(100, (matched / total) * 100) : 0;

  const body = (
    <>
      <div className={cn("h-1 rounded-t-xl", STRIPE[run ? display.tone : "idle"])} />
      <div className="flex flex-1 flex-col px-4 pt-3 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate text-[14px] font-semibold text-gray-900" title={client.name}>
              {client.name}
            </div>
            <div className="truncate text-[12px] text-gray-500">{client.industry}</div>
          </div>
          <StatusPill tone={display.tone} spinning={running} size="sm" data-testid={`tile-status-${client.id}`}>
            {display.label}
          </StatusPill>
        </div>

        <div className="mt-2 flex h-[20px] items-center">
          {hasBadges && run ? (
            <SandboxBadges badges={run.badges} dim={run.sandbox_state === "destroyed"} />
          ) : (
            <span className="text-[11px] text-gray-400">
              {run?.status === "running" ? (
                <span className="inline-flex items-center gap-1.5">
                  <Loader2Icon className="size-3 animate-spin" /> Starting a sealed sandbox
                </span>
              ) : run?.status === "queued" ? (
                "Waiting for a sandbox slot"
              ) : run ? (
                "No sandbox"
              ) : (
                "Gets its own sandbox when the close runs"
              )}
            </span>
          )}
        </div>

        <div className="mt-2.5 grid grid-cols-[1.25fr_0.9fr_1fr] gap-2">
          <Metric label="Matched">
            {matched !== null && total ? (
              <span className="money">
                {formatInt(matched)}
                <span className="font-normal text-gray-400">/{formatInt(total)}</span>
              </span>
            ) : run && (run.status === "running" || run.status === "queued") ? (
              <Pending>Matching</Pending>
            ) : (
              <Pending>{run ? "n/a" : "0"}</Pending>
            )}
          </Metric>
          <Metric label="Exceptions">
            {run?.exception_count !== null && run?.exception_count !== undefined ? (
              <span className="money">
                {run.exception_count}
                {!!run.needs_review_count && <span className="ml-1 text-[11px] font-medium text-amber-700">({run.needs_review_count} review)</span>}
              </span>
            ) : (
              <Pending>{run ? "..." : "0"}</Pending>
            )}
          </Metric>
          <Metric label="Difference" className="text-right">
            {run?.difference !== null && run?.difference !== undefined ? <Difference value={run.difference} size="sm" /> : <Pending>{run ? "Pending" : "n/a"}</Pending>}
          </Metric>
        </div>

        <div className="mt-2 h-1 overflow-hidden rounded-full bg-gray-100" aria-hidden="true">
          <div
            className={cn(
              "h-full rounded-full transition-[width] duration-700 ease-out",
              display.tone === "warning" ? "bg-amber-500" : display.tone === "danger" ? "bg-gray-300" : settled ? "bg-emerald-500" : "bg-indigo-500",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>

        <div className="mt-2 flex min-h-[18px] items-center justify-between gap-2 text-[12px]">
          <span className="min-w-0 truncate text-gray-500" data-testid={`tile-steps-${client.id}`}>
            {!run && "Not started"}
            {run?.status === "queued" && "Queued"}
            {running && (
              <>
                <span className="tnum font-medium text-gray-700">Step {Math.max(run.step_count, activity?.n ?? 0) || 1}</span>
                {activity?.text ? <span className="text-gray-400"> · {activity.text}</span> : null}
              </>
            )}
            {settled && run && (
              <>
                <span className="tnum">
                  {run.step_count} step{run.step_count === 1 ? "" : "s"}
                </span>
                {run.duration_ms ? <span className="text-gray-400"> · {formatDuration(run.duration_ms)}</span> : null}
                {matched !== null && total ? <span className="text-gray-400"> · {formatPercent(matched, total)} matched</span> : null}
              </>
            )}
          </span>
          {run && (run.status === "failed" || run.status === "stopped") && onRerun ? (
            <Button
              size="sm"
              variant="outline"
              className="relative z-10 h-6 gap-1 px-2 text-[11.5px]"
              data-testid="rerun-button"
              disabled={rerunning}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onRerun(run);
              }}
            >
              {rerunning ? <Loader2Icon className="size-3 animate-spin" /> : <RotateCwIcon className="size-3" />} Re-run
            </Button>
          ) : (
            run && <ApprovalMark run={run} />
          )}
        </div>
        {run?.status === "failed" && run.error && <div className="mt-1 line-clamp-1 text-[11px] text-red-600" title={run.error}>{run.error}</div>}
      </div>
    </>
  );

  const className = cn(
    "group relative flex min-h-[164px] flex-col rounded-xl border border-gray-200 bg-white shadow-card transition-[box-shadow,border-color,transform] duration-200",
    run && "hover:-translate-y-px hover:border-gray-300 hover:shadow-raised",
    flash && "tile-settle",
  );

  if (!run) {
    return (
      <div className={className} data-testid={`client-tile-${client.id}`} data-status="idle" data-recon="">
        {body}
      </div>
    );
  }
  // The whole card opens the run through a covering link; the Re-run button sits above it.
  return (
    <div
      className={cn(className, "has-[a:focus-visible]:ring-2 has-[a:focus-visible]:ring-ring/50")}
      data-testid={`client-tile-${client.id}`}
      data-status={run.status}
      data-recon={run.recon_status ?? ""}
      data-approval={run.approval_status ?? ""}
      data-run-id={run.id}
    >
      <Link to={`/runs/${run.id}`} className="absolute inset-0 z-[1] rounded-xl outline-none" aria-label={`Open ${client.name}: ${display.label}`} />
      {body}
    </div>
  );
}

function ApprovalMark({ run }: { run: RunSummary }) {
  if (run.approval_status === "approved")
    return (
      <span className="inline-flex shrink-0 items-center gap-1 font-medium text-emerald-700">
        <CheckCircle2Icon className="size-3.5" /> Approved
      </span>
    );
  if (run.approval_status === "rejected")
    return (
      <span className="inline-flex shrink-0 items-center gap-1 font-medium text-red-700">
        <XCircleIcon className="size-3.5" /> Rejected
      </span>
    );
  if (run.approval_status === "pending")
    return (
      <span className="inline-flex shrink-0 items-center gap-1 font-medium text-amber-700">
        <ClockIcon className="size-3.5" /> Awaiting approval
      </span>
    );
  if (run.status === "stopped")
    return (
      <span className="inline-flex shrink-0 items-center gap-1 font-medium text-red-700">
        <CircleAlertIcon className="size-3.5" /> Stopped
      </span>
    );
  return null;
}
