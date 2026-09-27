import type { ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router";
import { toast } from "sonner";
import {
  CheckIcon,
  ChevronDownIcon,
  LogOutIcon,
  OctagonAlertIcon,
  RepeatIcon,
  ShieldCheckIcon,
} from "lucide-react";
import { isMock } from "@/api";
import type { DemoAccount, Health, Role } from "@/api/types";
import { Logo } from "@/components/brand/Logo";
import { ToneDot } from "@/components/status";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuthActions, useDemoAccounts, useHealth, useMe, useSystem } from "@/hooks/queries";
import { firstName, formatClock, initials } from "@/lib/format";
import { HEALTH_LABEL, ROLE_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";

function NavItem({ to, children, testId, end }: { to: string; children: ReactNode; testId?: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      data-testid={testId}
      className={({ isActive }) =>
        cn(
          "relative inline-flex h-14 shrink-0 items-center px-2 text-[13px] font-medium transition-colors sm:px-3",
          isActive ? "text-gray-900 after:absolute after:inset-x-2 after:bottom-0 sm:after:inset-x-3 after:h-0.5 after:rounded-full after:bg-primary" : "text-gray-500 hover:text-gray-900",
        )
      }
    >
      {children}
    </NavLink>
  );
}

function healthTone(h: Health | undefined, error: boolean) {
  if (error) return { tone: "danger" as const, label: "API unreachable" };
  if (!h) return { tone: "muted" as const, label: "Checking systems" };
  const bad = Object.values(h.checks).filter((c) => !c.ok).length;
  if (bad === 0) return { tone: "success" as const, label: "All systems operational" };
  return { tone: bad >= 2 ? ("danger" as const) : ("warning" as const), label: `${bad} check${bad > 1 ? "s" : ""} failing` };
}

export function HealthDot({ isAdmin }: { isAdmin: boolean }) {
  const health = useHealth();
  const navigate = useNavigate();
  const { tone, label } = healthTone(health.data, health.isError);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          data-testid="health-dot"
          data-health={tone}
          aria-label={label}
          onClick={() => isAdmin && navigate("/admin")}
          className="flex h-8 items-center gap-2 rounded-full border border-gray-200 bg-white px-2.5 text-[12px] text-gray-600 transition-colors hover:bg-gray-50"
        >
          <ToneDot tone={tone} pulse={tone === "success"} className={tone === "success" ? "text-emerald-400" : ""} />
          <span className="hidden xl:inline">{tone === "success" ? "Healthy" : label}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="w-72 max-w-none p-3">
        <div className="mb-2 font-semibold">{label}</div>
        {health.data ? (
          <ul className="space-y-1.5">
            {Object.entries(health.data.checks).map(([k, c]) => (
              <li key={k} className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2">
                  <ToneDot tone={c.ok ? "success" : "danger"} />
                  {c.label ?? HEALTH_LABEL[k] ?? k}
                </span>
                <span className="tnum text-gray-400">{c.ms} ms</span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-gray-300">{health.isError ? "The health endpoint did not respond." : "Checking inference, database, storage and runner."}</div>
        )}
        {isAdmin && <div className="mt-2 border-t border-white/10 pt-2 text-gray-400">Click for the admin console</div>}
      </TooltipContent>
    </Tooltip>
  );
}

function roleSwitchLabel(a: DemoAccount) {
  return `Switch to ${firstName(a.name)} (${ROLE_LABEL[a.role]})`;
}

export function UserMenu() {
  const me = useMe();
  const accounts = useDemoAccounts();
  const { logout, switchTo } = useAuthActions();
  const navigate = useNavigate();
  const user = me.data;
  if (!user) return null;
  const order: Role[] = ["preparer", "reviewer", "admin"];
  const list = [...(accounts.data ?? [])].sort((a, b) => order.indexOf(a.role) - order.indexOf(b.role));

  const onSwitch = async (a: DemoAccount) => {
    if (a.email.toLowerCase() === user.email.toLowerCase()) return;
    try {
      const u = await switchTo(a);
      toast.success(`Signed in as ${u.name}`, { description: `${u.title}, ${ROLE_LABEL[u.role]} role` });
    } catch (e) {
      toast.error("Could not switch accounts", { description: e instanceof Error ? e.message : String(e) });
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          data-testid="user-menu"
          className="flex h-10 items-center gap-2.5 rounded-lg py-1 pr-2 pl-1 text-left transition-colors outline-none hover:bg-gray-100 focus-visible:ring-2 focus-visible:ring-ring/40"
        >
          <span className="flex size-8 items-center justify-center rounded-full bg-indigo-100 text-[12px] font-semibold text-indigo-800">{initials(user.name)}</span>
          <span className="hidden leading-tight lg:block">
            <span className="block text-[13px] font-medium text-gray-900" data-testid="current-user-name">
              {user.name}
            </span>
            <span className="block text-[11px] text-gray-500" data-testid="current-user-role" data-role={user.role}>
              {ROLE_LABEL[user.role]} · {user.title}
            </span>
          </span>
          <ChevronDownIcon className="hidden size-4 text-gray-400 sm:block" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <div className="px-2 py-2">
          <div className="text-[13px] font-semibold text-gray-900">{user.name}</div>
          <div className="text-[12px] text-gray-500">{user.email}</div>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="flex items-center gap-1.5">
          <RepeatIcon className="size-3" /> Switch demo account
        </DropdownMenuLabel>
        {list.map((a) => {
          const current = a.email.toLowerCase() === user.email.toLowerCase();
          return (
            <DropdownMenuItem key={a.email} data-testid={`role-switch-${a.role}`} onSelect={() => void onSwitch(a)} className="py-2">
              <span className="flex size-7 items-center justify-center rounded-full bg-gray-100 text-[11px] font-semibold text-gray-700">{initials(a.name)}</span>
              <span className="min-w-0 flex-1 leading-tight">
                <span className="block text-[13px] text-gray-900">{roleSwitchLabel(a)}</span>
                <span className="block truncate text-[11px] text-gray-500">{a.title}</span>
              </span>
              {current && <CheckIcon className="size-4 text-indigo-600" />}
            </DropdownMenuItem>
          );
        })}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          data-testid="sign-out"
          onSelect={() =>
            void logout().then(() => {
              navigate("/login");
            })
          }
        >
          <LogOutIcon /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function KillSwitchBanner() {
  const me = useMe();
  const system = useSystem(!!me.data);
  const health = useHealth();
  const on = system.data?.kill_switch || health.data?.kill_switch;
  if (!on) return null;
  return (
    <div className="border-b border-red-200 bg-red-50" data-testid="kill-switch-banner">
      <div className="mx-auto flex max-w-[1560px] flex-wrap items-center gap-x-2 gap-y-1 px-4 py-2 text-[13px] text-red-800 sm:px-6">
        <OctagonAlertIcon className="size-4 text-red-600" />
        <span className="font-semibold">Kill switch is on.</span>
        <span>New work is stopped and running sandboxes were destroyed.</span>
        {system.data?.kill_switch_auto_resume_at && (
          <span className="text-red-700/80">Auto-resumes at {formatClock(system.data.kill_switch_auto_resume_at)} (public demo safeguard).</span>
        )}
        {me.data?.role === "admin" ? (
          <Link to="/admin" className="ml-1 font-medium underline underline-offset-2">
            Open the admin console
          </Link>
        ) : (
          <span className="text-red-700/80">An admin can turn it off.</span>
        )}
      </div>
    </div>
  );
}

export function TopBar() {
  const me = useMe();
  const system = useSystem(!!me.data);
  const isAdmin = me.data?.role === "admin";
  return (
    <header className="sticky top-0 z-40 border-b border-gray-200 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/80">
      <div className="mx-auto flex h-14 max-w-[1560px] items-center gap-3 px-4 sm:gap-6 sm:px-6">
        <Link to="/" className="flex shrink-0 items-center gap-3" aria-label="Tieout home">
          <Logo className="max-sm:[&_.logo-text]:hidden" />
        </Link>
        <div className="hidden h-6 w-px bg-gray-200 md:block" />
        <div className="hidden items-center gap-2 md:flex">
          <span className="text-[13px] font-medium text-gray-800">{system.data?.firm ?? "Harbor & Pine CPA"}</span>
          <span className="rounded-md border border-gray-200 bg-gray-50 px-2 py-0.5 text-[12px] text-gray-600">{system.data?.period_label ?? "September 2026"}</span>
        </div>
        <nav className="flex min-w-0 items-center overflow-x-auto sm:ml-2">
          <NavItem to="/" end testId="nav-close">
            Close
          </NavItem>
          <NavItem to="/how-it-works" testId="nav-how">
            How it works
          </NavItem>
          {isAdmin && (
            <NavItem to="/admin" testId="nav-admin">
              Admin
            </NavItem>
          )}
        </nav>
        <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">
          {isMock && (
            <span className="rounded-md border border-dashed border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800" title="VITE_MOCK=1: data comes from recorded fixtures">
              Mock data
            </span>
          )}
          <HealthDot isAdmin={isAdmin} />
          <UserMenu />
        </div>
      </div>
      <KillSwitchBanner />
    </header>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <TopBar />
      <main>{children}</main>
    </div>
  );
}

export function PublicShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-gray-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1560px] items-center gap-3 px-4 sm:gap-6 sm:px-6">
          <Link to="/login" aria-label="Tieout">
            <Logo />
          </Link>
          <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">
            <span className="hidden items-center gap-1.5 text-[12px] text-gray-500 md:flex">
              <ShieldCheckIcon className="size-3.5 text-indigo-600" /> Demo accounts are listed on the sign-in page
            </span>
            <Button asChild size="sm">
              <Link to="/login">Sign in</Link>
            </Button>
          </div>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
