import { createContext, useContext, type ReactNode } from "react";

import type { UiBootstrap } from "./types/bootstrap";

interface AppContextValue {
  bootstrap: UiBootstrap;
  signOut: () => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppContextProvider({
  value,
  children,
}: {
  value: AppContextValue;
  children: ReactNode;
}) {
  return (
    <AppContext.Provider value={value}>{children}</AppContext.Provider>
  );
}

export function useAppContext(): AppContextValue {
  const value = useContext(AppContext);
  if (!value) {
    throw new Error("AppContext is not available");
  }
  return value;
}
