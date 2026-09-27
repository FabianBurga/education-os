import { useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAppContext } from "../app-context";
import {
  academicCapabilities,
  academicErrorMessage,
  createAcademicEntity,
  createPeriod,
  getAcademicCollection,
  getAcademicOptions,
  getAssignmentOptions,
  getPeriods,
  transitionPeriod,
  type AcademicEntity,
} from "../m28/academic-structure";

type Command =
  | { kind: "entity"; path: string; payload: Record<string, unknown> }
  | { kind: "period"; payload: { code: string; name: string; starts_on: string; ends_on: string } }
  | { kind: "period-status"; id: string; expected: string; target: "ACTIVE" | "CLOSED" };

function FormField({ label, value, onChange, type = "text", required = true }: {
  label: string; value: string; onChange: (value: string) => void; type?: string; required?: boolean;
}) {
  return <label className="grid gap-1 text-sm font-medium text-slate-700">{label}<input required={required} type={type} value={value} onChange={(event) => onChange(event.target.value)} className="min-w-0 rounded-lg border border-slate-300 px-3 py-2" /></label>;
}

function SelectField({ label, value, onChange, options }: {
  label: string; value: string; onChange: (value: string) => void; options: Array<{ id: string; label: string }>;
}) {
  return <label className="grid gap-1 text-sm font-medium text-slate-700">{label}<select required value={value} onChange={(event) => onChange(event.target.value)} className="min-w-0 rounded-lg border border-slate-300 bg-white px-3 py-2"><option value="">Selecciona…</option>{options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}</select></label>;
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="min-w-0 rounded-xl border border-slate-200 bg-white p-4" aria-label={title}><h2 className="mb-3 text-lg font-bold text-slate-900">{title}</h2>{children}</section>;
}

export function AcademicStructurePage() {
  const { bootstrap } = useAppContext();
  const capabilities = academicCapabilities(bootstrap.permissions);
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState({ code: "", name: "", starts_on: "", ends_on: "" });
  const [level, setLevel] = useState({ code: "", name: "" });
  const [grade, setGrade] = useState({ academic_level_id: "", code: "", name: "" });
  const [subject, setSubject] = useState({ code: "", name: "", area: "" });
  const [section, setSection] = useState({ academic_period_id: "", campus_id: "", grade_level_id: "", code: "", name: "" });
  const [offering, setOffering] = useState({ section_id: "", subject_id: "" });
  const [assignment, setAssignment] = useState({ course_offering_id: "", staff_profile_id: "" });
  const options = useQuery({ queryKey: ["m28-academic-options", bootstrap.tenant.institution_id], queryFn: getAcademicOptions, enabled: capabilities.canRead, retry: false });
  const periods = useQuery({ queryKey: ["m28-academic-periods", bootstrap.tenant.institution_id], queryFn: getPeriods, enabled: capabilities.canRead, retry: false });
  const levels = useQuery({ queryKey: ["m28-academic-levels", bootstrap.tenant.institution_id], queryFn: () => getAcademicCollection("levels"), enabled: capabilities.canRead, retry: false });
  const grades = useQuery({ queryKey: ["m28-academic-grades", bootstrap.tenant.institution_id], queryFn: () => getAcademicCollection("grades"), enabled: capabilities.canRead, retry: false });
  const subjects = useQuery({ queryKey: ["m28-academic-subjects", bootstrap.tenant.institution_id], queryFn: () => getAcademicCollection("subjects"), enabled: capabilities.canRead, retry: false });
  const sections = useQuery({ queryKey: ["m28-academic-sections", bootstrap.tenant.institution_id], queryFn: () => getAcademicCollection("sections"), enabled: capabilities.canRead, retry: false });
  const offerings = useQuery({ queryKey: ["m28-academic-offerings", bootstrap.tenant.institution_id], queryFn: () => getAcademicCollection("course-offerings"), enabled: capabilities.canRead, retry: false });
  const assignments = useQuery({ queryKey: ["m28-academic-assignments", bootstrap.tenant.institution_id], queryFn: () => getAcademicCollection("teaching-assignments"), enabled: capabilities.canRead && capabilities.canAssign, retry: false });
  const assignmentOptions = useQuery({ queryKey: ["m28-academic-assignment-options", bootstrap.tenant.institution_id], queryFn: getAssignmentOptions, enabled: capabilities.canRead && capabilities.canAssign, retry: false });
  const command = useMutation<AcademicEntity, unknown, Command>({
    mutationFn: (input) => input.kind === "period"
      ? createPeriod(input.payload)
      : input.kind === "period-status"
        ? transitionPeriod(input.id, input.expected, input.target)
        : createAcademicEntity(input.path, input.payload),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["m28-academic"] }); },
  });

  function submit(event: FormEvent, input: Command) { event.preventDefault(); command.mutate(input); }
  const periodOptions = (options.data?.periods ?? []).map((item) => ({ id: item.id, label: `${item.name} · ${item.status}` }));
  const campusOptions = (options.data?.campuses ?? []).map((item) => ({ id: item.id, label: item.name }));
  const levelOptions = (levels.data ?? []).map((item) => ({ id: item.id, label: `${item.name} (${item.code})` }));
  const gradeOptions = (grades.data ?? []).map((item) => ({ id: item.id, label: `${item.name} (${item.code})` }));
  const subjectOptions = (subjects.data ?? []).map((item) => ({ id: item.id, label: `${item.name} (${item.code})` }));
  const sectionOptions = (sections.data ?? []).map((item) => ({ id: item.id, label: `${item.name} (${item.code})` }));
  const offeringOptions = (offerings.data ?? []).map((item) => ({ id: item.id, label: item.id.slice(0, 8) }));
  const readError = [options, periods, levels, grades, subjects, sections, offerings].find((query) => query.isError)?.error;

  if (!capabilities.canRead) return <section role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-5 text-sm text-amber-950">La configuración académica requiere el permiso efectivo academics.read.</section>;

  return <main className="space-y-5" aria-labelledby="academic-structure-heading">
    <header><p className="text-xs font-bold uppercase tracking-wider text-slate-500">M28 · Configuración institucional</p><h1 id="academic-structure-heading" className="mt-1 text-2xl font-bold text-slate-950">Estructura académica</h1><p className="mt-2 text-sm text-slate-600">Períodos, niveles, secciones, asignaturas y ofertas reutilizan las autoridades M1/M2. La matrícula y la ubicación del estudiante permanecen separadas.</p></header>
    {periods.isPending || levels.isPending ? <p role="status" className="rounded-xl border bg-white p-4 text-sm text-slate-600">Cargando configuración académica…</p> : null}
    {readError ? <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{academicErrorMessage(readError)}</p> : null}
    {options.isError ? <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">No se pudieron cargar períodos y campus. {academicErrorMessage(options.error)}</p> : null}
    {command.error ? <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{academicErrorMessage(command.error)}</p> : null}
    {capabilities.canManage ? <div className="grid gap-4 lg:grid-cols-2">
      <Panel title="Períodos"><form className="grid gap-2 sm:grid-cols-2" onSubmit={(event) => submit(event, { kind: "period", payload: period })}><FormField label="Código" value={period.code} onChange={(code) => setPeriod({ ...period, code })}/><FormField label="Nombre" value={period.name} onChange={(name) => setPeriod({ ...period, name })}/><FormField label="Inicio" type="date" value={period.starts_on} onChange={(starts_on) => setPeriod({ ...period, starts_on })}/><FormField label="Fin" type="date" value={period.ends_on} onChange={(ends_on) => setPeriod({ ...period, ends_on })}/><button disabled={command.isPending} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Crear período planificado</button></form><ul className="mt-3 divide-y">{(periods.data ?? []).map((item) => <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"><span>{item.name} · {item.code} · {item.status}</span>{item.status === "PLANNED" ? <button type="button" disabled={command.isPending} onClick={() => command.mutate({ kind: "period-status", id: item.id, expected: item.status, target: "ACTIVE" })} className="rounded border px-2 py-1">Activar</button> : item.status === "ACTIVE" ? <button type="button" disabled={command.isPending} onClick={() => command.mutate({ kind: "period-status", id: item.id, expected: item.status, target: "CLOSED" })} className="rounded border px-2 py-1">Cerrar</button> : <span className="text-slate-500">Solo lectura</span>}</li>)}</ul></Panel>
      <Panel title="Niveles y grados"><form className="grid gap-2 sm:grid-cols-2" onSubmit={(event) => submit(event, { kind: "entity", path: "levels", payload: { ...level, sort_order: 0 } })}><FormField label="Código de nivel" value={level.code} onChange={(code) => setLevel({ ...level, code })}/><FormField label="Nombre de nivel" value={level.name} onChange={(name) => setLevel({ ...level, name })}/><button disabled={command.isPending} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Crear nivel</button></form><form className="mt-4 grid gap-2 sm:grid-cols-2" onSubmit={(event) => submit(event, { kind: "entity", path: "grades", payload: { ...grade, sort_order: 0 } })}><SelectField label="Nivel padre" value={grade.academic_level_id} onChange={(academic_level_id) => setGrade({ ...grade, academic_level_id })} options={levelOptions}/><FormField label="Código de grado" value={grade.code} onChange={(code) => setGrade({ ...grade, code })}/><FormField label="Nombre de grado" value={grade.name} onChange={(name) => setGrade({ ...grade, name })}/><button disabled={command.isPending} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Crear grado</button></form><p className="mt-3 text-xs text-slate-600">{levels.data?.length ?? 0} niveles · {grades.data?.length ?? 0} grados</p></Panel>
      <Panel title="Asignaturas"><form className="grid gap-2 sm:grid-cols-2" onSubmit={(event) => submit(event, { kind: "entity", path: "subjects", payload: { ...subject, area: subject.area || null } })}><FormField label="Código" value={subject.code} onChange={(code) => setSubject({ ...subject, code })}/><FormField label="Nombre" value={subject.name} onChange={(name) => setSubject({ ...subject, name })}/><FormField label="Área (opcional)" required={false} value={subject.area} onChange={(area) => setSubject({ ...subject, area })}/><button disabled={command.isPending} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Crear asignatura</button></form><ul className="mt-3 divide-y">{(subjects.data ?? []).map((item) => <li key={item.id} className="py-2 text-sm">{item.name} · {item.code}</li>)}</ul></Panel>
      <Panel title="Secciones"><form className="grid gap-2 sm:grid-cols-2" onSubmit={(event) => submit(event, { kind: "entity", path: "sections", payload: { ...section, capacity: 40, shift: null } })}><SelectField label="Período" value={section.academic_period_id} onChange={(academic_period_id) => setSection({ ...section, academic_period_id })} options={periodOptions}/><SelectField label="Campus" value={section.campus_id} onChange={(campus_id) => setSection({ ...section, campus_id })} options={campusOptions}/><SelectField label="Grado" value={section.grade_level_id} onChange={(grade_level_id) => setSection({ ...section, grade_level_id })} options={gradeOptions}/><FormField label="Código" value={section.code} onChange={(code) => setSection({ ...section, code })}/><FormField label="Nombre" value={section.name} onChange={(name) => setSection({ ...section, name })}/><button disabled={command.isPending || !periodOptions.length || !campusOptions.length || !gradeOptions.length} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Crear sección</button></form><ul className="mt-3 divide-y">{(sections.data ?? []).map((item) => <li key={item.id} className="py-2 text-sm">{item.name} · {item.code}</li>)}</ul></Panel>
      <Panel title="Ofertas de curso"><p className="mb-2 text-xs text-slate-600">Cada oferta vincula una sección y una asignatura existente; no crea una autoridad Course paralela.</p><form className="grid gap-2 sm:grid-cols-2" onSubmit={(event) => submit(event, { kind: "entity", path: "course-offerings", payload: offering })}><SelectField label="Sección" value={offering.section_id} onChange={(section_id) => setOffering({ ...offering, section_id })} options={sectionOptions}/><SelectField label="Asignatura" value={offering.subject_id} onChange={(subject_id) => setOffering({ ...offering, subject_id })} options={subjectOptions}/><button disabled={command.isPending} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Crear oferta</button></form><p className="mt-3 text-xs text-slate-600">{offerings.data?.length ?? 0} ofertas configuradas</p></Panel>
      {capabilities.canAssign ? <Panel title="Asignación docente"><form className="grid gap-2 sm:grid-cols-2" onSubmit={(event) => submit(event, { kind: "entity", path: "teaching-assignments", payload: { ...assignment, assignment_role: "LEAD" } })}><SelectField label="Oferta" value={assignment.course_offering_id} onChange={(course_offering_id) => setAssignment({ ...assignment, course_offering_id })} options={offeringOptions}/><SelectField label="Personal activo" value={assignment.staff_profile_id} onChange={(staff_profile_id) => setAssignment({ ...assignment, staff_profile_id })} options={assignmentOptions.data ?? []}/><button disabled={command.isPending} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Asignar docente</button></form><p className="mt-3 text-xs text-slate-600">La terminación y transferencia de asignaciones pertenece al slice posterior de continuidad de roster.</p>{assignments.isError ? <p role="alert" className="mt-2 text-sm text-rose-800">{academicErrorMessage(assignments.error)}</p> : null}</Panel> : null}
    </div> : <p className="rounded-lg border bg-white p-4 text-sm text-slate-700">Vista de solo lectura. Los comandos requieren academics.manage; asignar personal requiere academics.assign.</p>}
  </main>;
}
