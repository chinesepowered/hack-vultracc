import { useEffect, useRef } from "react";
import { Link } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { BadgeCheckIcon, CheckIcon, ExternalLinkIcon, Loader2Icon, ShieldCheckIcon, XIcon } from "lucide-react";
import type { RunDetail, RunEvent } from "@/api/types";
import { Hash } from "@/components/hash";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { isTerminal, qk, useRun, useRunEvents, useRunLive } from "@/hooks/queries";
import { formatDuration } from "@/lib/format";
import { RUN_FILE_ORDER } from "@/lib/labels";
import { cn } from "@/lib/utils";

export interface CompareFile {
  name: string;
  original: string | null;
  replay: string | null;
  match: boolean;
}

export function filesFromHashes(original: Record<string, string>, replay: Record<string, string>): CompareFile[] {
  const names = Array.from(new Set([...Object.keys(original), ...Object.keys(replay)]));
  return sortFiles(names.map((n) => ({ name: n, original: original[n] ?? null, replay: replay[n] ?? null, match: !!original[n] && original[n] === replay[n] })));
}

function sortFiles(files: CompareFile[]) {
  return [...files].sort((a, b) => {
    const ia = RUN_FILE_ORDER.indexOf(a.name);
    const ib = RUN_FILE_ORDER.indexOf(b.name);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
}

export function ReproducibleBadge({ match, testId = "reproducible-badge", size = "md" }: { match: boolean; testId?: string; size?: "md" | "lg" }) {
  return (
    <span
      data-testid={testId}
      data-match={String(match)}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border font-semibold",
        size === "lg" ? "px-3 py-1 text-[13px]" : "px-2.5 py-0.5 text-[12px]",
        match ? "border-emerald-300 bg-emerald-50 text-emerald-800" : "border-red-300 bg-red-50 text-red-700",
      )}
    >
      {match ? <BadgeCheckIcon className="size-4" /> : <XIcon className="size-4" />}
      {match ? "Reproducible" : "Not reproducible"}
    </span>
  );
}

export function ReplayComparison({ files, match, originalId, replayId, className }: { files: CompareFile[]; match: boolean; originalId?: string; replayId?: string; className?: string }) {
  const sorted = sortFiles(files);
  return (
    <div className={cn("rounded-xl border border-gray-200 bg-white", className)} data-testid="replay-result" data-match={String(match)}>
      <div className={cn("flex items-center justify-between gap-3 rounded-t-xl border-b px-4 py-3", match ? "border-emerald-100 bg-emerald-50/60" : "border-red-100 bg-red-50/60")}>
        <div>
          <div className="text-[13.5px] font-semibold text-gray-900">{match ? "Same code, same inputs, same bytes" : "Outputs differ from the original"}</div>
          <div className="text-[12px] text-gray-500">
            SHA-256 of every output, original run vs a fresh sandbox replay
            {originalId && replayId ? (
              <>
                {" "}
                (<span className="mono">{originalId}</span> vs <span className="mono">{replayId}</span>)
              </>
            ) : null}
          </div>
        </div>
        <ReproducibleBadge match={match} size="lg" />
      </div>
      <table className="w-full text-[12.5px]">
        <thead>
          <tr className="border-b border-gray-100 text-left text-[11px] font-semibold tracking-wide text-gray-500 uppercase">
            <th className="px-4 py-2">File</th>
            <th className="px-4 py-2">Original</th>
            <th className="px-4 py-2">Replay</th>
            <th className="w-20 px-4 py-2 text-right">Result</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((f) => (
            <tr key={f.name} className="border-b border-gray-100 last:border-0" data-testid={`replay-file-${f.name}`} data-match={String(f.match)}>
              <td className="mono px-4 py-2.5 font-medium text-gray-900">{f.name}</td>
              <td className="px-4 py-2.5">
                <Hash value={f.original} head={12} tail={8} copy={false} />
              </td>
              <td className="px-4 py-2.5">
                <Hash value={f.replay} head={12} tail={8} copy={false} />
              </td>
              <td className="px-4 py-2.5 text-right">
                {f.match ? (
                  <span className="inline-flex items-center gap-1 font-medium text-emerald-700">
                    <CheckIcon className="size-3.5" strokeWidth={3} /> match
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 font-medium text-red-700">
                    <XIcon className="size-3.5" strokeWidth={3} /> differs
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Live replay progress: fresh sandbox, same code, same inputs, then the hash comparison. */
export function ReplayDialog({ replayId, original, open, onOpenChange }: { replayId: string | null; original: RunDetail; open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const run = useRun(replayId ?? undefined);
  const events = useRunEvents(replayId ?? undefined);
  useRunLive(replayId ?? undefined, run.data?.status, events.isSuccess);
  const list: RunEvent[] = events.data ?? [];
  const started = list.find((e) => e.type === "run_started");
  const total: number = started?.payload?.steps ?? original.step_count ?? 0;
  const steps = list.filter((e) => e.type === "replay_step");
  const sandbox = list.find((e) => e.type === "sandbox_created");
  const compared = list.find((e) => e.type === "replay_compared");
  const status = run.data?.status;
  const done = isTerminal(status);
  const refreshed = useRef(false);

  useEffect(() => {
    if (done && !refreshed.current) {
      refreshed.current = true;
      void qc.invalidateQueries({ queryKey: qk.run(original.id), exact: true });
    }
  }, [done, qc, original.id]);

  const files: CompareFile[] | null = compared?.payload?.files
    ? (compared.payload.files as CompareFile[])
    : done && run.data?.hashes && Object.keys(run.data.hashes).length
      ? filesFromHashes(original.hashes, run.data.hashes)
      : null;
  const match = compared?.payload?.match ?? run.data?.replay_match ?? false;
  const pct = total ? Math.min(100, (steps.length / total) * 100) : 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[860px]" data-testid="replay-dialog">
        <DialogHeader>
          <DialogTitle>Replay {original.client_name}</DialogTitle>
          <DialogDescription>
            A fresh sandbox re-executes the recorded code, step by step, on the same inputs. No model is involved. Then every output is compared by SHA-256.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-xl border border-gray-200 p-4">
          <div className="flex items-center justify-between text-[13px]">
            <div className="flex items-center gap-2 font-medium text-gray-900">
              {done ? (
                status === "succeeded" ? (
                  <CheckIcon className="size-4 text-emerald-600" />
                ) : (
                  <XIcon className="size-4 text-red-600" />
                )
              ) : (
                <Loader2Icon className="size-4 animate-spin text-indigo-600" />
              )}
              {!replayId
                ? "Starting replay"
                : !sandbox
                  ? "Creating a fresh sandbox"
                  : done
                    ? status === "succeeded"
                      ? "Replay finished"
                      : `Replay ${status}`
                    : `Re-running step ${Math.min(steps.length + 1, total || 1)} of ${total || "?"}`}
            </div>
            <span className="tnum text-[12px] text-gray-500">
              {steps.length} of {total || "?"} steps
            </span>
          </div>
          <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-gray-100">
            <div className={cn("h-full rounded-full transition-[width] duration-500", done && status === "succeeded" ? "bg-emerald-500" : "bg-indigo-500")} style={{ width: `${done ? 100 : pct}%` }} />
          </div>
          {sandbox && (
            <div className="mt-3 flex items-center gap-2 text-[12px] text-gray-600">
              <ShieldCheckIcon className="size-3.5 text-indigo-600" />
              Fresh sandbox <span className="mono">{sandbox.payload.sandbox_id}</span> on {sandbox.payload.host}, attestation{" "}
              {sandbox.payload.attestation?.ok ? "passed" : "pending"}
            </div>
          )}
          {steps.length > 0 && (
            <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1">
              {steps.map((s) => (
                <div key={s.seq} className="flex items-center justify-between gap-2 text-[12px]">
                  <span className="flex min-w-0 items-center gap-2">
                    <span className={cn("flex size-4 items-center justify-center rounded-full text-[10px] font-semibold", s.payload.exit_code === 0 ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700")}>
                      {s.payload.n}
                    </span>
                    <span className="mono truncate text-gray-700">{(s.payload.argv ?? []).join(" ")}</span>
                  </span>
                  <span className="tnum shrink-0 text-gray-400">
                    exit {s.payload.exit_code} · {formatDuration(s.payload.duration_ms)}
                  </span>
                </div>
              ))}
            </div>
          )}
          {run.data?.error && <div className="mt-3 text-[12px] text-red-700">{run.data.error}</div>}
        </div>

        {files && <ReplayComparison files={files} match={!!match} originalId={original.id} replayId={replayId ?? undefined} />}

        <DialogFooter>
          {replayId && (
            <Button variant="outline" asChild>
              <Link to={`/runs/${replayId}`} onClick={() => onOpenChange(false)}>
                <ExternalLinkIcon /> Open replay run
              </Link>
            </Button>
          )}
          <Button onClick={() => onOpenChange(false)}>{done ? "Done" : "Close"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
