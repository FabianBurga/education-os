import { CheckCircle2, FileSearch, History, Link2, ShieldAlert, Upload } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { useAppContext } from "../app-context";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import {
  CSV_IMPORT_CONTRACT,
  applyRun,
  canApplyPreview,
  canReadAuditEvents,
  createConnector,
  csvFileIsAccepted,
  getRun,
  integrationCapabilities,
  integrationErrorMessage,
  itemErrorMessage,
  listConnectors,
  listRunEvents,
  listRunItems,
  listRuns,
  previewStudentEnrollmentCsv,
  setConnectorStatus,
  type IntegrationRun,
} from "../m24/integrations";

function formatDate(value: string | null): string {
  return value ? new Intl.DateTimeFormat("es-EC", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

function short(value: string | null, size = 12): string { return value ? `${value.slice(0, size)}…` : "—"; }
function statusTone(status: string): "neutral" | "success" | "warning" | "danger" {
  if (status === "APPLIED" || status === "COMPLETED" || status === "VALID") return "success";
  if (status === "INVALID" || status === "CONFLICT" || status === "FAILED") return "danger";
  return "warning";
}

function Summary({ run }: { run: Pick<IntegrationRun, "total_rows" | "valid_rows" | "invalid_rows" | "conflict_rows" | "applied_rows" | "failed_rows"> }) {
  const cells = [["Total", run.total_rows], ["Válidas", run.valid_rows], ["Inválidas", run.invalid_rows], ["Conflictos", run.conflict_rows], ["Aplicadas", run.applied_rows], ["Fallidas", run.failed_rows]];
  return <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">{cells.map(([label, value]) => <div key={String(label)} className="rounded-xl bg-slate-50 p-3"><dt className="text-xs font-bold uppercase tracking-wide text-slate-400">{label}</dt><dd className="mt-1 text-xl font-bold text-slate-800">{value}</dd></div>)}</dl>;
}

function CsvContract() {
  return <div className="grid gap-4 text-sm sm:grid-cols-3"><div><h3 className="font-semibold text-slate-700">Límites</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-slate-600">{CSV_IMPORT_CONTRACT.limits.map(value => <li key={value}>{value}</li>)}</ul></div><div><h3 className="font-semibold text-slate-700">Campos requeridos</h3><ul className="mt-2 space-y-1 font-mono text-xs text-slate-600">{CSV_IMPORT_CONTRACT.required.map(value => <li key={value}>{value}</li>)}</ul></div><div><h3 className="font-semibold text-slate-700">Campos opcionales</h3><ul className="mt-2 space-y-1 font-mono text-xs text-slate-600">{CSV_IMPORT_CONTRACT.optional.map(value => <li key={value}>{value}</li>)}</ul></div></div>;
}

export function IntegrationWorkspacePage() {
  const { bootstrap } = useAppContext();
  const queryClient = useQueryClient();
  const capabilities = integrationCapabilities(bootstrap.permissions);
  const [connectorId, setConnectorId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [confirmApply, setConfirmApply] = useState(false);
  const [connectorKey, setConnectorKey] = useState("");
  const [connectorName, setConnectorName] = useState("");

  const connectors = useQuery({ queryKey: ["m24-connectors"], queryFn: listConnectors, enabled: capabilities.canView });
  const runs = useQuery({ queryKey: ["m24-runs"], queryFn: listRuns, enabled: capabilities.canView });
  const selectedConnector = useMemo(() => connectors.data?.find(value => value.id === connectorId) ?? connectors.data?.find(value => value.connector_type === "CSV_STUDENT_ENROLLMENT" && value.status === "ENABLED") ?? null, [connectorId, connectors.data]);
  const currentRunId = selectedRunId;
  const run = useQuery({ queryKey: ["m24-run", currentRunId], queryFn: () => getRun(currentRunId!), enabled: Boolean(currentRunId) && capabilities.canView });
  const items = useQuery({ queryKey: ["m24-run-items", currentRunId], queryFn: () => listRunItems(currentRunId!), enabled: Boolean(currentRunId) && capabilities.canView });
  const events = useQuery({ queryKey: ["m24-run-events", currentRunId], queryFn: () => listRunEvents(currentRunId!), enabled: canReadAuditEvents(capabilities.canAudit, currentRunId) });
  const refresh = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ["m24-connectors"] }),
    queryClient.invalidateQueries({ queryKey: ["m24-runs"] }),
    queryClient.invalidateQueries({ queryKey: ["m24-run"] }),
    queryClient.invalidateQueries({ queryKey: ["m24-run-items"] }),
    queryClient.invalidateQueries({ queryKey: ["m24-run-events"] }),
  ]);
  const create = useMutation({ mutationFn: () => createConnector({ connector_key: connectorKey.trim(), connector_type: "CSV_STUDENT_ENROLLMENT", display_name: connectorName.trim(), configuration: { workflow: "CSV_STUDENT_ENROLLMENT" } }), onSuccess: result => { setConnectorId(result.id); setConnectorKey(""); setConnectorName(""); refresh(); } });
  const changeConnector = useMutation({ mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => setConnectorStatus(id, enabled), onSuccess: refresh });
  const preview = useMutation({ mutationFn: () => previewStudentEnrollmentCsv(selectedConnector!.id, file!), onSuccess: result => { setSelectedRunId(result.run.id); setConfirmApply(false); refresh(); } });
  const apply = useMutation({ mutationFn: () => applyRun(currentRunId!), onSuccess: () => { setConfirmApply(false); refresh(); } });

  if (!capabilities.canView) return <Card><CardContent className="flex min-h-72 flex-col items-center justify-center p-6 text-center"><ShieldAlert className="h-11 w-11 text-rose-500" /><h1 className="mt-4 text-xl font-bold">Centro de integraciones no disponible</h1><p className="mt-2 text-sm text-slate-500">Tu contexto autenticado no posee integrations.view.</p></CardContent></Card>;
  const previewedRun = Boolean(preview.data && currentRunId === preview.data.run.id);
  const canPreview = capabilities.canRun && selectedConnector?.status === "ENABLED" && Boolean(file) && !fileError;
  const canApply = canApplyPreview(capabilities.canRun, preview.data?.run.id ?? null, currentRunId, run.data?.status);

  return <div className="space-y-5" data-testid="m24-integration-workspace">
    <div><div className="flex flex-wrap gap-2"><Badge tone="success">M24 · Centro de integraciones</Badge><Badge tone="neutral">CSV gobernado</Badge></div><h1 className="mt-3 text-3xl font-bold">Centro de integraciones</h1><p className="mt-2 max-w-3xl text-sm text-slate-600">La vista previa valida el archivo sin crear registros. La aplicación siempre requiere confirmación humana explícita.</p></div>

    <Card><CardHeader><h2 className="font-bold">Conectores</h2><p className="mt-1 text-sm text-slate-500">Definiciones de conectores visibles en este contexto institucional.</p></CardHeader><CardContent className="space-y-4">
      {connectors.isError ? <p className="text-sm text-rose-700">{integrationErrorMessage(connectors.error)}</p> : null}
      <div className="grid gap-3 lg:grid-cols-2">{connectors.data?.map(connector => <div key={connector.id} className="rounded-xl border border-slate-200 p-4"><div className="flex items-start justify-between gap-3"><div><div className="font-semibold text-slate-800">{connector.display_name}</div><div className="mt-1 font-mono text-xs text-slate-500">{connector.connector_key}</div></div><Badge tone={connector.status === "ENABLED" ? "success" : "warning"}>{connector.status}</Badge></div><div className="mt-3 text-xs text-slate-500">{connector.connector_type} · configuración v{connector.config_version} · {formatDate(connector.created_at)}</div>{capabilities.canManage ? <div className="mt-3 flex gap-2"><Button variant="secondary" className="h-8 px-3 text-xs" disabled={connector.status === "ENABLED" || changeConnector.isPending} onClick={() => changeConnector.mutate({ id: connector.id, enabled: true })}>Habilitar</Button><Button variant="secondary" className="h-8 px-3 text-xs" disabled={connector.status === "DISABLED" || changeConnector.isPending} onClick={() => changeConnector.mutate({ id: connector.id, enabled: false })}>Deshabilitar</Button></div> : null}</div>)}</div>
      {!connectors.isPending && !connectors.data?.length ? <p className="text-sm text-slate-500">No hay conectores visibles.</p> : null}
      {capabilities.canManage ? <form className="grid gap-3 rounded-xl bg-slate-50 p-4 sm:grid-cols-[1fr_1fr_auto]" onSubmit={event => { event.preventDefault(); create.mutate(); }}><label className="text-sm font-semibold text-slate-700">Clave<input required value={connectorKey} onChange={event => setConnectorKey(event.target.value)} placeholder="institucion.csv" className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 font-mono text-sm font-normal" /></label><label className="text-sm font-semibold text-slate-700">Nombre<input required value={connectorName} onChange={event => setConnectorName(event.target.value)} placeholder="Importación CSV" className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal" /></label><Button type="submit" className="self-end" disabled={create.isPending || !connectorKey.trim() || !connectorName.trim()}><Link2 className="mr-2 h-4 w-4" />Crear CSV</Button>{create.isError ? <p className="text-sm text-rose-700 sm:col-span-3">{integrationErrorMessage(create.error)}</p> : null}</form> : null}
    </CardContent></Card>

    <Card><CardHeader><h2 className="font-bold">Nueva importación CSV de estudiantes y matrícula</h2><p className="mt-1 text-sm text-slate-500">Validación en seco: no crea personas, estudiantes ni matrículas.</p></CardHeader><CardContent className="space-y-5"><CsvContract />
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]"><label className="text-sm font-semibold text-slate-700">Archivo CSV<input type="file" accept=".csv,text/csv" className="mt-1 block w-full text-sm font-normal text-slate-600" onChange={event => { const next = event.target.files?.[0] ?? null; setFile(next); setFileError(next && !csvFileIsAccepted(next) ? "Selecciona un archivo .csv de hasta 1 MB." : null); }} /></label><label className="text-sm font-semibold text-slate-700">Conector<select value={selectedConnector?.id ?? ""} onChange={event => setConnectorId(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal">{connectors.data?.filter(value => value.connector_type === "CSV_STUDENT_ENROLLMENT").map(value => <option key={value.id} value={value.id}>{value.display_name} · {value.status}</option>)}</select></label></div>
      {file ? <p className="text-sm text-slate-600">Archivo seleccionado: <span className="font-semibold">{file.name}</span> ({Math.ceil(file.size / 1024)} KB)</p> : null}{fileError ? <p className="text-sm text-rose-700">{fileError}</p> : null}
      {!capabilities.canRun ? <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-600">Tu contexto puede consultar integraciones, pero no ejecutar vistas previas ni aplicaciones.</p> : <Button disabled={!canPreview || preview.isPending} onClick={() => preview.mutate()} data-testid="m24-preview"><FileSearch className="mr-2 h-4 w-4" />{preview.isPending ? "Validando…" : "Vista previa y validación"}</Button>}{preview.isError ? <p className="text-sm text-rose-700">{integrationErrorMessage(preview.error)}</p> : null}
    </CardContent></Card>

    <Card><CardHeader><h2 className="font-bold">Historial de ejecuciones</h2><p className="mt-1 text-sm text-slate-500">Ordenado por el backend, de más reciente a más antiguo.</p></CardHeader><CardContent>{runs.isPending ? <p className="text-sm text-slate-500">Cargando ejecuciones…</p> : runs.isError ? <p className="text-sm text-rose-700">{integrationErrorMessage(runs.error)}</p> : <div className="space-y-2">{runs.data?.map(value => <button key={value.id} type="button" onClick={() => { setSelectedRunId(value.id); setConfirmApply(false); }} className="w-full rounded-xl border border-slate-200 p-3 text-left hover:bg-slate-50"><div className="flex flex-wrap items-center gap-2"><Badge tone={statusTone(value.status)}>{value.status}</Badge><span className="font-semibold text-slate-800">{value.connector_display_name}</span><span className="font-mono text-xs text-slate-500">{short(value.id)}</span></div><div className="mt-2 grid gap-1 text-xs text-slate-500 sm:grid-cols-4"><span>{value.source_filename ?? "Archivo no registrado"}</span><span>SHA {short(value.source_fingerprint_sha256)}</span><span>{formatDate(value.created_at)}</span><span>Actor {short(value.initiated_by_user_id)}</span></div><div className="mt-2 text-xs text-slate-600">Total {value.total_rows} · Válidas {value.valid_rows} · Inválidas {value.invalid_rows} · Conflictos {value.conflict_rows} · Aplicadas {value.applied_rows} · Fallidas {value.failed_rows}</div></button>)}{!runs.data?.length ? <p className="text-sm text-slate-500">No hay ejecuciones visibles.</p> : null}</div>}</CardContent></Card>

    {currentRunId ? <Card data-testid="m24-run-detail"><CardHeader><h2 className="font-bold">Detalle de ejecución</h2><p className="mt-1 text-sm text-slate-500">Proveniencia e impactos reportados por el backend.</p></CardHeader><CardContent className="space-y-5">{run.isPending ? <p className="text-sm text-slate-500">Cargando detalle…</p> : run.isError ? <p className="text-sm text-rose-700">{integrationErrorMessage(run.error)}</p> : run.data ? <><div className="flex flex-wrap gap-2"><Badge tone={statusTone(run.data.status)}>{run.data.status}</Badge>{previewedRun && run.data.status !== "VALIDATED" ? <Badge tone="warning">Esta entrada ya corresponde a una ejecución existente</Badge> : null}</div><Summary run={run.data} /><div className="grid gap-3 rounded-xl bg-slate-50 p-4 text-sm sm:grid-cols-2"><div><span className="text-slate-500">Conector</span><div className="font-semibold">{run.data.connector_display_name}</div></div><div><span className="text-slate-500">Archivo</span><div className="font-semibold">{run.data.source_filename ?? "No registrado"}</div></div><div><span className="text-slate-500">SHA-256</span><div className="break-all font-mono text-xs">{run.data.source_fingerprint_sha256}</div></div><div><span className="text-slate-500">Configuración / modo</span><div className="font-semibold">v{run.data.connector_config_version} · {run.data.mode}</div></div><div><span className="text-slate-500">Actor</span><div className="break-all font-mono text-xs">{run.data.initiated_by_user_id}</div></div><div><span className="text-slate-500">Creado</span><div className="font-semibold">{formatDate(run.data.created_at)}</div></div></div>
      {canApply ? <div className="rounded-xl border border-amber-200 bg-amber-50 p-4"><p className="text-sm font-semibold text-amber-900">Solo las filas válidas serán aplicadas. Las filas inválidas o en conflicto permanecerán sin cambios.</p><p className="mt-1 text-sm text-amber-800">Válidas: {run.data.valid_rows} · Inválidas: {run.data.invalid_rows} · Conflictos: {run.data.conflict_rows}</p>{confirmApply ? <div className="mt-3 flex flex-wrap gap-2"><Button disabled={apply.isPending} onClick={() => apply.mutate()} data-testid="m24-confirm-apply"><CheckCircle2 className="mr-2 h-4 w-4" />{apply.isPending ? "Aplicando…" : "Confirmar aplicación"}</Button><Button variant="secondary" disabled={apply.isPending} onClick={() => setConfirmApply(false)}>Cancelar</Button></div> : <Button className="mt-3" onClick={() => setConfirmApply(true)} data-testid="m24-request-apply">Aplicar filas válidas</Button>}{apply.isError ? <p className="mt-2 text-sm text-rose-700">{integrationErrorMessage(apply.error)}</p> : null}</div> : null}
      <div><h3 className="font-bold text-slate-800">Filas procesadas</h3><div className="mt-3 overflow-x-auto"><table className="min-w-full text-left text-sm"><thead className="border-b border-slate-200 text-xs uppercase text-slate-400"><tr><th className="p-2">Fila</th><th className="p-2">ID externo</th><th className="p-2">Estado</th><th className="p-2">Validación</th><th className="p-2">IDs canónicos</th></tr></thead><tbody>{items.data?.map(item => <tr key={item.id} className="border-b border-slate-100 align-top"><td className="p-2">{item.source_row_number ?? "—"}</td><td className="p-2 font-mono text-xs">{item.external_student_id ?? "—"}</td><td className="p-2"><Badge tone={statusTone(item.status)}>{item.status}</Badge></td><td className="p-2 text-xs text-slate-600">{itemErrorMessage(item.error_code) ?? "Sin error"}</td><td className="p-2 break-all font-mono text-xs text-slate-600">{item.student_profile_id ? <>Estudiante: {item.student_profile_id}<br /></> : null}{item.enrollment_id ? <>Matrícula: {item.enrollment_id}</> : "—"}</td></tr>)}{!items.data?.length ? <tr><td colSpan={5} className="p-4 text-center text-slate-500">No hay filas visibles.</td></tr> : null}</tbody></table></div></div>
      {capabilities.canAudit ? <div><h3 className="flex items-center gap-2 font-bold text-slate-800"><History className="h-4 w-4" />Eventos de ciclo de vida</h3>{events.isPending ? <p className="mt-2 text-sm text-slate-500">Cargando eventos…</p> : events.isError ? <p className="mt-2 text-sm text-rose-700">{integrationErrorMessage(events.error)}</p> : <ol className="mt-3 space-y-2">{events.data?.map(event => <li key={event.sequence} className="rounded-xl bg-slate-50 p-3 text-sm"><div className="flex flex-wrap gap-2"><Badge tone={statusTone(event.event_type)}>{event.event_type}</Badge><span className="text-slate-500">{formatDate(event.created_at)}</span></div><div className="mt-2 text-xs text-slate-600">{event.metadata.source_filename ? <>Archivo: {event.metadata.source_filename} </> : null}{event.metadata.external_student_id ? <>· ID externo: {event.metadata.external_student_id} </> : null}{event.metadata.error_code ? <>· Código: {event.metadata.error_code}</> : null}{event.actor_user_id ? <span className="ml-2 font-mono">Actor: {short(event.actor_user_id)}</span> : null}</div></li>)}</ol>}</div> : null}</> : null}</CardContent></Card> : null}
  </div>;
}
