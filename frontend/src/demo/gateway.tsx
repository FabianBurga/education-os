import { useEffect, useState } from "react";
import { Outlet } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AppContextProvider } from "../app-context";
import { AppShell } from "../components/layout/app-shell";
import { clearAccessToken } from "../lib/session";
import type { UiBootstrap } from "../types/bootstrap";

export const PERSONAS = { RECTOR: "Rector", COORDINATION: "Coordinación académica", TEACHER: "Docente", STUDENT: "Estudiante", GUARDIAN: "Representante" } as const;
export interface DemoStatus { demo: true; entrance: boolean; alias: keyof typeof PERSONAS | null }

export async function demoRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/demo/${path}`, {
    method: body === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new Error("No fue posible acceder a la demostración. Revisa el acceso o inténtalo más tarde.");
  return response.json() as Promise<T>;
}

export async function clearDemoBrowserState() {
  clearAccessToken();
  sessionStorage.removeItem("education_os_coord_token");
  // The isolated demo origin holds no production state. Never retain another
  // persona's offline rows when switching, expiring or opening another tab.
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase("education-os-teacher-offline");
    request.onsuccess = () => resolve();
    request.onerror = () => reject(new Error("Cierra las otras ventanas de la demostración."));
    request.onblocked = () => reject(new Error("Cierra las otras ventanas de la demostración."));
  });
}

export function DemoEntrance({ status, refresh }: { status: DemoStatus; refresh: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function enter(alias?: keyof typeof PERSONAS) {
    setBusy(true); setError("");
    try {
      await clearDemoBrowserState();
      await demoRequest(alias ? "session" : "entrance", alias ? { alias } : { code });
      setCode(""); refresh();
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  }
  return <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-6 p-6">
    <h1 className="text-3xl font-bold">Education OS — Demostración</h1>
    <p>Explore una institución con información exclusivamente sintética.</p>
    {status.entrance ? <><h2 className="text-xl font-semibold">Seleccione el perfil que desea explorar</h2>
      <div className="grid gap-3">{Object.entries(PERSONAS).map(([alias, label]) => <button key={alias} disabled={busy} className="rounded-xl border bg-white p-4 text-left font-semibold focus-visible:outline-2 focus-visible:outline-slate-900" onClick={() => void enter(alias as keyof typeof PERSONAS)}>{label}</button>)}</div>
    </> : <form className="space-y-4" onSubmit={event => { event.preventDefault(); void enter(); }}>
      <label className="block">Código de acceso<input type="password" autoComplete="off" maxLength={256} value={code} onChange={event => setCode(event.target.value)} className="mt-2 w-full rounded-xl border p-3" /></label>
      <button disabled={busy || !code} className="rounded-xl bg-slate-900 px-5 py-3 text-white">Entrar a la demostración</button>
    </form>}
    {busy && <p role="status">Verificando acceso…</p>}{error && <p role="alert">{error}</p>}
  </main>;
}

export function DemoGateway() {
  const client = useQueryClient();
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState("");
  const status = useQuery({ queryKey: ["demo-session"], queryFn: () => demoRequest<DemoStatus>("session"), retry: false, refetchInterval: 15000, refetchOnWindowFocus: "always" });
  useEffect(() => { client.removeQueries({ predicate: query => !String(query.queryKey[0]).startsWith("demo-") }); }, [client, status.data?.alias]);
  useEffect(() => { void clearDemoBrowserState().then(() => setChecked(true)).catch(failure => setError(failure.message)); }, []);
  const bootstrap = useQuery({ queryKey: ["demo-bootstrap", status.data?.alias], enabled: checked && Boolean(status.data?.alias), retry: false, refetchInterval: 15000,
    queryFn: async () => { const response = await fetch("/api/v1/ui/bootstrap", { cache: "no-store", credentials: "same-origin" }); if (!response.ok) throw new Error("La sesión no está disponible."); return response.json() as Promise<UiBootstrap>; } });
  async function leave(path: "exit" | "logout") {
    try { await demoRequest(path, {}); await clearDemoBrowserState(); refresh(); }
    catch { setError("No fue posible cerrar la sesión. Inténtalo de nuevo."); }
  }
  useEffect(() => {
    const channel = new BroadcastChannel("education-demo-session");
    channel.onmessage = () => window.location.replace("/app/");
    const onFocus = () => { void client.invalidateQueries({ queryKey: ["demo-session"] }); };
    const onRestore = (event: PageTransitionEvent) => { if (event.persisted) window.location.replace("/app/"); };
    window.addEventListener("focus", onFocus);
    window.addEventListener("pageshow", onRestore);
    return () => { channel.close(); window.removeEventListener("focus", onFocus); window.removeEventListener("pageshow", onRestore); };
  }, [client]);
  const refresh = () => { const channel = new BroadcastChannel("education-demo-session"); channel.postMessage("changed"); channel.close(); client.clear(); window.location.assign("/app/"); };
  if (error || status.isError) return <main className="p-8" role="alert">{error || "No fue posible verificar la demostración. Recarga la página."}</main>;
  if (!checked || !status.data) return <main className="p-8" role="status">Verificando sesión…</main>;
  if (!status.data.alias) return <DemoEntrance status={status.data} refresh={refresh} />;
  if (bootstrap.isError) return <main className="p-8"><p>La sesión no está disponible.</p><button onClick={() => void leave("logout")}>Cerrar sesión</button></main>;
  if (!bootstrap.data) return <main className="p-8">Cargando perfil…</main>;
  return <AppContextProvider key={status.data.alias} value={{ bootstrap: bootstrap.data, signOut: () => void leave("logout") }}><AppShell>
    <div className="mb-5 flex flex-wrap items-center gap-4"><span>Demostración · {PERSONAS[status.data.alias]}</span><button className="rounded-lg border p-2" onClick={() => void leave("exit")}>Salir del perfil</button></div><Outlet />
  </AppShell></AppContextProvider>;
}
