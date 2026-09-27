import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileSpreadsheetIcon, FileTextIcon, ListChecksIcon, Loader2Icon, ReceiptIcon, TriangleAlertIcon } from "lucide-react";
import { api } from "@/api";
import type { ReconResult, RunDetail } from "@/api/types";
import { EmptyState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Hint } from "@/components/ui/tooltip";
import { formatDate, formatMoney, moneyNumber, shortHash, sumMoney } from "@/lib/format";
import { EXCEPTION_DESCRIPTION, EXCEPTION_LABEL, exceptionTone, treatmentLabel } from "@/lib/labels";
import { Markdown } from "@/lib/markdown";
import { cn } from "@/lib/utils";

function KindBadge({ kind }: { kind: keyof typeof EXCEPTION_LABEL }) {
  const tone = exceptionTone(kind);
  return (
    <Hint label={EXCEPTION_DESCRIPTION[kind]}>
      <Badge variant={tone === "timing" ? "secondary" : tone === "review" ? "danger" : "warning"}>{EXCEPTION_LABEL[kind]}</Badge>
    </Hint>
  );
}

function Refs({ bank, gl }: { bank: string | null; gl: string | null }) {
  return (
    <div className="mono space-y-0.5 text-[11.5px] leading-tight">
      {bank && (
        <div>
          <span className="text-gray-400">bank </span>
          <span className="text-gray-700">{bank}</span>
        </div>
      )}
      {gl && (
        <div>
          <span className="text-gray-400">gl </span>
          <span className="text-gray-700">{gl}</span>
        </div>
      )}
      {!bank && !gl && <span className="text-gray-400">n/a</span>}
    </div>
  );
}

function ExceptionsTable({ result }: { result: ReconResult }) {
  if (!result.exceptions.length) return <EmptyState icon={<ListChecksIcon />} title="No exceptions">Every bank line matched a ledger line.</EmptyState>;
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Kind</TableHead>
          <TableHead>Date</TableHead>
          <TableHead>Description</TableHead>
          <TableHead>References</TableHead>
          <TableHead className="text-right">Amount</TableHead>
          <TableHead>Treatment</TableHead>
          <TableHead>Agent's note</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {result.exceptions.map((e, i) => (
          <TableRow key={i} className={cn(e.needs_review && "bg-red-50/40")}>
            <TableCell>
              <KindBadge kind={e.kind} />
            </TableCell>
            <TableCell className="tnum whitespace-nowrap text-gray-600">{formatDate(e.date)}</TableCell>
            <TableCell className="max-w-[260px] font-medium text-gray-900">{e.description}</TableCell>
            <TableCell>
              <Refs bank={e.bank_ref} gl={e.gl_ref} />
            </TableCell>
            <TableCell className="money text-right font-medium">{formatMoney(e.amount)}</TableCell>
            <TableCell className="whitespace-nowrap">
              <span className={cn("text-[12.5px]", e.needs_review ? "font-medium text-red-700" : e.aje_id ? "font-medium text-indigo-700" : "text-gray-600")}>{treatmentLabel(e)}</span>
            </TableCell>
            <TableCell className="max-w-[320px] text-[12.5px] leading-snug text-gray-600">{e.note}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function AjesTable({ result, approved }: { result: ReconResult; approved: boolean }) {
  if (!result.ajes.length)
    return (
      <EmptyState icon={<ReceiptIcon />} title="No adjusting entries needed">
        Every exception was a timing item. The reviewer signs off the reconciliation as is.
      </EmptyState>
    );
  const total = sumMoney(result.ajes.map((a) => a.amount));
  return (
    <div>
      <div className="flex items-center gap-2 border-b border-gray-100 px-4 py-2.5 text-[12.5px] text-gray-600">
        <ReceiptIcon className="size-4 text-gray-400" />
        {approved
          ? "Approved by a reviewer. Export the CSV and import it into the ledger; the agent never posts."
          : "Proposals only. The agent has no ledger access, and these entries export only after a reviewer approves them."}
      </div>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Entry</TableHead>
            <TableHead>Date</TableHead>
            <TableHead>Account</TableHead>
            <TableHead className="text-right">Debit</TableHead>
            <TableHead className="text-right">Credit</TableHead>
            <TableHead>Memo</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {result.ajes.map((a) => (
            <FragmentRows key={a.id} aje={a} />
          ))}
        </TableBody>
        <TableFooter>
          <TableRow className="hover:bg-transparent">
            <TableCell colSpan={3} className="text-[12px] font-semibold text-gray-700">
              Total ({result.ajes.length} entries, balanced)
            </TableCell>
            <TableCell className="money text-right font-semibold">{formatMoney(total)}</TableCell>
            <TableCell className="money text-right font-semibold">{formatMoney(total)}</TableCell>
            <TableCell />
          </TableRow>
        </TableFooter>
      </Table>
    </div>
  );
}

function FragmentRows({ aje }: { aje: ReconResult["ajes"][number] }) {
  return (
    <>
      <TableRow className="border-b-0">
        <TableCell rowSpan={2} className="align-top">
          <div className="mono text-[12.5px] font-semibold text-gray-900">{aje.id}</div>
          <div className="mt-1">
            <KindBadge kind={aje.exception_kind} />
          </div>
        </TableCell>
        <TableCell rowSpan={2} className="tnum align-top whitespace-nowrap text-gray-600">
          {formatDate(aje.date)}
        </TableCell>
        <TableCell>
          <span className="mono text-gray-500">{aje.debit_account}</span> <span className="text-gray-900">{aje.debit_account_name}</span>
        </TableCell>
        <TableCell className="money text-right">{formatMoney(aje.amount)}</TableCell>
        <TableCell />
        <TableCell rowSpan={2} className="max-w-[360px] align-top text-[12.5px] leading-snug text-gray-600">
          {aje.memo}
        </TableCell>
      </TableRow>
      <TableRow>
        <TableCell className="pl-8">
          <span className="mono text-gray-500">{aje.credit_account}</span> <span className="text-gray-900">{aje.credit_account_name}</span>
        </TableCell>
        <TableCell />
        <TableCell className="money text-right">{formatMoney(aje.amount)}</TableCell>
      </TableRow>
    </>
  );
}

type Sheet = "summary" | "exceptions" | "ajes" | "matches";

function Workpaper({ run, result }: { run: RunDetail; result: ReconResult }) {
  const [sheet, setSheet] = useState<Sheet>("summary");
  const [limit, setLimit] = useState(120);
  const download = useMutation({
    mutationFn: () => api.download(run.id, "workpaper.xlsx", `${run.client_id}-${run.period}-workpaper.xlsx`),
    onError: (e: unknown) => toast.error("Download failed", { description: e instanceof Error ? e.message : String(e) }),
  });
  const dit = sumMoney(result.deposits_in_transit.map((d) => d.amount));
  const oc = sumMoney(result.outstanding_checks.map((d) => d.amount));
  const hash = run.hashes["workpaper.xlsx"];
  const sheets: { id: Sheet; label: string }[] = [
    { id: "summary", label: "Summary" },
    { id: "matches", label: `Matches (${result.matches.length})` },
    { id: "exceptions", label: `Exceptions (${result.exceptions.length})` },
    { id: "ajes", label: `Proposed AJEs (${result.ajes.length})` },
  ];
  const summaryRows: [string, string | null, boolean?][] = useMemo(
    () => [
      ["Balance per bank statement", result.bank_ending_balance],
      ["Add: deposits in transit", dit],
      ["Less: outstanding checks", (-moneyNumber(oc)).toFixed(2)],
      ["Adjusted bank balance", result.adjusted_bank_balance, true],
      ["Balance per general ledger", result.gl_ending_balance],
      ["Proposed adjusting entries", result.adjustments_total],
      ["Unidentified items (flagged)", result.unresolved_total],
      ["Adjusted book balance", result.adjusted_book_balance, true],
      ["Difference", result.difference, true],
    ],
    [result, dit, oc],
  );

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
            <FileSpreadsheetIcon className="size-5" />
          </div>
          <div>
            <div className="text-[13px] font-semibold text-gray-900">
              {result.client_name} · {run.period} · workpaper.xlsx
            </div>
            <div className="text-[11.5px] text-gray-500">
              Prepared by {result.prepared_by ?? "Tieout agent"}, run <span className="mono">{result.run_id}</span>
              {hash ? (
                <>
                  {" "}
                  · sha256 <span className="mono">{shortHash(hash, 10, 6)}</span>
                </>
              ) : null}
            </div>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={() => download.mutate()} disabled={download.isPending} data-testid="workpaper-download">
          {download.isPending ? <Loader2Icon className="animate-spin" /> : <FileSpreadsheetIcon />} Download .xlsx
        </Button>
      </div>
      <div className="flex items-center gap-1 border-b border-gray-100 bg-gray-50/60 px-3 pt-2">
        {sheets.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setSheet(s.id)}
            className={cn(
              "-mb-px rounded-t-md border border-b-0 px-3 py-1.5 text-[12px] font-medium",
              sheet === s.id ? "border-gray-200 bg-white text-gray-900" : "border-transparent text-gray-500 hover:text-gray-800",
            )}
          >
            {s.label}
          </button>
        ))}
      </div>
      <div className="scrollbar-thin max-h-[440px] overflow-auto">
        {sheet === "summary" && (
          <table className="w-full max-w-2xl text-[13px]">
            <tbody>
              {summaryRows.map(([label, value, strong]) => (
                <tr key={label} className={cn("border-b border-gray-100", strong && "bg-gray-50/80")}>
                  <td className={cn("px-4 py-2", strong ? "font-semibold text-gray-900" : "text-gray-700")}>{label}</td>
                  <td className={cn("money px-4 py-2 text-right", strong && "font-semibold", label === "Difference" && (moneyNumber(value) === 0 ? "text-emerald-700" : "text-red-700"))}>
                    {formatMoney(value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {sheet === "exceptions" && <ExceptionsTable result={result} />}
        {sheet === "ajes" && <AjesTable result={result} approved={run.approval_status === "approved"} />}
        {sheet === "matches" && (
          <>
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Bank ref</TableHead>
                  <TableHead>Bank date</TableHead>
                  <TableHead>GL ref</TableHead>
                  <TableHead>GL date</TableHead>
                  <TableHead>Method</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.matches.slice(0, limit).map((m) => (
                  <TableRow key={m.bank_ref}>
                    <TableCell className="mono text-[12px]">{m.bank_ref}</TableCell>
                    <TableCell className="tnum text-gray-600">{formatDate(m.bank_date)}</TableCell>
                    <TableCell className="mono text-[12px]">{m.gl_ref}</TableCell>
                    <TableCell className="tnum text-gray-600">{formatDate(m.gl_date)}</TableCell>
                    <TableCell className="text-gray-600">{m.method.replace("_", " ")}</TableCell>
                    <TableCell className="money text-right">{formatMoney(m.amount)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {result.matches.length > limit && (
              <div className="flex items-center justify-center gap-3 border-t border-gray-100 py-3 text-[12px] text-gray-500">
                Showing {limit} of {result.matches.length} matches
                <Button variant="outline" size="sm" onClick={() => setLimit(result.matches.length)}>
                  Show all
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export function RunTabs({ run }: { run: RunDetail }) {
  const result = run.result;
  const counts = result
    ? { exceptions: result.exceptions.length, ajes: result.ajes.length, flagged: result.exceptions.filter((e) => e.needs_review).length }
    : null;
  return (
    <Card className="overflow-hidden" data-testid="run-tabs">
      <Tabs defaultValue="exceptions">
        <TabsList className="px-3">
          <TabsTrigger value="exceptions" data-testid="tab-exceptions">
            <TriangleAlertIcon /> Exceptions
            {counts && (
              <Badge variant={counts.flagged ? "warning" : "secondary"} className="px-1.5 py-0 text-[11px]">
                {counts.exceptions}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="ajes" data-testid="tab-ajes">
            <ReceiptIcon /> Proposed AJEs
            {counts && (
              <Badge variant="secondary" className="px-1.5 py-0 text-[11px]">
                {counts.ajes}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="workpaper" data-testid="tab-workpaper">
            <FileSpreadsheetIcon /> Workpaper preview
          </TabsTrigger>
          <TabsTrigger value="memo" data-testid="tab-memo">
            <FileTextIcon /> Memo
          </TabsTrigger>
        </TabsList>
        {!result ? (
          <EmptyState icon={<ListChecksIcon />} title="Results appear when the run finishes">
            Exceptions, proposed entries, the workpaper and the reviewer memo all come from result.json, written by code in the sandbox.
          </EmptyState>
        ) : (
          <>
            <TabsContent value="exceptions" data-testid="panel-exceptions">
              <ExceptionsTable result={result} />
            </TabsContent>
            <TabsContent value="ajes" data-testid="panel-ajes">
              <AjesTable result={result} approved={run.approval_status === "approved"} />
            </TabsContent>
            <TabsContent value="workpaper" data-testid="panel-workpaper">
              <Workpaper run={run} result={result} />
            </TabsContent>
            <TabsContent value="memo" data-testid="panel-memo">
              {run.memo_md ? (
                <div className="grid grid-cols-1 gap-6 px-4 py-5 sm:px-6 lg:grid-cols-[1fr_260px]">
                  <Markdown source={run.memo_md} className="max-w-3xl text-[13.5px] text-gray-700" />
                  <div className="h-fit rounded-lg border border-gray-200 bg-gray-50 p-4 text-[12px] leading-relaxed text-gray-600">
                    <div className="mb-1 font-semibold text-gray-800">About this memo</div>
                    Written by the agent for the reviewer. It is narrative only: every number in it comes from code executed in the sandbox, and the memo is not part of the
                    replay hashes.
                  </div>
                </div>
              ) : (
                <EmptyState icon={<FileTextIcon />} title="No memo">
                  {run.kind === "replay" ? "Replays re-run code only; the memo lives on the original run." : "The agent did not write a memo for this run."}
                </EmptyState>
              )}
            </TabsContent>
          </>
        )}
      </Tabs>
    </Card>
  );
}
