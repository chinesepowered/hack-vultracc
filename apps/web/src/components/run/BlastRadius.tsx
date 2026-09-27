import { useState } from "react";
import {
  AlertTriangleIcon,
  CheckIcon,
  ChevronDownIcon,
  CircleDashedIcon,
  FileInputIcon,
  FileOutputIcon,
  ServerIcon,
  ShieldAlertIcon,
  ShieldCheckIcon,
  XIcon,
} from "lucide-react";
import type { Attestation, DockerSummary, FileRef, SandboxLimits, UntrustedText } from "@/api/types";
import { Hash } from "@/components/hash";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { formatBytes, shortHash } from "@/lib/format";
import { modelName } from "@/lib/labels";
import { cn } from "@/lib/utils";

interface Item {
  id: string;
  ok: boolean | null;
  title: React.ReactNode;
  summary?: React.ReactNode;
  details?: React.ReactNode;
}

function Evidence({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[92px_1fr] gap-2 text-[11.5px]">
      <span className="text-gray-400">{label}</span>
      <span className="mono min-w-0 break-words text-gray-700">{children}</span>
    </div>
  );
}

function CheckRow({ item, open, onToggle }: { item: Item; open: boolean; onToggle: () => void }) {
  const Icon = item.ok === null ? CircleDashedIcon : item.ok ? CheckIcon : XIcon;
  return (
    <li className="border-b border-gray-100 last:border-0" data-testid={`blast-item-${item.id}`} data-ok={String(item.ok)}>
      <button type="button" onClick={onToggle} className="flex w-full items-start gap-2.5 py-2 text-left" aria-expanded={open}>
        <span
          className={cn(
            "mt-px flex size-[18px] shrink-0 items-center justify-center rounded-full",
            item.ok === null ? "bg-gray-100 text-gray-400" : item.ok ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700",
          )}
        >
          <Icon className="size-3" strokeWidth={3} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[13px] leading-snug font-medium text-gray-900">{item.title}</span>
          {item.summary && <span className="mt-0.5 block text-[12px] leading-snug text-gray-500">{item.summary}</span>}
        </span>
        {item.details && <ChevronDownIcon className={cn("mt-0.5 size-4 shrink-0 text-gray-400 transition-transform", open && "rotate-180")} />}
      </button>
      {open && item.details && <div className="mb-2.5 ml-7 space-y-1 rounded-md bg-gray-50 px-3 py-2">{item.details}</div>}
    </li>
  );
}

function FileList({ files, empty }: { files: FileRef[]; empty: string }) {
  if (!files.length) return <div className="text-[12px] text-gray-400">{empty}</div>;
  return (
    <ul className="space-y-1">
      {files.map((f) => (
        <li key={f.name} className="flex items-center justify-between gap-2 text-[12px]">
          <span className="mono min-w-0 truncate text-gray-800">{f.name}</span>
          <span className="flex shrink-0 items-center gap-2">
            <span className="text-gray-400">{formatBytes(f.bytes)}</span>
            <Hash value={f.sha256} head={8} tail={0} />
          </span>
        </li>
      ))}
    </ul>
  );
}

export function UntrustedCallout({ items }: { items: UntrustedText[] }) {
  if (!items.length) return null;
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 px-3.5 py-3" data-testid="untrusted-text-callout">
      {items.map((u, i) => (
        <div key={i} className={cn(i > 0 && "mt-3 border-t border-amber-200 pt-3")}>
          <div className="flex items-start gap-2">
            <AlertTriangleIcon className="mt-0.5 size-4 shrink-0 text-amber-600" />
            <div className="min-w-0 text-[12.5px] leading-relaxed text-amber-950">
              <div className="font-semibold">
                Instruction-like text found in {u.file}, line {u.row}
              </div>
              <blockquote className="mono mt-1.5 rounded border border-amber-200 bg-white/70 px-2 py-1.5 text-[11px] leading-relaxed break-words text-gray-800">
                {u.preview}
                {u.preview.length >= 200 ? "..." : ""}
              </blockquote>
              <div className="mt-1.5">
                <span className="font-semibold">Treated as data.</span> The sandbox has no network and no ledger access, so it could not act on it.
              </div>
              {u.classifier?.verdict === "unsafe" && (
                <div className="mt-1.5 flex items-center gap-1.5 text-[12px] text-amber-900" data-testid="untrusted-classifier">
                  <ShieldAlertIcon className="size-3.5 shrink-0 text-amber-700" />
                  Second opinion: {modelName(u.classifier.model)} flagged it as unsafe.
                </div>
              )}
              {u.reason && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {u.reason.split(";").map((r) => (
                    <span key={r} className="rounded bg-amber-100 px-1.5 py-0.5 text-[10.5px] text-amber-900">
                      {r.trim()}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function BlastRadius({
  attestation,
  docker,
  limits,
  inputs,
  outputs,
  tenant,
  sandboxId,
  host,
  imageDigest,
  untrusted,
  running,
  ended,
}: {
  attestation: Attestation | null;
  docker: DockerSummary | null;
  limits: SandboxLimits | null;
  inputs: FileRef[];
  outputs: FileRef[];
  tenant: string;
  sandboxId: string | null;
  host: string | null;
  imageDigest: string | null;
  untrusted: UntrustedText[];
  running: boolean;
  ended?: boolean;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [raw, setRaw] = useState(false);
  const check = (id: string) => attestation?.checks.find((c) => c.id === id);
  const ok = (...ids: string[]) => (attestation ? ids.every((id) => check(id)?.ok) : null);
  const facts = attestation?.facts;

  if (!attestation && !docker) {
    return (
      <Card className="p-5 scroll-mt-20" id="blast-radius" data-testid="blast-radius" data-state="pending">
        <Header passed={null} total={null} onRaw={undefined} />
        <UntrustedCallout items={untrusted} />
        <div className={cn("rounded-lg border border-dashed border-gray-300 px-4 py-6 text-center text-[12.5px] text-gray-500", untrusted.length && "mt-3")}>
          {ended ? "This run ended before a sandbox was created, so there was nothing to attest." : "The blast radius appears when the sandbox starts and attests itself."}
        </div>
      </Card>
    );
  }

  const cpus = docker?.NanoCpus ? docker.NanoCpus / 1e9 : limits?.cpus;
  const memMb = docker?.Memory ? Math.round(docker.Memory / 1024 / 1024) : limits?.memory_mb;
  const pids = docker?.PidsLimit ?? limits?.pids;
  const execS = limits?.exec_timeout_s ?? 60;
  const inMount = docker?.Mounts?.find((m) => m.Destination === "/in");
  const passed = attestation?.checks.filter((c) => c.ok).length ?? 0;
  const total = attestation?.checks.length ?? 0;
  const memLabel = memMb ? (memMb >= 1024 ? `${(memMb / 1024).toFixed(memMb % 1024 ? 1 : 0)} GiB` : `${memMb} MB`) : "n/a";

  const items: Item[] = [
    {
      id: "runtime",
      ok: docker ? docker.Runtime === "runsc" && (ok("gvisor_kernel") ?? true) : ok("gvisor_kernel"),
      title: <>Runtime: gVisor ({docker?.Runtime ?? "runsc"})</>,
      summary: "A user-space kernel sits between the agent's code and the host.",
      details: (
        <>
          <Evidence label="docker runtime">{docker?.Runtime ?? "n/a"}</Evidence>
          <Evidence label="kernel inside">{facts?.kernel ?? check("gvisor_kernel")?.detail ?? "n/a"}</Evidence>
        </>
      ),
    },
    {
      id: "network",
      ok: docker ? docker.NetworkMode === "none" && (ok("network_interfaces", "egress_blocked", "dns_blocked") ?? true) : ok("network_interfaces", "egress_blocked", "dns_blocked"),
      title: <>Network: {docker?.NetworkMode ?? "none"}</>,
      summary: "Only loopback. The outbound connection attempt failed, and so did DNS.",
      details: (
        <>
          <Evidence label="interfaces">{(facts?.interfaces ?? []).join(", ") || check("network_interfaces")?.detail}</Evidence>
          <Evidence label="outbound">{check("egress_blocked")?.detail ?? "n/a"}</Evidence>
          <Evidence label="dns">{check("dns_blocked")?.detail ?? "n/a"}</Evidence>
        </>
      ),
    },
    {
      id: "rootfs",
      ok: docker ? docker.ReadonlyRootfs && (ok("rootfs_readonly") ?? true) : ok("rootfs_readonly"),
      title: "Root filesystem read-only",
      summary: "Writing to / failed, as expected.",
      details: <Evidence label="write test">{check("rootfs_readonly")?.detail ?? "n/a"}</Evidence>,
    },
    {
      id: "inputs",
      ok: ok("inputs_readonly") !== false && (inMount ? !inMount.RW : true),
      title: "Inputs read-only",
      summary: "Client files are mounted at /in read-only. The write test failed, as expected.",
      details: (
        <>
          <Evidence label="write test">{check("inputs_readonly")?.detail ?? "n/a"}</Evidence>
          <Evidence label="mounts">{(docker?.Mounts ?? []).map((m) => `${m.Destination} ${m.RW ? "rw" : "ro"}`).join(", ")}</Evidence>
          <Evidence label="scratch">{[check("work_writable"), check("out_writable")].filter(Boolean).map((c) => c?.label).join("; ")}</Evidence>
        </>
      ),
    },
    {
      id: "user",
      ok: ok("non_root", "no_capabilities"),
      title: `User uid ${facts?.uid ?? 10001}, no capabilities`,
      summary: `Not root. CapEff ${facts?.cap_eff ?? "0000000000000000"}, every capability dropped.`,
      details: (
        <>
          <Evidence label="identity">{check("non_root")?.detail}</Evidence>
          <Evidence label="capabilities">{check("no_capabilities")?.detail}</Evidence>
          <Evidence label="cap drop">{(docker?.CapDrop ?? []).join(", ") || "n/a"}</Evidence>
        </>
      ),
    },
    {
      id: "privesc",
      ok: (ok("no_new_privs") ?? true) && (docker ? !docker.Privileged && docker.SecurityOpt.includes("no-new-privileges") : true),
      title: "No privilege escalation",
      summary: "no-new-privileges is set and the container is not privileged.",
      details: (
        <>
          <Evidence label="kernel flag">{check("no_new_privs")?.detail}</Evidence>
          <Evidence label="security opt">{(docker?.SecurityOpt ?? []).join(", ")}</Evidence>
          <Evidence label="privileged">{String(docker?.Privileged ?? false)}</Evidence>
        </>
      ),
    },
    {
      id: "limits",
      ok: cpus !== undefined && memMb !== undefined ? true : null,
      title: `Limits: ${cpus ?? 1} CPU, ${memLabel}, ${pids ?? 256} pids, ${execS} s per step`,
      summary: `Sandbox expires after ${Math.round((limits?.ttl_s ?? 900) / 60)} minutes even if nobody deletes it.`,
      details: (
        <>
          <Evidence label="docker">{`NanoCpus ${docker?.NanoCpus ?? "n/a"}, Memory ${docker?.Memory ?? "n/a"}, PidsLimit ${docker?.PidsLimit ?? "n/a"}`}</Evidence>
          <Evidence label="cgroup">
            {facts?.cgroup ? Object.entries(facts.cgroup).map(([k, v]) => `${k}=${v}`).join(", ") : "n/a"}
          </Evidence>
          <Evidence label="per step">{`timeout -s KILL ${execS}s, ttl ${limits?.ttl_s ?? 900}s`}</Evidence>
        </>
      ),
    },
    {
      id: "secrets",
      ok: ok("no_secrets_in_env"),
      title: "Secrets in environment: none",
      summary: (
        <span className="mt-1 flex flex-wrap gap-1">
          {(facts?.env_names ?? docker?.Env ?? []).map((n) => (
            <span key={n} className="mono rounded border border-gray-200 bg-white px-1 py-px text-[10.5px] text-gray-600">
              {n}
            </span>
          ))}
        </span>
      ),
    },
  ];

  return (
    <Card className="scroll-mt-20 p-5" id="blast-radius" data-testid="blast-radius" data-state="ready" data-passed={passed} data-total={total}>
      <Header passed={passed} total={total} onRaw={() => setRaw(true)} />
      <UntrustedCallout items={untrusted} />
      <ul className={cn(untrusted.length && "mt-2")}>
        {items.map((it) => (
          <CheckRow key={it.id} item={it} open={!!open[it.id]} onToggle={() => setOpen((o) => ({ ...o, [it.id]: !o[it.id] }))} />
        ))}
      </ul>

      <div className="mt-3 space-y-3">
        <div className="rounded-lg border border-gray-200 p-3" data-testid="blast-inputs">
          <div className="mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-[12px] font-semibold text-gray-800">
              <FileInputIcon className="size-3.5 text-gray-500" /> Files it could read
            </span>
            <span className="text-[11px] text-gray-400">/in, read-only</span>
          </div>
          <FileList files={inputs} empty="Inputs are listed when the sandbox starts." />
        </div>
        <div className="rounded-lg border border-gray-200 p-3" data-testid="blast-outputs">
          <div className="mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-[12px] font-semibold text-gray-800">
              <FileOutputIcon className="size-3.5 text-gray-500" /> Files that left
            </span>
            <span className="text-[11px] text-gray-400">validated, hashed, stored</span>
          </div>
          <FileList files={outputs} empty={running ? "Nothing has left the sandbox yet." : "No files left the sandbox."} />
          {outputs.length > 0 && (
            <div className="mt-2 text-[11px] leading-relaxed text-gray-500">
              Pulled out by the runner (no symlinks, size caps), hashed, and stored in Vultr Object Storage. Nothing else leaves.
            </div>
          )}
        </div>
      </div>

      <dl className="mt-3 space-y-1.5 border-t border-gray-100 pt-3 text-[12px]">
        <div className="flex items-center justify-between gap-3">
          <dt className="text-gray-500">Tenant label</dt>
          <dd className="mono truncate text-gray-800">arena.tenant={tenant}</dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="text-gray-500">Image</dt>
          <dd className="flex min-w-0 items-center gap-1.5">
            <span className="mono truncate text-gray-800">
              {facts?.image_build ? `${facts.image_build.image} ${facts.image_build.version}` : (docker?.Image ?? "tieout-sandbox")}
            </span>
          </dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="text-gray-500">Image digest</dt>
          <dd className="min-w-0">
            <Hash value={(imageDigest ?? docker?.ImageDigest ?? "").split("@").pop() || null} head={12} tail={6} />
          </dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="text-gray-500">Host</dt>
          <dd className="flex min-w-0 items-center gap-1.5 text-gray-800">
            <ServerIcon className="size-3.5 text-gray-400" />
            <span className="mono truncate">{host ?? docker?.Host ?? "n/a"}</span>
            {sandboxId && <span className="mono truncate text-gray-400">{shortHash(sandboxId, 12, 0).replace("...", "")}</span>}
          </dd>
        </div>
      </dl>

      <Dialog open={raw} onOpenChange={setRaw}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Raw attestation</DialogTitle>
            <DialogDescription>
              Produced by /opt/attest.py inside the sandbox at start, plus the runner's docker inspect summary. Stored with the run.
            </DialogDescription>
          </DialogHeader>
          <pre className="mono scrollbar-thin max-h-[60vh] overflow-auto rounded-lg border bg-gray-50 p-3 text-[11px] leading-relaxed text-gray-700">
            {JSON.stringify({ attestation, docker }, null, 2)}
          </pre>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Header({ passed, total, onRaw }: { passed: number | null; total: number | null; onRaw?: () => void }) {
  return (
    <div className="mb-3 flex items-start justify-between gap-2">
      <div>
        <div className="flex items-center gap-2 text-[14px] font-semibold text-gray-900">
          <ShieldCheckIcon className="size-4 text-indigo-600" /> Blast radius
        </div>
        <div className="mt-0.5 text-[12px] leading-snug text-gray-500">What this client's sandbox could touch, attested from inside it at start.</div>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        {passed !== null && total !== null && (
          <Badge variant={passed === total ? "success" : "danger"} data-testid="attestation-badge">
            <CheckIcon strokeWidth={3} /> {passed}/{total} attested
          </Badge>
        )}
        {onRaw && (
          <button type="button" onClick={onRaw} className="text-[11px] font-medium text-indigo-700 hover:underline">
            Raw JSON
          </button>
        )}
      </div>
    </div>
  );
}
