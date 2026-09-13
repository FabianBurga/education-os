import {
  AlertTriangle,
  Cloud,
  CloudOff,
  Download,
  ExternalLink,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useAppContext } from "../app-context";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import { apiFetch } from "../lib/api";
import {
  applyAttendanceStateToSnapshot,
  deleteTeacherOfflineOperation,
  deleteTeacherOfflineSnapshot,
  listTeacherOfflineOperations,
  loadTeacherOfflineSnapshot,
  putTeacherOfflineOperation,
  saveTeacherOfflineSnapshot,
} from "../lib/teacher-offline-store";
import {
  attendanceBaseFromRow,
  chunkTeacherOfflineOperations,
  effectiveAttendanceRow,
  teacherOfflinePartitionKey,
  teacherOfflineQueueKey,
  teacherOfflineSnapshotExpired,
  teacherOfflineTargetKey,
} from "../teacher-offline-core";
import type {
  TeacherOfflineAttendanceRow,
  TeacherOfflineQueuedOperation,
  TeacherOfflineSnapshot,
  TeacherOfflineSyncResponse,
} from "../types/teacher-offline";

export function TeacherPwaPage() {
  const { bootstrap } = useAppContext();
  const partitionKey = useMemo(
    () => teacherOfflinePartitionKey(bootstrap),
    [bootstrap],
  );
  const capability = bootstrap.capabilities["teacher.offline_pwa"] === true;
  const [snapshot, setSnapshot] = useState<TeacherOfflineSnapshot | null>(null);
  const [queued, setQueued] = useState<TeacherOfflineQueuedOperation[]>([]);
  const [classId, setClassId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [online, setOnline] = useState(navigator.onLine);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function reload() {
    const [storedSnapshot, operations] = await Promise.all([
      loadTeacherOfflineSnapshot(partitionKey),
      listTeacherOfflineOperations(partitionKey),
    ]);
    if (
      storedSnapshot &&
      teacherOfflineSnapshotExpired(storedSnapshot.expires_at) &&
      operations.length === 0
    ) {
      await deleteTeacherOfflineSnapshot(partitionKey);
      setSnapshot(null);
    } else {
      setSnapshot(storedSnapshot);
    }
    setQueued(operations);
  }

  useEffect(() => {
    void reload();
  }, [partitionKey]);

  useEffect(() => {
    const markOnline = () => setOnline(true);
    const markOffline = () => setOnline(false);
    window.addEventListener("online", markOnline);
    window.addEventListener("offline", markOffline);
    return () => {
      window.removeEventListener("online", markOnline);
      window.removeEventListener("offline", markOffline);
    };
  }, []);

  useEffect(() => {
    if (!snapshot?.classes.length) return;
    const classroom =
      snapshot.classes.find(
        (item) => item.classroom.course_offering_id === classId,
      ) ?? snapshot.classes[0];
    if (classroom.classroom.course_offering_id !== classId) {
      setClassId(classroom.classroom.course_offering_id);
    }
    const classSession =
      classroom.sessions.find((item) => item.session.id === sessionId) ??
      classroom.sessions[0];
    if (classSession && classSession.session.id !== sessionId) {
      setSessionId(classSession.session.id);
    }
  }, [snapshot, classId, sessionId]);

  const expired = snapshot
    ? teacherOfflineSnapshotExpired(snapshot.expires_at)
    : false;
  const selectedClass =
    snapshot?.classes.find(
      (item) => item.classroom.course_offering_id === classId,
    ) ?? null;
  const selectedSession =
    selectedClass?.sessions.find((item) => item.session.id === sessionId) ??
    null;
  const byTarget = useMemo(
    () => new Map(queued.map((item) => [item.targetKey, item])),
    [queued],
  );
  const pending = queued.filter((item) => item.status === "PENDING").length;
  const conflicts = queued.filter((item) => item.status === "CONFLICT").length;

  async function prepare() {
    if (!online || !capability) return;
    setBusy(true);
    try {
      const fresh = await apiFetch<TeacherOfflineSnapshot>(
        "/api/v1/teacher/offline/snapshot?days=14",
      );
      await saveTeacherOfflineSnapshot(partitionKey, fresh);
      setSnapshot(fresh);
      setMessage("Paquete docente actualizado.");
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "No fue posible preparar el modo sin conexión.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function queue(row: TeacherOfflineAttendanceRow, code: string) {
    if (!selectedSession || expired) return;
    const target = teacherOfflineTargetKey(
      selectedSession.session.id,
      row.student_section_assignment_id,
    );
    const existing = byTarget.get(target);
    if (existing?.status === "CONFLICT") return;
    const operationId = crypto.randomUUID();
    await putTeacherOfflineOperation({
      queueKey: teacherOfflineQueueKey(
        partitionKey,
        selectedSession.session.id,
        row.student_section_assignment_id,
      ),
      partitionKey,
      operationId,
      targetKey: target,
      createdAt: new Date().toISOString(),
      status: "PENDING",
      detail: null,
      serverState: null,
      operation: {
        operation_id: operationId,
        operation_type: "ATTENDANCE_MARK",
        class_session_id: selectedSession.session.id,
        base:
          existing?.status === "PENDING"
            ? existing.operation.base
            : attendanceBaseFromRow(row),
        desired: {
          student_section_assignment_id: row.student_section_assignment_id,
          attendance_code_id: code,
          minutes_late: row.minutes_late,
          note: row.note,
        },
      },
    });
    await reload();
  }

  async function sync() {
    if (!online || !pending) return;
    const operations = queued.filter((item) => item.status === "PENDING");
    setBusy(true);
    try {
      let nextSnapshot = snapshot;
      for (const batch of chunkTeacherOfflineOperations(operations)) {
        const response = await apiFetch<TeacherOfflineSyncResponse>(
          "/api/v1/teacher/offline/sync",
          {
            method: "POST",
            body: JSON.stringify({
              operations: batch.map((item) => item.operation),
            }),
          },
        );
        for (const result of response.results) {
          const local = batch.find(
            (item) => item.operationId === result.operation_id,
          );
          if (!local) continue;
          if (
            (result.status === "APPLIED" || result.status === "REPLAYED") &&
            result.server_state
          ) {
            if (nextSnapshot) {
              nextSnapshot = applyAttendanceStateToSnapshot(
                nextSnapshot,
                local.operation.class_session_id,
                local.operation.desired.student_section_assignment_id,
                result.server_state,
              );
            }
            await deleteTeacherOfflineOperation(local.queueKey);
          } else {
            await putTeacherOfflineOperation({
              ...local,
              status: "CONFLICT",
              detail:
                result.detail ??
                `Sincronización detenida: ${result.status}`,
              serverState: result.server_state,
            });
          }
        }
        if (nextSnapshot) {
          await saveTeacherOfflineSnapshot(partitionKey, nextSnapshot);
          setSnapshot(nextSnapshot);
        }
      }
      await reload();
      setMessage("Sincronización finalizada.");
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "La sincronización no pudo completarse.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function acceptServer(item: TeacherOfflineQueuedOperation) {
    if (!snapshot || !item.serverState) return;
    const nextSnapshot = applyAttendanceStateToSnapshot(
      snapshot,
      item.operation.class_session_id,
      item.operation.desired.student_section_assignment_id,
      item.serverState,
    );
    await saveTeacherOfflineSnapshot(partitionKey, nextSnapshot);
    await deleteTeacherOfflineOperation(item.queueKey);
    setSnapshot(nextSnapshot);
    await reload();
  }

  async function retryLocal(item: TeacherOfflineQueuedOperation) {
    if (!item.serverState) return;
    const operationId = crypto.randomUUID();
    await putTeacherOfflineOperation({
      ...item,
      operationId,
      createdAt: new Date().toISOString(),
      status: "PENDING",
      detail: null,
      serverState: null,
      operation: {
        ...item.operation,
        operation_id: operationId,
        base: item.serverState,
      },
    });
    await reload();
  }

  async function discard(item: TeacherOfflineQueuedOperation) {
    await deleteTeacherOfflineOperation(item.queueKey);
    await reload();
  }

  if (!capability) {
    return (
      <Card data-testid="teacher-pwa-page">
        <CardContent className="py-10 text-center">
          <ShieldCheck className="mx-auto h-10 w-10 text-amber-500" />
          <h1 className="mt-4 text-xl font-bold">
            Modo docente sin conexión deshabilitado
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            La capability teacher.offline_pwa está deshabilitada.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-5" data-testid="teacher-pwa-page">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex gap-2">
            <Badge tone={online ? "success" : "warning"}>
              {online ? "En línea" : "Sin conexión"}
            </Badge>
            <Badge tone="neutral">M20 · Docentes</Badge>
          </div>
          <h1 className="mt-3 text-3xl font-bold">
            Asistencia offline-first
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-600">
            Prepara tus clases con conexión, registra asistencia localmente si
            la red falla y sincroniza con control explícito de conflictos.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            onClick={prepare}
            disabled={!online || busy}
            data-testid="teacher-offline-prepare"
            className="gap-2"
          >
            <Download className="h-4 w-4" />
            Preparar sin conexión
          </Button>
          <Button
            variant="secondary"
            onClick={sync}
            disabled={!online || pending === 0 || busy}
            data-testid="teacher-offline-sync"
            className="gap-2"
          >
            <RefreshCw className="h-4 w-4" />
            Sincronizar {pending || ""}
          </Button>
          <Button
            variant="ghost"
            onClick={() => window.location.assign("/api/v1/teacher/dashboard")}
            className="gap-2"
          >
            Consola completa
            <ExternalLink className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <Card>
          <CardContent className="pt-5">
            <div className="text-xs font-bold uppercase text-slate-400">Red</div>
            <div className="mt-2 flex items-center gap-2 font-semibold">
              {online ? (
                <Cloud className="h-4 w-4" />
              ) : (
                <CloudOff className="h-4 w-4" />
              )}
              {online ? "Disponible" : "Trabajo local"}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <div className="text-xs font-bold uppercase text-slate-400">
              Pendientes
            </div>
            <div
              className="mt-2 text-2xl font-bold"
              data-testid="teacher-offline-pending"
            >
              {pending}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <div className="text-xs font-bold uppercase text-slate-400">
              Conflictos
            </div>
            <div className="mt-2 text-2xl font-bold">{conflicts}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <div className="text-xs font-bold uppercase text-slate-400">
              Cache
            </div>
            <div className="mt-2 text-sm font-semibold">
              {!snapshot
                ? "No preparada"
                : expired
                  ? "Caducada"
                  : new Date(snapshot.expires_at).toLocaleString()}
            </div>
          </CardContent>
        </Card>
      </div>

      {message ? (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm">
          {message}
        </div>
      ) : null}

      {snapshot && expired ? (
        <div className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <AlertTriangle className="h-5 w-5" />
          La copia local superó 24 horas. No admite registros nuevos; todavía
          puedes sincronizar o resolver cambios pendientes.
        </div>
      ) : null}

      {!snapshot ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-slate-500">
            Usa <strong>Preparar sin conexión</strong> antes de salir de una zona
            con conectividad.
          </CardContent>
        </Card>
      ) : null}

      {snapshot ? (
        <Card>
          <CardHeader>
            <h2 className="font-bold">Clase y sesión</h2>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="text-sm font-semibold">
                Clase
                <select
                  className="mt-2 w-full rounded-xl border px-3 py-2"
                  value={classId}
                  onChange={(event) => {
                    setClassId(event.target.value);
                    setSessionId("");
                  }}
                  data-testid="teacher-class-select"
                >
                  {snapshot.classes.map((item) => (
                    <option
                      key={item.classroom.course_offering_id}
                      value={item.classroom.course_offering_id}
                    >
                      {item.classroom.grade_name} · {item.classroom.section_name} ·{" "}
                      {item.classroom.subject_name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm font-semibold">
                Sesión
                <select
                  className="mt-2 w-full rounded-xl border px-3 py-2"
                  value={sessionId}
                  onChange={(event) => setSessionId(event.target.value)}
                  data-testid="teacher-session-select"
                >
                  {(selectedClass?.sessions ?? []).map((item) => (
                    <option key={item.session.id} value={item.session.id}>
                      {item.session.session_date} · {item.session.starts_at.slice(0, 5)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {selectedSession && snapshot ? (
        <Card>
          <CardHeader>
            <h2 className="font-bold">Registro de asistencia</h2>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead>
                  <tr className="border-b text-xs uppercase text-slate-400">
                    <th className="px-2 py-3">Estudiante</th>
                    <th className="px-2 py-3">Estado</th>
                    <th className="px-2 py-3">Local</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedSession.attendance.map((row) => {
                    const target = teacherOfflineTargetKey(
                      selectedSession.session.id,
                      row.student_section_assignment_id,
                    );
                    const local = byTarget.get(target);
                    const effective = effectiveAttendanceRow(row, local);
                    return (
                      <tr
                        key={row.student_section_assignment_id}
                        className="border-b"
                      >
                        <td className="px-2 py-3">
                          <div className="font-semibold">{row.student_name}</div>
                          <div className="text-xs text-slate-400">
                            {row.student_code ?? "Sin código"}
                          </div>
                        </td>
                        <td className="px-2 py-3">
                          <select
                            className="w-full rounded-lg border px-3 py-2"
                            value={effective.attendance_code_id ?? ""}
                            disabled={expired || local?.status === "CONFLICT"}
                            onChange={(event) => void queue(row, event.target.value)}
                            data-testid={`attendance-select-${row.student_section_assignment_id}`}
                          >
                            <option value="" disabled>
                              Seleccionar
                            </option>
                            {snapshot.attendance_codes.map((code) => (
                              <option key={code.id} value={code.id}>
                                {code.code} · {code.label}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="px-2 py-3">
                          {!local ? (
                            <span className="text-xs text-slate-400">Servidor</span>
                          ) : local.status === "PENDING" ? (
                            <Badge tone="warning">Pendiente</Badge>
                          ) : (
                            <div className="space-y-2">
                              <Badge tone="warning">Conflicto</Badge>
                              <div className="text-xs text-slate-500">
                                {local.detail}
                              </div>
                              <div className="flex gap-2">
                                <Button
                                  variant="secondary"
                                  className="h-8 px-2 text-xs"
                                  disabled={!local.serverState}
                                  onClick={() => void acceptServer(local)}
                                >
                                  Usar servidor
                                </Button>
                                <Button
                                  variant="secondary"
                                  className="h-8 px-2 text-xs"
                                  disabled={!local.serverState}
                                  onClick={() => void retryLocal(local)}
                                >
                                  Reintentar local
                                </Button>
                                <Button
                                  variant="ghost"
                                  className="h-8 px-2 text-xs"
                                  onClick={() => void discard(local)}
                                >
                                  Descartar local
                                </Button>
                              </div>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="rounded-xl border bg-slate-50 p-4 text-xs text-slate-500">
        El Service Worker solo conserva el shell estático. Las respuestas
        autenticadas de /api/ nunca entran en CacheStorage; el token permanece
        únicamente en sessionStorage.
      </div>
    </div>
  );
}
