import { ExternalLink,ShieldAlert } from "lucide-react";
import { useEffect } from "react";
import { useAppContext } from "../app-context";
import { findModule,moduleCapabilityState,modulesForContext } from "../navigation";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card,CardContent,CardHeader } from "../components/ui/card";
import { TeacherPwaPage } from "./teacher-pwa-page";

function OperationalTeacherRedirect() {
  useEffect(() => {
    window.location.replace("/api/v1/teacher/dashboard");
  }, []);

  return (
    <Card data-testid="teacher-operational-redirect">
      <CardContent className="flex min-h-64 items-center justify-center text-center">
        <p className="text-sm font-semibold text-slate-600">
          Abriendo la consola docente...
        </p>
      </CardContent>
    </Card>
  );
}

export function WorkspacePage({moduleId}:{moduleId:string}){const{bootstrap}=useAppContext();const module=findModule(moduleId);const allowedIds=new Set(modulesForContext(bootstrap).map(x=>x.id));if(!module||!allowedIds.has(module.id)){return<Card><CardContent className="flex min-h-64 flex-col items-center justify-center text-center"><ShieldAlert className="h-10 w-10 text-rose-500"/><h1 className="mt-4 text-xl font-bold">Espacio no disponible</h1><p className="mt-2 max-w-lg text-sm text-slate-500">Esta vista no está disponible para tu perfil.</p></CardContent></Card>;}const capability=moduleCapabilityState(module,bootstrap);if(module.id==="teacher")return bootstrap.capabilities["teacher.offline_pwa"]===true?<TeacherPwaPage/>:<OperationalTeacherRedirect/>;const legacyPath=module.legacyPath;return<div className="space-y-5" data-testid={`workspace-${module.id}`}><div><div className="flex gap-2"><Badge tone="neutral">{module.audience}</Badge>{capability==="disabled"?<Badge tone="warning">Vista no disponible</Badge>:null}</div><h1 className="mt-3 text-3xl font-bold">{module.label}</h1><p className="mt-2 max-w-3xl text-sm text-slate-600">{module.description}</p></div><Card><CardHeader><h2 className="font-bold">Vista de {module.label}</h2><p className="mt-1 text-sm text-slate-500">Consulta y gestiona la información disponible para tu perfil.</p></CardHeader><CardContent><Button onClick={()=>window.location.assign(legacyPath)} className="mt-5 gap-2" data-testid={`legacy-${module.id}`}>Abrir espacio operativo actual<ExternalLink className="h-4 w-4"/></Button></CardContent></Card></div>}
