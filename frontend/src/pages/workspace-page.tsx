import { ExternalLink, ShieldAlert } from "lucide-react";

import { useAppContext } from "../app-context";
import {
  findModule,
  moduleCapabilityState,
  modulesForContext,
} from "../navigation";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
} from "../components/ui/card";

export function WorkspacePage({
  moduleId,
}: {
  moduleId: string;
}) {
  const { bootstrap } = useAppContext();
  const module = findModule(moduleId);
  const allowedIds = new Set(
    modulesForContext(bootstrap).map((item) => item.id),
  );

  if (!module || !allowedIds.has(module.id)) {
    return (
      <Card>
        <CardContent className="flex min-h-64 flex-col items-center justify-center text-center">
          <ShieldAlert className="h-10 w-10 text-rose-500" />
          <h1 className="mt-4 text-xl font-bold text-slate-900">
            Espacio no disponible
          </h1>
          <p className="mt-2 max-w-lg text-sm leading-6 text-slate-500">
            El frontend no mostrará un módulo si tu contexto autenticado no
            tiene su permiso de acceso.
          </p>
        </CardContent>
      </Card>
    );
  }

  const capability = moduleCapabilityState(module, bootstrap);

  const legacyPath = module.legacyPath;

  function openLegacy() {
    window.location.assign(legacyPath);
  }

  return (
    <div className="space-y-5" data-testid={`workspace-${module.id}`}>
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="neutral">{module.audience}</Badge>
          {capability === "disabled" ? (
            <Badge tone="warning">Capability deshabilitada</Badge>
          ) : null}
        </div>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-950">
          {module.label}
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          {module.description}
        </p>
      </div>

      <Card>
        <CardHeader>
          <h2 className="text-base font-bold text-slate-900">
            Vista unificada de {module.label}
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            M15 establece el shell, navegación, identidad visual y contexto de
            permisos. La migración funcional completa de cada consola se hará
            progresivamente sin reescribir sus reglas de backend.
          </p>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl bg-slate-50 p-4">
              <div className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
                Permiso que habilita este espacio
              </div>
              <div className="mt-2 font-mono text-sm text-slate-700">
                {module.permission}
              </div>
            </div>
            <div className="rounded-xl bg-slate-50 p-4">
              <div className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
                Estado de transición
              </div>
              <div className="mt-2 text-sm font-semibold text-slate-700">
                Shell React activo · consola heredada preservada
              </div>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button
              onClick={openLegacy}
              className="gap-2"
              data-testid={`legacy-${module.id}`}
            >
              Abrir consola operativa actual
              <ExternalLink className="h-4 w-4" />
            </Button>
            <p className="max-w-2xl text-xs leading-5 text-slate-500">
              El token unificado se refleja temporalmente en las claves de
              sessionStorage usadas por las consolas M8–M14 para mantener la
              compatibilidad durante la transición.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
