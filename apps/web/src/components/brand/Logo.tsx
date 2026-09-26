import { cn } from "@/lib/utils";

/** Tieout mark: two ledgers (bank and books) joined by a matching curve. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#3730a3" />
      <g stroke="#fff" strokeWidth="2.4" strokeLinecap="round" fill="none">
        <path d="M7 10h5M7 16h5M7 22h5M20 10h5M20 16h5M20 22h5" strokeOpacity="0.55" />
        <path d="M12 10c4 0 4 12 8 12" />
      </g>
    </svg>
  );
}

export function Logo({ className, subtitle }: { className?: string; subtitle?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      <div className="leading-none">
        <div className="text-[17px] font-semibold tracking-tight text-gray-900">Tieout</div>
        {subtitle && <div className="mt-0.5 text-[11px] text-gray-500">{subtitle}</div>}
      </div>
    </div>
  );
}
