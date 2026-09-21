import type { ReactNode } from "react";
import {
  BellRing,
  Building2,
  Cable,
  ClipboardList,
  Bot,
  GraduationCap,
  Home,
  Landmark,
  LogOut,
  Megaphone,
  Shield,
  Users,
  WalletCards,
} from "lucide-react";
import { Link } from "@tanstack/react-router";

import { useAppContext } from "../../app-context";
import {
  moduleCapabilityState,
  modulesForContext,
  type ModuleDefinition,
} from "../../navigation";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";

function institutionTypeLabel(value: string) {
  return { PRIVATE: "Privado", PUBLIC: "Público", FISCOMISIONAL: "Fiscomisional", MUNICIPAL: "Municipal" }[value] ?? value;
}

const icons: Record<string, typeof Home> = {
  integrations: Cable,
  administration: Shield,
  coordination: Landmark,
  teacher: GraduationCap,
  student: GraduationCap,
  guardian: Users,
  communications: Megaphone,
  finance: WalletCards,
};

function ModuleLink({ module }: { module: ModuleDefinition }) {
  const { bootstrap } = useAppContext();
  const Icon = icons[module.id] ?? Building2;
  const capability = moduleCapabilityState(module, bootstrap);

  return (
    <Link
      to="/workspace/$moduleId"
      params={{ moduleId: module.id }}
      className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
      activeProps={{
        className:
          "flex items-center gap-3 rounded-xl bg-slate-900 px-3 py-2.5 text-sm font-semibold text-white",
      }}
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span className="min-w-0 flex-1 truncate">{module.shortLabel}</span>
      {capability === "disabled" ? (
        <span className="h-2 w-2 rounded-full bg-amber-400" title="Vista no disponible" />
      ) : null}
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { bootstrap, signOut } = useAppContext();
  const modules = modulesForContext(bootstrap);
  const canReadM21Suggestions = bootstrap.permissions.includes(
    "intervention.suggestion.read",
  );

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/90 backdrop-blur md:hidden">
        <div className="flex items-center justify-between gap-3 px-4 py-3">
          <div>
            <div className="text-sm font-bold text-slate-900">Education OS</div>
            <div className="max-w-[220px] truncate text-xs text-slate-500">
              {bootstrap.tenant.institution_name}
            </div>
          </div>
          <Button variant="ghost" className="h-9 px-3" onClick={signOut}>
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
        <nav className="flex gap-2 overflow-x-auto px-4 pb-3">
          <Link
            to="/"
            className="whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700"
          >
            Inicio
          </Link>
          {modules.map((module) => (
            <Link
              key={module.id}
              to="/workspace/$moduleId"
              params={{ moduleId: module.id }}
              className="whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700"
            >
              {module.shortLabel}
            </Link>
          ))}
          {canReadM21Suggestions ? (
            <Link
              to="/m21/suggestions"
              className="whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700"
            >
              Sugerencias
            </Link>
          ) : null}
          {bootstrap.permissions.includes("copilot.use") ? (
            <Link to="/copilot" className="whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700">Copiloto</Link>
          ) : null}
        </nav>
      </header>

      <div className="mx-auto grid min-h-screen max-w-[1680px] md:grid-cols-[270px_minmax(0,1fr)]">
        <aside className="sticky top-0 hidden h-screen border-r border-slate-200 bg-white p-4 md:flex md:flex-col">
          <div className="flex items-center gap-3 px-2 py-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-900 text-white">
              <Building2 className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="font-bold text-slate-900">Education OS</div>
              <div className="truncate text-xs text-slate-500">
                Plataforma educativa
              </div>
            </div>
          </div>

          <div className="mt-5 px-2">
            <div className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400">
              Institución activa
            </div>
            <div className="mt-2 truncate text-sm font-semibold text-slate-800">
              {bootstrap.tenant.institution_name}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {institutionTypeLabel(bootstrap.tenant.institution_type)}
            </div>
          </div>

          <nav className="mt-6 flex-1 space-y-1 overflow-y-auto">
            <Link
              to="/"
              className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
              activeOptions={{ exact: true }}
              activeProps={{
                className:
                  "flex items-center gap-3 rounded-xl bg-slate-900 px-3 py-2.5 text-sm font-semibold text-white",
              }}
            >
              <Home className="h-4 w-4" />
              Inicio
            </Link>

            {modules.map((module) => (
              <ModuleLink key={module.id} module={module} />
            ))}

            {canReadM21Suggestions ? (
              <Link
                to="/m21/suggestions"
                className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
                activeProps={{
                  className:
                    "flex items-center gap-3 rounded-xl bg-slate-900 px-3 py-2.5 text-sm font-semibold text-white",
                }}
              >
                <ClipboardList className="h-4 w-4" />
                Sugerencias de seguimiento
              </Link>
            ) : null}

            {bootstrap.permissions.includes("copilot.use") ? (
              <Link to="/copilot" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900" activeProps={{className:"flex items-center gap-3 rounded-xl bg-slate-900 px-3 py-2.5 text-sm font-semibold text-white"}}>
                <Bot className="h-4 w-4" />
                Copiloto gobernado
              </Link>
            ) : null}

            <Link
              to="/context"
              className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
              activeProps={{
                className:
                  "flex items-center gap-3 rounded-xl bg-slate-900 px-3 py-2.5 text-sm font-semibold text-white",
              }}
            >
              <BellRing className="h-4 w-4" />
              Mi contexto
            </Link>
          </nav>

          <div className="border-t border-slate-100 pt-4">
            <div className="px-2">
              <div className="truncate text-sm font-semibold text-slate-800">
                {bootstrap.user.display_name}
              </div>
            </div>
            <Button
              variant="ghost"
              className="mt-3 w-full justify-start gap-2"
              onClick={signOut}
            >
              <LogOut className="h-4 w-4" />
              Cerrar sesión
            </Button>
          </div>
        </aside>

        <main className="min-w-0 p-4 sm:p-6 lg:p-8">{children}</main>
      </div>

      <div className="fixed bottom-4 right-4 hidden md:block">
        <Badge tone="success">Plataforma lista</Badge>
      </div>
    </div>
  );
}
