import { CpuIcon, LockIcon, ShieldCheckIcon, WifiOffIcon } from "lucide-react";
import type { Badges } from "@/api/types";
import { Hint } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

function Chip({ icon, label, hint, dim }: { icon: React.ReactNode; label: string; hint: string; dim?: boolean }) {
  return (
    <Hint label={hint}>
      <span
        className={cn(
          "pop-in inline-flex items-center gap-[3px] rounded-md border px-1 py-px text-[11px] font-medium whitespace-nowrap [&_svg]:size-3 max-[1399px]:[&_svg]:hidden",
          dim ? "border-gray-200 bg-gray-50 text-gray-500" : "border-indigo-100 bg-indigo-50/80 text-indigo-800",
        )}
      >
        {icon}
        {label}
      </span>
    </Hint>
  );
}

/** gVisor / No network / Read-only / 1 CPU. Rendered only once the sandbox exists. */
export function SandboxBadges({ badges, dim, className }: { badges: Badges; dim?: boolean; className?: string }) {
  const gvisor = badges.runtime === "runsc";
  const cpus = badges.cpus ?? null;
  return (
    <div className={cn("flex flex-nowrap items-center gap-1 overflow-hidden", className)}>
      {badges.runtime && (
        <Chip dim={dim} icon={<ShieldCheckIcon />} label={gvisor ? "gVisor" : badges.runtime} hint="Container runtime runsc: gVisor's user-space kernel sits between the code and the host." />
      )}
      {badges.network && (
        <Chip dim={dim} icon={<WifiOffIcon />} label={badges.network === "none" ? "No network" : `Network ${badges.network}`} hint="Docker network mode none: only a loopback interface. Outbound connections and DNS fail." />
      )}
      {badges.readonly_rootfs && <Chip dim={dim} icon={<LockIcon />} label="Read-only" hint="Read-only root filesystem, and client inputs mounted read-only." />}
      {cpus !== null && (
        <Chip
          dim={dim}
          icon={<CpuIcon />}
          label={`${cpus % 1 === 0 ? cpus.toFixed(0) : cpus} CPU`}
          hint={`Hard limits: ${cpus} CPU${badges.memory_mb ? `, ${badges.memory_mb >= 1024 ? `${badges.memory_mb / 1024} GiB` : `${badges.memory_mb} MB`} memory` : ""}, 256 processes, 60 s per step.`}
        />
      )}
    </div>
  );
}
