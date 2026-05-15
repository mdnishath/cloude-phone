import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Copy } from 'lucide-react';
import type { Device } from '@/lib/queries';

export const AdbInfoCard = ({ device }: { device: Device }): JSX.Element | null => {
  if (device.state !== 'running' || device.adb_host_port === null) return null;
  const adbCmd = `adb connect localhost:${device.adb_host_port}`;
  const scrcpyCmd = `scrcpy -s localhost:${device.adb_host_port}`;
  const copy = (s: string): void => { void navigator.clipboard.writeText(s); };

  return (
    <Card>
      <CardHeader>
        <CardTitle>ADB / scrcpy</CardTitle>
        <CardDescription>Use these commands from a terminal on this machine.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex items-center gap-2">
          <code className="flex-1 rounded bg-muted px-3 py-2 font-mono text-sm">{adbCmd}</code>
          <Button size="icon" variant="outline" onClick={() => copy(adbCmd)}><Copy className="h-4 w-4" /></Button>
        </div>
        <div className="flex items-center gap-2">
          <code className="flex-1 rounded bg-muted px-3 py-2 font-mono text-sm">{scrcpyCmd}</code>
          <Button size="icon" variant="outline" onClick={() => copy(scrcpyCmd)}><Copy className="h-4 w-4" /></Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Install scrcpy from{' '}
          <button
            className="underline"
            onClick={() => void window.api.invoke('app:openExternal', 'https://github.com/Genymobile/scrcpy/releases')}
          >
            github.com/Genymobile/scrcpy/releases
          </button>
          .
        </p>
      </CardContent>
    </Card>
  );
};
