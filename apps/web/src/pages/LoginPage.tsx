import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";
import { toast } from "sonner";
import { ArrowRightIcon, GitCompareArrowsIcon, Loader2Icon, LockKeyholeIcon, ShieldCheckIcon, UserCheckIcon } from "lucide-react";
import type { DemoAccount, Role } from "@/api/types";
import { LogoMark } from "@/components/brand/Logo";
import { CopyButton } from "@/components/hash";
import { Alert } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuthActions, useDemoAccounts, useMe } from "@/hooks/queries";
import { firstName, initials } from "@/lib/format";
import { ROLE_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";

const ROLE_ORDER: Role[] = ["preparer", "reviewer", "admin"];

const ROLE_STYLE: Record<Role, string> = {
  preparer: "bg-indigo-100 text-indigo-800",
  reviewer: "bg-emerald-100 text-emerald-800",
  admin: "bg-gray-200 text-gray-700",
};

/** A small, deliberate picture of what the product does: bank lines tied to ledger lines. Sits in the flow, never behind text. */
function MatchingMotif() {
  const left = [18, 44, 70, 96, 122];
  const right = [31, 57, 5, 109, 83];
  return (
    <svg viewBox="0 0 360 132" className="h-[112px] w-[306px]" aria-hidden="true">
      {left.map((y, i) => (
        <g key={i}>
          <rect x="0" y={y - 5} width={86 + ((i * 23) % 34)} height="10" rx="5" fill="#a5b4fc" fillOpacity="0.28" />
          <rect x={240 + ((i * 17) % 26)} y={right[i] - 5} width={120 - ((i * 17) % 26)} height="10" rx="5" fill="#a5b4fc" fillOpacity="0.28" />
          <path
            d={`M ${92 + ((i * 23) % 34)} ${y} C 170 ${y}, 170 ${right[i]}, ${234 + ((i * 17) % 26)} ${right[i]}`}
            stroke="#c7d2fe"
            strokeOpacity={i === 2 ? 0.95 : 0.5}
            strokeWidth={i === 2 ? 2 : 1.5}
            fill="none"
          />
        </g>
      ))}
    </svg>
  );
}

function BrandPanel() {
  return (
    <div className="relative hidden overflow-hidden bg-[#1e1b4b] text-white lg:flex lg:w-[46%] lg:flex-col">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,#3730a3_0%,transparent_55%),radial-gradient(ellipse_at_bottom_right,#312e81_0%,transparent_50%)]" />
      <div className="relative flex min-h-full flex-1 flex-col px-12 py-9 xl:px-16">
        <div className="flex items-center gap-3">
          <LogoMark className="size-9 [&_rect]:fill-white/10" />
          <span className="text-xl font-semibold tracking-tight">Tieout</span>
        </div>
        <div className="my-auto max-w-lg py-8">
          <MatchingMotif />
          <div className="mt-6 text-[13px] font-medium tracking-wide text-indigo-200 uppercase">AI month-end close</div>
          <h1 className="mt-2.5 text-[38px] leading-[1.1] font-semibold tracking-tight">Month-end close, contained.</h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-indigo-100/90">
            An agent reconciles every client's bank account by writing and running real Python inside that client's own sealed sandbox on Vultr. A human approves every
            adjusting entry, and every number can be replayed and verified.
          </p>
          <ul className="mt-7 space-y-4">
            {[
              {
                icon: <LockKeyholeIcon />,
                title: "One sealed sandbox per client",
                body: "gVisor, no network, read-only inputs, no access to the ledger.",
              },
              {
                icon: <UserCheckIcon />,
                title: "The agent never posts",
                body: "Adjusting entries export only after a reviewer approves them.",
              },
              {
                icon: <GitCompareArrowsIcon />,
                title: "Every number is reproducible",
                body: "Replay re-runs the recorded code in a fresh sandbox and compares SHA-256 hashes.",
              },
            ].map((f) => (
              <li key={f.title} className="flex gap-4">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-white/10 text-indigo-100 ring-1 ring-white/15 [&_svg]:size-[18px]">{f.icon}</div>
                <div>
                  <div className="text-[15px] font-medium">{f.title}</div>
                  <div className="mt-0.5 text-[14px] text-indigo-200/90">{f.body}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <div className="text-[12px] leading-relaxed text-indigo-200/70">
          Runs entirely on Vultr: Cloud Compute, Serverless Inference, Managed PostgreSQL and Object Storage.
          <br />
          Harbor &amp; Pine CPA and its 12 clients are fictional. All data is synthetic.
        </div>
      </div>
    </div>
  );
}

function DemoAccountCard({ account, busy, disabled, onSignIn }: { account: DemoAccount; busy: boolean; disabled: boolean; onSignIn: () => void }) {
  return (
    <div className="group rounded-xl border border-gray-200 bg-white px-4 py-3.5 shadow-card transition-shadow hover:shadow-raised">
      <div className="flex items-start gap-3">
        <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold", ROLE_STYLE[account.role])}>{initials(account.name)}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[14px] font-semibold text-gray-900">{account.name}</span>
            <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", ROLE_STYLE[account.role])}>{ROLE_LABEL[account.role]}</span>
          </div>
          <div className="text-[12px] text-gray-500">{account.title}</div>
          <div className="mt-1 text-[13px] leading-snug text-gray-600">{account.blurb}</div>
        </div>
        <Button data-testid={`demo-login-${account.role}`} onClick={onSignIn} disabled={disabled} className="shrink-0">
          {busy ? <Loader2Icon className="animate-spin" /> : null}
          Sign in as {firstName(account.name)}
        </Button>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg bg-gray-50 px-3 py-1.5 text-[12px]">
        <span className="flex items-center gap-1.5 text-gray-500">
          Email <span className="mono text-gray-800">{account.email}</span>
          <CopyButton value={account.email} label="Copy email" />
        </span>
        <span className="flex items-center gap-1.5 text-gray-500">
          Password <span className="mono text-gray-800">{account.password}</span>
          <CopyButton value={account.password} label="Copy password" />
        </span>
      </div>
    </div>
  );
}

export function LoginPage() {
  const me = useMe();
  const accounts = useDemoAccounts();
  const { login } = useAuthActions();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (me.data) return <Navigate to={from === "/login" ? "/" : from} replace />;

  const doLogin = async (em: string, pw: string, key: string) => {
    setBusy(key);
    setError(null);
    try {
      const u = await login(em, pw);
      toast.success(`Welcome, ${firstName(u.name)}`, { description: `Signed in as ${ROLE_LABEL[u.role]}` });
      navigate(from === "/login" ? "/" : from, { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign in failed");
    } finally {
      setBusy(null);
    }
  };

  const list = [...(accounts.data ?? [])].sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role));

  return (
    <div className="flex min-h-screen bg-background">
      <BrandPanel />
      <div className="flex flex-1 items-center justify-center px-6 py-8">
        <div className="w-full max-w-[520px]">
          <div className="mb-6 flex items-center gap-2.5 lg:hidden">
            <LogoMark className="size-8" />
            <span className="text-lg font-semibold">Tieout</span>
          </div>
          <div className="text-[13px] font-medium text-indigo-700">Harbor &amp; Pine CPA</div>
          <h2 className="mt-1 text-[26px] font-semibold tracking-tight text-gray-900">Sign in to the September close</h2>
          <p className="mt-1 text-[14px] text-gray-500">Pick a demo account to try each role. One click, no typing.</p>

          <div className="mt-5 space-y-3" data-testid="demo-accounts">
            {accounts.isLoading &&
              Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-[132px] rounded-xl" />)}
            {accounts.isError && (
              <Alert tone="warning" title="Demo accounts unavailable">
                The API did not respond. You can still sign in with an email and password below.
              </Alert>
            )}
            {list.map((a) => (
              <DemoAccountCard key={a.email} account={a} busy={busy === a.role} disabled={busy !== null} onSignIn={() => void doLogin(a.email, a.password, a.role)} />
            ))}
          </div>

          <div className="my-5 flex items-center gap-3 text-[12px] text-gray-400">
            <div className="h-px flex-1 bg-gray-200" />
            or sign in with email
            <div className="h-px flex-1 bg-gray-200" />
          </div>

          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void doLogin(email, password, "form");
            }}
          >
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  data-testid="login-email"
                  type="email"
                  autoComplete="username"
                  placeholder="you@harborpine.example"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  data-testid="login-password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
            </div>
            {error && (
              <Alert tone="danger" data-testid="login-error">
                {error}
              </Alert>
            )}
            <Button type="submit" data-testid="login-submit" variant="outline" className="w-full" disabled={busy !== null}>
              {busy === "form" ? <Loader2Icon className="animate-spin" /> : null}
              Sign in
              <ArrowRightIcon />
            </Button>
          </form>

          <div className="mt-6 flex items-center justify-between text-[12px] text-gray-500">
            <Link to="/how-it-works" className="inline-flex items-center gap-1.5 font-medium text-indigo-700 hover:underline">
              <ShieldCheckIcon className="size-3.5" /> Why does this need a sandbox?
            </Link>
            <span>Synthetic data only</span>
          </div>
        </div>
      </div>
    </div>
  );
}
