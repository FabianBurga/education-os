import {
  Activity,
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  Plus,
  ShieldAlert,
  UserRoundCog,
} from "lucide-react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";

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
  allowedActionTransitions,
  allowedInterventionTransitions,
  canCompleteAction,
  cancelIntervention,
  closeIntervention,
  completeInterventionAction,
  createInterventionAction,
  createInterventionFollowUp,
  getIntervention,
  interventionWorkspaceCapabilities,
  listInterventionActions,
  listInterventionFollowUps,
  minimumFollowUpSensitivity,
  resolveIntervention,
  transitionIntervention,
  transitionInterventionAction,
  assignIntervention,
  type ActionStatus,
  type FollowUpType,
  type InterventionStatus,
  type OutcomeType,
  type Sensitivity,
} from "../m21/intervention-workspace";

const outcomeTypes: OutcomeType[] = [
  "IMPROVED",
  "STABLE",
  "NO_CHANGE",
  "WORSENED",
  "REFERRED",
  "TRANSFERRED",
  "NOT_ASSESSABLE",
];

const followUpTypes: FollowUpType[] = [
  "MEETING",
  "PHONE_CALL",
  "FAMILY_CONTACT",
  "STUDENT_CONVERSATION",
  "TEACHER_REVIEW",
  "ACADEMIC_REVIEW",
  "ATTENDANCE_REVIEW",
  "PSYCHOLOGY_SESSION",
  "REFERRAL",
  "OTHER",
];

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "No fue posible completar la operación.";
}

function localDateTimeNow(): string {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offsetMs)
    .toISOString()
    .slice(0, 16);
}

function isoOrNull(value: string): string | null {
  if (!value.trim()) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toISOString();
}

function statusTone(
  status: string,
): "neutral" | "success" | "warning" | "danger" {
  if (["CLOSED", "COMPLETED"].includes(status)) {
    return "success";
  }
  if (["CANCELLED", "OVERDUE"].includes(status)) {
    return "danger";
  }
  if (["IN_PROGRESS", "MONITORING", "ACKNOWLEDGED"].includes(status)) {
    return "warning";
  }
  return "neutral";
}

function sensitivityTone(
  sensitivity: string,
): "neutral" | "success" | "warning" | "danger" {
  if (sensitivity === "CONFIDENTIAL") {
    return "danger";
  }
  if (sensitivity === "RESTRICTED") {
    return "warning";
  }
  return "neutral";
}

export function InterventionWorkspacePage({
  interventionId,
}: {
  interventionId: string;
}) {
  const { bootstrap } = useAppContext();
  const queryClient = useQueryClient();
  const capabilities = interventionWorkspaceCapabilities(
    bootstrap.permissions,
  );

  const interventionQuery = useQuery({
    queryKey: ["m21-intervention", interventionId],
    queryFn: () => getIntervention(interventionId),
    enabled: capabilities.canRead,
    retry: false,
  });

  const actionsQuery = useQuery({
    queryKey: ["m21-intervention-actions", interventionId],
    queryFn: () => listInterventionActions(interventionId),
    enabled: capabilities.canRead,
    retry: false,
  });

  const followUpsQuery = useQuery({
    queryKey: ["m21-intervention-followups", interventionId],
    queryFn: () => listInterventionFollowUps(interventionId),
    enabled: capabilities.canRead,
    retry: false,
  });

  const intervention = interventionQuery.data ?? null;
  const actions = actionsQuery.data?.items ?? [];
  const followUps = followUpsQuery.data?.items ?? [];

  const [assignedRole, setAssignedRole] = useState("");
  const [assignedUser, setAssignedUser] = useState("");
  const [targetAt, setTargetAt] = useState("");

  const [actionTitle, setActionTitle] = useState("");
  const [actionType, setActionType] = useState("REVIEW");
  const [actionDescription, setActionDescription] = useState("");
  const [actionAssignedRole, setActionAssignedRole] = useState("");
  const [actionAssignedUser, setActionAssignedUser] = useState("");
  const [actionDueAt, setActionDueAt] = useState("");
  const [completionNotes, setCompletionNotes] = useState<
    Record<string, string>
  >({});

  const [followUpType, setFollowUpType] =
    useState<FollowUpType>("MEETING");
  const [followUpSensitivity, setFollowUpSensitivity] =
    useState<Sensitivity>("GENERAL");
  const [followUpNote, setFollowUpNote] = useState("");
  const [observedAt, setObservedAt] = useState(
    localDateTimeNow(),
  );

  const [outcomeType, setOutcomeType] =
    useState<OutcomeType>("IMPROVED");
  const [outcomeSummary, setOutcomeSummary] = useState("");
  const [cancelReason, setCancelReason] = useState("");

  useEffect(() => {
    if (!intervention) {
      return;
    }
    setAssignedRole(intervention.assigned_role_code ?? "");
    setAssignedUser(intervention.assigned_user_id ?? "");
    setTargetAt(
      intervention.target_at
        ? intervention.target_at.slice(0, 16)
        : "",
    );
    setFollowUpSensitivity(
      minimumFollowUpSensitivity(intervention.sensitivity),
    );
    if (intervention.outcome_type) {
      setOutcomeType(intervention.outcome_type as OutcomeType);
    }
    setOutcomeSummary(intervention.outcome_summary ?? "");
  }, [intervention]);

  async function refreshWorkspace() {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["m21-intervention", interventionId],
      }),
      queryClient.invalidateQueries({
        queryKey: ["m21-intervention-actions", interventionId],
      }),
      queryClient.invalidateQueries({
        queryKey: ["m21-intervention-followups", interventionId],
      }),
      queryClient.invalidateQueries({
        queryKey: ["m21-student-interventions"],
      }),
      queryClient.invalidateQueries({
        queryKey: ["m21-student-timeline"],
      }),
    ]);
  }

  const assignMutation = useMutation({
    mutationFn: () =>
      assignIntervention(interventionId, {
        assigned_role_code: assignedRole.trim() || null,
        assigned_user_id: assignedUser.trim() || null,
        target_at: isoOrNull(targetAt),
      }),
    onSuccess: refreshWorkspace,
  });

  const transitionMutation = useMutation({
    mutationFn: (status: "IN_PROGRESS" | "MONITORING") =>
      transitionIntervention(interventionId, status),
    onSuccess: refreshWorkspace,
  });

  const actionCreateMutation = useMutation({
    mutationFn: () =>
      createInterventionAction(interventionId, {
        action_type: actionType.trim() || "REVIEW",
        title: actionTitle.trim(),
        description: actionDescription.trim() || null,
        assigned_role_code:
          actionAssignedRole.trim() || null,
        assigned_user_id:
          actionAssignedUser.trim() || null,
        due_at: isoOrNull(actionDueAt),
      }),
    onSuccess: async () => {
      setActionTitle("");
      setActionDescription("");
      await refreshWorkspace();
    },
  });

  const actionTransitionMutation = useMutation({
    mutationFn: ({
      actionId,
      status,
    }: {
      actionId: string;
      status: "ACKNOWLEDGED" | "IN_PROGRESS" | "CANCELLED";
    }) => transitionInterventionAction(actionId, status),
    onSuccess: refreshWorkspace,
  });

  const actionCompleteMutation = useMutation({
    mutationFn: (actionId: string) =>
      completeInterventionAction(
        actionId,
        completionNotes[actionId] ?? "",
      ),
    onSuccess: async (_, actionId) => {
      setCompletionNotes((current) => ({
        ...current,
        [actionId]: "",
      }));
      await refreshWorkspace();
    },
  });

  const followUpMutation = useMutation({
    mutationFn: () =>
      createInterventionFollowUp(interventionId, {
        followup_type: followUpType,
        sensitivity: followUpSensitivity,
        note: followUpNote.trim(),
        observed_at:
          isoOrNull(observedAt) ?? new Date().toISOString(),
      }),
    onSuccess: async () => {
      setFollowUpNote("");
      setObservedAt(localDateTimeNow());
      await refreshWorkspace();
    },
  });

  const resolveMutation = useMutation({
    mutationFn: () =>
      resolveIntervention(
        interventionId,
        outcomeType,
        outcomeSummary,
      ),
    onSuccess: refreshWorkspace,
  });

  const closeMutation = useMutation({
    mutationFn: () =>
      closeIntervention(
        interventionId,
        outcomeType,
        outcomeSummary,
      ),
    onSuccess: refreshWorkspace,
  });

  const cancelMutation = useMutation({
    mutationFn: () =>
      cancelIntervention(interventionId, cancelReason),
    onSuccess: async () => {
      setCancelReason("");
      await refreshWorkspace();
    },
  });

  const mutations = [
    assignMutation,
    transitionMutation,
    actionCreateMutation,
    actionTransitionMutation,
    actionCompleteMutation,
    followUpMutation,
    resolveMutation,
    closeMutation,
    cancelMutation,
  ];
  const mutationError = mutations.find((item) => item.isError)?.error;
  const isMutating = mutations.some((item) => item.isPending);

  const activeActions = useMemo(
    () =>
      actions.filter((action) =>
        ["OPEN", "ACKNOWLEDGED", "IN_PROGRESS", "OVERDUE"].includes(
          action.status,
        ),
      ),
    [actions],
  );

  if (!capabilities.canRead) {
    return (
      <Card>
        <CardContent className="flex min-h-72 flex-col items-center justify-center p-6 text-center">
          <ShieldAlert className="h-11 w-11 text-rose-500" />
          <h1 className="mt-4 text-xl font-bold text-slate-900">
            Espacio de intervención no disponible
          </h1>
          <p className="mt-2 max-w-xl text-sm text-slate-500">
            Tu contexto autenticado no posee intervention.read.
            La autorización efectiva continúa en API y PostgreSQL
            RLS.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (interventionQuery.isPending) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-sm text-slate-500">
          Cargando intervención…
        </CardContent>
      </Card>
    );
  }

  if (interventionQuery.isError || !intervention) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-sm font-medium text-rose-700">
          {errorMessage(interventionQuery.error)}
        </CardContent>
      </Card>
    );
  }

  const status = intervention.status as InterventionStatus;
  const transitionTargets =
    allowedInterventionTransitions(status);
  const terminal = ["CLOSED", "CANCELLED"].includes(status);
  const canResolveNow =
    capabilities.canResolve &&
    ["IN_PROGRESS", "MONITORING"].includes(status);
  const canCloseNow =
    capabilities.canClose &&
    status === "RESOLVED" &&
    Boolean(intervention.outcome_type) &&
    Boolean(intervention.outcome_summary);

  return (
    <div
      className="space-y-5"
      data-testid="m21-intervention-workspace"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap gap-2">
            <Badge tone={statusTone(status)}>{status}</Badge>
            <Badge tone="warning">{intervention.severity}</Badge>
            <Badge tone={sensitivityTone(intervention.sensitivity)}>
              {intervention.sensitivity}
            </Badge>
            {intervention.protected_detail ? (
              <Badge tone="danger">Detalle protegido</Badge>
            ) : null}
          </div>
          <h1 className="mt-3 text-3xl font-bold text-slate-900">
            {intervention.title}
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Espacio operativo para ejecutar acciones, registrar
            seguimientos y cerrar el ciclo con un resultado humano
            trazable.
          </p>
        </div>

        <Link
          to="/m21/students/$studentProfileId"
          params={{
            studentProfileId: intervention.student_profile_id,
          }}
          className="inline-flex h-10 items-center justify-center gap-2 self-start rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-800 transition hover:bg-slate-50"
        >
          <ArrowLeft className="h-4 w-4" />
          Volver a Student 360
        </Link>
      </div>

      {mutationError ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm font-medium text-rose-700">
          {errorMessage(mutationError)}
        </div>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-slate-500" />
                <h2 className="font-bold text-slate-900">
                  Estado y contexto
                </h2>
              </div>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-4 sm:grid-cols-2">
                <div>
                  <dt className="text-xs font-bold uppercase text-slate-400">
                    Tipo
                  </dt>
                  <dd className="mt-1 text-sm font-semibold text-slate-800">
                    {intervention.intervention_type}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-bold uppercase text-slate-400">
                    Origen
                  </dt>
                  <dd className="mt-1 text-sm font-semibold text-slate-800">
                    {intervention.origin_type}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-bold uppercase text-slate-400">
                    Responsable
                  </dt>
                  <dd className="mt-1 text-sm text-slate-700">
                    {intervention.assigned_role_code ??
                      intervention.assigned_user_id ??
                      "Sin asignar"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-bold uppercase text-slate-400">
                    Acciones activas
                  </dt>
                  <dd className="mt-1 text-sm font-semibold text-slate-800">
                    {activeActions.length}
                  </dd>
                </div>
              </dl>

              {intervention.reason ? (
                <div className="mt-4 rounded-xl bg-slate-50 p-4">
                  <div className="text-xs font-bold uppercase text-slate-400">
                    Motivo
                  </div>
                  <div className="mt-2 text-sm leading-6 text-slate-700">
                    {intervention.reason}
                  </div>
                </div>
              ) : null}

              {intervention.objective ? (
                <div className="mt-3 rounded-xl bg-slate-50 p-4">
                  <div className="text-xs font-bold uppercase text-slate-400">
                    Objetivo
                  </div>
                  <div className="mt-2 text-sm leading-6 text-slate-700">
                    {intervention.objective}
                  </div>
                </div>
              ) : null}

              {capabilities.canUpdate &&
              transitionTargets.length > 0 ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {transitionTargets.map((target) => (
                    <Button
                      key={target}
                      variant="secondary"
                      disabled={isMutating}
                      onClick={() =>
                        transitionMutation.mutate(
                          target as
                            | "IN_PROGRESS"
                            | "MONITORING",
                        )
                      }
                    >
                      Pasar a {target}
                    </Button>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <ClipboardCheck className="h-5 w-5 text-slate-500" />
                <h2 className="font-bold text-slate-900">
                  Acciones
                </h2>
              </div>
            </CardHeader>
            <CardContent>
              {capabilities.canManageActions && !terminal ? (
                <div className="mb-5 grid gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:grid-cols-2">
                  <input
                    value={actionTitle}
                    onChange={(event) =>
                      setActionTitle(event.target.value)
                    }
                    placeholder="Título de la acción"
                    className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400 sm:col-span-2"
                  />
                  <input
                    value={actionType}
                    onChange={(event) =>
                      setActionType(event.target.value)
                    }
                    placeholder="Tipo, ej. REVIEW"
                    className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
                  />
                  <input
                    value={actionAssignedRole}
                    onChange={(event) =>
                      setActionAssignedRole(event.target.value)
                    }
                    placeholder="Rol responsable opcional"
                    className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
                  />
                  <input
                    value={actionAssignedUser}
                    onChange={(event) =>
                      setActionAssignedUser(event.target.value)
                    }
                    placeholder="UUID responsable opcional"
                    className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
                  />
                  <input
                    type="datetime-local"
                    value={actionDueAt}
                    onChange={(event) =>
                      setActionDueAt(event.target.value)
                    }
                    className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
                  />
                  <textarea
                    value={actionDescription}
                    onChange={(event) =>
                      setActionDescription(event.target.value)
                    }
                    placeholder="Descripción opcional"
                    className="min-h-24 resize-y rounded-xl border border-slate-200 bg-white p-3 text-sm outline-none focus:border-slate-400 sm:col-span-2"
                  />
                  <Button
                    className="gap-2 sm:col-span-2"
                    disabled={
                      !actionTitle.trim() ||
                      actionCreateMutation.isPending
                    }
                    onClick={() =>
                      actionCreateMutation.mutate()
                    }
                  >
                    <Plus className="h-4 w-4" />
                    Crear acción
                  </Button>
                </div>
              ) : null}

              {actionsQuery.isPending ? (
                <div className="text-sm text-slate-500">
                  Cargando acciones…
                </div>
              ) : actionsQuery.isError ? (
                <div className="text-sm font-medium text-rose-700">
                  {errorMessage(actionsQuery.error)}
                </div>
              ) : actions.length === 0 ? (
                <div className="text-sm text-slate-500">
                  Sin acciones registradas.
                </div>
              ) : (
                <div className="space-y-3">
                  {actions.map((action) => (
                    <div
                      key={action.id}
                      className="rounded-2xl border border-slate-200 p-4"
                    >
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <div className="flex flex-wrap gap-2">
                            <Badge tone={statusTone(action.status)}>
                              {action.status}
                            </Badge>
                            <Badge tone="neutral">
                              {action.action_type}
                            </Badge>
                          </div>
                          <div className="mt-2 font-bold text-slate-900">
                            {action.title}
                          </div>
                          {action.description ? (
                            <div className="mt-1 text-sm text-slate-600">
                              {action.description}
                            </div>
                          ) : null}
                        </div>
                        {action.due_at ? (
                          <div className="flex items-center gap-1 text-xs text-slate-500">
                            <Clock3 className="h-3.5 w-3.5" />
                            {new Date(
                              action.due_at,
                            ).toLocaleString("es-EC")}
                          </div>
                        ) : null}
                      </div>

                      {capabilities.canManageActions &&
                      !terminal ? (
                        <div className="mt-3 space-y-3 border-t border-slate-100 pt-3">
                          <div className="flex flex-wrap gap-2">
                            {allowedActionTransitions(
                              action.status as ActionStatus,
                            ).map((target) => (
                              <Button
                                key={target}
                                variant="secondary"
                                disabled={isMutating}
                                onClick={() =>
                                  actionTransitionMutation.mutate({
                                    actionId: action.id,
                                    status:
                                      target as
                                        | "ACKNOWLEDGED"
                                        | "IN_PROGRESS"
                                        | "CANCELLED",
                                  })
                                }
                              >
                                {target}
                              </Button>
                            ))}
                          </div>

                          {canCompleteAction(
                            action.status as ActionStatus,
                          ) ? (
                            <div className="flex flex-col gap-2 sm:flex-row">
                              <input
                                value={
                                  completionNotes[action.id] ?? ""
                                }
                                onChange={(event) =>
                                  setCompletionNotes(
                                    (current) => ({
                                      ...current,
                                      [action.id]:
                                        event.target.value,
                                    }),
                                  )
                                }
                                placeholder="Nota de cierre opcional"
                                className="h-10 flex-1 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
                              />
                              <Button
                                disabled={isMutating}
                                onClick={() =>
                                  actionCompleteMutation.mutate(
                                    action.id,
                                  )
                                }
                              >
                                Completar
                              </Button>
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h2 className="font-bold text-slate-900">
                Seguimientos
              </h2>
            </CardHeader>
            <CardContent>
              {capabilities.canCreateFollowUp && !terminal ? (
                <div className="mb-5 grid gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:grid-cols-2">
                  <select
                    value={followUpType}
                    onChange={(event) =>
                      setFollowUpType(
                        event.target.value as FollowUpType,
                      )
                    }
                    className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm"
                  >
                    {followUpTypes.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                  <select
                    value={followUpSensitivity}
                    onChange={(event) =>
                      setFollowUpSensitivity(
                        event.target.value as Sensitivity,
                      )
                    }
                    className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm"
                  >
                    <option value="GENERAL">GENERAL</option>
                    <option value="RESTRICTED">RESTRICTED</option>
                    <option value="CONFIDENTIAL">
                      CONFIDENTIAL
                    </option>
                  </select>
                  <input
                    type="datetime-local"
                    value={observedAt}
                    onChange={(event) =>
                      setObservedAt(event.target.value)
                    }
                    className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm sm:col-span-2"
                  />
                  <textarea
                    value={followUpNote}
                    maxLength={4000}
                    onChange={(event) =>
                      setFollowUpNote(event.target.value)
                    }
                    placeholder="Nota de seguimiento"
                    className="min-h-28 resize-y rounded-xl border border-slate-200 bg-white p-3 text-sm sm:col-span-2"
                  />
                  <Button
                    className="sm:col-span-2"
                    disabled={
                      !followUpNote.trim() ||
                      followUpMutation.isPending
                    }
                    onClick={() => followUpMutation.mutate()}
                  >
                    Registrar seguimiento
                  </Button>
                </div>
              ) : null}

              {followUpsQuery.isPending ? (
                <div className="text-sm text-slate-500">
                  Cargando seguimientos…
                </div>
              ) : followUpsQuery.isError ? (
                <div className="text-sm font-medium text-rose-700">
                  {errorMessage(followUpsQuery.error)}
                </div>
              ) : followUps.length === 0 ? (
                <div className="text-sm text-slate-500">
                  Sin seguimientos registrados.
                </div>
              ) : (
                <div className="space-y-3">
                  {followUps.map((followUp) => (
                    <div
                      key={followUp.id}
                      className="rounded-xl border border-slate-200 p-4"
                    >
                      <div className="flex flex-wrap gap-2">
                        <Badge tone="neutral">
                          {followUp.followup_type}
                        </Badge>
                        <Badge
                          tone={sensitivityTone(
                            followUp.sensitivity,
                          )}
                        >
                          {followUp.sensitivity}
                        </Badge>
                      </div>
                      {followUp.note ? (
                        <div className="mt-2 text-sm leading-6 text-slate-700">
                          {followUp.note}
                        </div>
                      ) : (
                        <div className="mt-2 text-sm italic text-slate-500">
                          Detalle protegido.
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <UserRoundCog className="h-5 w-5 text-slate-500" />
                <h2 className="font-bold text-slate-900">
                  Asignación
                </h2>
              </div>
            </CardHeader>
            <CardContent>
              {!capabilities.canAssign || terminal ? (
                <div className="text-sm text-slate-500">
                  Asignación en modo solo lectura.
                </div>
              ) : (
                <div className="space-y-3">
                  <input
                    value={assignedRole}
                    onChange={(event) =>
                      setAssignedRole(event.target.value)
                    }
                    placeholder="Código de rol"
                    className="h-10 w-full rounded-xl border border-slate-200 px-3 text-sm"
                  />
                  <input
                    value={assignedUser}
                    onChange={(event) =>
                      setAssignedUser(event.target.value)
                    }
                    placeholder="UUID de usuario"
                    className="h-10 w-full rounded-xl border border-slate-200 px-3 text-sm"
                  />
                  <input
                    type="datetime-local"
                    value={targetAt}
                    onChange={(event) =>
                      setTargetAt(event.target.value)
                    }
                    className="h-10 w-full rounded-xl border border-slate-200 px-3 text-sm"
                  />
                  <Button
                    className="w-full"
                    disabled={
                      (!assignedRole.trim() &&
                        !assignedUser.trim()) ||
                      assignMutation.isPending
                    }
                    onClick={() => assignMutation.mutate()}
                  >
                    Guardar asignación
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-slate-500" />
                <h2 className="font-bold text-slate-900">
                  Resultado y cierre
                </h2>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <select
                  value={outcomeType}
                  onChange={(event) =>
                    setOutcomeType(
                      event.target.value as OutcomeType,
                    )
                  }
                  disabled={
                    !canResolveNow && status !== "RESOLVED"
                  }
                  className="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm disabled:bg-slate-50"
                >
                  {outcomeTypes.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
                <textarea
                  value={outcomeSummary}
                  maxLength={2000}
                  disabled={
                    !canResolveNow && status !== "RESOLVED"
                  }
                  onChange={(event) =>
                    setOutcomeSummary(event.target.value)
                  }
                  placeholder="Resumen del resultado"
                  className="min-h-28 w-full resize-y rounded-xl border border-slate-200 p-3 text-sm disabled:bg-slate-50"
                />

                {activeActions.length > 0 &&
                ["IN_PROGRESS", "MONITORING", "RESOLVED"].includes(
                  status,
                ) ? (
                  <div className="rounded-xl bg-amber-50 p-3 text-xs font-medium text-amber-800">
                    Debes completar o cancelar las acciones activas
                    antes de resolver o cerrar.
                  </div>
                ) : null}

                {canResolveNow ? (
                  <Button
                    className="w-full"
                    disabled={
                      !outcomeSummary.trim() ||
                      activeActions.length > 0 ||
                      resolveMutation.isPending
                    }
                    onClick={() => resolveMutation.mutate()}
                  >
                    Resolver intervención
                  </Button>
                ) : null}

                {status === "RESOLVED" ? (
                  <Button
                    className="w-full"
                    disabled={
                      !canCloseNow ||
                      activeActions.length > 0 ||
                      closeMutation.isPending
                    }
                    onClick={() => closeMutation.mutate()}
                  >
                    Cerrar intervención
                  </Button>
                ) : null}
              </div>
            </CardContent>
          </Card>

          {capabilities.canUpdate && !terminal ? (
            <Card>
              <CardHeader>
                <h2 className="font-bold text-slate-900">
                  Cancelación
                </h2>
              </CardHeader>
              <CardContent>
                <textarea
                  value={cancelReason}
                  maxLength={1000}
                  onChange={(event) =>
                    setCancelReason(event.target.value)
                  }
                  placeholder="Motivo de cancelación"
                  className="min-h-24 w-full resize-y rounded-xl border border-slate-200 p-3 text-sm"
                />
                <Button
                  variant="danger"
                  className="mt-3 w-full"
                  disabled={
                    !cancelReason.trim() ||
                    cancelMutation.isPending
                  }
                  onClick={() => cancelMutation.mutate()}
                >
                  Cancelar intervención
                </Button>
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}
