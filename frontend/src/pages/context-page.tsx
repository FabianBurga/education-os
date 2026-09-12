import { useAppContext } from "../app-context";
import { Badge } from "../components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
} from "../components/ui/card";

export function ContextPage() {
  const { bootstrap } = useAppContext();

  const profileLabels = [
    ["Personal", bootstrap.profiles.staff],
    ["Estudiante", bootstrap.profiles.student],
    ["Representante", bootstrap.profiles.guardian],
  ] as const;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-slate-950">
          Mi contexto de acceso
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Lo que la interfaz conoce proviene del backend autenticado.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <h2 className="font-bold text-slate-900">Identidad</h2>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div>
              <span className="text-slate-500">Usuario</span>
              <div className="font-semibold text-slate-800">
                {bootstrap.user.display_name}
              </div>
            </div>
            <div>
              <span className="text-slate-500">Correo</span>
              <div className="font-semibold text-slate-800">
                {bootstrap.user.login_email}
              </div>
            </div>
            <div>
              <span className="text-slate-500">Institución</span>
              <div className="font-semibold text-slate-800">
                {bootstrap.tenant.institution_name}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="font-bold text-slate-900">Perfiles detectados</h2>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {profileLabels.map(([label, active]) => (
              <Badge key={label} tone={active ? "success" : "neutral"}>
                {label}: {active ? "sí" : "no"}
              </Badge>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="font-bold text-slate-900">Roles</h2>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {bootstrap.roles.length ? (
              bootstrap.roles.map((role) => (
                <Badge key={role} tone="neutral">
                  {role}
                </Badge>
              ))
            ) : (
              <span className="text-sm text-slate-500">
                Sin roles asignados.
              </span>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="font-bold text-slate-900">Capabilities</h2>
          </CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(bootstrap.capabilities).length ? (
              Object.entries(bootstrap.capabilities).map(
                ([key, enabled]) => (
                  <div
                    key={key}
                    className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2"
                  >
                    <span className="font-mono text-xs text-slate-600">
                      {key}
                    </span>
                    <Badge tone={enabled ? "success" : "warning"}>
                      {enabled ? "ON" : "OFF"}
                    </Badge>
                  </div>
                ),
              )
            ) : (
              <span className="text-sm text-slate-500">
                Sin capabilities explícitas.
              </span>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <h2 className="font-bold text-slate-900">
            Permisos efectivos
          </h2>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {bootstrap.permissions.map((permission) => (
              <div
                key={permission}
                className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-600"
              >
                {permission}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
