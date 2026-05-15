import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import type { ReactNode } from 'react';

export const ProtectedRoute = ({ children }: { children: ReactNode }): JSX.Element => {
  const status = useAuthStore((s) => s.status);
  if (status === 'loading') return <div className="p-6">Loading…</div>;
  if (status === 'anonymous') return <Navigate to="/login" replace />;
  return <>{children}</>;
};
