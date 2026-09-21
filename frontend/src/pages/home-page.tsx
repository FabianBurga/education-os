import { useMemo } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  KeyRound,
  Layers3,
  ShieldCheck,
} from "lucide-react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";

import { useAppContext } from "../app-context";
import { apiFetch } from "../lib/api";
import { canUseMentor } from "../m26/mentor";
import { MentorBriefingPanel } from "./mentor-briefing-page";
import {
  moduleCapabilityState,
  modulesForContext,
} from "../navigation";
import type { Campus } from "../types/bootstrap";
import { Badge } from "../components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
} from "../components/ui/card";

const columnHelper = createColumnHelper<Campus>();

export function HomePage() {
  const { bootstrap } = useAppContext();
  const modules = modulesForContext(bootstrap);

  const campusesQuery = useQuery({
    queryKey: ["campuses"],
    queryFn: () => apiFetch<Campus[]>("/api/v1/campuses"),
  });

  const columns = useMemo(
    () => [
      columnHelper.accessor("name", {
        header: "Campus",
        cell: (info) => (
          <span className="font-semibold text-slate-800">
            {info.getValue()}
          </span>
        ),
      }),
    ],
    [],
  );

  const table = useReactTable({
    data: campusesQuery.data ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  const metrics = [
    {
      label: "Roles activos",
      value: bootstrap.roles.length,
      icon: ShieldCheck,
    },
    {
      label: "Permisos efectivos",
      value: bootstrap.permissions.length,
      icon: KeyRound,
    },
    {
      label: "Módulos visibles",
      value: modules.length,
      icon: Layers3,
    },
    {
      label: "Campus",
      value: campusesQuery.data?.length ?? "—",
      icon: Building2,
    },
  ];

  return (
    <div className="space-y-6" data-testid="unified-home">
      <section className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-500">
            {bootstrap.tenant.organization_name}
          </p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-950">
            {bootstrap.tenant.institution_name}
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">Accede a la información disponible para tu comunidad educativa.</p>
        </div>
        <Badge tone="success">Plataforma lista</Badge>
      </section>

      {canUseMentor(bootstrap.permissions) ? <MentorBriefingPanel /> : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric) => {
          const Icon = metric.icon;
          return (
            <Card key={metric.label}>
              <CardContent className="flex items-center gap-4 p-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-700">
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <div className="text-2xl font-bold text-slate-950">
                    {metric.value}
                  </div>
                  <div className="text-xs font-semibold text-slate-500">
                    {metric.label}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </section>

      <section>
        <div className="mb-3">
          <h2 className="text-lg font-bold text-slate-900">
            Tus espacios de trabajo
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            La navegación se construye con permisos reales, no con menús
            estáticos.
          </p>
        </div>

        {modules.length ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {modules.map((module) => {
              const capability = moduleCapabilityState(
                module,
                bootstrap,
              );
              return (
                <Link
                  key={module.id}
                  to="/workspace/$moduleId"
                  params={{ moduleId: module.id }}
                  className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-bold text-slate-900">
                        {module.label}
                      </div>
                      <div className="mt-1 text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
                        {module.audience}
                      </div>
                    </div>
                    {capability === "disabled" ? (
                      <Badge tone="warning">Vista no disponible</Badge>
                    ) : (
                      <Badge tone="neutral">Disponible</Badge>
                    )}
                  </div>
                  <p className="mt-4 text-sm leading-6 text-slate-600">
                    {module.description}
                  </p>
                  <div className="mt-5 text-sm font-semibold text-slate-900">
                    Abrir espacio →
                  </div>
                </Link>
              );
            })}
          </div>
        ) : (
          <Card>
            <CardContent className="py-10 text-center">
              <p className="font-semibold text-slate-800">
                Tu sesión no tiene módulos de consola asignados.
              </p>
              <p className="mt-2 text-sm text-slate-500">
                El shell puede autenticarte, pero no inventa permisos que el
                backend no haya concedido.
              </p>
            </CardContent>
          </Card>
        )}
      </section>

      <Card>
        <CardHeader>
          <h2 className="text-base font-bold text-slate-900">
            Campus disponibles
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            Consulta los campus disponibles para tu institución.
          </p>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          {campusesQuery.isPending ? (
            <div className="p-5 text-sm text-slate-500">
              Cargando campus…
            </div>
          ) : campusesQuery.isError ? (
            <div className="p-5 text-sm text-rose-700">
              No fue posible cargar los campus.
            </div>
          ) : (
            <table className="w-full min-w-[620px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                {table.getHeaderGroups().map((group) => (
                  <tr key={group.id}>
                    {group.headers.map((header) => (
                      <th key={header.id} className="px-5 py-3">
                        {header.isPlaceholder
                          ? null
                          : flexRender(
                              header.column.columnDef.header,
                              header.getContext(),
                            )}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    className="border-t border-slate-100"
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-5 py-3.5">
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
