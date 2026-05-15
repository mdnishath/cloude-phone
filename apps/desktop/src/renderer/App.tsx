import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { ProtectedRoute } from '@/components/layout/ProtectedRoute';
import { Login } from '@/routes/Login';
import { Redeem } from '@/routes/Redeem';
import { DevicesIndex } from '@/routes/DevicesIndex';
import { DeviceDetail } from '@/routes/DeviceDetail';
import { DeviceNew } from '@/routes/DeviceNew';
import { ProxiesIndex } from '@/routes/ProxiesIndex';
import { ProxyNew } from '@/routes/ProxyNew';
import { Settings } from '@/routes/Settings';

export const App = (): JSX.Element => (
  <HashRouter>
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/redeem" element={<Redeem />} />
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/devices" replace />} />
        <Route path="/devices" element={<DevicesIndex />} />
        <Route path="/devices/new" element={<DeviceNew />} />
        <Route path="/devices/:id" element={<DeviceDetail />} />
        <Route path="/proxies" element={<ProxiesIndex />} />
        <Route path="/proxies/new" element={<ProxyNew />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  </HashRouter>
);
