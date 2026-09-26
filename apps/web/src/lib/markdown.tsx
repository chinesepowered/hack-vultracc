import type { ReactNode } from "react";

// Minimal, safe Markdown for agent memos: headings, paragraphs, lists, code, bold, italics, links.
// Builds React nodes only; never injects HTML.

function renderInline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(\*\*([^*]+)\*\*)|(`([^`]+)`)|(\*([^*\s][^*]*)\*)|(_([^_\s][^_]*)_)|(\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const key = `${keyBase}-${k++}`;
    if (m[2] !== undefined) nodes.push(<strong key={key} className="font-semibold text-gray-900">{renderInline(m[2], key)}</strong>);
    else if (m[4] !== undefined) nodes.push(<code key={key} className="rounded bg-gray-100 px-1 py-0.5 font-mono text-[0.85em] text-gray-800">{m[4]}</code>);
    else if (m[6] !== undefined) nodes.push(<em key={key}>{renderInline(m[6], key)}</em>);
    else if (m[8] !== undefined) nodes.push(<em key={key}>{renderInline(m[8], key)}</em>);
    else if (m[10] !== undefined)
      nodes.push(
        <span key={key} className="text-indigo-700 underline decoration-indigo-300 underline-offset-2">
          {m[10]} <span className="text-gray-500">({m[11]})</span>
        </span>,
      );
    last = re.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

type Block =
  | { type: "h"; level: number; text: string }
  | { type: "p"; text: string }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] }
  | { type: "code"; text: string };

function parseBlocks(md: string): Block[] {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    if (line.trim().startsWith("```")) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) buf.push(lines[i++]);
      i++;
      blocks.push({ type: "code", text: buf.join("\n") });
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      blocks.push({ type: "h", level: h[1].length, text: h[2] });
      i++;
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && (/^\s*[-*]\s+/.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        if (/^\s*[-*]\s+/.test(lines[i])) items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        else items[items.length - 1] += " " + lines[i].trim();
        i++;
      }
      blocks.push({ type: "ul", items });
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+[.)]\s+/, ""));
      blocks.push({ type: "ol", items });
      continue;
    }
    const buf: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,4})\s+/.test(lines[i]) &&
      !/^\s*[-*]\s+/.test(lines[i]) &&
      !lines[i].trim().startsWith("```")
    )
      buf.push(lines[i++].trim());
    blocks.push({ type: "p", text: buf.join(" ") });
  }
  return blocks;
}

export function Markdown({ source, className }: { source: string; className?: string }) {
  const blocks = parseBlocks(source);
  return (
    <div className={className}>
      {blocks.map((b, idx) => {
        const key = `b${idx}`;
        switch (b.type) {
          case "h": {
            const cls =
              b.level <= 1
                ? "mt-1 mb-3 text-lg font-semibold text-gray-900"
                : b.level === 2
                  ? "mt-5 mb-2 text-base font-semibold text-gray-900"
                  : "mt-4 mb-2 text-sm font-semibold text-gray-900";
            return (
              <p key={key} className={cls}>
                {renderInline(b.text, key)}
              </p>
            );
          }
          case "ul":
            return (
              <ul key={key} className="my-3 list-disc space-y-1.5 pl-5 marker:text-gray-400">
                {b.items.map((it, j) => (
                  <li key={j}>{renderInline(it, `${key}-${j}`)}</li>
                ))}
              </ul>
            );
          case "ol":
            return (
              <ol key={key} className="my-3 list-decimal space-y-1.5 pl-5 marker:text-gray-400">
                {b.items.map((it, j) => (
                  <li key={j}>{renderInline(it, `${key}-${j}`)}</li>
                ))}
              </ol>
            );
          case "code":
            return (
              <pre key={key} className="my-3 overflow-x-auto rounded-md border bg-gray-50 p-3 font-mono text-xs text-gray-800">
                {b.text}
              </pre>
            );
          default:
            return (
              <p key={key} className="my-3 leading-relaxed">
                {renderInline(b.text, key)}
              </p>
            );
        }
      })}
    </div>
  );
}
