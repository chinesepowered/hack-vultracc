import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router";
import { Toaster } from "sonner";
import { ApiError } from "@/api";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppShell, PublicShell } from "@/components/layout/AppShell";
import { FullPageLoader } from "@/components/layout/FullPageLoader";
import { useMe } from "@/hooks/queries";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { RunPage } from "@/pages/RunPage";
import { AdminPage } from "@/pages/AdminPage";
import { HowItWorksPage } from "@/pages/HowItWorksPage";
import { NotFoundPage } from "@/pages/NotFoundPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 5_000,
      retry: (count, err) => !(err instanceof ApiError && [400, 401, 403, 404, 409].includes(err.status)) && count < 2,
    },
  },
});

function RequireAuth({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const location = useLocation();
  if (me.isLoading) return <FullPageLoader />;
  if (!me.data) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <>{children}</>;
}

function HowItWorksRoute() {
  const me = useMe();
  if (me.isLoading) return <FullPageLoader />;
  if (me.data) {
    return (
      <AppShell>
        <HowItWorksPage />
      </AppShell>
    );
  }
  return (
    <PublicShell>
      <HowItWorksPage />
    </PublicShell>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/how-it-works" element={<HowItWorksRoute />} />
            <Route
              path="/*"
              element={
                <RequireAuth>
                  <AppShell>
                    <Routes>
                      <Route index element={<DashboardPage />} />
                      <Route path="runs/:id" element={<RunPage />} />
                      <Route path="admin" element={<AdminPage />} />
                      <Route path="*" element={<NotFoundPage />} />
                    </Routes>
                  </AppShell>
                </RequireAuth>
              }
            />
          </Routes>
        </BrowserRouter>
        <Toaster position="bottom-right" richColors closeButton toastOptions={{ className: "font-sans text-[13px]" }} />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
