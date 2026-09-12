import { FormEvent, useState } from "react";
import { KeyRound, ShieldCheck } from "lucide-react";

import { Button } from "../ui/button";
import { Card, CardContent } from "../ui/card";

interface TokenGateProps {
  initialToken: string;
  errorMessage?: string;
  onSubmit: (token: string) => void;
}

export function TokenGate({
  initialToken,
  errorMessage,
  onSubmit,
}: TokenGateProps) {
  const [token, setToken] = useState(initialToken);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit(token);
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-10">
      <Card className="w-full max-w-lg overflow-hidden">
        <div className="bg-slate-900 px-6 py-7 text-white">
          <div className="mb-5 inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10">
            <ShieldCheck className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-bold">Education OS</h1>
          <p className="mt-2 max-w-md text-sm leading-6 text-slate-300">
            M15 unifica la experiencia visual sin cambiar las reglas de
            seguridad ni los permisos del backend.
          </p>
        </div>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label
                htmlFor="education-token"
                className="mb-2 block text-sm font-semibold text-slate-700"
              >
                Token de sesión
              </label>
              <div className="relative">
                <KeyRound className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
                <input
                  id="education-token"
                  data-testid="unified-token-input"
                  type="password"
                  autoComplete="off"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  placeholder="Bearer token autorizado"
                  className="h-10 w-full rounded-xl border border-slate-200 bg-white pl-9 pr-3 text-sm outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200"
                />
              </div>
            </div>

            {errorMessage ? (
              <div
                role="alert"
                className="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm text-rose-700"
              >
                {errorMessage}
              </div>
            ) : null}

            <Button
              type="submit"
              className="w-full"
              data-testid="unified-enter-button"
              disabled={!token.trim()}
            >
              Entrar al entorno unificado
            </Button>

            <p className="text-xs leading-5 text-slate-500">
              En M15 el token se conserva únicamente en sessionStorage. El
              inicio de sesión con credenciales se mantiene fuera del alcance
              de este milestone.
            </p>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
