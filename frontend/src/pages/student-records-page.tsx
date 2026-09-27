import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../lib/api";
import { useAppContext } from "../app-context";
import {
  getStudentRecord,
  getStudentRecords,
  studentRecordCapabilities,
  studentRecordErrorMessage,
  updateStudentRecord,
  type StudentRecord,
} from "../m28/student-records";

export function StudentRecordsPage() {
  const { bootstrap } = useAppContext();
  const capabilities = studentRecordCapabilities(bootstrap.permissions);
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
        {detail.data ? <StudentRecordEditor key={`${detail.data.id}:${detail.data.updated_at}`} record={detail.data} canManage={capabilities.canManage} saving={update.isPending} error={update.error ? studentRecordErrorMessage(update.error) : null} onSave={(input) => update.mutate(input)} /> : null}
      </section>
    </div>
  </main>;
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
