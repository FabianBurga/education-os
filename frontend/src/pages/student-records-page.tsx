import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../lib/api";
import { useAppContext } from "../app-context";
import {
  getStudentRecord,
  getStudentRecords,
  getStudentEnrollments,
  getEnrollmentOptions,
  createEnrollment,
  enrollmentCapabilities,
  getEnrollmentHistory,
  studentRecordCapabilities,
  studentRecordErrorMessage,
  transitionEnrollment,
  updateStudentRecord,
  type StudentRecord,
} from "../m28/student-records";

export function StudentRecordsPage() {
  const { bootstrap } = useAppContext();
  const capabilities = studentRecordCapabilities(bootstrap.permissions);
  const enrollmentAccess = enrollmentCapabilities(bootstrap.permissions);
  const queryClient = useQueryClient();
  const [cursor, setCursor] = useState<string | null>(null);
  const [items, setItems] = useState<StudentRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const page = useQuery({
    queryKey: ["m28-student-records", bootstrap.tenant.institution_id, cursor],
    queryFn: () => getStudentRecords(cursor),
    enabled: capabilities.canRead,
    retry: false,
  });
  const detail = useQuery({
    queryKey: ["m28-student-record", bootstrap.tenant.institution_id, selectedId],
    queryFn: () => getStudentRecord(selectedId!),
    enabled: capabilities.canRead && selectedId !== null,
    retry: false,
  });

  useEffect(() => {
    if (!page.data) return;
    setItems((current) => {
      if (!cursor) return page.data.items;
      const known = new Set(current.map((item) => item.id));
      return [...current, ...page.data.items.filter((item) => !known.has(item.id))];
    });
  }, [cursor, page.data]);

  const update = useMutation({
    mutationFn: (input: Pick<StudentRecord, "student_code" | "status"> & { expected_updated_at: string }) =>
      updateStudentRecord(selectedId!, input),
    onSuccess: async (saved) => {
      setItems((current) => current.map((item) => item.id === saved.id ? saved : item));
      await queryClient.invalidateQueries({ queryKey: ["m28-student-records"] });
      await queryClient.invalidateQueries({ queryKey: ["m28-student-record"] });
    },
    onError: async (error) => {
      if (error instanceof ApiError && error.status === 409) {
        await queryClient.invalidateQueries({ queryKey: ["m28-student-record"] });
        await queryClient.invalidateQueries({ queryKey: ["m28-student-records"] });
      }
    },
  });

  if (!capabilities.canRead) {
    return <section role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-5 text-sm text-amber-950">No tienes el permiso efectivo students.read para consultar registros estudiantiles.</section>;
  }

  return <main className="space-y-5" aria-labelledby="student-records-heading">
    <header>
      <p className="text-xs font-bold uppercase tracking-wider text-slate-500">M28 · Administración operativa</p>
      <h1 id="student-records-heading" className="mt-1 text-2xl font-bold text-slate-950">Registros estudiantiles</h1>
      <p className="mt-2 text-sm text-slate-600">Identidad mínima de la institución activa. Matrícula y ubicación académica se gestionan por separado.</p>
    </header>
    {page.isPending ? <p role="status" className="rounded-xl border bg-white p-5 text-sm text-slate-600">Cargando registros…</p> : null}
    {page.isError ? <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-900">{studentRecordErrorMessage(page.error)}</p> : null}
    {!page.isPending && !page.isError && items.length === 0 ? <p className="rounded-xl border bg-white p-6 text-sm text-slate-600">No hay registros estudiantiles en esta institución.</p> : null}
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.85fr)]">
      <section aria-label="Lista de estudiantes" className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <ul className="divide-y divide-slate-100">{items.map((item) => <li key={item.id}>
          <button type="button" onClick={() => setSelectedId(item.id)} aria-current={selectedId === item.id ? "true" : undefined} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700">
            <span className="min-w-0"><span className="block truncate text-sm font-semibold text-slate-900">{item.display_name}</span><span className="text-xs text-slate-500">{item.student_code || "Sin código"}</span></span>
            <span className="shrink-0 rounded-full border px-2 py-1 text-xs font-medium">{item.status}</span>
          </button>
        </li>)}</ul>
        {page.data?.next_cursor ? <div className="border-t p-3"><button type="button" onClick={() => setCursor(page.data?.next_cursor ?? null)} disabled={page.isFetching} className="rounded-lg border px-3 py-2 text-sm font-semibold disabled:opacity-50">{page.isFetching ? "Cargando…" : "Cargar más"}</button></div> : null}
      </section>
      <section aria-label="Detalle estudiantil" className="min-w-0 rounded-xl border border-slate-200 bg-white p-5">
        {!selectedId ? <p className="text-sm text-slate-500">Selecciona un registro para consultar o editar sus campos permitidos.</p> : null}
        {selectedId && detail.isPending ? <p role="status" className="text-sm text-slate-500">Cargando detalle…</p> : null}
        {selectedId && detail.isError ? <p role="alert" className="text-sm text-rose-800">{studentRecordErrorMessage(detail.error)}</p> : null}
        {detail.data ? <>
          <StudentRecordEditor key={`${detail.data.id}:${detail.data.updated_at}`} record={detail.data} canManage={capabilities.canManage} saving={update.isPending} error={update.error ? studentRecordErrorMessage(update.error) : null} onSave={(input) => update.mutate(input)} />
          {enrollmentAccess.canRead
            ? <EnrollmentPanel studentId={detail.data.id} canManage={enrollmentAccess.canManage} />
            : <p className="mt-6 border-t pt-4 text-xs text-slate-600">La lectura de matrículas e historial requiere enrollments.read.</p>}
        </> : null}
      </section>
    </div>
  </main>;
}

function EnrollmentPanel({ studentId, canManage }: { studentId: string; canManage: boolean }) {
  const client = useQueryClient();
  const enrollments = useQuery({
    queryKey: ["m28-enrollments", studentId],
    queryFn: () => getStudentEnrollments(studentId),
    retry: false,
  });
  const options = useQuery({
    queryKey: ["m28-enrollment-options"],
    queryFn: getEnrollmentOptions,
    enabled: canManage,
    retry: false,
  });
  const command = useMutation({
    mutationFn: (input: { id: string; status: string; expected_updated_at: string; effective_on: string | null; reason_code: string | null }) => {
      const { id, ...body } = input;
      return transitionEnrollment(id, body);
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["m28-enrollments", studentId] });
      await client.invalidateQueries({ queryKey: ["m28-enrollment-history"] });
    },
    onError: async (error) => {
      if (error instanceof ApiError && error.status === 409) {
        await client.invalidateQueries({ queryKey: ["m28-enrollments", studentId] });
      }
    },
  });
  const create = useMutation({
    mutationFn: createEnrollment,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["m28-enrollments", studentId] });
    },
  });
  const [effectiveOn, setEffectiveOn] = useState("");
  const [createEffectiveOn, setCreateEffectiveOn] = useState("");
  const [reasonCode, setReasonCode] = useState("");
  const [periodId, setPeriodId] = useState("");
  const [campusId, setCampusId] = useState("");
  const [enrollmentNumber, setEnrollmentNumber] = useState("");
  const [initialStatus, setInitialStatus] = useState<"PENDING" | "ACTIVE">("PENDING");

  return <section aria-labelledby="enrollment-heading" className="mt-6 border-t border-slate-200 pt-5">
    <h3 id="enrollment-heading" className="text-base font-bold text-slate-900">Matrículas e trayectoria</h3>
    {enrollments.isPending ? <p role="status" className="mt-2 text-sm text-slate-600">Cargando matrículas…</p> : null}
    {enrollments.isError ? <p role="alert" className="mt-2 text-sm text-rose-800">{studentRecordErrorMessage(enrollments.error)}</p> : null}
    {enrollments.data?.length === 0 ? <p className="mt-2 text-sm text-slate-600">No hay matrículas registradas.</p> : null}
    {canManage ? <form className="mt-3 grid gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3" onSubmit={(event) => {
      event.preventDefault();
      if (!periodId || !campusId) return;
      create.mutate({ student_profile_id: studentId, academic_period_id: periodId, campus_id: campusId, enrollment_number: enrollmentNumber.trim() || null, status: initialStatus, enrolled_on: createEffectiveOn || null });
    }}>
      <h4 className="text-sm font-semibold">Nueva matrícula</h4>
      {options.isPending ? <p role="status" className="text-xs text-slate-600">Cargando períodos y campus…</p> : null}
      {options.isError ? <p role="alert" className="text-xs text-rose-800">{studentRecordErrorMessage(options.error)}</p> : null}
      {options.data ? <>
        <label className="text-xs font-medium">Período<select aria-label="Período académico" required value={periodId} onChange={(event) => setPeriodId(event.target.value)} className="mt-1 block w-full rounded border px-2 py-1.5"><option value="">Selecciona un período</option>{options.data.periods.map((period) => <option key={period.id} value={period.id}>{period.name} · {period.code} · {period.status}</option>)}</select></label>
        <label className="text-xs font-medium">Campus<select aria-label="Campus" required value={campusId} onChange={(event) => setCampusId(event.target.value)} className="mt-1 block w-full rounded border px-2 py-1.5"><option value="">Selecciona un campus</option>{options.data.campuses.map((campus) => <option key={campus.id} value={campus.id}>{campus.name}</option>)}</select></label>
        <label className="text-xs font-medium">Número de matrícula (opcional)<input maxLength={64} value={enrollmentNumber} onChange={(event) => setEnrollmentNumber(event.target.value)} className="mt-1 block w-full rounded border px-2 py-1.5" /></label>
        <label className="text-xs font-medium">Estado inicial<select aria-label="Estado inicial de matrícula" value={initialStatus} onChange={(event) => setInitialStatus(event.target.value as "PENDING" | "ACTIVE")} className="mt-1 block w-full rounded border px-2 py-1.5"><option value="PENDING">Pendiente</option><option value="ACTIVE">Activa</option></select></label>
        <label className="text-xs font-medium">Fecha de inicio<input type="date" value={createEffectiveOn} onChange={(event) => setCreateEffectiveOn(event.target.value)} className="mt-1 block w-full rounded border px-2 py-1.5" /></label>
        <button type="submit" disabled={create.isPending || !options.data.periods.length || !options.data.campuses.length} className="justify-self-start rounded bg-slate-900 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{create.isPending ? "Guardando…" : "Crear matrícula"}</button>
      </> : null}
      {create.error ? <p role="alert" className="text-xs text-rose-800">{studentRecordErrorMessage(create.error)}</p> : null}
    </form> : null}
    {options.data && canManage && (!options.data.periods.length || !options.data.campuses.length) ? <p className="mt-2 text-xs text-amber-800">Configura un período no cerrado y un campus antes de crear matrículas.</p> : null}
    <ul className="mt-3 space-y-3">{enrollments.data?.map((item) => <li key={item.id} className="rounded-lg border border-slate-200 p-3">
      <p className="text-sm font-semibold text-slate-900">{item.status} · {item.academic_period_name} ({item.academic_period_code})</p>
      <p className="mt-1 text-xs text-slate-600">Inicio: {item.enrolled_on ?? "sin fecha"} · Retiro: {item.withdrawn_on ?? "—"}</p>
      <p className="mt-1 text-xs text-slate-500">Registro histórico: {item.id}</p>
      {canManage && item.allowed_actions.length > 0 ? <div className="mt-3 space-y-2">
        <label className="block text-xs font-medium text-slate-700">Fecha efectiva (según transición)<input type="date" value={effectiveOn} onChange={(event) => setEffectiveOn(event.target.value)} disabled={command.isPending} className="mt-1 block w-full rounded border px-2 py-1.5" /></label>
        <label className="block text-xs font-medium text-slate-700">Código de motivo cuando corresponda<input maxLength={40} pattern="[A-Z][A-Z0-9_]{1,39}" value={reasonCode} onChange={(event) => setReasonCode(event.target.value.toUpperCase())} placeholder="EJEMPLO_ADMINISTRATIVO" disabled={command.isPending} className="mt-1 block w-full rounded border px-2 py-1.5" /></label>
        <div className="flex flex-wrap gap-2">{item.allowed_actions.map((action) => <button key={action} type="button" disabled={command.isPending} onClick={() => command.mutate({ id: item.id, status: action, expected_updated_at: item.updated_at, effective_on: effectiveOn || null, reason_code: reasonCode || null })} className="rounded border border-slate-300 px-3 py-1.5 text-xs font-semibold disabled:opacity-50">{enrollmentActionLabel(action)}</button>)}</div>
      </div> : null}
      <EnrollmentHistory enrollmentId={item.id} />
    </li>)}</ul>
    {command.error ? <p role="alert" className="mt-3 text-sm text-rose-800">{studentRecordErrorMessage(command.error)}</p> : null}
    {enrollments.data?.length && !canManage ? <p className="mt-2 text-xs text-slate-600">Solo lectura; las transiciones requieren enrollments.manage.</p> : null}
  </section>;
}

function EnrollmentHistory({ enrollmentId }: { enrollmentId: string }) {
  const [expanded, setExpanded] = useState(false);
  const history = useQuery({
    queryKey: ["m28-enrollment-history", enrollmentId],
    queryFn: () => getEnrollmentHistory(enrollmentId),
    enabled: expanded,
    retry: false,
  });
  return <div className="mt-3 border-t border-slate-100 pt-2">
    <button type="button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)} className="text-xs font-semibold text-blue-800 underline">{expanded ? "Ocultar historial" : "Ver historial de estados"}</button>
    {expanded && history.isPending ? <p role="status" className="mt-2 text-xs text-slate-600">Cargando historial…</p> : null}
    {expanded && history.isError ? <p role="alert" className="mt-2 text-xs text-rose-800">{studentRecordErrorMessage(history.error)}</p> : null}
    {expanded && history.data?.length === 0 ? <p className="mt-2 text-xs text-slate-600">Aún no hay transiciones registradas.</p> : null}
    {expanded ? <ol className="mt-2 space-y-2">{history.data?.map((entry) => <li key={entry.id} className="text-xs text-slate-700">
      <span className="font-medium">{String(entry.details.from_status ?? "—")} → {String(entry.details.to_status ?? "CREATED")}</span>
      <span className="ml-2">{String(entry.details.effective_on ?? "")}</span>
      <span className="ml-2 text-slate-500">{entry.created_at} · actor {entry.actor_user_id ?? "sistema"}</span>
    </li>)}</ol> : null}
  </div>;
}

function enrollmentActionLabel(action: string): string {
  const labels: Record<string, string> = {
    ACTIVE: "Activar / reanudar",
    WITHDRAWN: "Registrar retiro",
    COMPLETED: "Completar",
    CANCELLED: "Cancelar pendiente",
  };
  return labels[action] ?? action;
}

export function StudentRecordEditor({ record, canManage, saving, error, onSave }: {
  record: StudentRecord;
  canManage: boolean;
  saving: boolean;
  error: string | null;
  onSave: (input: Pick<StudentRecord, "student_code" | "status"> & { expected_updated_at: string }) => void;
}) {
  const [code, setCode] = useState(record.student_code ?? "");
  const [status, setStatus] = useState<StudentRecord["status"]>(record.status);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSave({ student_code: code.trim() || null, status, expected_updated_at: record.updated_at });
  }
  return <form className="space-y-4" onSubmit={submit}>
    <div><h2 className="text-lg font-bold text-slate-900">{record.display_name}</h2><p className="text-xs text-slate-500">Identificador de perfil: {record.id}</p></div>
    <label className="block text-sm font-medium text-slate-700">Código estudiantil<input aria-label="Código estudiantil" maxLength={64} value={code} onChange={(event) => setCode(event.target.value)} disabled={!canManage || saving} className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
    <label className="block text-sm font-medium text-slate-700">Estado del perfil<select aria-label="Estado del perfil" value={status} onChange={(event) => setStatus(event.target.value as StudentRecord["status"])} disabled={!canManage || saving} className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"><option value="ACTIVE">Activo</option><option value="INACTIVE">Inactivo</option><option value="ARCHIVED">Archivado</option></select></label>
    {error ? <p role="alert" className="text-sm text-rose-800">{error}</p> : null}
    {canManage ? <button type="submit" disabled={saving} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{saving ? "Guardando…" : "Guardar cambios"}</button> : <p className="text-sm text-slate-600">Tienes acceso de lectura; la edición requiere students.manage.</p>}
  </form>;
}
