import { useState } from "react";
import { CheckCircle2Icon, ChevronRightIcon, CircleAlertIcon } from "lucide-react";
import type { OutstandingItem, ReconResult } from "@/api/types";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatMoney, formatShortDate, isZeroMoney, moneyNumber, sumMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

function Row({
  label,
  value,
  kind = "item",
  items,
  negate,
}: {
  label: React.ReactNode;
  value: string;
  kind?: "balance" | "item" | "total";
  items?: { key: string; label: React.ReactNode; amount: string }[];
  negate?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const expandable = !!items && items.length > 0;
  const shown = negate ? formatMoney(-moneyNumber(value)) : formatMoney(value);
  return (
    <>
      <div
        className={cn(
          "flex items-center justify-between gap-3 py-1.5",
          kind === "item" && "pl-3 text-[13px] text-gray-600",
          kind === "balance" && "text-[13px] font-medium text-gray-800",
          kind === "total" && "mt-1 border-t border-gray-200 pt-2 text-[13px] font-semibold text-gray-900",
        )}
      >
        {expandable ? (
          <button type="button" onClick={() => setOpen((o) => !o)} className="flex min-w-0 items-center gap-1 text-left hover:text-gray-900">
            <ChevronRightIcon className={cn("size-3.5 shrink-0 text-gray-400 transition-transform", open && "rotate-90")} />
            <span className="truncate">{label}</span>
          </button>
        ) : (
          <span className={cn("min-w-0 truncate", kind === "item" && "pl-[18px]")}>{label}</span>
        )}
        <span className="money shrink-0 text-right">{shown}</span>
      </div>
      {open && items && (
        <div className="mb-1 ml-8 space-y-0.5 border-l border-gray-200 pl-3">
          {items.map((it) => (
            <div key={it.key} className="flex items-center justify-between gap-3 text-[12px] text-gray-500">
              <span className="min-w-0 truncate">{it.label}</span>
              <span className="money shrink-0">{formatMoney(it.amount)}</span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function itemRows(list: OutstandingItem[]) {
  return list.map((o) => ({
    key: o.ref,
    label: (
      <>
        {o.description} <span className="text-gray-400">{formatShortDate(o.date)}{o.carried_from_prior ? ", from August" : ""}</span>
      </>
    ),
    amount: o.amount,
  }));
}

export function ReconSummary({ result, loading }: { result: ReconResult | null | undefined; loading?: boolean }) {
  if (!result) {
    return (
      <Card className="p-5" data-testid="recon-summary" data-state={loading ? "loading" : "pending"}>
        <div className="text-[14px] font-semibold text-gray-900">Reconciliation</div>
        <div className="mt-1 text-[12px] text-gray-500">Computed by code in the sandbox. Appears when result.json validates.</div>
        <div className="mt-4 space-y-2.5">
          {Array.from({ length: 7 }).map((_, i) => (
            <Skeleton key={i} className={cn("h-4", i % 3 === 0 ? "w-full" : "ml-4 w-[90%]")} />
          ))}
        </div>
      </Card>
    );
  }
  const r = result;
  const dit = sumMoney(r.deposits_in_transit.map((d) => d.amount));
  const oc = sumMoney(r.outstanding_checks.map((d) => d.amount));
  const unresolvedCount = r.exceptions.filter((e) => e.needs_review).length;
  const ok = isZeroMoney(r.difference);
  const periodEnd = formatShortDate(r.period_end);

  return (
    <Card className="p-5" data-testid="recon-summary" data-state="ready" data-difference={r.difference}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[14px] font-semibold text-gray-900">Reconciliation</div>
          <div className="text-[12px] text-gray-500">Cash, account 1010 · as of {periodEnd}, 2026</div>
        </div>
      </div>

      <div className="mt-3">
        <Row kind="balance" label={`Balance per bank, ${periodEnd}`} value={r.bank_ending_balance} />
        <Row label={`Add: deposits in transit (${r.deposits_in_transit.length})`} value={dit} items={itemRows(r.deposits_in_transit)} />
        <Row label={`Less: outstanding checks (${r.outstanding_checks.length})`} value={oc} negate items={itemRows(r.outstanding_checks)} />
        <Row kind="total" label="Adjusted bank balance" value={r.adjusted_bank_balance} />
      </div>

      <div className="mt-4">
        <Row kind="balance" label={`Balance per books, ${periodEnd}`} value={r.gl_ending_balance} />
        <Row
          label={`Proposed adjusting entries (${r.ajes.length})`}
          value={r.adjustments_total}
          items={r.exceptions
            .filter((e) => e.aje_id)
            .map((e) => ({ key: `${e.aje_id}`, label: `${e.aje_id} ${e.description}`, amount: e.effect }))}
        />
        <Row
          label={`Unidentified items flagged (${unresolvedCount})`}
          value={r.unresolved_total}
          items={r.exceptions.filter((e) => e.needs_review).map((e) => ({ key: `${e.bank_ref ?? e.gl_ref}`, label: e.description, amount: e.effect }))}
        />
        <Row kind="total" label="Adjusted book balance" value={r.adjusted_book_balance} />
      </div>

      <div
        className={cn(
          "mt-4 flex items-center justify-between rounded-lg border px-3.5 py-3",
          ok ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-red-200 bg-red-50 text-red-800",
        )}
      >
        <div className="flex items-center gap-2 text-[13px] font-semibold">
          {ok ? <CheckCircle2Icon className="size-5 text-emerald-600" /> : <CircleAlertIcon className="size-5 text-red-600" />}
          Difference
        </div>
        <div className="money text-[20px] font-semibold" data-testid="recon-difference">
          {formatMoney(r.difference)}
        </div>
      </div>
      <div className="mt-2 text-[11.5px] leading-relaxed text-gray-500">
        {ok
          ? unresolvedCount
            ? "Ties to the penny once the flagged item is treated as a reconciling item. A human must investigate it before sign-off."
            : "Ties to the penny after the proposed adjusting entries."
          : "Does not tie. The run cannot be approved until the difference is explained."}
      </div>
    </Card>
  );
}
