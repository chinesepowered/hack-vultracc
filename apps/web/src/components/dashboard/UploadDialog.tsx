import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheetIcon, Loader2Icon, OctagonAlertIcon, ShieldCheckIcon, UploadIcon } from "lucide-react";
import { api, ApiError } from "@/api";
import type { UploadField } from "@/api/types";
import { Alert } from "@/components/states";
import { StatusPill } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { qk } from "@/hooks/queries";
import { formatBytes, formatDateTime } from "@/lib/format";
import { runStatusDisplay } from "@/lib/labels";

const MAX_BYTES = 512 * 1024;

const FIELDS: { key: UploadField; label: string; hint: string; required: boolean; sample: string }[] = [
  { key: "bank_statement", label: "Bank statement export", hint: "CSV from the bank portal, any column layout or date format.", required: true, sample: "bank_statement.csv" },
  { key: "gl_cash_detail", label: "Cash ledger detail", hint: "The cash account's general ledger detail for the month (CSV).", required: true, sample: "gl_cash_detail.csv" },
  { key: "prior_outstanding", label: "Prior month outstanding items", hint: "Checks and deposits still open at last month end.", required: false, sample: "prior_outstanding.csv" },
];

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] ?? "");
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
    reader.readAsDataURL(file);
  });
}

export function UploadDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [periodEnd, setPeriodEnd] = useState("2026-09-30");
  const [files, setFiles] = useState<Partial<Record<UploadField, File>>>({});
  const [error, setError] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: async () => {
      const encoded: Partial<Record<UploadField, string>> = {};
      for (const f of FIELDS) {
        const file = files[f.key];
        if (file) encoded[f.key] = await toBase64(file);
      }
      return api.upload({ name: name.trim(), period_end: periodEnd, files: encoded });
    },
    onSuccess: (run) => {
      void qc.invalidateQueries({ queryKey: qk.uploads });
      onOpenChange(false);
      setName("");
      setFiles({});
      navigate(`/runs/${run.id}`);
    },
    onError: (e) => setError(e instanceof ApiError || e instanceof Error ? e.message : "Could not upload the files."),
  });

  const tooBig = FIELDS.find((f) => (files[f.key]?.size ?? 0) > MAX_BYTES);
  const missing = !name.trim() ? "Give the client a name." : !files.bank_statement ? "Choose the bank statement file." : !files.gl_cash_detail ? "Choose the cash ledger file." : null;

  return (
    <Dialog open={open} onOpenChange={(o) => !submit.isPending && onOpenChange(o)}>
      <DialogContent className="max-w-xl" data-testid="upload-dialog">
        <DialogHeader>
          <DialogTitle>Reconcile your own files</DialogTitle>
          <DialogDescription>
            Upload a bank statement export and the matching cash ledger detail. The agent works out the format and reconciles them in a fresh gVisor sandbox with no
            network. Inside it the files are read-only; they stay in the firm's private storage.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid grid-cols-[1fr_170px] gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="upload-name">Client name</Label>
              <Input id="upload-name" data-testid="upload-name" value={name} maxLength={60} placeholder="Acme Plumbing" onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="upload-period">Period end</Label>
              <Input id="upload-period" data-testid="upload-period" type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
            </div>
          </div>
          {FIELDS.map((f) => {
            const file = files[f.key];
            return (
              <div key={f.key} className="grid gap-1.5">
                <Label htmlFor={`upload-${f.key}`}>
                  {f.label}
                  {!f.required && <span className="font-normal text-gray-400">(optional)</span>}
                </Label>
                <Input
                  id={`upload-${f.key}`}
                  data-testid={`upload-file-${f.key}`}
                  type="file"
                  accept=".csv,.txt,text/csv,text/plain"
                  className="h-auto py-1.5 file:mr-3 file:rounded file:border-0 file:bg-gray-100 file:px-2.5 file:py-1 file:text-[12px] file:font-medium file:text-gray-700"
                  onChange={(e) => setFiles((prev) => ({ ...prev, [f.key]: e.target.files?.[0] }))}
                />
                <p className={file && file.size > MAX_BYTES ? "text-[12px] text-red-600" : "text-[12px] text-gray-500"}>
                  {file ? `${file.name}, ${formatBytes(file.size)}${file.size > MAX_BYTES ? ": larger than the 512 KB limit" : ""}` : f.hint}
                </p>
              </div>
            );
          })}
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-gray-600" data-testid="upload-samples">
            No files handy? Start from a sample client (Ironwood Brewing):{" "}
            {FIELDS.map((f, i) => (
              <span key={f.key}>
                <a className="font-medium text-indigo-700 underline-offset-2 hover:underline" href={api.sampleUrl(f.sample)} download={`sample-${f.sample}`}>
                  {f.label.toLowerCase().replace(" export", "").replace(" detail", "")}
                </a>
                {i < FIELDS.length - 1 ? ", " : ". "}
              </span>
            ))}
            Add a bank fee or change an amount, upload them, and watch the agent find it.
          </div>
          <div className="flex items-start gap-2 text-[12px] text-gray-500">
            <ShieldCheckIcon className="mt-0.5 size-3.5 shrink-0 text-emerald-600" />
            Uploads are limited in size and rate, never join the monthly close, and every upload is written to the audit log with the SHA-256 of each file.
          </div>
          {error && (
            <Alert tone="warning" icon={<OctagonAlertIcon />} data-testid="upload-error">
              {error}
            </Alert>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submit.isPending}>
            Cancel
          </Button>
          <Button
            data-testid="upload-submit"
            title={missing ?? (tooBig ? `The ${tooBig.label.toLowerCase()} is larger than 512 KB.` : undefined)}
            disabled={!!missing || !!tooBig || submit.isPending}
            onClick={() => {
              setError(null);
              submit.mutate();
            }}
          >
            {submit.isPending ? <Loader2Icon className="animate-spin" /> : <UploadIcon />}
            {submit.isPending ? "Starting the sandbox" : "Reconcile in a sandbox"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Recent runs from uploaded files, below the client grid. Hidden until there is one. */
export function UploadsCard() {
  const uploads = useQuery({
    queryKey: qk.uploads,
    queryFn: () => api.uploads(),
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === "queued" || r.status === "running") ? 3000 : 30_000),
  });
  if (!uploads.data?.length) return null;
  return (
    <Card className="mt-6 gap-0 overflow-hidden p-0" data-testid="uploads-list">
      <div className="border-b border-gray-100 px-5 py-3">
        <h2 className="text-[14px] font-semibold text-gray-900">Uploaded files</h2>
        <p className="text-[12.5px] text-gray-500">Reconciled outside the monthly close, each in its own sandbox.</p>
      </div>
      <ul className="divide-y divide-gray-100">
        {uploads.data.slice(0, 4).map((r) => {
          const d = runStatusDisplay(r.status, r.recon_status, r.sandbox_state);
          return (
            <li key={r.id}>
              <Link to={`/runs/${r.id}`} className="flex items-center gap-3 px-5 py-2.5 hover:bg-gray-50" data-testid={`upload-row-${r.id}`}>
                <FileSpreadsheetIcon className="size-4 shrink-0 text-gray-400" />
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-gray-900">{r.client_name}</span>
                <span className="hidden text-[12px] text-gray-500 sm:inline">
                  {r.created_by_name ? `${r.created_by_name} · ` : ""}
                  {formatDateTime(r.started_at ?? r.finished_at)}
                </span>
                <StatusPill tone={d.tone} spinning={r.status === "running"} size="sm">
                  {d.label}
                </StatusPill>
              </Link>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
