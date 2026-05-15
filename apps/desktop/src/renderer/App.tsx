import { useAuthStore } from '@/stores/auth';
import { useSettingsStore } from '@/stores/settings';

export const App = (): JSX.Element => {
  const status = useAuthStore((s) => s.status);
  const backend = useSettingsStore((s) => s.prefs.backendUrl);
  const theme = useSettingsStore((s) => s.prefs.theme);
  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Cloude Phone</h1>
      <p className="text-muted-foreground">
        auth.status={status} backend={backend} theme={theme}
      </p>
    </div>
  );
};
