import { useEffect, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { isAuthenticated } from '../api';

type Props = { children: ReactNode };

export default function ProtectedRoute({ children }: Props) {
  const [status, setStatus] = useState<'loading' | 'ok' | 'denied'>('loading');
  const location = useLocation();

  useEffect(() => {
    let cancelled = false;
    isAuthenticated().then((ok: boolean) => {
      if (!cancelled) setStatus(ok ? 'ok' : 'denied');
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === 'loading') {
    return <div className="main loading">Checking session…</div>;
  }
  if (status === 'denied') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}
