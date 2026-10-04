import { ExternalLink, RefreshCw, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { ApiError } from "../lib/api";
import {
  teacherContinuityQuery,
  type TeacherContinuityItem,
} from "./teacher-continuity";

function formatDueAt(value: string | null): string {
  if (!value) return "Sin fecha límite";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Fecha no disponible";
  return date.toLocaleString();
}

function sourceLabel(item: TeacherContinuityItem): string {
  return item.source_domain === "M21" ? "Seguimiento M21" : "Obligación M27";
}

export function appDeepLink(path: string): string {
  return path.startsWith("/app/") ? path : `/app${path}`;
}

function stateLabel(state: string): string {
  const labels: Record<string, string> = {
    OPEN: "Abierto",
    IN_PROGRESS: "En curso",
    MONITORING: "En seguimiento",
    OVERDUE: "Vencido",
    PENDING: "Pendiente",
    ACTIVE: "Activo",
    VOIDED: "Anulado",
    SUPERSEDED: "Reemplazado",
  };
  return labels[state] ?? state;
}

function ContinuityRow({ item }: { item: TeacherContinuityItem }) {
  const studentLabel = item.student_profile_id
    ? `Estudiante ${item.student_profile_id.slice(0, 8)}`
    : "Estudiante no especificado";
  return (
    <li
      className="rounded-xl border border-slate-200 p-4"
      data-testid="continuity-item"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">{sourceLabel(item)}</Badge>
            <Badge tone={item.source_state === "OVERDUE" ? "warning" : "neutral"}>
              {stateLabel(item.source_state)}
            </Badge>
          </div>
          <h3 className="mt-2 truncate font-bold text-slate-900">
            {studentLabel}
          </h3>
          <p className="mt-1 text-sm text-slate-600">{item.kind}</p>
        </div>
        <a
          href={appDeepLink(item.deep_link)}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm font-semibold text-slate-700 hover:bg-slate-100"
          data-testid="continuity-deep-link"
        >
          Abrir fuente
          <ExternalLink className="h-4 w-4" />
        </a>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-500">
        <span>Próximo vencimiento: {formatDueAt(item.due_at)}</span>
        {item.family_acknowledgement_indicator ? (
          <Badge tone="success">Familia reconoció</Badge>
        ) : null}
      </div>
    </li>
  );
}

export function TeacherContinuityPage() {
  const [items, setItems] = useState<TeacherContinuityItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const page = await teacherContinuityQuery({ limit: 25 });
      setItems(page.items);
      setHasMore(page.has_more);
    } catch (reason) {
      if (
        reason instanceof ApiError &&
        (reason.status === 401 || reason.status === 403)
      ) {
        setError("Esta vista no está disponible para el contexto actual.");
      } else {
        setError("No fue posible cargar la continuidad docente.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card data-testid="teacher-continuity">
      <CardHeader className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Badge tone="neutral">M29 · Continuidad</Badge>
          <h2 className="mt-2 text-xl font-bold">Mi continuidad</h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Seguimientos autorizados que requieren tu atención. Las acciones se realizan en su fuente institucional.
          </p>
        </div>
        <Button
          variant="secondary"
          className="gap-2"
          onClick={() => void load()}
          disabled={loading}
          data-testid="teacher-continuity-refresh"
        >
          <RefreshCw className="h-4 w-4" />
          Actualizar
        </Button>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="py-8 text-center text-sm text-slate-500" role="status">
            Cargando continuidad…
          </div>
        ) : error ? (
          <div
            className="flex items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
            role="alert"
          >
            <ShieldAlert className="h-5 w-5 shrink-0" />
            <span>{error}</span>
          </div>
        ) : items.length === 0 ? (
          <div
            className="py-8 text-center text-sm text-slate-500"
            data-testid="teacher-continuity-empty"
          >
            No hay seguimientos autorizados pendientes de atención.
          </div>
        ) : (
          <>
            <ul className="space-y-3">
              {items.map((item) => (
                <ContinuityRow
                  key={`${item.source_domain}:${item.source_id}`}
                  item={item}
                />
              ))}
            </ul>
            {hasMore ? (
              <p className="mt-4 text-center text-xs text-slate-500">
                Se muestran los primeros 25 elementos autorizados.
              </p>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
