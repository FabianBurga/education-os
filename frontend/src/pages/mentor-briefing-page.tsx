import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAppContext } from "../app-context";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader } from "../components/ui/card";
import {
  canUseMentor, FOCUS_LABELS, freshnessLabel, MENTOR_FOCUSES, mentorErrorMessage,
  mentorQueryOptions, type BriefingFocus, type MentorBriefing,
} from "../m26/mentor";

export interface MentorViewProps {
  focus: BriefingFocus;
  onFocus: (focus: BriefingFocus) => void;
  onRefresh: () => void;
  loading: boolean;
  allowed: boolean;
  error?: unknown;
  briefing?: MentorBriefing;
}

export function MentorBriefingView({ focus, onFocus, onRefresh, loading, allowed, error, briefing }: MentorViewProps) {
  const visible = allowed && !loading && !error ? briefing : undefined;
  return <Card className="min-w-0" data-testid="m26-mentor">
    <CardHeader>
      <h2 className="text-xl font-bold text-slate-950">Mentor institucional</h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">Un panorama para comprender lo que ocurre y orientar la revisión humana. Las decisiones siguen en tus manos.</p>
    </CardHeader>
    <CardContent className="space-y-5">
      {allowed ? <div className="flex flex-wrap gap-2" role="group" aria-label="Enfoque del resumen">
        {MENTOR_FOCUSES.map(value => <Button key={value} variant={focus === value ? "primary" : "secondary"}
          aria-pressed={focus === value} onClick={() => onFocus(value)}>{FOCUS_LABELS[value]}</Button>)}
      </div> : null}
      <div aria-live="polite" aria-atomic="true" aria-busy={allowed && loading} className="min-w-0 space-y-5 break-words [overflow-wrap:anywhere]">
        {!allowed ? <p role="status" className="text-sm text-slate-700">El resumen no está disponible con tus permisos actuales.</p>
          : loading ? <p role="status" className="text-sm text-slate-600">Preparando el resumen institucional…</p>
          : error ? <p role="status" className="text-sm text-slate-700">{mentorErrorMessage(error)}</p>
          : !visible ? <p role="status" className="text-sm text-slate-600">No hay un resumen disponible.</p> : null}
        {visible ? <>
          <div className="flex flex-wrap items-center gap-3">
            <Badge tone={visible.freshness === "CURRENT" ? "success" : "warning"}>{freshnessLabel(visible.freshness)}</Badge>
            <p className="text-sm text-slate-600">Fecha de la evidencia: <time dateTime={visible.snapshot_date}>{visible.snapshot_date}</time></p>
          </div>
          {visible.freshness !== "CURRENT" ? <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">La evidencia no corresponde al día actual. Revisa su fecha antes de tomar decisiones.</p> : null}
          <section aria-label="Resumen"><h3 className="font-bold text-slate-900">{FOCUS_LABELS[focus]}</h3><p className="mt-2 whitespace-pre-wrap text-base leading-7 text-slate-800">{visible.summary}</p></section>
          <section><h3 className="font-bold text-slate-900">{focus === "FOLLOW_UPS" ? "Áreas para revisión humana" : "Hallazgos principales"}</h3>
            <ul className="mt-3 space-y-3">{visible.key_findings.map((finding, index) => <li key={index} className="rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-700">
              <p className="whitespace-pre-wrap">{finding.text}</p><p className="mt-2 text-xs font-semibold text-slate-600">Fuente: evidencia institucional 1</p>
            </li>)}</ul>
          </section>
          <section><h3 className="font-bold text-slate-900">Alcance y cautelas</h3><ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-600">{visible.caveats.map((caveat, index) => <li key={index}>{caveat}</li>)}</ul></section>
          <section className="rounded-xl border border-slate-200 p-4"><h3 className="font-bold text-slate-900">Evidencia institucional 1</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">Resumen agregado de inteligencia institucional autorizado para tu contexto. Fecha: <time dateTime={visible.snapshot_date}>{visible.snapshot_date}</time>.</p>
            <p className="mt-2 text-sm leading-6 text-slate-600">{visible.explanation_mode === "DETERMINISTIC_FALLBACK" ? "Resumen generado a partir de datos institucionales disponibles." : "Explicación asistida y verificada a partir de evidencia institucional."}</p>
          </section>
        </> : null}
      </div>
      {allowed ? <Button variant="secondary" disabled={loading} onClick={onRefresh}>Actualizar resumen</Button> : null}
    </CardContent>
  </Card>;
}

function MentorBriefingSession() {
  const { bootstrap } = useAppContext();
  const [focus, setFocus] = useState<BriefingFocus>("OVERVIEW");
  const query = useQuery(mentorQueryOptions(bootstrap, focus));
  return <MentorBriefingView focus={focus} onFocus={setFocus} onRefresh={() => { void query.refetch(); }}
    allowed={canUseMentor(bootstrap.permissions)} loading={query.isPending || query.isFetching}
    error={query.error} briefing={query.data} />;
}

export function MentorBriefingPanel() {
  const { bootstrap } = useAppContext();
  // Remount on context changes: no old focus/result may follow another principal/tenant.
  return <MentorBriefingSession key={JSON.stringify([bootstrap.tenant, bootstrap.user.user_id, bootstrap.permissions])} />;
}

export function MentorBriefingPage() {
  return <div className="space-y-5"><h1 className="text-3xl font-bold text-slate-950">Resumen institucional</h1><MentorBriefingPanel /></div>;
}
