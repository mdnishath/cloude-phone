import { Button } from '@/components/ui/button';

export const App = (): JSX.Element => {
  const handleBoot = async (): Promise<void> => {
    const result = await window.api.invoke('auth:bootstrap');
    console.log('bootstrap', result);
  };
  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Cloude Phone</h1>
      <p className="text-muted-foreground">IPC contract wired. Handlers land in Tasks 3-4.</p>
      <Button onClick={handleBoot}>Test IPC (will throw until Task 3)</Button>
    </div>
  );
};
