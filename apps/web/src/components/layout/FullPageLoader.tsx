import { LogoMark } from "@/components/brand/Logo";

export function FullPageLoader() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background">
      <LogoMark className="size-10 animate-pulse" />
      <div className="text-[13px] text-gray-500">Loading Tieout</div>
    </div>
  );
}
