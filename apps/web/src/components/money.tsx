import { CheckCircle2Icon, AlertCircleIcon } from "lucide-react";
import { formatMoney, isZeroMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

export function Money({
  value,
  className,
  sign,
  muted,
}: {
  value: string | number | null | undefined;
  className?: string;
  sign?: boolean;
  muted?: boolean;
}) {
  if (value === null || value === undefined || value === "") return <span className={cn("text-gray-400", className)}>n/a</span>;
  return <span className={cn("money", muted && "text-gray-500", className)}>{formatMoney(value, { sign })}</span>;
}

/** The reconciliation difference: 0.00 with a check when it ties, red otherwise. */
export function Difference({ value, className, size = "md" }: { value: string | null | undefined; className?: string; size?: "sm" | "md" | "lg" }) {
  if (value === null || value === undefined) return <span className={cn("text-gray-400", className)}>Pending</span>;
  const ok = isZeroMoney(value);
  const Icon = ok ? CheckCircle2Icon : AlertCircleIcon;
  return (
    <span className={cn("inline-flex items-center gap-1 font-semibold", ok ? "text-emerald-700" : "text-red-700", className)}>
      <span className="money">{formatMoney(value)}</span>
      <Icon className={cn(size === "sm" ? "size-3.5" : size === "lg" ? "size-5" : "size-4")} />
    </span>
  );
}
