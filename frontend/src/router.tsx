import { useMemo, useState } from "react";
import {
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { AppContextProvider } from "./app-context";
import { TokenGate } from "./components/auth/token-gate";
import { AppShell } from "./components/layout/app-shell";
import { ApiError, apiFetch } from "./lib/api";
import {
  clearAccessToken,
  readAccessToken,
  saveAccessToken,
} from "./lib/session";
import { ContextPage } from "./pages/context-page";
import { HomePage } from "./pages/home-page";
import { WorkspacePage } from "./pages/workspace-page";
import type { UiBootstrap } from "./types/bootstrap";

function RootLayout() {
  const queryClient = useQueryClient();
  const [authRevision, setAuthRevision] = useState(0);
  const token = readAccessToken();

  const bootstrapQuery = useQuery({
    queryKey: ["ui-bootstrap", token, authRevision],
    queryFn: () => apiFetch<UiBootstrap>("/api/v1/ui/bootstrap"),
    enabled: Boolean(token),
    retry: false,
  });

  function submitToken(nextToken: string) {
    saveAccessToken(nextToken);
    queryClient.clear();
    setAuthRevision((value) => value + 1);
  }

  function signOut() {
    clearAccessToken();
    queryClient.clear();
    setAuthRevision((value) => value + 1);
  }

  const errorMessage = useMemo(() => {
    if (!bootstrapQuery.error) {
      return undefined;
    }
    if (bootstrapQuery.error instanceof ApiError) {
      if (
        bootstrapQuery.error.status === 401 ||
        bootstrapQuery.error.status === 403
      ) {
        return "El token no tiene un contexto válido para Education OS.";
      }
      return `No fue posible iniciar la sesión: ${bootstrapQuery.error.message}`;
    }
    return "No fue posible iniciar la sesión.";
  }, [bootstrapQuery.error]);

  if (!token || bootstrapQuery.isError) {
    return (
      <TokenGate
        initialToken={token}
        errorMessage={errorMessage}
        onSubmit={submitToken}
      />
    );
  }

  if (bootstrapQuery.isPending || !bootstrapQuery.data) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="rounded-2xl border border-slate-200 bg-white px-6 py-5 text-sm font-semibold text-slate-600 shadow-sm">
          Cargando contexto institucional…
        </div>
      </main>
    );
  }

  return (
    <AppContextProvider
      value={{
        bootstrap: bootstrapQuery.data,
        signOut,
      }}
    >
      <AppShell>
        <Outlet />
      </AppShell>
    </AppContextProvider>
  );
}

const rootRoute = createRootRoute({
  component: RootLayout,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: HomePage,
});

const contextRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/context",
  component: ContextPage,
});

const workspaceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/workspace/$moduleId",
  component: WorkspaceRouteComponent,
});

function WorkspaceRouteComponent() {
  const { moduleId } = workspaceRoute.useParams();
  return <WorkspacePage moduleId={moduleId} />;
}

const routeTree = rootRoute.addChildren([
  indexRoute,
  contextRoute,
  workspaceRoute,
]);

export const router = createRouter({
  routeTree,
  basepath: "/app",
  defaultPreload: "intent",
  defaultPreloadStaleTime: 0,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
