import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { useSettingsStore } from '@/stores/settings';
import { ConnectionBanner } from '@/components/feedback/ConnectionBanner';

export const AppShell = (): JSX.Element => {
  const backend = useSettingsStore((s) => s.prefs.backendUrl);
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <header className="flex items-center justify-between border-b px-4 py-2 text-sm">
          <span className="text-muted-foreground">Backend:</span>
          <span className="font-mono">{backend}</span>
        </header>
        <ConnectionBanner />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
