import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ActivityIcon,
  BoxesIcon,
  CheckIcon,
  CoinsIcon,
  FlameIcon,
  LinkIcon,
  Loader2Icon,
  OctagonAlertIcon,
  PowerIcon,
  ScrollTextIcon,
  ShieldXIcon,
  TimerIcon,
  UnlinkIcon,
} from "lucide-react";
import { api } from "@/api";
import type { AuditEntry, KillSwitchResult } from "@/api/types";
import { Hash } from "@/components/hash";
import { EmptyState, ErrorState } from "@/components/states";
import { ToneDot } from "@/components/status";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Hint } from "@/components/ui/tooltip";
import { qk, useAdminOverview, useMe } from "@/hooks/queries";
import { formatClock, formatCompact, formatInt, formatTime, toDate } from "@/lib/format";
import { HEALTH_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";

function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

function countdown(expires: string | number, now: number) {
  const d = toDate(expires);
  if (!d) return "";
  const s = Math.max(0, Math.round((d.getTime() - now) / 1000));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

function detailText(d: unknown): string {
  if (d === null || d === undefined) return "";
  if (typeof d === "string") return d;
  try {
    const entries = Object.entries(d as Record<string, unknown>).filter(([, v]) => v !== "" && v !== null && v !== undefined);
    return entries.map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join("  ");
  } catch {
    return JSON.stringify(d);
  }
}

const ACTION_TONE: Record<string, string> = {
  kill_switch_on: "text-red-700",
  kill_switch_off: "text-emerald-700",
  run_approved: "text-emerald-700",
  run_rejected: "text-red-700",
  untrusted_text_detected: "text-amber-700",
  batch_started: "text-indigo-700",
};

export function AdminPage() {
  const me = useMe();
  const isAdmin = me.data?.role === "admin";
  const overview = useAdminOverview(isAdmin);
  const qc = useQueryClient();
  const now = useNow();
  const [confirm, setConfirm] = useState(false);
  const [last, setLast] = useState<KillSwitchResult | null>(null);

  const kill = useMutation({
    mutationFn: (enabled: boolean) => api.killSwitch(enabled),
    onSuccess: (r) => {
      setLast(r);
      if (r.kill_switch) {
        toast.error("Kill switch engaged", { description: `Destroyed ${r.destroyed} sandbox${r.destroyed === 1 ? "" : "es"} and cancelled ${r.cancelled_runs} run${r.cancelled_runs === 1 ? "" : "s"}. New work is blocked.` });
      } else {
        toast.success("Kill switch released", { description: "New closes and replays can start again." });
      }
      void qc.invalidateQueries({ queryKey: qk.admin });
      void qc.invalidateQueries({ queryKey: qk.system });
      void qc.invalidateQueries({ queryKey: qk.health });
      void qc.invalidateQueries({ queryKey: qk.latestBatch });
    },
    onError: (e: unknown) => toast.error("Kill switch failed", { description: e instanceof Error ? e.message : String(e) }),
  });

  const warm = useMutation({
    mutationFn: () => api.warmup(),
    onSuccess: (r) =>
      toast.success("Warm-up complete", {
        description: `Created and destroyed a test sandbox in ${formatInt(r.ms)} ms. Attestation ${r.attestation_ok ? "passed" : "did not pass"}.`,
      }),
    onError: (e: unknown) => toast.error("Warm-up failed", { description: e instanceof Error ? e.message : String(e) }),
  });

  if (me.data && !isAdmin) {
    return (
      <div className="mx-auto max-w-[1560px] px-6 pt-10">
        <Card>
          <EmptyState
            icon={<ShieldXIcon />}
            title="Admins only"
            action={
              <Button asChild variant="outline">
                <Link to="/">Back to the September close</Link>
              </Button>
            }
          >
            The admin console shows live sandboxes, usage, health and the kill switch. Switch to the admin demo account from the user menu to see it.
          </EmptyState>
        </Card>
      </div>
    );
  }

  const o = overview.data;
  const on = !!o?.kill_switch;
  const budgetPct = o ? Math.min(100, (o.usage.tokens_today / Math.max(1, o.usage.budget)) * 100) : 0;
  const sandboxes = o?.runner.sandboxes ?? [];

  return (
    <div className="mx-auto max-w-[1560px] px-6 pt-6 pb-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[12px] font-medium text-indigo-700">Operations</div>
          <h1 className="mt-1 text-[26px] font-semibold tracking-tight text-gray-900">Admin console</h1>
          <p className="mt-1 text-[14px] text-gray-500">Guardrails for a public URL that runs code: live sandboxes, the daily token budget, health, the audit trail and a kill switch.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[12px] text-gray-400">{overview.isFetching ? "Refreshing" : "Auto-refresh every 3 s"}</span>
          <Hint label="Pull the image, create a test sandbox, attest it and destroy it, so nothing cold-starts on stage.">
            <Button variant="outline" onClick={() => warm.mutate()} disabled={warm.isPending || on} data-testid="warmup-button">
              {warm.isPending ? <Loader2Icon className="animate-spin" /> : <FlameIcon />} Warm up
            </Button>
          </Hint>
        </div>
      </div>

      {overview.isError && !o ? (
        <Card className="mt-6">
          <ErrorState message={(overview.error as Error)?.message} onRetry={() => void overview.refetch()} />
        </Card>
      ) : (
        <>
          <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card className={cn("overflow-hidden", on ? "border-red-300" : "")} data-testid="kill-switch-card" data-on={String(on)}>
              <div className={cn("h-1", on ? "bg-red-500" : "bg-gray-200")} />
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <OctagonAlertIcon className={cn("size-4", on ? "text-red-600" : "text-gray-400")} /> Kill switch
                </CardTitle>
                <CardDescription>Stops new work and destroys every running sandbox, on every host.</CardDescription>
              </CardHeader>
              <CardContent>
                {!o ? (
                  <Skeleton className="h-20" />
                ) : (
                  <>
                    <div className="flex items-center justify-between rounded-lg border border-gray-200 px-3 py-2.5">
                      <span className="text-[13px] text-gray-600">State</span>
                      <span className={cn("inline-flex items-center gap-2 text-[13px] font-semibold", on ? "text-red-700" : "text-emerald-700")}>
                        <ToneDot tone={on ? "danger" : "success"} /> {on ? "On: new work blocked" : "Off: accepting work"}
                      </span>
                    </div>
                    {on && (o.kill_switch_auto_resume_at ?? last?.auto_resume_at) && (
                      <div className="mt-2 flex items-center gap-1.5 text-[12px] font-medium text-red-700" data-testid="kill-switch-auto-resume">
                        <TimerIcon className="size-3.5" /> Auto-resumes at {formatClock(o.kill_switch_auto_resume_at ?? last?.auto_resume_at)} (public demo safeguard)
                      </div>
                    )}
                    {last && (
                      <div className="mt-2 text-[12px] text-gray-600" data-testid="kill-switch-result">
                        {last.kill_switch
                          ? `Destroyed ${last.destroyed} sandbox${last.destroyed === 1 ? "" : "es"}, cancelled ${last.cancelled_runs} run${last.cancelled_runs === 1 ? "" : "s"}.`
                          : "Released. The runner accepts new sandboxes again."}
                      </div>
                    )}
                    <ul className="mt-3 space-y-1.5 text-[12.5px] text-gray-600">
                      {[
                        "Cancels every running close and replay",
                        "Destroys every sandbox on the runner",
                        "Refuses new closes and replays (HTTP 409)",
                        "Keeps recorded runs, results and approvals",
                      ].map((t) => (
                        <li key={t} className="flex items-start gap-2">
                          <CheckIcon className="mt-0.5 size-3.5 shrink-0 text-gray-400" /> {t}
                        </li>
                      ))}
                    </ul>
                    <Button
                      size="xl"
                      variant={on ? "outline" : "destructive"}
                      className="mt-4 w-full"
                      onClick={() => (on ? kill.mutate(false) : setConfirm(true))}
                      disabled={kill.isPending}
                      data-testid="kill-switch"
                      data-on={String(on)}
                    >
                      {kill.isPending ? <Loader2Icon className="animate-spin" /> : <PowerIcon />}
                      {on ? "Release kill switch" : "Engage kill switch"}
                    </Button>
                  </>
                )}
              </CardContent>
            </Card>

            <Card data-testid="usage-card">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <CoinsIcon className="size-4 text-gray-400" /> Token usage today
                </CardTitle>
                <CardDescription>Every LLM call goes through Vultr Serverless Inference. A daily budget stops runs when it is spent.</CardDescription>
              </CardHeader>
              <CardContent>
                {!o ? (
                  <Skeleton className="h-20" />
                ) : (
                  <>
                    <div className="flex items-baseline justify-between">
                      <span className="money text-[26px] font-semibold text-gray-900">{formatCompact(o.usage.tokens_today)}</span>
                      <span className="money text-[12px] text-gray-500">of {formatCompact(o.usage.budget)} daily budget</span>
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-gray-100">
                      <div className={cn("h-full rounded-full", budgetPct > 85 ? "bg-red-500" : budgetPct > 60 ? "bg-amber-500" : "bg-indigo-500")} style={{ width: `${Math.max(budgetPct, 0.8)}%` }} />
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                      <div className="rounded-lg bg-gray-50 px-2 py-2">
                        <div className="text-[11px] text-gray-500">Cost today</div>
                        <div className="money text-[14px] font-semibold text-gray-900">${o.usage.cost_today_usd.toFixed(2)}</div>
                      </div>
                      <div className="rounded-lg bg-gray-50 px-2 py-2">
                        <div className="text-[11px] text-gray-500">Runs today</div>
                        <div className="money text-[14px] font-semibold text-gray-900">{o.usage.runs_today}</div>
                      </div>
                      <div className="rounded-lg bg-gray-50 px-2 py-2">
                        <div className="text-[11px] text-gray-500">Budget used</div>
                        <div className="money text-[14px] font-semibold text-gray-900">{budgetPct.toFixed(1)}%</div>
                      </div>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            <Card data-testid="health-card">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ActivityIcon className="size-4 text-gray-400" /> Health
                  {o && (
                    <Badge variant={o.health.ok ? "success" : "danger"} className="ml-auto">
                      {o.health.ok ? "All green" : "Degraded"}
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription>Checked live against each dependency.</CardDescription>
              </CardHeader>
              <CardContent>
                {!o ? (
                  <Skeleton className="h-24" />
                ) : (
                  <ul className="space-y-2">
                    {Object.entries(o.health.checks).map(([k, c]) => (
                      <li key={k} className="rounded-lg border border-gray-100 px-3 py-2" data-testid={`health-${k}`} data-ok={String(c.ok)}>
                        <div className="flex items-center justify-between gap-2 text-[13px]">
                          <span className="flex items-center gap-2 font-medium text-gray-800">
                            <ToneDot tone={c.ok ? "success" : "danger"} /> {c.label ?? HEALTH_LABEL[k] ?? k}
                          </span>
                          <span className="tnum text-[12px] text-gray-500">{c.ms} ms</span>
                        </div>
                        <div className="mt-0.5 truncate pl-4 text-[11.5px] text-gray-500" title={c.detail}>
                          {c.detail}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>

          <Card className="mt-4" data-testid="sandboxes-card">
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <BoxesIcon className="size-4 text-gray-400" /> Live sandboxes
                </CardTitle>
                <CardDescription>
                  {o
                    ? `${sandboxes.length} of ${o.runner.max ?? "?"} slots in use on ${o.runner.host ?? "the sandbox host"}${o.runner.accepting === false ? ", not accepting new sandboxes" : ""}. Each is destroyed when its run ends, or by the TTL janitor.`
                    : "Loading"}
                </CardDescription>
              </div>
              {o?.runner.error && <Badge variant="danger">Runner unreachable</Badge>}
            </CardHeader>
            <CardContent className="px-0 pb-2">
              {!o ? (
                <div className="px-5 pb-3">
                  <Skeleton className="h-24" />
                </div>
              ) : sandboxes.length === 0 ? (
                <EmptyState icon={<BoxesIcon />} title="No sandboxes running">
                  Start a close to watch one sandbox per client appear here, then disappear as each run finishes.
                </EmptyState>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="pl-5">Sandbox</TableHead>
                      <TableHead>Tenant</TableHead>
                      <TableHead>Task</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead>TTL left</TableHead>
                      <TableHead className="text-right">Execs</TableHead>
                      <TableHead>Limits</TableHead>
                      <TableHead className="pr-5">Host</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sandboxes.map((sb) => (
                      <TableRow key={sb.id} data-testid={`sandbox-row-${sb.id}`}>
                        <TableCell className="mono pl-5 text-[12px]">{sb.id}</TableCell>
                        <TableCell className="font-medium text-gray-900">{sb.labels?.["arena.tenant"] ?? "n/a"}</TableCell>
                        <TableCell className="mono text-[12px] text-gray-600">
                          {sb.labels?.["arena.task"] ? (
                            <Link to={`/runs/${sb.labels["arena.task"]}`} className="hover:text-indigo-700 hover:underline">
                              {sb.labels["arena.task"]}
                            </Link>
                          ) : (
                            "n/a"
                          )}
                          {sb.labels?.["arena.kind"] === "replay" && <Badge variant="accent" className="ml-1.5">replay</Badge>}
                        </TableCell>
                        <TableCell>
                          <span className="inline-flex items-center gap-1.5 text-[12.5px]">
                            <ToneDot tone={sb.status === "running" ? "running" : "muted"} pulse={sb.status === "running"} className="text-indigo-300" /> {sb.status}
                          </span>
                        </TableCell>
                        <TableCell className="tnum text-gray-600">{formatTime(sb.created_at)}</TableCell>
                        <TableCell className="tnum text-gray-600">{countdown(sb.expires_at, now)}</TableCell>
                        <TableCell className="money text-right">{sb.exec_count}</TableCell>
                        <TableCell className="text-[12px] text-gray-600">
                          {sb.limits ? `${sb.limits.cpus} CPU, ${sb.limits.memory_mb} MB, ${sb.limits.pids} pids` : "n/a"}
                        </TableCell>
                        <TableCell className="mono pr-5 text-[12px] text-gray-600">{sb.host}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
            <Card data-testid="usage-by-model">
              <CardHeader>
                <CardTitle>Usage by model</CardTitle>
                <CardDescription>Today, priced at Vultr Serverless Inference rates.</CardDescription>
              </CardHeader>
              <CardContent className="px-0">
                {!o ? (
                  <div className="px-5">
                    <Skeleton className="h-16" />
                  </div>
                ) : o.usage.by_model.length === 0 ? (
                  <div className="px-5 text-[13px] text-gray-500">No model calls yet today.</div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow className="hover:bg-transparent">
                        <TableHead className="pl-5">Model</TableHead>
                        <TableHead className="text-right">In</TableHead>
                        <TableHead className="text-right">Out</TableHead>
                        <TableHead className="pr-5 text-right">Cost</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {o.usage.by_model.map((m) => (
                        <TableRow key={m.model}>
                          <TableCell className="mono pl-5 text-[12px]">
                            {m.model}
                            {m.runs ? <span className="ml-1.5 font-sans text-[11px] text-gray-400">{m.runs} runs</span> : null}
                          </TableCell>
                          <TableCell className="money text-right">{formatCompact(m.tokens_in)}</TableCell>
                          <TableCell className="money text-right">{formatCompact(m.tokens_out)}</TableCell>
                          <TableCell className="money pr-5 text-right">${m.cost_usd.toFixed(3)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

            <Card data-testid="audit-log">
              <CardHeader className="flex-row items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <ScrollTextIcon className="size-4 text-gray-400" /> Audit log
                  </CardTitle>
                  <CardDescription>Append-only. Each entry's SHA-256 covers the previous entry's hash.</CardDescription>
                </div>
                {o && (
                  <Badge variant={o.audit_chain_ok ? "success" : "danger"} className="gap-1.5 px-2.5 py-1 text-[12px]" data-testid="audit-chain">
                    {o.audit_chain_ok ? <LinkIcon /> : <UnlinkIcon />}
                    {o.audit_chain_ok ? "Chain verified" : "Chain broken"}
                  </Badge>
                )}
              </CardHeader>
              <CardContent className="px-0">
                {!o ? (
                  <div className="px-5">
                    <Skeleton className="h-40" />
                  </div>
                ) : (
                  <div className="scrollbar-thin max-h-[420px] overflow-y-auto">
                    <Table>
                      <TableHeader className="sticky top-0 z-10 bg-white">
                        <TableRow className="hover:bg-transparent">
                          <TableHead className="pl-5">#</TableHead>
                          <TableHead>Time</TableHead>
                          <TableHead>Actor</TableHead>
                          <TableHead>Action</TableHead>
                          <TableHead>Target</TableHead>
                          <TableHead>Detail</TableHead>
                          <TableHead className="pr-5">Hash</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {o.audit.map((a: AuditEntry) => (
                          <TableRow key={a.seq}>
                            <TableCell className="tnum pl-5 text-gray-400">{a.seq}</TableCell>
                            <TableCell className="tnum whitespace-nowrap text-gray-600">{formatTime(a.ts)}</TableCell>
                            <TableCell className="max-w-[180px] truncate text-gray-700">{a.actor}</TableCell>
                            <TableCell className={cn("font-medium whitespace-nowrap", ACTION_TONE[a.action] ?? "text-gray-900")}>{a.action}</TableCell>
                            <TableCell className="mono max-w-[160px] truncate text-[12px] text-gray-600">{a.target}</TableCell>
                            <TableCell className="max-w-[280px] truncate text-[12px] text-gray-500" title={detailText(a.detail)}>
                              {detailText(a.detail)}
                            </TableCell>
                            <TableCell className="pr-5">
                              <Hint label={<span className="mono">prev {a.prev_sha256 ?? "none"}</span>}>
                                <span className="inline-flex items-center gap-1">
                                  <CheckIcon className="size-3 text-emerald-600" />
                                  <Hash value={a.sha256} head={8} tail={0} copy={false} />
                                </span>
                              </Hint>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}

      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <OctagonAlertIcon className="size-5 text-red-600" /> Engage the kill switch?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Every running sandbox is destroyed immediately, running closes and replays are cancelled, and no new work can start until an admin releases the switch.
              Recorded runs, results and approvals are kept.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="kill-switch-cancel">Cancel</AlertDialogCancel>
            <AlertDialogAction className="bg-red-600 hover:bg-red-700" onClick={() => kill.mutate(true)} data-testid="kill-switch-confirm">
              <PowerIcon className="size-4" /> Engage kill switch
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
