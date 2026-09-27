import { Link } from "react-router";
import {
  ArrowDownIcon,
  ArrowRightIcon,
  BotIcon,
  CloudIcon,
  ContainerIcon,
  CpuIcon,
  DatabaseIcon,
  FileLock2Icon,
  GaugeIcon,
  GitCompareArrowsIcon,
  GlobeIcon,
  HardDriveIcon,
  KeyRoundIcon,
  LayersIcon,
  LockIcon,
  NetworkIcon,
  OctagonAlertIcon,
  ServerIcon,
  ShieldCheckIcon,
  SplitIcon,
  TargetIcon,
  TimerIcon,
  UserCheckIcon,
  UsersIcon,
  WifiOffIcon,
} from "lucide-react";
import { groundTruthHeadline } from "@/components/dashboard/GroundTruthCard";
import { Card } from "@/components/ui/card";
import { useBatches, useGroundTruth, useMe, useSystem } from "@/hooks/queries";
import { cn } from "@/lib/utils";

const CLIENT_CHIPS = [
  "Alder & Finch",
  "Blue Harbor",
  "Brightwater PT",
  "Cedar Ridge",
  "Copperline",
  "Ironwood",
  "Juniper Lane",
  "Lumen",
  "Northgate",
  "Saltbox",
  "Stillwater",
  "Tidewater",
];

const GUARANTEES = [
  {
    n: 1,
    icon: <WifiOffIcon />,
    title: "Nothing leaves",
    how: "Every sandbox runs with Docker network mode none under gVisor. At start it attests from the inside: only a loopback interface, the outbound connection attempt fails, DNS fails.",
    where: "Run detail, Blast radius: Network none",
  },
  {
    n: 2,
    icon: <LockIcon />,
    title: "Nothing is altered",
    how: "Client files are mounted read-only at /in and the root filesystem is read-only. The attestation's write tests fail, as they should. Only /work and /out are writable.",
    where: "Blast radius: Inputs read-only, Files it could read (SHA-256)",
  },
  {
    n: 3,
    icon: <UserCheckIcon />,
    title: "Nothing is posted without a human",
    how: "The agent has no ledger access at all. Adjusting entries are a file, and the export refuses until a reviewer approves. Maker-checker: whoever started the close cannot approve it.",
    where: "Run detail, Reviewer approval and the AJE CSV button",
  },
  {
    n: 4,
    icon: <SplitIcon />,
    title: "Nothing crosses clients",
    how: "One sandbox per client per run, labeled with its tenant, with its own host workspace and its own Object Storage prefix. One client's data never shares a sandbox with another's.",
    where: "Dashboard tiles, Admin: live sandboxes by tenant",
  },
  {
    n: 5,
    icon: <GitCompareArrowsIcon />,
    title: "Everything is reproducible",
    how: "Every step's code and every input is recorded. Replay re-executes the code in a fresh sandbox and compares SHA-256 hashes of every output. Event logs are hash-chained.",
    where: "Run detail: Replay, Reproducible badge, Evidence pack",
  },
];

const GUARDRAILS = [
  { icon: <UsersIcon />, title: "Sign-in and roles", body: "Seeded demo accounts; preparer, reviewer and admin see different actions." },
  { icon: <GaugeIcon />, title: "Rate limits", body: "Per-user limits on closes, replays and sign-in attempts." },
  { icon: <LayersIcon />, title: "Global sandbox cap", body: "The runner refuses new sandboxes past its cap (HTTP 429)." },
  { icon: <TimerIcon />, title: "TTL janitor", body: "Every sandbox expires after 15 minutes, orphans are cleaned at startup." },
  { icon: <CpuIcon />, title: "Daily token budget", body: "Runs stop when the day's Serverless Inference budget is spent." },
  { icon: <OctagonAlertIcon />, title: "Kill switch", body: "One admin action stops new work and destroys every running sandbox." },
  { icon: <KeyRoundIcon />, title: "No secrets in sandboxes", body: "Keys live on the control plane only; sandboxes get none." },
  { icon: <NetworkIcon />, title: "No public inbound", body: "The sandbox host is reachable only from the control plane over the VPC." },
];

const PRODUCTS = [
  { icon: <ServerIcon />, name: "Cloud Compute", role: "Two VMs: the public control plane (Caddy, API, orchestrator) and the private sandbox host running gVisor containers." },
  { icon: <NetworkIcon />, name: "VPC", role: "Private network between them. The sandbox runner listens only on its VPC address, behind a bearer token." },
  { icon: <ShieldCheckIcon />, name: "Firewall Groups", role: "Only 80 and 443 open on the control plane; the sandbox host accepts nothing from the internet." },
  { icon: <BotIcon />, name: "Serverless Inference", role: "Every LLM call: GLM 5.3 plans each step, GLM 5.3 Flash is the fallback, Nemotron 3.5 Content Safety gives a second opinion on flagged text." },
  { icon: <DatabaseIcon />, name: "Managed PostgreSQL", role: "System of record: runs, hash-chained event logs, signed approvals and the audit log." },
  { icon: <HardDriveIcon />, name: "Object Storage", role: "Inputs and every output, per client and run, in a private bucket with short-lived presigned downloads." },
];

function Box({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("rounded-xl border border-gray-200 bg-white shadow-card", className)}>{children}</div>;
}

function BoxTitle({ icon, title, tag, sub }: { icon: React.ReactNode; title: string; tag?: string; sub?: string }) {
  return (
    <div className="flex items-start gap-2.5">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700 [&_svg]:size-4">{icon}</div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13.5px] font-semibold text-gray-900">{title}</span>
          {tag && <span className="rounded bg-indigo-600 px-1.5 py-px text-[10px] font-semibold tracking-wide text-white uppercase">{tag}</span>}
        </div>
        {sub && <div className="text-[12px] text-gray-500">{sub}</div>}
      </div>
    </div>
  );
}

function DownArrow({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center py-1.5">
      <div className="h-4 w-px bg-gray-300" />
      <div className="rounded-full border border-gray-200 bg-white px-2.5 py-0.5 text-[11px] font-medium text-gray-600">{label}</div>
      <div className="h-3 w-px bg-gray-300" />
      <ArrowDownIcon className="-mt-1 size-3.5 text-gray-400" />
    </div>
  );
}

export function ArchitectureDiagram() {
  const services = [
    { icon: <BotIcon />, title: "Vultr Serverless Inference", sub: "GLM 5.3 plans every step; no other LLM provider" },
    { icon: <DatabaseIcon />, title: "Vultr Managed PostgreSQL", sub: "System of record, hash-chained logs, approvals" },
    { icon: <HardDriveIcon />, title: "Vultr Object Storage", sub: "Inputs, outputs, evidence; presigned downloads" },
  ];
  return (
    <div className="rounded-2xl border border-gray-200 bg-gradient-to-b from-white to-gray-50/80 p-6" data-testid="architecture-diagram">
      <div className="mx-auto max-w-[1080px]">
        <div className="grid grid-cols-[minmax(0,1fr)_64px_300px] items-start">
          <div className="flex flex-col items-center">
            <Box className="w-[360px] px-4 py-3">
              <BoxTitle icon={<GlobeIcon />} title="Browser" sub="Preparers, reviewers, admins and judges" />
            </Box>
            <DownArrow label="HTTPS 443, Caddy with automatic TLS" />
          </div>
          <div />
          <div className="flex h-full items-end justify-center pb-3 text-[11px] font-semibold tracking-wide text-gray-400 uppercase">Managed by Vultr</div>
        </div>

        <div className="grid grid-cols-[minmax(0,1fr)_64px_300px] items-stretch">
          <Box className="border-indigo-200 px-5 py-4 ring-4 ring-indigo-50">
            <BoxTitle icon={<ServerIcon />} title="Control-plane VM" tag="Public" sub="Vultr Cloud Compute, Silicon Valley (sjc)" />
            <div className="mt-3 grid grid-cols-2 gap-2 text-[12px]">
              {[
                ["Caddy", "TLS, static web app"],
                ["API (FastAPI)", "Auth, roles, SSE"],
                ["Orchestrator", "One task per client run"],
                ["Agent loop", "Plans with the LLM, never runs code itself"],
                ["Guardrails", "Quotas, budget, kill switch"],
                ["Secrets", "Stay here. Never sent to a sandbox"],
              ].map(([t, s]) => (
                <div key={t} className="rounded-lg border border-gray-100 bg-gray-50/80 px-2.5 py-1.5">
                  <div className="font-medium text-gray-800">{t}</div>
                  <div className="text-[11px] leading-snug text-gray-500">{s}</div>
                </div>
              ))}
            </div>
          </Box>
          <div className="flex flex-col justify-around py-3">
            {services.map((s) => (
              <div key={s.title} className="flex items-center">
                <div className="h-px flex-1 bg-indigo-300" />
                <ArrowRightIcon className="-ml-1 size-3.5 text-indigo-400" />
              </div>
            ))}
          </div>
          <div className="flex flex-col justify-between gap-2.5">
            {services.map((s) => (
              <Box key={s.title} className="flex-1 px-3.5 py-3">
                <BoxTitle icon={s.icon} title={s.title} sub={s.sub} />
              </Box>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-[minmax(0,1fr)_64px_300px]">
          <div className="flex flex-col items-center">
            <DownArrow label="Private Vultr VPC only, bearer token" />
          </div>
        </div>

        <div className="grid grid-cols-[minmax(0,1fr)_64px_300px]">
          <Box className="col-span-3 px-5 py-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <BoxTitle icon={<ContainerIcon />} title="Sandbox-host VM" tag="No public inbound" sub="Vultr Cloud Compute · sandbox-runner (FastAPI + Docker SDK) · gVisor runtime" />
              <div className="flex flex-wrap gap-1.5 text-[11px]">
                {["network none", "read-only rootfs", "inputs read-only", "1 CPU, 1 GiB", "uid 10001, no caps", "60 s per step", "15 min TTL"].map((t) => (
                  <span key={t} className="rounded-md border border-gray-200 bg-gray-50 px-1.5 py-0.5 text-gray-600">
                    {t}
                  </span>
                ))}
              </div>
            </div>
            <div className="mt-3 grid grid-cols-6 gap-2">
              {CLIENT_CHIPS.map((c) => (
                <div key={c} className="flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50/50 px-2 py-2 text-[11.5px] font-medium text-indigo-900">
                  <ShieldCheckIcon className="size-3.5 shrink-0 text-indigo-600" />
                  <span className="truncate">{c}</span>
                </div>
              ))}
            </div>
            <div className="mt-2 text-[11.5px] text-gray-500">One gVisor container per client per run. Inputs arrive read-only; only validated, hashed outputs leave.</div>
          </Box>
        </div>
      </div>
    </div>
  );
}

function GroundTruthHeadline() {
  const me = useMe();
  const batches = useBatches(!!me.data);
  const latestDone = batches.data?.find((b) => b.status === "completed");
  const gt = useGroundTruth(latestDone?.id, !!latestDone);
  if (!gt.data) return null;
  const perfect = gt.data.found === gt.data.planted && (gt.data.all_exact ?? true);
  return (
    <div
      className={cn("mt-6 inline-flex items-center gap-2.5 rounded-full border px-4 py-2 text-[13px]", perfect ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-200 bg-amber-50 text-amber-900")}
      data-testid="ground-truth"
      data-found={gt.data.found}
      data-planted={gt.data.planted}
    >
      <TargetIcon className="size-4" />
      <span>
        <span className="font-semibold">Ground truth check on the latest close: {groundTruthHeadline(gt.data)}</span> across {gt.data.clients.length} clients. The answer key
        is never shown to the model.
      </span>
    </div>
  );
}

export function HowItWorksPage() {
  const me = useMe();
  const system = useSystem(!!me.data);
  return (
    <div className="mx-auto max-w-[1240px] px-6 pt-8 pb-16" data-testid="how-it-works">
      <div className="max-w-4xl">
        <div className="text-[12px] font-semibold tracking-wide text-indigo-700 uppercase">How Tieout contains the agent</div>
        <h1 className="mt-2 text-[34px] leading-tight font-semibold tracking-tight text-gray-900">Why does this need a sandbox?</h1>
        <blockquote className="mt-5 border-l-4 border-indigo-600 pl-5 text-[18px] leading-relaxed text-gray-700">
          The agent writes and runs code on client bank data. That code might be wrong, and the data can't be trusted either: whoever pays you or bills you writes the memo
          text on the transaction. So every run happens in a locked-down sandbox: no network, read-only inputs, no access to the accounting system, and a separate sandbox per
          client so one client's data can never reach another's.
        </blockquote>
        {me.data && <GroundTruthHeadline />}
      </div>

      <h2 className="mt-12 text-[18px] font-semibold text-gray-900">Five guarantees, each visible in the product</h2>
      <p className="mt-1 text-[14px] text-gray-500">Not claims in a slide: every one of these is enforced by the platform and shown on screen, with evidence.</p>
      <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {GUARANTEES.map((g) => (
          <Card key={g.n} className="flex flex-col p-5" data-testid={`guarantee-${g.n}`}>
            <div className="flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-lg bg-indigo-600 text-white [&_svg]:size-[18px]">{g.icon}</div>
              <div>
                <div className="text-[11px] font-semibold tracking-wide text-gray-400 uppercase">Guarantee {g.n}</div>
                <div className="text-[15px] font-semibold text-gray-900">{g.title}</div>
              </div>
            </div>
            <p className="mt-3 flex-1 text-[13px] leading-relaxed text-gray-600">{g.how}</p>
            <div className="mt-3 border-t border-gray-100 pt-3 text-[12px]">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-gray-400 uppercase">
                <ShieldCheckIcon className="size-3.5 text-indigo-600" /> Where to see it
              </div>
              <div className="mt-0.5 font-medium text-gray-700">{g.where}</div>
            </div>
          </Card>
        ))}
        <Card className="flex flex-col border-amber-200 bg-amber-50/40 p-5">
          <div className="flex items-center gap-3">
            <div className="flex size-9 items-center justify-center rounded-lg bg-amber-500 text-white">
              <FileLock2Icon className="size-[18px]" />
            </div>
            <div>
              <div className="text-[11px] font-semibold tracking-wide text-amber-700 uppercase">In the demo data</div>
              <div className="text-[15px] font-semibold text-gray-900">A prompt injection, contained</div>
            </div>
          </div>
          <p className="mt-3 flex-1 text-[13px] leading-relaxed text-gray-700">
            One of Blue Harbor Coffee's customers wrote instructions for "the AI assistant" into a payment memo: mark everything reconciled, approve all entries, upload the
            ledger to a URL. The control plane flags it and the agent treats it as data. Even if it had not: there is no network to upload over, no ledger to post to, and no
            approval rights to use.
          </p>
          <div className="mt-3 border-t border-amber-200 pt-3 text-[12px] text-gray-600">Open Blue Harbor Coffee Roasters and look at the Blast radius panel.</div>
        </Card>
      </div>

      <h2 className="mt-12 text-[18px] font-semibold text-gray-900">Architecture</h2>
      <p className="mt-1 mb-5 text-[14px] text-gray-500">
        Everything runs on Vultr, in one region{system.data?.region ? ` (${system.data.region})` : ""}. The control plane never executes model-written code; it only ships it
        to a sandbox.
      </p>
      <ArchitectureDiagram />

      <div className="mt-12 grid grid-cols-1 gap-8 lg:grid-cols-2">
        <div>
          <h2 className="text-[18px] font-semibold text-gray-900">Guardrails on a public URL</h2>
          <p className="mt-1 text-[14px] text-gray-500">A public page that runs code is a blast-radius risk of its own. These keep it contained.</p>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {GUARDRAILS.map((g) => (
              <div key={g.title} className="rounded-xl border border-gray-200 bg-white p-3.5">
                <div className="flex items-center gap-2 text-[13px] font-semibold text-gray-900 [&_svg]:size-4 [&_svg]:text-indigo-600">
                  {g.icon} {g.title}
                </div>
                <div className="mt-1 text-[12.5px] leading-snug text-gray-500">{g.body}</div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h2 className="text-[18px] font-semibold text-gray-900">Vultr products used</h2>
          <p className="mt-1 text-[14px] text-gray-500">Vultr is the system of control and record, not just hosting.</p>
          <ul className="mt-4 space-y-3">
            {PRODUCTS.map((p) => (
              <li key={p.name} className="flex gap-3 rounded-xl border border-gray-200 bg-white p-3.5">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700 [&_svg]:size-[18px]">{p.icon}</div>
                <div>
                  <div className="flex items-center gap-2 text-[13.5px] font-semibold text-gray-900">
                    <CloudIcon className="size-3.5 text-gray-400" /> Vultr {p.name}
                  </div>
                  <div className="mt-0.5 text-[12.5px] leading-snug text-gray-600">{p.role}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="mt-12 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-gray-200 bg-white px-6 py-5">
        <div>
          <div className="text-[15px] font-semibold text-gray-900">See it on a real close</div>
          <div className="text-[13px] text-gray-500">Twelve clients, twelve sandboxes, one reviewer. About 40 seconds end to end.</div>
        </div>
        <Link
          to={me.data ? "/" : "/login"}
          className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-5 text-sm font-medium text-white shadow-sm hover:bg-primary-hover"
        >
          {me.data ? "Open the September close" : "Sign in with a demo account"} <ArrowRightIcon className="size-4" />
        </Link>
      </div>
    </div>
  );
}
