// Formatting helpers. Money arrives from the API as strings with two decimals ("1250.00").

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function groupThousands(intPart: string): string {
  return intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** "1250.5" -> "1,250.50"; "-845.00" -> "(845.00)". String based, so no float drift. */
export function formatMoney(value: string | number | null | undefined, opts: { parens?: boolean; sign?: boolean } = {}): string {
  if (value === null || value === undefined || value === "") return "";
  const parens = opts.parens ?? true;
  let s = typeof value === "number" ? value.toFixed(2) : String(value).trim().replace(/,/g, "");
  let negative = false;
  if (s.startsWith("(") && s.endsWith(")")) {
    negative = true;
    s = s.slice(1, -1);
  }
  if (s.startsWith("-")) {
    negative = true;
    s = s.slice(1);
  } else if (s.startsWith("+")) {
    s = s.slice(1);
  }
  const n = Number(s);
  if (!Number.isFinite(n)) return String(value);
  const [i, d = ""] = n.toFixed(2).split(".");
  const body = `${groupThousands(i)}.${d.padEnd(2, "0")}`;
  const isZero = Number(body.replace(/,/g, "")) === 0;
  if (negative && !isZero) return parens ? `(${body})` : `-${body}`;
  if (opts.sign && !isZero) return `+${body}`;
  return body;
}

export function moneyNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  if (typeof value === "number") return value;
  const n = Number(String(value).replace(/,/g, ""));
  return Number.isFinite(n) ? n : 0;
}

export function isZeroMoney(value: string | null | undefined): boolean {
  return value !== null && value !== undefined && Math.abs(moneyNumber(value)) < 0.005;
}

export function sumMoney(values: (string | number | null | undefined)[]): string {
  const cents = values.reduce<number>((acc, v) => acc + Math.round(moneyNumber(v) * 100), 0);
  return (cents / 100).toFixed(2);
}

export function formatInt(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "";
  return groupThousands(String(Math.round(n)));
}

export function formatCompact(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "0";
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 1 : 2)}M`;
  if (Math.abs(n) >= 10_000) return `${Math.round(n / 1000)}k`;
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export function formatPercent(part: number | null | undefined, whole: number | null | undefined, digits = 1): string {
  if (!whole || part === null || part === undefined) return "";
  const p = (part / whole) * 100;
  if (p >= 99.95 && part < whole) return `${(99.9).toFixed(digits)}%`;
  return `${p.toFixed(digits)}%`;
}

/** "2026-09-16" -> "Sep 16" */
export function formatShortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}`;
}

/** "2026-09-16" -> "09/16/2026" */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${m[2]}/${m[3]}/${m[1]}`;
}

/** ISO timestamp -> "Sep 26, 2026, 1:45 PM" in the viewer's time zone. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** ISO timestamp -> "1:45:12 PM" */
export function formatTime(iso: string | number | null | undefined): string {
  if (iso === null || iso === undefined || iso === "") return "";
  const d = typeof iso === "number" ? new Date(iso * 1000) : new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

export function toDate(v: string | number | null | undefined): Date | null {
  if (v === null || v === undefined || v === "") return null;
  const d = typeof v === "number" ? new Date(v < 1e12 ? v * 1000 : v) : new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 2 : 1)} s`;
  const m = Math.floor(s / 60);
  const rest = Math.round(s - m * 60);
  return `${m} min ${rest} s`;
}

export function formatBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function shortHash(h: string | null | undefined, head = 10, tail = 6): string {
  if (!h) return "";
  const clean = h.replace(/^sha256:/, "");
  if (clean.length <= head + tail + 1) return clean;
  // note: slice(-0) is slice(0), so a zero tail needs its own branch
  return tail > 0 ? `${clean.slice(0, head)}...${clean.slice(-tail)}` : `${clean.slice(0, head)}...`;
}

export function shortId(id: string | null | undefined, n = 12): string {
  if (!id) return "";
  return id.length > n + 4 ? `${id.slice(0, n)}...` : id;
}

export function initials(name: string | null | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export function firstName(name: string | null | undefined): string {
  return (name ?? "").trim().split(/\s+/)[0] ?? "";
}

export function pluralize(n: number, one: string, many?: string): string {
  return `${formatInt(n)} ${n === 1 ? one : (many ?? `${one}s`)}`;
}

export function relativeFromNow(v: string | number | null | undefined, now = Date.now()): string {
  const d = toDate(v);
  if (!d) return "";
  const diff = Math.round((d.getTime() - now) / 1000);
  const abs = Math.abs(diff);
  const unit = abs < 60 ? `${abs} s` : abs < 3600 ? `${Math.floor(abs / 60)} min ${abs % 60} s` : `${Math.floor(abs / 3600)} h`;
  return diff >= 0 ? `in ${unit}` : `${unit} ago`;
}

/** ISO timestamp -> "9:45 PM" */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}
