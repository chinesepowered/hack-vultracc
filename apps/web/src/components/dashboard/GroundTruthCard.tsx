import { useState } from "react";
import { Link } from "react-router";
import { CheckIcon, ChevronDownIcon, KeyRoundIcon, TargetIcon, XIcon } from "lucide-react";
import type { GroundTruth } from "@/api/types";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function groundTruthHeadline(gt: GroundTruth) {
  return `${gt.found} of ${gt.planted} planted discrepancies found`;
}

export function GroundTruthCard({ gt, names, className }: { gt: GroundTruth; names?: Record<string, string>; className?: string }) {
  const [open, setOpen] = useState(false);
  const allExact = gt.all_exact ?? gt.clients.every((c) => c.exact);
  const perfect = allExact && gt.found === gt.planted;
  const exactCount = gt.clients.filter((c) => c.exact).length;
  return (
    <Card className={cn("overflow-hidden", className)} data-testid="ground-truth" data-found={gt.found} data-planted={gt.planted} data-exact={String(allExact)}>
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-3 px-4 py-2.5 text-left" aria-expanded={open}>
        <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-full", perfect ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700")}>
          <TargetIcon className="size-4" />
        </span>
        <span className="min-w-0 flex-1 truncate text-[13px]">
          <span className="font-semibold text-gray-900">Ground truth check: </span>
          <span className={cn("font-semibold", perfect ? "text-emerald-700" : "text-amber-700")}>{groundTruthHeadline(gt)}</span>
          <span className="text-gray-500">
            {" "}
            · {exactCount} of {gt.clients.length} clients exact{perfect ? ", every difference 0.00" : ""} · scored against the generator's answer key, never shown to the model
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1 text-[12px] font-medium text-indigo-700">
          {open ? "Hide" : "Per-client detail"}
          <ChevronDownIcon className={cn("size-4 transition-transform", open && "rotate-180")} />
        </span>
      </button>
      {open && (
        <div className="border-t border-gray-100 px-5 py-4">
          <div className="grid grid-cols-2 gap-x-8 gap-y-1 lg:grid-cols-3">
            {gt.clients.map((c) => (
              <div key={c.client_id} className="flex items-center justify-between gap-3 border-b border-gray-100 py-1.5 text-[12.5px]" data-testid={`ground-truth-${c.client_id}`}>
                <span className="flex min-w-0 items-center gap-2">
                  <span className={cn("flex size-4 shrink-0 items-center justify-center rounded-full", c.exact ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700")}>
                    {c.exact ? <CheckIcon className="size-2.5" strokeWidth={3.5} /> : <XIcon className="size-2.5" strokeWidth={3.5} />}
                  </span>
                  {c.run_id ? (
                    <Link to={`/runs/${c.run_id}`} className="truncate text-gray-800 hover:text-indigo-700 hover:underline">
                      {names?.[c.client_id] ?? c.client_id}
                    </Link>
                  ) : (
                    <span className="truncate text-gray-800">{names?.[c.client_id] ?? c.client_id}</span>
                  )}
                </span>
                <span className="tnum shrink-0 text-gray-500">
                  {c.found}/{c.planted}
                  {c.missing.length > 0 && <span className="ml-1.5 text-red-700">missing {c.missing.length}</span>}
                  {c.extra.length > 0 && <span className="ml-1.5 text-amber-700">extra {c.extra.length}</span>}
                </span>
              </div>
            ))}
          </div>
          {gt.clients.some((c) => c.missing.length || c.extra.length) && (
            <div className="mt-3 space-y-1 text-[12px] text-gray-600">
              {gt.clients
                .filter((c) => c.missing.length || c.extra.length)
                .map((c) => (
                  <div key={c.client_id}>
                    <span className="font-medium">{names?.[c.client_id] ?? c.client_id}:</span>
                    {c.missing.length ? ` missing ${c.missing.join(", ")}` : ""}
                    {c.extra.length ? ` extra ${c.extra.join(", ")}` : ""}
                  </div>
                ))}
            </div>
          )}
          <div className="mt-3 flex items-center gap-1.5 text-[11.5px] text-gray-500">
            <KeyRoundIcon className="size-3.5" /> Matched on kind, amount and references. The answer key lives on the control plane only; it never enters a sandbox or a prompt.
          </div>
        </div>
      )}
    </Card>
  );
}
