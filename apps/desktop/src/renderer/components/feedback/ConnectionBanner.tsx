import { useWsStore } from '@/lib/ws';

export const ConnectionBanner = (): JSX.Element | null => {
  const reconnecting = useWsStore((s) => s.reconnecting);
  if (!reconnecting) return null;
  return (
    <div className="bg-amber-500/15 text-amber-700 dark:text-amber-300 px-4 py-1 text-xs">
      Live updates reconnecting…
    </div>
  );
};
