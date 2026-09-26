import { useMemo } from "react";
import { highlightPython } from "@/lib/highlight";
import { CopyButton } from "@/components/hash";
import { cn } from "@/lib/utils";

export function CodeBlock({
  code,
  className,
  maxHeight = 320,
  title,
  wrap = false,
}: {
  code: string;
  className?: string;
  maxHeight?: number | "none";
  title?: string;
  /** Wrap long lines with a hanging indent (for narrow columns). */
  wrap?: boolean;
}) {
  const nodes = useMemo(() => (wrap ? null : highlightPython(code)), [code, wrap]);
  const lineNodes = useMemo(() => (wrap ? code.split("\n").map((l) => highlightPython(l)) : null), [code, wrap]);
  const lines = code.split("\n").length;
  return (
    <div className={cn("overflow-hidden rounded-lg border border-gray-200 bg-[#fbfbfd]", className)}>
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-3 py-1.5 text-[11px] text-gray-500">
        <span className="mono">{title ?? "python"}</span>
        <span className="flex items-center gap-2">
          <span className="tnum">{lines} lines</span>
          <CopyButton value={code} label="Copy code" />
        </span>
      </div>
      <div className="scrollbar-thin overflow-auto" style={{ maxHeight: maxHeight === "none" ? undefined : maxHeight }}>
        {lineNodes ? (
          <div className="mono p-3 text-[11.5px] leading-[1.55] text-gray-800">
            {lineNodes.map((ln, i) => (
              <div key={i} className="min-h-[1.55em] whitespace-pre-wrap [overflow-wrap:break-word]" style={{ paddingLeft: "4ch", textIndent: "-4ch" }}>
                {ln}
              </div>
            ))}
          </div>
        ) : (
          <pre className="mono p-3 text-[12px] leading-[1.6] text-gray-800">
            <code>{nodes}</code>
          </pre>
        )}
      </div>
    </div>
  );
}

export function OutputBlock({
  stdout,
  stderr,
  className,
  maxHeight = 280,
}: {
  stdout?: string | null;
  stderr?: string | null;
  className?: string;
  maxHeight?: number | "none";
}) {
  const out = (stdout ?? "").replace(/\s+$/, "");
  const err = (stderr ?? "").replace(/\s+$/, "");
  return (
    <div className={cn("overflow-hidden rounded-lg border border-gray-200 bg-white", className)}>
      <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-3 py-1.5 text-[11px] text-gray-500">
        <span className="mono">stdout</span>
        {out && <CopyButton value={out} label="Copy output" />}
      </div>
      <div className="scrollbar-thin overflow-auto" style={{ maxHeight: maxHeight === "none" ? undefined : maxHeight }}>
        <pre className="mono p-3 text-[11.5px] leading-[1.55] whitespace-pre text-gray-700">{out || <span className="text-gray-400">(no output)</span>}</pre>
      </div>
      {err && (
        <>
          <div className="border-t border-gray-200 bg-gray-50 px-3 py-1.5 text-[11px] text-gray-500">
            <span className="mono">stderr</span>
          </div>
          <div className="scrollbar-thin overflow-auto" style={{ maxHeight: 120 }}>
            <pre className="mono p-3 text-[11.5px] leading-[1.55] whitespace-pre-wrap text-amber-800">{err}</pre>
          </div>
        </>
      )}
    </div>
  );
}
