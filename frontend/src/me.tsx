import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { getMe, type MeResponse } from './api';

const MeContext = createContext<MeResponse | null>(null);

export function MeProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<MeResponse | null>(null);

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  return <MeContext.Provider value={me}>{children}</MeContext.Provider>;
}

export function useMe(): MeResponse | null {
  return useContext(MeContext);
}
