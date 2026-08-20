"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

/**
 * There is no authentication in this build. Institution context comes from the
 * header selector and lives here so it survives navigation between the four
 * Lite routes — the provider sits in the root layout, which does not remount.
 */
interface InstitutionContextValue {
  institutionId: string | null;
  setInstitutionId: (id: string) => void;
}

const InstitutionContext = createContext<InstitutionContextValue>({
  institutionId: null,
  setInstitutionId: () => {},
});

export function InstitutionProvider({ children }: { children: ReactNode }) {
  const [institutionId, setInstitutionId] = useState<string | null>(null);
  const value = useMemo(() => ({ institutionId, setInstitutionId }), [institutionId]);

  return <InstitutionContext.Provider value={value}>{children}</InstitutionContext.Provider>;
}

export function useSelectedInstitution() {
  return useContext(InstitutionContext);
}
