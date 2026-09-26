import { useState } from "react";
import {
  AlertTriangleIcon,
  BoxIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  CloudUploadIcon,
  CodeXmlIcon,
  FileSearchIcon,
  FlagIcon,
  Loader2Icon,
  Maximize2Icon,
  MessageSquareTextIcon,
  PlayIcon,
  ShieldCheckIcon,
  SquareTerminalIcon,
  Trash2Icon,
  XCircleIcon,
} from "lucide-react";
import type { RunEvent } from "@/api/types";
import { CodeBlock, OutputBlock } from "@/components/run/code";
import { buildTimeline, type StepItem, type TimelineItem } from "@/components/run/timeline-model";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Hint } from "@/components/ui/tooltip";
import { formatBytes, formatCompact, formatDuration, formatInt, formatTime } from "@/lib/format";
import { modelName, TOOL_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";

function Rail({ icon, tone = "neutral", last }: { icon: React.ReactNode; tone?: "neutral" | "accent" | "success" | "warning" | "danger" | "running"; last?: boolean }) {
  const styles = {
    neutral: "border-gray-200 bg-white text-gray-500",
    accent: "border-indigo-200 bg-indigo-50 text-indigo-700",
    success: "border-emerald-200 bg-emerald-50 text-emerald-700",
    warning: "border-amber-200 bg-amber-50 text-amber-700",
    danger: "border-red-200 bg-red-50 text-red-700",
    running: "border-indigo-300 bg-white text-indigo-600",
  }[tone];
  return (
    <div className="relative flex w-7 shrink-0 flex-col items-center">
      <div className={cn("z-10 flex size-7 items-center justify-center rounded-full border text-[11px] font-semibold [&_svg]:size-3.5", styles)}>{icon}</div>
      {!last && <div className="absolute top-7 bottom-[-12px] w-px bg-gray-200" />}
    </div>
  );
}

function Meta({ children }: { children: React.ReactNode }) {
  return <span className="tnum shrink-0 text-[11px] whitespace-nowrap text-gray-500">{children}</span>;
}

function ExitBadge({ code, timedOut }: { code: number | null | undefined; timedOut?: boolean }) {
  if (timedOut) return <Badge variant="danger">timed out</Badge>;
  if (code === null || code === undefined) return null;
  return <Badge variant={code === 0 ? "success" : "danger"} className="mono px-1.5 py-0 text-[10.5px]">exit {code}</Badge>;
}

function StepCard({ step, index, last, live, onExpand }: { step: StepItem; index: number; last: boolean; live: boolean; onExpand: (s: StepItem) => void }) {
  const [showCode, setShowCode] = useState(false);
  const [showOut, setShowOut] = useState(false);
  const args = step.call.payload?.args ?? {};
  const res = step.result?.payload;
  const isFinish = step.tool === "finish";
  const isSniff = step.tool === "sniff_file";
  const running = live && !isFinish && !step.result;
  const failed = res && res.exit_code !== 0;
  const purpose: string = isSniff ? `Inspect ${args.name}` : isFinish ? "Finish and hand in result.json" : (args.purpose ?? "Run Python");
  const icon = isFinish ? <FlagIcon /> : running ? <Loader2Icon className="animate-spin" /> : failed ? <XCircleIcon /> : <span>{step.n ?? index + 1}</span>;
  const tone = isFinish ? (step.validation?.payload?.ok ? "success" : step.validation ? "warning" : "accent") : running ? "running" : failed ? "danger" : "accent";
  const ToolIcon = isSniff ? FileSearchIcon : isFinish ? FlagIcon : SquareTerminalIcon;
  const outFiles: { path: string; size: number; sha256: string }[] = res?.out_files ?? [];
  const testId = isFinish ? "timeline-step-finish" : `timeline-step-${step.n ?? index + 1}`;

  return (
    <li className="flex gap-3" data-testid={testId} data-tool={step.tool} data-exit-code={res?.exit_code ?? ""}>
      <Rail icon={icon} tone={tone} last={last} />
      <div className={cn("mb-3 min-w-0 flex-1 rounded-lg border bg-white px-3.5 py-3", running ? "border-indigo-200 ring-2 ring-indigo-100" : "border-gray-200")}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-gray-500 uppercase">
              <ToolIcon className="size-3.5" /> {TOOL_LABEL[step.tool] ?? step.tool}
            </div>
            <div className="mt-0.5 text-[13px] leading-snug font-medium text-gray-900">{purpose}</div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            {res ? <ExitBadge code={res.exit_code} timedOut={res.timed_out} /> : running ? <Badge variant="accent">in sandbox</Badge> : null}
            {res?.duration_ms !== undefined && <Meta>{formatDuration(res.duration_ms)}</Meta>}
          </div>
        </div>

        {step.thought?.payload?.text && (
          <div className="mt-2 flex gap-2 rounded-md bg-gray-50 px-2.5 py-2 text-[12.5px] leading-snug text-gray-600">
            <MessageSquareTextIcon className="mt-0.5 size-3.5 shrink-0 text-gray-400" />
            <span className="line-clamp-4">{step.thought.payload.text}</span>
          </div>
        )}

        {isSniff && (
          <div className="mono mt-2 truncate rounded-md border border-gray-200 bg-[#fbfbfd] px-2.5 py-1.5 text-[11.5px] text-gray-700">
            <span className="text-gray-400">$ </span>python -m tieout_lib.sniff /in/{args.name}
          </div>
        )}

        {isFinish && (
          <div className="mt-2 space-y-2">
            {args.summary && <p className="text-[12.5px] leading-relaxed text-gray-700">{args.summary}</p>}
            {step.validation && (
              <div
                className={cn(
                  "flex items-start gap-2 rounded-md px-2.5 py-2 text-[12px]",
                  step.validation.payload.ok ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900",
                )}
              >
                {step.validation.payload.ok ? <CheckCircle2Icon className="mt-0.5 size-3.5 shrink-0" /> : <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0" />}
                <div>
                  {step.validation.payload.ok ? (
                    "Control plane validated result.json: schema, arithmetic and difference all check out."
                  ) : (
                    <>
                      <div className="font-medium">Validation failed, errors sent back to the agent:</div>
                      <ul className="mt-1 list-disc pl-4">
                        {(step.validation.payload.errors ?? []).slice(0, 5).map((e: string, i: number) => (
                          <li key={i}>{e}</li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              </div>
            )}
            {!step.validation && live && (
              <div className="flex items-center gap-2 text-[12px] text-gray-500">
                <Loader2Icon className="size-3.5 animate-spin" /> Validating result.json
              </div>
            )}
          </div>
        )}

        {!isFinish && (res || args.code) && (
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            {!isSniff && args.code && (
              <Button variant={showCode ? "secondary" : "outline"} size="sm" className="h-7 px-2 text-[12px]" onClick={() => setShowCode((v) => !v)} data-testid="toggle-code">
                <CodeXmlIcon className="size-3.5" /> Code
                <ChevronDownIcon className={cn("size-3.5 transition-transform", showCode && "rotate-180")} />
              </Button>
            )}
            {res && (
              <Button variant={showOut ? "secondary" : "outline"} size="sm" className="h-7 px-2 text-[12px]" onClick={() => setShowOut((v) => !v)} data-testid="toggle-output">
                <SquareTerminalIcon className="size-3.5" /> Output
                <ChevronDownIcon className={cn("size-3.5 transition-transform", showOut && "rotate-180")} />
              </Button>
            )}
            <Hint label="Open code and output side by side">
              <Button variant="ghost" size="icon-sm" className="ml-auto size-7" onClick={() => onExpand(step)} aria-label="Expand step">
                <Maximize2Icon className="size-3.5" />
              </Button>
            </Hint>
          </div>
        )}

        {showCode && args.code && <CodeBlock code={args.code} className="mt-2" title={`/work/step_${step.n}.py`} wrap maxHeight={380} />}
        {showOut && res && <OutputBlock stdout={res.stdout} stderr={res.stderr} className="mt-2" />}

        {outFiles.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-gray-500">
            <span>Wrote to /out:</span>
            {outFiles.map((f) => (
              <Hint key={f.path} label={<span className="mono">sha256 {f.sha256}</span>}>
                <span className="mono rounded border border-gray-200 bg-gray-50 px-1.5 py-0.5 text-gray-700">
                  {f.path} <span className="text-gray-400">{formatBytes(f.size)}</span>
                </span>
              </Hint>
            ))}
          </div>
        )}
        {step.llm && (
          <div className="mt-2 text-[11px] text-gray-400">
            Planned by {step.llm.payload.model} in {formatDuration(step.llm.payload.latency_ms)} · {formatCompact(step.llm.payload.tokens_in)} in, {formatCompact(step.llm.payload.tokens_out)} out
          </div>
        )}
      </div>
    </li>
  );
}

function EventRow({ item, last }: { item: Exclude<TimelineItem, StepItem>; last: boolean }) {
  const ev: RunEvent = item.ev;
  const p = ev.payload ?? {};
  let icon: React.ReactNode = <BoxIcon />;
  let tone: "neutral" | "accent" | "success" | "warning" | "danger" = "neutral";
  let title: React.ReactNode = ev.type;
  let body: React.ReactNode = null;
  let testId: string | undefined;

  switch (item.kind) {
    case "run_started":
      icon = <PlayIcon />;
      title = p.replay_of ? "Replay started" : "Run started";
      body = p.replay_of ? (
        <>Re-running {p.steps} recorded steps with the same inputs. No model involved.</>
      ) : (
        <>
          Model <span className="mono text-gray-700">{p.model}</span>
          {p.fallback_model ? <> (fallback {p.fallback_model})</> : null}, up to {p.max_tool_calls} tool calls, {(p.inputs ?? []).length} input files
        </>
      );
      break;
    case "untrusted":
      icon = <AlertTriangleIcon />;
      tone = "warning";
      title = "Instruction-like text found in the inputs";
      body = (
        <>
          {p.file} row {p.row}: <span className="italic">"{String(p.preview ?? "").slice(0, 90)}..."</span> Flagged by the control plane before the run. Treated as data.
          {p.classifier?.verdict === "unsafe" && <> Second opinion: {modelName(p.classifier.model)} flagged it as unsafe.</>}
        </>
      );
      testId = "timeline-untrusted";
      break;
    case "sandbox": {
      const att = p.attestation;
      const passed = att?.checks?.filter((c: { ok: boolean }) => c.ok).length ?? 0;
      const total = att?.checks?.length ?? 0;
      icon = <ShieldCheckIcon />;
      tone = att?.ok ? "success" : "warning";
      title = <>Sandbox created on {p.host}</>;
      body = (
        <>
          <span className="mono text-[11px] text-gray-600">{p.sandbox_id}</span>
          <br />
          Attestation {passed} of {total} checks passed: gVisor, no network, read-only inputs.{" "}
          <button
            type="button"
            className="font-medium text-indigo-700 hover:underline"
            onClick={() => document.getElementById("blast-radius")?.scrollIntoView({ behavior: "smooth", block: "start" })}
          >
            View blast radius
          </button>
        </>
      );
      break;
    }
    case "stored":
      icon = <CloudUploadIcon />;
      title = "Outputs stored in Vultr Object Storage";
      body = (
        <span className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5">
          {(p.artifacts ?? []).map((a: { name: string; sha256: string }) => (
            <span key={a.name} className="mono truncate text-[11px]">
              <span className="text-gray-700">{a.name}</span> <span className="text-gray-400">{a.sha256.slice(0, 8)}</span>
            </span>
          ))}
        </span>
      );
      break;
    case "sandbox_destroyed":
      icon = <Trash2Icon />;
      title = "Sandbox destroyed";
      body = <span className="mono text-[11px]">{p.sandbox_id}</span>;
      break;
    case "run_finished":
      icon = <CheckCircle2Icon />;
      tone = p.status === "succeeded" ? "success" : "danger";
      title = p.replay_of !== undefined || p.replay_match !== undefined ? `Replay finished: ${p.replay_match ? "hashes match" : "hashes differ"}` : `Run finished: ${p.status}${p.recon_status ? `, ${String(p.recon_status).replace("_", " ")}` : ""}`;
      body =
        p.tool_calls !== undefined ? (
          <>
            {formatDuration(p.duration_ms)} · {p.tool_calls} tool calls · {p.llm_calls} LLM calls · {formatInt((p.tokens_in ?? 0) + (p.tokens_out ?? 0))} tokens · difference {p.difference ?? "n/a"}
          </>
        ) : p.error ? (
          <span className="text-red-700">{p.error}</span>
        ) : null;
      break;
    case "stopped":
      icon = <XCircleIcon />;
      tone = "danger";
      title = "Stopped";
      body = p.reason;
      break;
    case "replay_step":
      icon = <span>{p.n}</span>;
      tone = p.exit_code === 0 ? "accent" : "danger";
      title = (
        <>
          Replayed step {p.n}: <span className="mono text-[12px]">{(p.argv ?? []).join(" ")}</span>
        </>
      );
      body = (
        <>
          exit {p.exit_code} · {formatDuration(p.duration_ms)}
        </>
      );
      testId = `timeline-step-${p.n}`;
      break;
    case "replay_compared":
      icon = p.match ? <CheckCircle2Icon /> : <XCircleIcon />;
      tone = p.match ? "success" : "danger";
      title = p.match ? "All output hashes match the original run" : "Some output hashes differ from the original run";
      body = <>{(p.files ?? []).length} files compared by SHA-256</>;
      break;
  }

  return (
    <li className="flex gap-3" data-testid={testId}>
      <Rail icon={icon} tone={tone} last={last} />
      <div className="mb-3 min-w-0 flex-1 pt-1">
        <div className="flex items-baseline justify-between gap-2">
          <div className={cn("text-[13px] font-medium", tone === "warning" ? "text-amber-800" : tone === "danger" ? "text-red-700" : "text-gray-800")}>{title}</div>
          <Meta>{formatTime(ev.ts)}</Meta>
        </div>
        {body && <div className="mt-0.5 text-[12px] leading-relaxed text-gray-500">{body}</div>}
      </div>
    </li>
  );
}

export function Timeline({ events, live, loading }: { events: RunEvent[]; live: boolean; loading?: boolean }) {
  const model = buildTimeline(events);
  const [expanded, setExpanded] = useState<StepItem | null>(null);
  const items = model.items;
  const showThinking = live && model.thinking;

  return (
    <div data-testid="timeline" data-steps={model.steps.length}>
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-[14px] font-semibold text-gray-900">Agent steps</div>
          <div className="text-[12px] text-gray-500">
            {model.steps.filter((s) => s.tool !== "finish").length} sandbox steps
            {model.llmCalls ? ` · ${model.llmCalls} LLM calls · ${formatCompact(model.tokensIn + model.tokensOut)} tokens` : ""}
          </div>
        </div>
        {live && (
          <Badge variant="accent" className="gap-1.5">
            <span className="size-1.5 animate-pulse rounded-full bg-indigo-500" /> Live
          </Badge>
        )}
      </div>
      {loading && !events.length ? (
        <div className="flex items-center gap-2 py-6 text-[13px] text-gray-500">
          <Loader2Icon className="size-4 animate-spin" /> Loading steps
        </div>
      ) : !events.length ? (
        <div className="rounded-lg border border-dashed border-gray-300 px-4 py-6 text-center text-[13px] text-gray-500">
          Waiting for a sandbox slot. Steps appear here as the agent works.
        </div>
      ) : (
        <ol>
          {items.map((it, i) => {
            const last = i === items.length - 1 && !showThinking;
            return it.kind === "step" ? (
              <StepCard key={it.key} step={it} index={i} last={last} live={live} onExpand={setExpanded} />
            ) : (
              <EventRow key={it.key} item={it} last={last} />
            );
          })}
          {showThinking && (
            <li className="flex gap-3">
              <Rail icon={<Loader2Icon className="animate-spin" />} tone="running" last />
              <div className="pt-1 text-[13px] text-gray-500">The agent is planning its next step on Vultr Serverless Inference...</div>
            </li>
          )}
        </ol>
      )}

      <Dialog open={!!expanded} onOpenChange={(o) => !o && setExpanded(null)}>
        <DialogContent className="max-w-[min(1320px,calc(100vw-48px))] gap-3">
          {expanded && (
            <>
              <DialogHeader>
                <DialogTitle>
                  Step {expanded.n}: {expanded.tool === "sniff_file" ? `Inspect ${expanded.call.payload.args?.name}` : expanded.call.payload.args?.purpose}
                </DialogTitle>
                <DialogDescription>
                  Executed inside the client's sandbox. Exit {expanded.result?.payload.exit_code ?? "pending"}
                  {expanded.result ? ` in ${formatDuration(expanded.result.payload.duration_ms)}` : ""}. The output below is exactly what the code printed.
                </DialogDescription>
              </DialogHeader>
              {expanded.thought?.payload?.text && (
                <div className="flex gap-2 rounded-md bg-gray-50 px-3 py-2 text-[13px] text-gray-600">
                  <MessageSquareTextIcon className="mt-0.5 size-4 shrink-0 text-gray-400" />
                  {expanded.thought.payload.text}
                </div>
              )}
              <div className={cn("grid gap-3", expanded.call.payload.args?.code ? "grid-cols-2" : "grid-cols-1")}>
                {expanded.call.payload.args?.code && <CodeBlock code={expanded.call.payload.args.code} maxHeight={560} title={`/work/step_${expanded.n}.py`} />}
                {expanded.result && <OutputBlock stdout={expanded.result.payload.stdout} stderr={expanded.result.payload.stderr} maxHeight={560} />}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
