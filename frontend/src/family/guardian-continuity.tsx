import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, RefreshCw } from "lucide-react";

import { useAppContext } from "../app-context";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { ApiError, apiFetch } from "../lib/api";

const ROOT = "/api/v1/guardian";

export interface GuardianContinuityStudent {
  student_profile_id: string;
  student_name: string;
}

export interface GuardianContinuityNotice {
  notice_id: string;
  student_profile_id: string | null;
  notice_type: string;
  title: string;
  requires_acknowledgement: boolean;
  published_at: string | null;
  acknowledged_at: string | null;
  scope: string;
}

function publishedTime(notice: GuardianContinuityNotice): number {
  if (!notice.published_at) return 0;
  const value = Date.parse(notice.published_at);
  return Number.isNaN(value) ? 0 : value;
}

export function selectCuratedGuardianNotice(
  notices: GuardianContinuityNotice[],
): GuardianContinuityNotice | null {
  return [...notices]
    .filter((notice) => notice.requires_acknowledgement)
    .sort((left, right) => publishedTime(right) - publishedTime(left))[0] ?? null;
}

export function guardianNoticeScopeLabel(
  notice: GuardianContinuityNotice,
  students: GuardianContinuityStudent[],
): string {
  if (!notice.student_profile_id) return "Aviso institucional";
  const student = students.find(
    (candidate) => candidate.student_profile_id === notice.student_profile_id,
  );
  return student ? `Aviso para ${student.student_name}` : "Aviso para estudiante autorizado";
}

function formatPublishedAt(value: string | null): string {
  if (!value) return "Fecha no disponible";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Fecha no disponible";
  return date.toLocaleDateString();
}

function isPermissionFailure(reason: unknown): boolean {
  return reason instanceof ApiError && (reason.status === 401 || reason.status === 403);
}

export function GuardianContinuityCard() {
  const { bootstrap } = useAppContext();
  const canViewNotices = bootstrap.permissions.includes("guardian.notices.view");
  const canViewStudents = bootstrap.permissions.includes("guardian.students.view");
  const canAcknowledge = bootstrap.permissions.includes("guardian.notices.acknowledge");

  const noticesQuery = useQuery({
    queryKey: ["guardian-continuity-notices"],
    queryFn: () => apiFetch<GuardianContinuityNotice[]>(`${ROOT}/notices`),
    enabled: canViewNotices,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const studentsQuery = useQuery({
    queryKey: ["guardian-continuity-students"],
    queryFn: () => apiFetch<GuardianContinuityStudent[]>(`${ROOT}/students`),
    enabled: canViewNotices && canViewStudents,
    retry: false,
    refetchOnWindowFocus: false,
  });
  const acknowledge = useMutation({
    mutationFn: (noticeId: string) =>
      apiFetch(`${ROOT}/notices/${encodeURIComponent(noticeId)}/acknowledge`, {
        method: "POST",
      }),
    onSuccess: () => {
      void noticesQuery.refetch();
    },
  });

  if (!canViewNotices) return null;

  const notice = selectCuratedGuardianNotice(noticesQuery.data ?? []);
  const students = studentsQuery.data ?? [];
  const loadError = noticesQuery.error;

  return (
    <Card data-testid="guardian-continuity-card">
      <CardHeader className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Badge tone="neutral">Continuidad familiar</Badge>
          <h2 className="mt-2 text-xl font-bold">Avisos para revisar</h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Consulta los avisos publicados para tu cuenta y reconoce el aviso cuando corresponda.
          </p>
        </div>
        <Button
          variant="secondary"
          className="gap-2"
          onClick={() => {
            void noticesQuery.refetch();
            if (canViewStudents) void studentsQuery.refetch();
          }}
          disabled={noticesQuery.isFetching || studentsQuery.isFetching}
          data-testid="guardian-continuity-refresh"
        >
          <RefreshCw className="h-4 w-4" />
          Actualizar
        </Button>
      </CardHeader>
      <CardContent>
        {noticesQuery.isPending ? (
          <div className="py-6 text-center text-sm text-slate-500" role="status">
            Cargando avisos…
          </div>
        ) : isPermissionFailure(loadError) ? null : loadError ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900" role="alert">
            No fue posible cargar los avisos familiares.
          </div>
        ) : !notice ? (
          <div className="py-6 text-center text-sm text-slate-500" data-testid="guardian-continuity-empty">
            No hay avisos que requieran revisión.
          </div>
        ) : (
          <article className="rounded-xl border border-slate-200 p-4" data-testid="guardian-continuity-item">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {guardianNoticeScopeLabel(notice, students)}
                </p>
                <h3 className="mt-1 font-bold text-slate-900">{notice.title}</h3>
                <p className="mt-1 text-xs text-slate-500">
                  Publicado: {formatPublishedAt(notice.published_at)}
                </p>
              </div>
              {notice.acknowledged_at ? (
                <Badge tone="success" className="gap-1">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Reconocido
                </Badge>
              ) : (
                <Badge tone="warning">Requiere revisión</Badge>
              )}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <a
                href="/api/v1/guardian/dashboard"
                className="inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-800 hover:bg-slate-50"
                data-testid="guardian-continuity-open"
              >
                Abrir avisos
                <ExternalLink className="h-4 w-4" />
              </a>
              {canAcknowledge && !notice.acknowledged_at ? (
                <Button
                  onClick={() => acknowledge.mutate(notice.notice_id)}
                  disabled={acknowledge.isPending}
                  data-testid="guardian-continuity-acknowledge"
                >
                  Reconocer aviso
                </Button>
              ) : null}
            </div>
          </article>
        )}
      </CardContent>
    </Card>
  );
}
