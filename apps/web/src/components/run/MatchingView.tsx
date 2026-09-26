import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ArrowLeftRightIcon, HistoryIcon, Loader2Icon, MousePointerClickIcon, RotateCcwIcon } from "lucide-react";
import type { AJE, BankLine, GlLine, Lines, ReconException, ReconResult } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/tooltip";
import { formatDate, formatInt, formatMoney, formatShortDate } from "@/lib/format";
import { EXCEPTION_LABEL, EXCEPTION_SHORT, exceptionTone } from "@/lib/labels";
import { cn } from "@/lib/utils";

const ROW_H = 30;
const GUTTER = 60;
const OVERSCAN = 8;
const INTRO_MS = 2000;
const BATCHES = 8;

type Side = "bank" | "gl";
type Filter = "all" | "exceptions";

interface Hover {
  side: Side;
  ref: string;
}

function badgeClass(kind: string | null) {
  const tone = exceptionTone(kind as never);
  return tone === "timing"
    ? "border-slate-200 bg-slate-50 text-slate-700"
    : tone === "review"
      ? "border-red-200 bg-red-50 text-red-700"
      : "border-amber-200 bg-amber-50 text-amber-800";
}

function glowClass(kind: string | null) {
  const tone = exceptionTone(kind as never);
  return tone === "timing" ? "row-glow-slate bg-slate-50/60" : tone === "review" ? "row-glow-red bg-red-50/60" : "row-glow-amber bg-amber-50/60";
}

function MethodLabel({ method }: { method: string | null }) {
  const label =
    method === "check_number"
      ? "check number"
      : method === "exact"
        ? "exact amount and date"
        : method === "fuzzy"
          ? "amount and similar description"
          : method === "prior_outstanding"
            ? "a prior-period outstanding item"
            : (method ?? "rule");
  return <>{label}</>;
}

export function MatchingView({
  lines,
  result,
  loading,
  pendingText,
  height = 520,
}: {
  lines: Lines | undefined;
  result: ReconResult | null | undefined;
  loading?: boolean;
  pendingText?: React.ReactNode;
  height?: number;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [hover, setHover] = useState<Hover | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [width, setWidth] = useState(640);
  const [introAt, setIntroAt] = useState(() => performance.now());
  const [introDone, setIntroDone] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const raf = useRef<number | null>(null);

  const bankAll = useMemo(() => lines?.bank ?? [], [lines]);
  const glAll = useMemo(() => lines?.gl ?? [], [lines]);

  const bank = useMemo(() => (filter === "all" ? bankAll : bankAll.filter((b) => !b.match)), [bankAll, filter]);
  const gl = useMemo(() => (filter === "all" ? glAll : glAll.filter((g) => !g.match)), [glAll, filter]);

  const glIndex = useMemo(() => new Map(gl.map((g, i) => [g.ref, i])), [gl]);
  const bankIndex = useMemo(() => new Map(bank.map((b, i) => [b.ref, i])), [bank]);
  const glByRef = useMemo(() => new Map(glAll.map((g) => [g.ref, g])), [glAll]);
  const bankByRef = useMemo(() => new Map(bankAll.map((b) => [b.ref, b])), [bankAll]);

  const exceptionsByRef = useMemo(() => {
    const m = new Map<string, ReconException>();
    for (const e of result?.exceptions ?? []) {
      if (e.bank_ref) m.set(`bank:${e.bank_ref}`, e);
      if (e.gl_ref) m.set(`gl:${e.gl_ref}`, e);
    }
    return m;
  }, [result]);
  const ajeById = useMemo(() => new Map<string, AJE>((result?.ajes ?? []).map((a) => [a.id, a])), [result]);

  // Links that are not matches: a transposition pairs a bank line with the ledger line it almost matches.
  const links = useMemo(
    () => (result?.exceptions ?? []).filter((e) => e.kind === "transposition" && e.bank_ref && e.gl_ref).map((e) => ({ bank: e.bank_ref as string, gl: e.gl_ref as string })),
    [result],
  );

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, [lines]);

  useEffect(() => {
    setIntroDone(false);
    const t = setTimeout(() => setIntroDone(true), INTRO_MS + 600);
    return () => clearTimeout(t);
  }, [introAt, lines]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    setScrollTop(0);
  }, [filter]);

  const onScroll = useCallback(() => {
    if (raf.current !== null) return;
    raf.current = requestAnimationFrame(() => {
      raf.current = null;
      if (scrollRef.current) setScrollTop(scrollRef.current.scrollTop);
    });
  }, []);

  const colW = Math.max(160, Math.floor((width - GUTTER) / 2));
  const rows = Math.max(bank.length, gl.length);
  const viewH = height;
  const first = Math.max(0, Math.floor(scrollTop / ROW_H) - OVERSCAN);
  const last = Math.min(rows - 1, Math.ceil((scrollTop + viewH) / ROW_H) + OVERSCAN);
  const firstVisible = Math.floor(scrollTop / ROW_H);
  const visibleCount = Math.ceil(viewH / ROW_H);
  const inIntro = !introDone;

  const curves = useMemo(() => {
    const out: { key: string; y1: number; y2: number; kind: "match" | "prior" | "link"; bankRef: string; glRef: string; batch: number }[] = [];
    const seen = new Set<string>();
    const batchOf = (i: number) => Math.max(0, Math.min(BATCHES - 1, Math.floor(((i - firstVisible) / Math.max(1, visibleCount)) * BATCHES)));
    for (let i = first; i <= last && i < bank.length; i++) {
      const b = bank[i];
      if (!b.match) continue;
      if (b.match.startsWith("AUG-")) {
        out.push({ key: `p-${b.ref}`, y1: i * ROW_H + ROW_H / 2, y2: i * ROW_H + ROW_H / 2, kind: "prior", bankRef: b.ref, glRef: b.match, batch: batchOf(i) });
        continue;
      }
      const j = glIndex.get(b.match);
      if (j === undefined) continue;
      seen.add(b.ref);
      out.push({ key: `m-${b.ref}`, y1: i * ROW_H + ROW_H / 2, y2: j * ROW_H + ROW_H / 2, kind: "match", bankRef: b.ref, glRef: b.match, batch: batchOf(Math.min(i, j)) });
    }
    for (let j = first; j <= last && j < gl.length; j++) {
      const g = gl[j];
      if (!g.match || seen.has(g.match)) continue;
      const i = bankIndex.get(g.match);
      if (i === undefined) continue;
      seen.add(g.match);
      out.push({ key: `m-${g.match}`, y1: i * ROW_H + ROW_H / 2, y2: j * ROW_H + ROW_H / 2, kind: "match", bankRef: g.match, glRef: g.ref, batch: batchOf(Math.min(i, j)) });
    }
    for (const l of links) {
      const i = bankIndex.get(l.bank);
      const j = glIndex.get(l.gl);
      if (i === undefined || j === undefined) continue;
      if ((i < first || i > last) && (j < first || j > last)) continue;
      out.push({ key: `l-${l.bank}`, y1: i * ROW_H + ROW_H / 2, y2: j * ROW_H + ROW_H / 2, kind: "link", bankRef: l.bank, glRef: l.gl, batch: BATCHES - 1 });
    }
    return out;
  }, [bank, gl, first, last, glIndex, bankIndex, links, firstVisible, visibleCount]);

  const hoverPartner = useMemo(() => {
    if (!hover) return null;
    if (hover.side === "bank") {
      const b = bankByRef.get(hover.ref);
      const link = links.find((l) => l.bank === hover.ref);
      return b?.match ?? link?.gl ?? null;
    }
    const g = glByRef.get(hover.ref);
    const link = links.find((l) => l.gl === hover.ref);
    return g?.match ?? link?.bank ?? null;
  }, [hover, bankByRef, glByRef, links]);

  const counts = useMemo(
    () => ({
      bankMatched: bankAll.filter((b) => b.match).length,
      glMatched: glAll.filter((g) => g.match).length,
      bankExc: bankAll.filter((b) => !b.match).length,
      glExc: glAll.filter((g) => !g.match).length,
      prior: bankAll.filter((b) => b.match?.startsWith("AUG-")).length,
    }),
    [bankAll, glAll],
  );

  const isHot = (side: Side, ref: string) => !!hover && ((hover.side === side && hover.ref === ref) || hoverPartner === ref);

  if (!lines) {
    return (
      <div data-testid="matching-view" data-state={loading ? "loading" : "pending"} className="flex h-full flex-col">
        <MatchingHeader counts={null} filter={filter} setFilter={setFilter} onReplay={() => undefined} />
        <div className="flex flex-1 flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 bg-gray-50/50 px-6 text-center" style={{ height }}>
          {loading ? (
            <div className="flex items-center gap-2 text-[13px] text-gray-500">
              <Loader2Icon className="size-4 animate-spin" /> Loading matched lines
            </div>
          ) : (
            <>
              <ArrowLeftRightIcon className="mb-2 size-5 text-gray-400" />
              <div className="text-[13px] font-medium text-gray-700">Matching view</div>
              <div className="mt-1 max-w-sm text-[12px] text-gray-500">{pendingText ?? "Appears when the run finishes and lines.json leaves the sandbox."}</div>
            </>
          )}
        </div>
      </div>
    );
  }

  const renderRow = (side: Side, line: BankLine | GlLine, i: number) => {
    const exc = exceptionsByRef.get(`${side}:${line.ref}`);
    const kind = line.exception ?? exc?.kind ?? null;
    const unmatched = !line.match;
    const prior = side === "bank" && line.match?.startsWith("AUG-");
    const hot = isHot(side, line.ref);
    const dim = !!hover && !hot;
    return (
      <div
        key={line.ref}
        data-ref={line.ref}
        data-side={side}
        data-exception={kind ?? ""}
        onMouseEnter={() => setHover({ side, ref: line.ref })}
        className={cn(
          "absolute right-0 left-0 flex items-center gap-2 border-b border-gray-100 px-2.5 text-[12px] transition-[background-color,opacity] duration-150",
          side === "bank" ? "pr-3" : "pl-3",
          unmatched && introDone && glowClass(kind),
          unmatched && !introDone && "bg-gray-50/80",
          hot && "bg-indigo-50",
          dim && "opacity-60",
        )}
        style={{ top: i * ROW_H, height: ROW_H }}
      >
        <span className="tnum w-[38px] shrink-0 text-gray-400">{formatShortDate(line.date)}</span>
        <span className={cn("min-w-0 flex-1 truncate", unmatched ? "font-medium text-gray-900" : "text-gray-700")} title={line.description}>
          {line.description}
        </span>
        {unmatched && kind && (
          <span className={cn("shrink-0 rounded border px-1 py-px text-[10.5px] font-medium whitespace-nowrap", badgeClass(kind))}>{EXCEPTION_SHORT[kind]}</span>
        )}
        {prior && (
          <Hint label={`Cleared a prior-period item carried from the August reconciliation (${line.match})`}>
            <span className="inline-flex shrink-0 items-center gap-0.5 rounded border border-indigo-200 bg-white px-1 py-px text-[10.5px] font-medium whitespace-nowrap text-indigo-700">
              <HistoryIcon className="size-2.5" /> Aug
            </span>
          </Hint>
        )}
        <span className={cn("money w-[72px] shrink-0 text-right", line.amount.startsWith("-") ? "text-gray-700" : "text-gray-900")}>{formatMoney(line.amount)}</span>
      </div>
    );
  };

  const bankRows: React.ReactNode[] = [];
  for (let i = first; i <= last && i < bank.length; i++) bankRows.push(renderRow("bank", bank[i], i));
  const glRows: React.ReactNode[] = [];
  for (let j = first; j <= last && j < gl.length; j++) glRows.push(renderRow("gl", gl[j], j));

  return (
    <div data-testid="matching-view" data-state="ready" data-bank={bankAll.length} data-gl={glAll.length} className="flex flex-col">
      <MatchingHeader counts={counts} filter={filter} setFilter={setFilter} onReplay={() => setIntroAt(performance.now())} />

      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
        <div className="grid border-b border-gray-200 bg-gray-50/80 text-[11px] font-semibold tracking-wide text-gray-500 uppercase" style={{ gridTemplateColumns: `${colW}px ${GUTTER}px 1fr` }}>
          <div className="flex items-center justify-between gap-2 px-2.5 py-2 whitespace-nowrap">
            <span>Bank statement</span>
            <span className="tnum font-normal tracking-normal text-gray-400 normal-case">
              {formatInt(bankAll.length)} lines · {counts.bankExc} open
            </span>
          </div>
          <div />
          <div className="flex items-center justify-between gap-2 px-2.5 py-2 pl-3 whitespace-nowrap">
            <span>Ledger 1010</span>
            <span className="tnum font-normal tracking-normal text-gray-400 normal-case">
              {formatInt(glAll.length)} lines · {counts.glExc} open
            </span>
          </div>
        </div>
        <div ref={scrollRef} onScroll={onScroll} onMouseLeave={() => setHover(null)} className="scrollbar-thin relative overflow-x-hidden overflow-y-auto" style={{ height: viewH }}>
          {rows === 0 ? (
            <div className="flex h-full items-center justify-center text-[13px] text-gray-500">No unmatched lines. Everything tied out.</div>
          ) : (
            <div className="relative" style={{ height: rows * ROW_H }}>
              <div className="absolute top-0 left-0" style={{ width: colW, height: rows * ROW_H }}>
                {bankRows}
              </div>
              <svg className="pointer-events-none absolute top-0" style={{ left: colW, width: GUTTER, height: rows * ROW_H }} aria-hidden="true">
                {curves.map((c) => {
                  const hot = !!hover && (c.bankRef === hover.ref || c.glRef === hover.ref);
                  const faded = !!hover && !hot;
                  const delay = inIntro ? `${c.batch * (INTRO_MS / BATCHES)}ms` : undefined;
                  if (c.kind === "prior") {
                    return (
                      <g key={`${c.key}-${introAt}`} opacity={faded ? 0.25 : 1}>
                        <path
                          d={`M 0 ${c.y1} C ${GUTTER * 0.35} ${c.y1}, ${GUTTER * 0.4} ${c.y1 - 7}, ${GUTTER * 0.55} ${c.y1 - 7}`}
                          pathLength={inIntro ? 1 : undefined}
                          className={inIntro ? "curve-draw" : undefined}
                          style={{ animationDelay: delay }}
                          stroke="#6366f1"
                          strokeWidth={hot ? 2 : 1.25}
                          strokeDasharray={inIntro ? undefined : "3 3"}
                          fill="none"
                        />
                        <circle cx={GUTTER * 0.55 + 3} cy={c.y1 - 7} r={3} fill="#fff" stroke="#6366f1" strokeWidth={1.25} />
                      </g>
                    );
                  }
                  const isLink = c.kind === "link";
                  return (
                    <path
                      key={`${c.key}-${introAt}`}
                      d={`M 0 ${c.y1} C ${GUTTER * 0.5} ${c.y1}, ${GUTTER * 0.5} ${c.y2}, ${GUTTER} ${c.y2}`}
                      pathLength={inIntro && !isLink ? 1 : undefined}
                      className={inIntro && !isLink ? "curve-draw" : undefined}
                      style={{ animationDelay: delay }}
                      stroke={isLink ? "#f59e0b" : hot ? "#4338ca" : "#818cf8"}
                      strokeOpacity={faded ? 0.22 : isLink ? 0.95 : hot ? 1 : 0.6}
                      strokeWidth={hot ? 2.25 : isLink ? 1.75 : 1.25}
                      strokeDasharray={isLink ? "4 3" : undefined}
                      fill="none"
                    />
                  );
                })}
              </svg>
              <div className="absolute top-0" style={{ left: colW + GUTTER, right: 0, height: rows * ROW_H }}>
                {glRows}
              </div>
            </div>
          )}
        </div>
        <Inspector
          hover={hover}
          bankByRef={bankByRef}
          glByRef={glByRef}
          exceptionsByRef={exceptionsByRef}
          ajeById={ajeById}
          links={links}
        />
      </div>
    </div>
  );
}

function MatchingHeader({
  counts,
  filter,
  setFilter,
  onReplay,
}: {
  counts: { bankMatched: number; glMatched: number; bankExc: number; glExc: number; prior: number } | null;
  filter: Filter;
  setFilter: (f: Filter) => void;
  onReplay: () => void;
}) {
  return (
    <div className="mb-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-[14px] font-semibold text-gray-900">Matching view</div>
        <div className="flex shrink-0 items-center gap-1.5">
          <div className="inline-flex items-center rounded-lg bg-gray-100 p-0.5" role="radiogroup" aria-label="Filter lines">
            {(["all", "exceptions"] as Filter[]).map((f) => (
              <button
                key={f}
                type="button"
                role="radio"
                aria-checked={filter === f}
                data-testid={`match-filter-${f}`}
                onClick={() => setFilter(f)}
                className={cn(
                  "inline-flex h-7 items-center rounded-md px-2.5 text-[12px] font-medium whitespace-nowrap transition-colors",
                  filter === f ? "bg-white text-gray-900 shadow-sm" : "text-gray-600 hover:text-gray-900",
                )}
              >
                {f === "all" ? "All lines" : `Exceptions only${counts ? ` (${counts.bankExc + counts.glExc})` : ""}`}
              </button>
            ))}
          </div>
          {counts && (
            <Hint label="Replay the matching animation">
              <Button variant="ghost" size="icon-sm" onClick={onReplay} aria-label="Replay the matching animation">
                <RotateCcwIcon className="size-3.5" />
              </Button>
            </Hint>
          )}
        </div>
      </div>
      <div className="mt-0.5 text-[12px] text-gray-500">
        {counts ? (
          <>
            {formatInt(counts.bankMatched)} bank lines matched
            {counts.prior ? `, ${counts.prior} of them to items outstanding from August` : ""}. {counts.bankExc + counts.glExc} leftovers, each explained.
          </>
        ) : (
          "Bank lines on the left, ledger lines on the right"
        )}
      </div>
    </div>
  );
}

function Inspector({
  hover,
  bankByRef,
  glByRef,
  exceptionsByRef,
  ajeById,
  links,
}: {
  hover: Hover | null;
  bankByRef: Map<string, BankLine>;
  glByRef: Map<string, GlLine>;
  exceptionsByRef: Map<string, ReconException>;
  ajeById: Map<string, AJE>;
  links: { bank: string; gl: string }[];
}) {
  let content: React.ReactNode = (
    <span className="flex items-center gap-2 text-gray-400">
      <MousePointerClickIcon className="size-3.5" /> Hover a line to see how it was matched, or why it was left over.
    </span>
  );
  if (hover) {
    const line = hover.side === "bank" ? bankByRef.get(hover.ref) : glByRef.get(hover.ref);
    if (line) {
      const exc = exceptionsByRef.get(`${hover.side}:${line.ref}`);
      const kind = line.exception ?? exc?.kind ?? null;
      const partnerRef = line.match ?? (hover.side === "bank" ? links.find((l) => l.bank === line.ref)?.gl : links.find((l) => l.gl === line.ref)?.bank) ?? null;
      const partner = partnerRef ? (hover.side === "bank" ? glByRef.get(partnerRef) : bankByRef.get(partnerRef)) : undefined;
      const aje = exc?.aje_id ? ajeById.get(exc.aje_id) : undefined;
      content = (
        <div className="min-w-0 space-y-0.5">
          <div className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 font-medium text-gray-900">{hover.side === "bank" ? "Bank" : "Ledger"}</span>
            <span className="mono shrink-0 text-gray-500">{line.ref}</span>
            <span className="shrink-0 text-gray-400">{formatDate(line.date)}</span>
            <span className="min-w-0 truncate text-gray-700">{line.description}</span>
            <span className="money ml-auto shrink-0 font-medium text-gray-900">{formatMoney(line.amount)}</span>
          </div>
          <div className="truncate text-gray-600">
            {line.match?.startsWith("AUG-") ? (
              <span className="inline-flex items-center gap-1.5">
                <HistoryIcon className="size-3.5 text-indigo-600" /> Cleared prior-period item <span className="mono">{line.match}</span>, carried from the August reconciliation.
              </span>
            ) : line.match ? (
              <>
                Matched to <span className="mono">{line.match}</span> by <MethodLabel method={line.method} />
                {partner ? (
                  <>
                    : <span className="text-gray-500">{partner.description}</span>, {formatShortDate(partner.date)}
                  </>
                ) : null}
              </>
            ) : kind ? (
              <>
                <span className="font-medium text-gray-800">{EXCEPTION_LABEL[kind]}</span>
                {exc?.note ? `: ${exc.note}` : ""}
                {aje ? (
                  <span className="text-gray-500">
                    {" "}
                    · {aje.id} Dr {aje.debit_account} {aje.debit_account_name} / Cr {aje.credit_account} {aje.credit_account_name} {formatMoney(aje.amount)}
                  </span>
                ) : exc?.needs_review ? (
                  <span className="font-medium text-red-700"> · flagged for a human to investigate</span>
                ) : null}
                {partner && kind === "transposition" ? <span className="text-gray-500"> · pairs with {partner.ref}</span> : null}
              </>
            ) : (
              "Unmatched"
            )}
          </div>
        </div>
      );
    }
  }
  return <div className="h-[52px] border-t border-gray-200 bg-gray-50/70 px-3 py-2 text-[12px]" data-testid="matching-inspector">{content}</div>;
}
