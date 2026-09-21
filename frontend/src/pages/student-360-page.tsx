import {
  Activity,
  ArrowLeft,
  BookOpenCheck,
  Clock3,
  ShieldAlert,
  Sparkles,
  UserRoundSearch,
} from "lucide-react";
import {
  useInfiniteQuery,
  useQuery,
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
  getStudentInterventions,
  getStudentTimeline,
  student360Capabilities,
  timelineCategoryTone,
  timelineSensitivityTone,
  type TimelineCategory,
  type TimelineSensitivity,
} from "../m21/student-360";
import { listSuggestions } from "../m21/suggestions";

const categoryLabels: Record<TimelineCategory, string> = {
  ENROLLMENT: "Matrícula",
  ATTENDANCE: "Asistencia",
  ACADEMIC: "Académico",
  SIGNAL: "Señal",
  INTERVENTION: "Intervención",
  ACTION: "Acción",
  FOLLOW_UP: "Seguimiento",
  COMMUNICATION: "Comunicación",
  OUTCOME: "Resultado",
  SYSTEM: "Sistema",
};

const sensitivityLabels: Record<TimelineSensitivity, string> = {
  GENERAL: "General",
  RESTRICTED: "Restringida",
  CONFIDENTIAL: "Confidencial",
};

function formatDate(value: string): string {
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
  return "No fue posible cargar Student 360.";
}

function Metric({
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

export function Student360Page({
  studentProfileId,
}: {
  studentProfileId: string;
}) {
  const { bootstrap } = useAppContext();
  const capabilities = student360Capabilities(
    bootstrap.permissions,
  );
  const [category, setCategory] = useState<
    TimelineCategory | ""
  >("");
  const [sensitivity, setSensitivity] = useState<
    TimelineSensitivity | ""
  >("");

  const timelineQuery = useInfiniteQuery({
    queryKey: [
      "m21-student-timeline",
      studentProfileId,
      category,
      sensitivity,
    ],
    queryFn: ({ pageParam }) =>
      getStudentTimeline(studentProfileId, {
        category,
        sensitivity,
        beforePosition: pageParam,
      }),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.next_before_position ?? undefined,
    enabled: capabilities.canReadTimeline,
    retry: false,
  });

  const interventionsQuery = useQuery({
    queryKey: ["m21-student-interventions", studentProfileId],
    queryFn: () => getStudentInterventions(studentProfileId),
    enabled: capabilities.canReadInterventions,
    retry: false,
  });

  const suggestionsQuery = useQuery({
    queryKey: ["m21-student-suggestions", studentProfileId],
    queryFn: () =>
      listSuggestions({
        studentProfileId,
      }),
    enabled: capabilities.canReadSuggestions,
    retry: false,
  });

  const timelineEntries =
    timelineQuery.data?.pages.flatMap(
      (page) => page.entries,
    ) ?? [];
  const interventions = interventionsQuery.data?.items ?? [];
  const suggestions = suggestionsQuery.data?.items ?? [];

  const timelineMetrics = useMemo(() => {
    return {
      loaded: timelineEntries.length,
      signals: timelineEntries.filter(
        (entry) => entry.category === "SIGNAL",
      ).length,
      outcomes: timelineEntries.filter(
        (entry) => entry.category === "OUTCOME",
      ).length,
      activeInterventions: interventions.filter(
        (intervention) =>
          !["CLOSED", "CANCELLED"].includes(
            intervention.status,
          ),
      ).length,
    };
  }, [timelineEntries, interventions]);

  if (!capabilities.canReadTimeline) {
    return (
      <Card>
        <CardContent className="flex min-h-72 flex-col items-center justify-center p-6 text-center">
          <ShieldAlert className="h-11 w-11 text-rose-500" />
          <h1 className="mt-4 text-xl font-bold text-slate-900">
            Student 360 no disponible
          </h1>
          <p className="mt-2 max-w-xl text-sm text-slate-500">
            Tu contexto autenticado no posee
            student_timeline.read. El backend y PostgreSQL RLS
            continúan siendo la autoridad de acceso.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-5" data-testid="m21-student-360">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap gap-2">
            <Badge tone="success">Seguimiento del estudiante</Badge>
            <Badge tone="neutral">
              Historia longitudinal
            </Badge>
          </div>
          <h1 className="mt-3 text-3xl font-bold text-slate-900">
            Student 360
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Una vista longitudinal autorizada de señales,
            intervenciones, acciones, seguimientos y resultados.
          </p>
          <div className="mt-3 break-all font-mono text-xs text-slate-500">
            {studentProfileId}
          </div>
        </div>

        {capabilities.canReadSuggestions ? (
          <Link
            to="/m21/suggestions"
            className="inline-flex h-10 items-center justify-center gap-2 self-start rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-800 transition hover:bg-slate-50"
          >
            <ArrowLeft className="h-4 w-4" />
            Volver a sugerencias
          </Link>
        ) : null}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Eventos cargados"
          value={timelineMetrics.loaded}
          detail="Entradas visibles de Timeline"
        />
        <Metric
          label="Señales"
          value={timelineMetrics.signals}
          detail="Eventos de señal visibles"
        />
        <Metric
          label="Intervenciones activas"
          value={timelineMetrics.activeInterventions}
          detail="Según permisos del contexto"
        />
        <Metric
          label="Resultados"
          value={timelineMetrics.outcomes}
          detail="Outcomes visibles en Timeline"
        />
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <UserRoundSearch className="h-5 w-5 text-slate-500" />
            <h2 className="font-bold text-slate-900">
              Filtros de historia
            </h2>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-sm font-semibold text-slate-700">
              <span>Categoría</span>
              <select
                value={category}
                onChange={(event) =>
                  setCategory(
                    event.target.value as TimelineCategory | "",
                  )
                }
                className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium outline-none focus:border-slate-400"
              >
                <option value="">Todas</option>
                {Object.entries(categoryLabels).map(
                  ([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ),
                )}
              </select>
            </label>

            <label className="space-y-1 text-sm font-semibold text-slate-700">
              <span>Sensibilidad</span>
              <select
                value={sensitivity}
                onChange={(event) =>
                  setSensitivity(
                    event.target.value as
                      | TimelineSensitivity
                      | "",
                  )
                }
                className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium outline-none focus:border-slate-400"
              >
                <option value="">Todas las autorizadas</option>
                <option value="GENERAL">General</option>
                <option value="RESTRICTED">Restringida</option>
                <option value="CONFIDENTIAL">
                  Confidencial
                </option>
              </select>
            </label>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.7fr)]">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-slate-500" />
              <h2 className="font-bold text-slate-900">
                Timeline longitudinal
              </h2>
            </div>
            <p className="mt-1 text-sm text-slate-500">
              Ordenado por el read model M21 y limitado por
              permisos, alcance docente y sensibilidad.
            </p>
          </CardHeader>
          <CardContent>
            {timelineQuery.isPending ? (
              <div className="py-12 text-center text-sm text-slate-500">
                Cargando Timeline…
              </div>
            ) : null}

            {timelineQuery.isError ? (
              <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm font-medium text-rose-700">
                {errorMessage(timelineQuery.error)}
              </div>
            ) : null}

            {!timelineQuery.isPending &&
            !timelineQuery.isError &&
            timelineEntries.length === 0 ? (
              <div className="flex min-h-52 flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center">
                <Sparkles className="h-9 w-9 text-slate-400" />
                <div className="mt-3 font-bold text-slate-800">
                  Sin eventos visibles
                </div>
                <div className="mt-1 max-w-md text-sm text-slate-500">
                  No existen entradas para este filtro o tu contexto
                  no tiene acceso a ellas.
                </div>
              </div>
            ) : null}

            <div className="space-y-3">
              {timelineEntries.map((entry) => (
                <article
                  key={entry.id}
                  className="relative rounded-2xl border border-slate-200 bg-white p-4 sm:p-5"
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex flex-wrap gap-2">
                      <Badge
                        tone={timelineCategoryTone(entry.category)}
                      >
                        {categoryLabels[entry.category] ??
                          entry.category}
                      </Badge>
                      <Badge
                        tone={timelineSensitivityTone(
                          entry.sensitivity,
                        )}
                      >
                        {sensitivityLabels[entry.sensitivity] ??
                          entry.sensitivity}
                      </Badge>
                      {entry.importance !== "NORMAL" ? (
                        <Badge tone="warning">
                          {entry.importance}
                        </Badge>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-1 text-xs text-slate-500">
                      <Clock3 className="h-3.5 w-3.5" />
                      {formatDate(entry.occurred_at)}
                    </div>
                  </div>

                  <h3 className="mt-3 font-bold text-slate-900">
                    {entry.title}
                  </h3>
                  {entry.summary ? (
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      {entry.summary}
                    </p>
                  ) : null}

                  <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
                    <span>{entry.event_type}</span>
                    <span>
                      Posición {entry.ledger_position}
                    </span>
                    <span>
                      {entry.source_aggregate_type}
                    </span>
                  </div>
                </article>
              ))}
            </div>

            {timelineQuery.hasNextPage ? (
              <div className="mt-4 flex justify-center">
                <Button
                  variant="secondary"
                  disabled={timelineQuery.isFetchingNextPage}
                  onClick={() => timelineQuery.fetchNextPage()}
                >
                  {timelineQuery.isFetchingNextPage
                    ? "Cargando…"
                    : "Cargar eventos anteriores"}
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <BookOpenCheck className="h-5 w-5 text-slate-500" />
                <h2 className="font-bold text-slate-900">
                  Intervenciones
                </h2>
              </div>
            </CardHeader>
            <CardContent>
              {!capabilities.canReadInterventions ? (
                <div className="text-sm text-slate-500">
                  Tu contexto no posee intervention.read.
                </div>
              ) : interventionsQuery.isPending ? (
                <div className="text-sm text-slate-500">
                  Cargando intervenciones…
                </div>
              ) : interventionsQuery.isError ? (
                <div className="text-sm font-medium text-rose-700">
                  {errorMessage(interventionsQuery.error)}
                </div>
              ) : interventions.length === 0 ? (
                <div className="text-sm text-slate-500">
                  Sin intervenciones visibles.
                </div>
              ) : (
                <div className="space-y-3">
                  {interventions.slice(0, 6).map((item) => (
                    <div
                      key={item.id}
                      className="rounded-xl border border-slate-200 p-3"
                    >
                      <div className="flex flex-wrap gap-2">
                        <Badge tone="neutral">
                          {item.status}
                        </Badge>
                        <Badge tone="warning">
                          {item.severity}
                        </Badge>
                      </div>
                      <div className="mt-2 text-sm font-bold text-slate-800">
                        {item.title}
                      </div>
                      <div className="mt-1 text-xs text-slate-500">
                        {item.intervention_type}
                      </div>
                      {item.outcome_type ? (
                        <div className="mt-2 text-xs font-semibold text-emerald-700">
                          Resultado: {item.outcome_type}
                        </div>
                      ) : null}
                      <Link
                        to="/m21/interventions/$interventionId"
                        params={{ interventionId: item.id }}
                        className="mt-3 inline-flex h-8 items-center justify-center rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-800 transition hover:bg-slate-100"
                        data-testid="m21-open-intervention-workspace"
                      >
                        Abrir espacio de intervención
                      </Link>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h2 className="font-bold text-slate-900">
                Sugerencias relacionadas
              </h2>
            </CardHeader>
            <CardContent>
              {!capabilities.canReadSuggestions ? (
                <div className="text-sm text-slate-500">
                  Tu contexto no posee
                  intervention.suggestion.read.
                </div>
              ) : suggestionsQuery.isPending ? (
                <div className="text-sm text-slate-500">
                  Cargando sugerencias…
                </div>
              ) : suggestionsQuery.isError ? (
                <div className="text-sm font-medium text-rose-700">
                  {errorMessage(suggestionsQuery.error)}
                </div>
              ) : suggestions.length === 0 ? (
                <div className="text-sm text-slate-500">
                  Sin sugerencias visibles.
                </div>
              ) : (
                <div className="space-y-3">
                  {suggestions.slice(0, 6).map((item) => (
                    <div
                      key={item.id}
                      className="rounded-xl border border-slate-200 p-3"
                    >
                      <div className="flex flex-wrap gap-2">
                        <Badge tone="neutral">
                          {item.status}
                        </Badge>
                        <Badge tone="warning">
                          {item.severity}
                        </Badge>
                      </div>
                      <div className="mt-2 text-sm font-bold text-slate-800">
                        {item.title}
                      </div>
                      <div className="mt-1 text-xs text-slate-500">
                        {item.rule_key}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
