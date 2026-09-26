import { useState } from "react";
import { CheckIcon, CopyIcon } from "lucide-react";
import { Hint } from "@/components/ui/tooltip";
import { shortHash } from "@/lib/format";
import { cn } from "@/lib/utils";

export function CopyButton({ value, className, label = "Copy" }: { value: string; className?: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      aria-label={label}
      onClick={(e) => {
        e.stopPropagation();
        void navigator.clipboard?.writeText(value).catch(() => undefined);
        setDone(true);
        setTimeout(() => setDone(false), 1200);
      }}
      className={cn("inline-flex size-5 items-center justify-center rounded text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700", className)}
    >
      {done ? <CheckIcon className="size-3 text-emerald-600" /> : <CopyIcon className="size-3" />}
    </button>
  );
}

export function Hash({
  value,
  head = 10,
  tail = 6,
  className,
  copy = true,
  full = false,
}: {
  value: string | null | undefined;
  head?: number;
  tail?: number;
  className?: string;
  copy?: boolean;
  full?: boolean;
}) {
  if (!value) return <span className="text-gray-400">n/a</span>;
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-1", className)}>
      <Hint label={<span className="mono break-all">{value}</span>} className="max-w-md">
        <span className={cn("mono truncate text-[12px] text-gray-700", full && "break-all whitespace-normal")}>{full ? value : shortHash(value, head, tail)}</span>
      </Hint>
      {copy && <CopyButton value={value} label="Copy hash" />}
    </span>
  );
}
