import {
  CheckCircle2,
  ClipboardList,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  XCircle,
} from "lucide-react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { useAppContext } from "../app-context";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
} from "../components/ui/card";
import { ApiError } from "../lib/api";
import {
  isSuggestionReviewable,
  listSuggestions,
  refreshSuggestions,
  reviewNoteError,
  reviewSuggestion,
  suggestionCapabilities,
  suggestionSensitivityTone,
  suggestionSeverityTone,
  suggestionStatusTone,
  type InterventionSuggestion,
  type SuggestionFilters,
  type SuggestionReviewAction,
  type SuggestionSensitivity,
  type SuggestionSeverity,
  type SuggestionStatus,
} from "../m21/suggestions";

const statusLabels: Record<SuggestionStatus, string> = {
  PENDING: "Pendiente",
  ACCEPTED: "Aceptada",
  DISMISSED: "Descartada",
  EXPIRED: "Expirada",
};

const severityLabels: Record<SuggestionSeverity, string> = {
  LOW: "Baja",
  MEDIUM: "Media",
  HIGH: "Alta",
  CRITICAL: "Crítica",
};

const sensitivityLabels: Record<SuggestionSensitivity, string> = {
  GENERAL: "General",
  RESTRICTED: "Restringida",
  CONFIDENTIAL: "Confidencial",
};

function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("es-EC", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "No fue posible completar la operación.";
}

function SuggestionBadges({
  suggestion,
}: {
  suggestion: InterventionSuggestion;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <Badge tone={suggestionStatusTone(suggestion.status)}>
        {statusLabels[suggestion.status]}
      </Badge>
      <Badge tone={suggestionSeverityTone(suggestion.severity)}>
        Severidad {severityLabels[suggestion.severity]}
      </Badge>
      <Badge
        tone={suggestionSensitivityTone(suggestion.sensitivity)}
      >
        {sensitivityLabels[suggestion.sensitivity]}
      </Badge>
    </div>
  );
}

function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: number;
  detail: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs font-bold uppercase tracking-wide text-slate-400">
          {label}
        </div>
        <div className="mt-2 text-2xl font-bold text-slate-900">
          {value}
        </div>
        <div className="mt-1 text-xs text-slate-500">
          {detail}
        </div>
      </CardContent>
    </Card>
  );
}

export function SuggestionInboxPage() {
  const { bootstrap } = useAppContext();
  const queryClient = useQueryClient();
  const capabilities = suggestionCapabilities(
    bootstrap.permissions,
  );

  const [filters, setFilters] = useState<SuggestionFilters>({
    status: "PENDING",
    severity: "",
    sensitivity: "",
    studentProfileId: "",
  });
  const [selectedId, setSelectedId] = useState<string | null>(
    null,
  );
  const [reviewNote, setReviewNote] = useState("");

  const suggestionsQuery = useQuery({
    queryKey: ["m21-suggestions", filters],
    queryFn: () => listSuggestions(filters),
    enabled: capabilities.canRead,
    retry: false,
  });

  const refreshMutation = useMutation({
    mutationFn: refreshSuggestions,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["m21-suggestions"],
      });
    },
  });

  const reviewMutation = useMutation({
    mutationFn: ({
      suggestionId,
      action,
      note,
    }: {
      suggestionId: string;
      action: SuggestionReviewAction;
      note: string;
    }) => reviewSuggestion(suggestionId, action, note),
    onSuccess: async () => {
      setReviewNote("");
      await queryClient.invalidateQueries({
        queryKey: ["m21-suggestions"],
      });
    },
  });

  const items = suggestionsQuery.data?.items ?? [];
  const selected =
    items.find((item) => item.id === selectedId) ??
    items[0] ??
    null;

  const metrics = useMemo(() => {
    return {
      visible: items.length,
      pending: items.filter((item) => item.status === "PENDING")
        .length,
      high: items.filter(
        (item) =>
          item.severity === "HIGH" ||
          item.severity === "CRITICAL",
      ).length,
      protected: items.filter(
        (item) =>
          item.sensitivity === "RESTRICTED" ||
          item.sensitivity === "CONFIDENTIAL",
      ).length,
    };
  }, [items]);

  function updateFilter<K extends keyof SuggestionFilters>(
    key: K,
    value: SuggestionFilters[K],
  ) {
    setSelectedId(null);
    setFilters((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function submitReview(action: SuggestionReviewAction) {
    if (!selected) {
      return;
    }
    const noteError = reviewNoteError(reviewNote);
    if (noteError) {
      return;
    }
    reviewMutation.mutate({
      suggestionId: selected.id,
      action,
      note: reviewNote,
    });
  }

  if (!capabilities.canRead) {
    return (
      <Card>
        <CardContent className="flex min-h-72 flex-col items-center justify-center p-6 text-center">
          <ShieldAlert className="h-11 w-11 text-rose-500" />
          <h1 className="mt-4 text-xl font-bold text-slate-900">
            Bandeja no disponible
          </h1>
          <p className="mt-2 max-w-xl text-sm text-slate-500">
            Tu contexto autenticado no posee el permiso
            intervention.suggestion.read. La autorización efectiva
            continúa siendo aplicada por API y PostgreSQL RLS.
          </p>
        </CardContent>
      </Card>
    );
  }

  const noteError = reviewNoteError(reviewNote);
  const canReviewSelected =
    Boolean(selected) &&
    capabilities.canReview &&
    selected !== null &&
    isSuggestionReviewable(selected.status);

  return (
    <div
      className="space-y-5"
      data-testid="m21-suggestion-inbox"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap gap-2">
            <Badge tone="success">M21 · Revisión humana</Badge>
            <Badge tone="neutral">
              Motor determinístico
            </Badge>
          </div>
          <h1 className="mt-3 text-3xl font-bold text-slate-900">
            Bandeja de sugerencias
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Revisa evidencia institucional antes de decidir. Una
            sugerencia nunca se convierte por sí sola en una
            intervención.
          </p>
        </div>

        {capabilities.canGenerate ? (
          <Button
            variant="secondary"
            className="gap-2 self-start"
            disabled={refreshMutation.isPending}
            onClick={() => refreshMutation.mutate()}
            data-testid="m21-refresh-suggestions"
          >
            <RefreshCw
              className={
                refreshMutation.isPending
                  ? "h-4 w-4 animate-spin"
                  : "h-4 w-4"
              }
            />
            {refreshMutation.isPending
              ? "Actualizando…"
              : "Actualizar sugerencias"}
          </Button>
        ) : null}
      </div>

      {refreshMutation.data ? (
        <Card>
          <CardContent className="flex flex-wrap gap-x-6 gap-y-2 p-4 text-sm">
            <span>
              Generadas:{" "}
              <strong>{refreshMutation.data.generated}</strong>
            </span>
            <span>
              Actualizadas:{" "}
              <strong>{refreshMutation.data.refreshed}</strong>
            </span>
            <span>
              Expiradas:{" "}
              <strong>{refreshMutation.data.expired}</strong>
            </span>
            <span>
              Pendientes:{" "}
              <strong>{refreshMutation.data.pending}</strong>
            </span>
          </CardContent>
        </Card>
      ) : null}

      {refreshMutation.isError ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm font-medium text-rose-700">
          {errorMessage(refreshMutation.error)}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Visibles"
          value={metrics.visible}
          detail="Resultado del filtro actual"
        />
        <MetricCard
          label="Pendientes"
          value={metrics.pending}
          detail="Requieren revisión humana"
        />
        <MetricCard
          label="Alta prioridad"
          value={metrics.high}
          detail="Alta o crítica"
        />
        <MetricCard
          label="Protegidas"
          value={metrics.protected}
          detail="Restringidas o confidenciales"
        />
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <ClipboardList className="h-5 w-5 text-slate-500" />
            <h2 className="font-bold text-slate-900">
              Filtros operativos
            </h2>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <label className="space-y-1 text-sm font-semibold text-slate-700">
              <span>Estado</span>
              <select
                value={filters.status ?? ""}
                onChange={(event) =>
                  updateFilter(
                    "status",
                    event.target.value as SuggestionStatus | "",
                  )
                }
                className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium outline-none focus:border-slate-400"
              >
                <option value="">Todos</option>
                <option value="PENDING">Pendientes</option>
                <option value="ACCEPTED">Aceptadas</option>
                <option value="DISMISSED">Descartadas</option>
                <option value="EXPIRED">Expiradas</option>
              </select>
            </label>

            <label className="space-y-1 text-sm font-semibold text-slate-700">
              <span>Severidad</span>
              <select
                value={filters.severity ?? ""}
                onChange={(event) =>
                  updateFilter(
                    "severity",
                    event.target.value as
                      | SuggestionSeverity
                      | "",
                  )
                }
                className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium outline-none focus:border-slate-400"
              >
                <option value="">Todas</option>
                <option value="LOW">Baja</option>
                <option value="MEDIUM">Media</option>
                <option value="HIGH">Alta</option>
                <option value="CRITICAL">Crítica</option>
              </select>
            </label>

            <label className="space-y-1 text-sm font-semibold text-slate-700">
              <span>Sensibilidad</span>
              <select
                value={filters.sensitivity ?? ""}
                onChange={(event) =>
                  updateFilter(
                    "sensitivity",
                    event.target.value as
                      | SuggestionSensitivity
                      | "",
                  )
                }
                className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium outline-none focus:border-slate-400"
              >
                <option value="">Todas</option>
                <option value="GENERAL">General</option>
                <option value="RESTRICTED">Restringida</option>
                <option value="CONFIDENTIAL">
                  Confidencial
                </option>
              </select>
            </label>

            <label className="space-y-1 text-sm font-semibold text-slate-700">
              <span>ID de estudiante</span>
              <input
                value={filters.studentProfileId ?? ""}
                onChange={(event) =>
                  updateFilter(
                    "studentProfileId",
                    event.target.value,
                  )
                }
                placeholder="UUID opcional"
                className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
              />
            </label>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
        <Card>
          <CardHeader>
            <h2 className="font-bold text-slate-900">
              Sugerencias visibles
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              La lista ya viene filtrada por permisos y RLS del
              servidor.
            </p>
          </CardHeader>
          <CardContent>
            {suggestionsQuery.isPending ? (
              <div className="py-12 text-center text-sm text-slate-500">
                Cargando sugerencias…
              </div>
            ) : null}

            {suggestionsQuery.isError ? (
              <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm font-medium text-rose-700">
                {errorMessage(suggestionsQuery.error)}
              </div>
            ) : null}

            {!suggestionsQuery.isPending &&
            !suggestionsQuery.isError &&
            items.length === 0 ? (
              <div className="flex min-h-52 flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center">
                <Sparkles className="h-9 w-9 text-slate-400" />
                <div className="mt-3 font-bold text-slate-800">
                  No hay sugerencias para este filtro
                </div>
                <div className="mt-1 max-w-md text-sm text-slate-500">
                  Ajusta los filtros o actualiza el motor si tienes
                  permiso para generar sugerencias.
                </div>
              </div>
            ) : null}

            <div className="space-y-3">
              {items.map((suggestion) => {
                const active = selected?.id === suggestion.id;
                return (
                  <button
                    key={suggestion.id}
                    type="button"
                    onClick={() => setSelectedId(suggestion.id)}
                    aria-pressed={active}
                    className={
                      "w-full rounded-2xl border p-4 text-left transition " +
                      (active
                        ? "border-slate-900 bg-slate-50 shadow-sm"
                        : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50")
                    }
                  >
                    <SuggestionBadges suggestion={suggestion} />
                    <div className="mt-3 font-bold text-slate-900">
                      {suggestion.title}
                    </div>
                    <div className="mt-2 line-clamp-2 text-sm text-slate-600">
                      {suggestion.rationale_summary}
                    </div>
                    <div className="mt-3 grid gap-1 text-xs text-slate-500 sm:grid-cols-2">
                      <span>
                        Regla:{" "}
                        <strong>{suggestion.rule_key}</strong>
                      </span>
                      <span className="truncate">
                        Estudiante:{" "}
                        <strong>
                          {suggestion.student_profile_id}
                        </strong>
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="font-bold text-slate-900">
              Revisión de sugerencia
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Evidencia y decisión humana.
            </p>
          </CardHeader>
          <CardContent>
            {!selected ? (
              <div className="py-12 text-center text-sm text-slate-500">
                Selecciona una sugerencia para revisar su detalle.
              </div>
            ) : (
              <div className="space-y-5">
                <SuggestionBadges suggestion={selected} />

                <div>
                  <h3 className="text-lg font-bold text-slate-900">
                    {selected.title}
                  </h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    {selected.rationale_summary}
                  </p>
                </div>

                <dl className="grid gap-3 rounded-2xl bg-slate-50 p-4 text-sm">
                  <div>
                    <dt className="text-xs font-bold uppercase text-slate-400">
                      Intervención recomendada
                    </dt>
                    <dd className="mt-1 font-semibold text-slate-800">
                      {selected.recommended_intervention_type}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs font-bold uppercase text-slate-400">
                      Estudiante
                    </dt>
                    <dd className="mt-1 break-all font-mono text-xs text-slate-700">
                      {selected.student_profile_id}
                    </dd>
                  </div>
                  <div>
                    <Link
                      to="/m21/students/$studentProfileId"
                      params={{
                        studentProfileId:
                          selected.student_profile_id,
                      }}
                      className="inline-flex h-9 items-center justify-center rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-800 transition hover:bg-slate-100"
                      data-testid="m21-open-student-360"
                    >
                      Abrir Student 360
                    </Link>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <dt className="text-xs font-bold uppercase text-slate-400">
                        Generada
                      </dt>
                      <dd className="mt-1 text-slate-700">
                        {formatDate(selected.generated_at)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-bold uppercase text-slate-400">
                        Última señal
                      </dt>
                      <dd className="mt-1 text-slate-700">
                        {formatDate(selected.last_seen_at)}
                      </dd>
                    </div>
                  </div>
                </dl>

                <div>
                  <div className="text-xs font-bold uppercase tracking-wide text-slate-400">
                    Evidencia referenciada
                  </div>
                  <div className="mt-2 space-y-2">
                    {selected.evidence.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-slate-200 p-3 text-sm text-slate-500">
                        Sin referencias de evidencia visibles.
                      </div>
                    ) : (
                      selected.evidence.map((evidence) => (
                        <div
                          key={evidence.id}
                          className="rounded-xl border border-slate-200 p-3"
                        >
                          <div className="text-xs font-bold text-slate-700">
                            {evidence.evidence_type}
                          </div>
                          <div className="mt-1 break-all font-mono text-[11px] text-slate-500">
                            {evidence.evidence_id}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {selected.review_note ? (
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <div className="text-xs font-bold uppercase text-slate-400">
                      Nota de revisión registrada
                    </div>
                    <div className="mt-2 text-sm text-slate-700">
                      {selected.review_note}
                    </div>
                  </div>
                ) : null}

                {selected.accepted_intervention_id ? (
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
                    <div>
                      Intervención creada:{" "}
                      <span className="break-all font-mono text-xs">
                        {selected.accepted_intervention_id}
                      </span>
                    </div>
                    <Link
                      to="/m21/interventions/$interventionId"
                      params={{
                        interventionId:
                          selected.accepted_intervention_id,
                      }}
                      className="mt-3 inline-flex h-8 items-center justify-center rounded-lg border border-emerald-200 bg-white px-3 text-xs font-semibold text-emerald-800 transition hover:bg-emerald-100"
                    >
                      Abrir espacio de intervención
                    </Link>
                  </div>
                ) : null}

                {canReviewSelected ? (
                  <div className="space-y-3 border-t border-slate-100 pt-4">
                    <label className="block text-sm font-semibold text-slate-700">
                      Nota de revisión humana
                      <textarea
                        value={reviewNote}
                        maxLength={1000}
                        onChange={(event) =>
                          setReviewNote(event.target.value)
                        }
                        placeholder="Documenta brevemente el criterio de revisión."
                        className="mt-2 min-h-28 w-full resize-y rounded-xl border border-slate-200 bg-white p-3 text-sm font-normal outline-none focus:border-slate-400"
                      />
                    </label>

                    <div className="flex items-center justify-between gap-3 text-xs text-slate-500">
                      <span>
                        {reviewNote.trim().length}/1000
                      </span>
                      {reviewNote.length > 0 && noteError ? (
                        <span className="font-semibold text-rose-600">
                          {noteError}
                        </span>
                      ) : null}
                    </div>

                    {reviewMutation.isError ? (
                      <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm font-medium text-rose-700">
                        {errorMessage(reviewMutation.error)}
                      </div>
                    ) : null}

                    <div className="grid gap-2 sm:grid-cols-2">
                      <Button
                        className="gap-2"
                        disabled={
                          Boolean(noteError) ||
                          reviewMutation.isPending
                        }
                        onClick={() => submitReview("accept")}
                        data-testid="m21-accept-suggestion"
                      >
                        <CheckCircle2 className="h-4 w-4" />
                        Aceptar
                      </Button>
                      <Button
                        variant="danger"
                        className="gap-2"
                        disabled={
                          Boolean(noteError) ||
                          reviewMutation.isPending
                        }
                        onClick={() => submitReview("dismiss")}
                        data-testid="m21-dismiss-suggestion"
                      >
                        <XCircle className="h-4 w-4" />
                        Descartar
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                    {selected.status !== "PENDING"
                      ? "Esta sugerencia ya no está pendiente de revisión."
                      : "Tu contexto puede consultar esta sugerencia, pero no revisarla."}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
