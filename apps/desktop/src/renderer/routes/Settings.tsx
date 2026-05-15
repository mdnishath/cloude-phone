import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { useSettingsStore, updateSettings } from '@/stores/settings';
import { clearAuth } from '@/stores/auth';
import { useQueryClient } from '@tanstack/react-query';

export const Settings = (): JSX.Element => {
  const navigate = useNavigate();
  const prefs = useSettingsStore((s) => s.prefs);
  const queryClient = useQueryClient();
  const [url, setUrl] = useState(prefs.backendUrl);
  const [testResult, setTestResult] = useState<'idle' | 'ok' | 'fail' | 'pending'>('idle');

  const onSaveUrl = async (): Promise<void> => {
    await updateSettings({ backendUrl: url });
    queryClient.clear();
  };

  const onTest = async (): Promise<void> => {
    setTestResult('pending');
    try {
      const r = await fetch(`${url.replace(/\/$/, '')}/healthz`);
      setTestResult(r.ok ? 'ok' : 'fail');
    } catch {
      setTestResult('fail');
    }
  };

  const onLogout = async (): Promise<void> => {
    await clearAuth();
    queryClient.clear();
    navigate('/login', { replace: true });
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <Card>
        <CardHeader>
          <CardTitle>Backend</CardTitle>
          <CardDescription>
            The Cloude Phone API base URL. Default <code>http://localhost:8000</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="url">URL</Label>
            <div className="flex gap-2">
              <Input id="url" value={url} onChange={(e) => setUrl(e.target.value)} />
              <Button variant="outline" onClick={onTest}>
                Test
              </Button>
            </div>
            {testResult === 'ok' && <p className="text-sm text-emerald-600">Reachable ✓</p>}
            {testResult === 'fail' && <p className="text-sm text-destructive">Unreachable ✗</p>}
            {testResult === 'pending' && <p className="text-sm text-muted-foreground">Testing…</p>}
          </div>
          <Button onClick={onSaveUrl} disabled={url === prefs.backendUrl}>
            Save
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Theme</CardTitle>
        </CardHeader>
        <CardContent>
          <RadioGroup
            value={prefs.theme}
            onValueChange={(v) => void updateSettings({ theme: v as 'system' | 'light' | 'dark' })}
            className="flex gap-6"
          >
            <div className="flex items-center gap-2">
              <RadioGroupItem id="th-sys" value="system" />
              <Label htmlFor="th-sys">System</Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem id="th-light" value="light" />
              <Label htmlFor="th-light">Light</Label>
            </div>
            <div className="flex items-center gap-2">
              <RadioGroupItem id="th-dark" value="dark" />
              <Label htmlFor="th-dark">Dark</Label>
            </div>
          </RadioGroup>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
        </CardHeader>
        <CardContent>
          <Button variant="destructive" onClick={onLogout}>
            Log out
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};
