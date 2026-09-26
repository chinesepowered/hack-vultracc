import type { ReactNode } from "react";
import { AlertTriangleIcon, Loader2Icon, RefreshCwIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon,
  title,
  children,
  action,
  className,
}: {
  icon?: ReactNode;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-10 text-center", className)}>
      {icon && <div className="mb-3 flex size-10 items-center justify-center rounded-full bg-gray-100 text-gray-500 [&_svg]:size-5">{icon}</div>}
      <div className="text-sm font-semibold text-gray-900">{title}</div>
      {children && <div className="mt-1 max-w-md text-[13px] leading-relaxed text-gray-500">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ title = "Something went wrong", message, onRetry, className }: { title?: string; message?: string; onRetry?: () => void; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-10 text-center", className)}>
      <div className="mb-3 flex size-10 items-center justify-center rounded-full bg-red-50 text-red-600">
        <AlertTriangleIcon className="size-5" />
      </div>
      <div className="text-sm font-semibold text-gray-900">{title}</div>
      {message && <div className="mt-1 max-w-md text-[13px] text-gray-500">{message}</div>}
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          <RefreshCwIcon /> Try again
        </Button>
      )}
    </div>
  );
}

export function LoadingState({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <div className={cn("flex items-center justify-center gap-2 py-10 text-[13px] text-gray-500", className)}>
      <Loader2Icon className="size-4 animate-spin" /> {label}
    </div>
  );
}

export function Alert({
  tone = "danger",
  icon,
  title,
  children,
  className,
  action,
  ...rest
}: {
  tone?: "danger" | "warning" | "info" | "success";
  icon?: ReactNode;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
  action?: ReactNode;
} & React.HTMLAttributes<HTMLDivElement>) {
  const styles = {
    danger: "border-red-200 bg-red-50 text-red-800 [&_.alert-icon]:text-red-600",
    warning: "border-amber-200 bg-amber-50 text-amber-900 [&_.alert-icon]:text-amber-600",
    info: "border-indigo-200 bg-indigo-50/70 text-indigo-900 [&_.alert-icon]:text-indigo-600",
    success: "border-emerald-200 bg-emerald-50 text-emerald-900 [&_.alert-icon]:text-emerald-600",
  }[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("flex items-start gap-3 rounded-lg border px-4 py-3 text-[13px]", styles, className)} {...rest}>
      {icon && <div className="alert-icon mt-0.5 shrink-0 [&_svg]:size-4">{icon}</div>}
      <div className="min-w-0 flex-1">
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className={cn("leading-relaxed", title && "mt-0.5 opacity-90")}>{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
