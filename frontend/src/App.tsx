/**
 * Root Application - Steps 40-43
 * AI Codebase Assistant v2.0
 */

import { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "react-hot-toast";
import { ThemeProvider } from "@/components/layout/ThemeProvider";
import { AppLayout } from "@/components/layout/AppLayout";
import { useAuthStore } from "@/stores/authStore";

// Lazy-loaded pages
const Login            = lazy(() => import("@/pages/auth/Login"));
const Register         = lazy(() => import("@/pages/auth/Register"));
const Dashboard        = lazy(() => import("@/pages/Dashboard"));
const ProjectWorkspace = lazy(() => import("@/pages/ProjectWorkspace"));
const Analytics        = lazy(() => import("@/pages/Analytics"));
const Settings         = lazy(() => import("@/pages/Settings"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 10 * 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: 0 },
  },
});

function PageLoader() {
  return (
    <div className="flex h-screen items-center justify-center bg-[var(--bg-primary)]">
      <div className="flex flex-col items-center gap-4">
        <div className="w-10 h-10 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
        <p className="text-[var(--text-muted)] text-sm">Loading...</p>
      </div>
    </div>
  );
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore();
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              {/* Public */}
              <Route path="/login"    element={<Login />} />
              <Route path="/register" element={<Register />} />

              {/* Dashboard */}
              <Route
                path="/"
                element={
                  <RequireAuth>
                    <AppLayout><Dashboard /></AppLayout>
                  </RequireAuth>
                }
              />

              {/* Project Workspace — NO AppLayout (full screen workspace) */}
              <Route
                path="/projects/:id"
                element={
                  <RequireAuth>
                    <div className="h-screen overflow-hidden bg-[var(--bg-primary)] text-[var(--text-primary)]">
                      <ProjectWorkspace />
                    </div>
                  </RequireAuth>
                }
              />

              {/* Other pages */}
              <Route
                path="/analytics"
                element={
                  <RequireAuth>
                    <AppLayout><Analytics /></AppLayout>
                  </RequireAuth>
                }
              />
              <Route
                path="/settings"
                element={
                  <RequireAuth>
                    <AppLayout><Settings /></AppLayout>
                  </RequireAuth>
                }
              />

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>

        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: "var(--bg-secondary)",
              color: "var(--text-primary)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              fontSize: "13px",
            },
            success: { iconTheme: { primary: "#10B981", secondary: "#fff" } },
            error:   { iconTheme: { primary: "#EF4444", secondary: "#fff" } },
          }}
        />
      </ThemeProvider>
    </QueryClientProvider>
  );
}