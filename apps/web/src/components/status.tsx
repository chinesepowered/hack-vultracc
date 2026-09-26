import type { ReactNode } from "react";
import { Loader2Icon } from "lucide-react";
import type { Tone } from "@/lib/labels";
import { cn } from "@/lib/utils";

const PILL: Record<Tone, string> = {
  neutral: "border-gray-200 bg-white text-gray-700",
  muted: "border-gray-200 bg-gray-50 text-gray-500",
  running: "border-indigo-200 bg-indigo-50 text-indigo-800",
  success: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warning: "border-amber-200 bg-amber-50 text-amber-800",
  danger: "border-red-200 bg-red-50 text-red-700",
};

const DOT: Record<Tone, string> = {
  neutral: "bg-gray-400",
  muted: "bg-gray-300",
  running: "bg-indigo-500",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
};

export function toneText(tone: Tone): string {
  return {
    neutral: "text-gray-700",
    muted: "text-gray-500",
    running: "text-indigo-700",
    success: "text-emerald-700",
    warning: "text-amber-700",
    danger: "text-red-700",
  }[tone];
}

export function ToneDot({ tone, pulse, className }: { tone: Tone; pulse?: boolean; className?: string }) {
  return <span className={cn("inline-block size-2 shrink-0 rounded-full", DOT[tone], pulse && "pulse-dot", className)} />;
}

export function StatusPill({
  tone,
  children,
  spinning,
  size = "md",
  className,
  ...rest
}: {
  tone: Tone;
  children: ReactNode;
  spinning?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
} & React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border font-medium whitespace-nowrap",
        size === "sm" && "px-2 py-0.5 text-[11px]",
        size === "md" && "px-2.5 py-0.5 text-xs",
        size === "lg" && "px-3 py-1 text-[13px]",
        PILL[tone],
        className,
      )}
      {...rest}
    >
      {spinning ? <Loader2Icon className="size-3 animate-spin" /> : <ToneDot tone={tone} />}
      {children}
    </span>
  );
}
