import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useProfilesQuery, useProxiesQuery, useCreateDevice } from '@/lib/queries';
import { ArrowLeft } from 'lucide-react';

export const DeviceNew = (): JSX.Element => {
  const navigate = useNavigate();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [name, setName] = useState('');
  const [profileId, setProfileId] = useState('');
  const [proxyId, setProxyId] = useState('');

  const profiles = useProfilesQuery();
  const proxies = useProxiesQuery();
  const create = useCreateDevice();

  const submit = (): void => {
    create.mutate(
      { name, profile_id: profileId, proxy_id: proxyId },
      { onSuccess: (d) => navigate(`/devices/${d.id}`, { replace: true }) }
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <Button asChild variant="outline" size="sm">
          <Link to="/devices">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold">Create device — Step {step} of 3</h1>
      </div>

      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle>Basics</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Device name</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={120}
              />
            </div>
            <div className="space-y-2">
              <Label>Profile</Label>
              {profiles.isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}
              {profiles.data && (
                <RadioGroup value={profileId} onValueChange={setProfileId}>
                  {profiles.data.map((p) => (
                    <div key={p.id} className="flex items-center gap-3 rounded-md border p-3">
                      <RadioGroupItem id={`prof-${p.id}`} value={p.id} />
                      <Label htmlFor={`prof-${p.id}`} className="flex-1 cursor-pointer">
                        <div className="font-medium">{p.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {p.manufacturer} {p.model} · {p.screen_width}×{p.screen_height} ·{' '}
                          {p.ram_mb}MB
                        </div>
                      </Label>
                    </div>
                  ))}
                </RadioGroup>
              )}
            </div>
            <div className="flex justify-end">
              <Button onClick={() => setStep(2)} disabled={name.length === 0 || profileId === ''}>
                Next
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle>Proxy</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {proxies.isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}
            {proxies.data && proxies.data.length === 0 && (
              <p className="text-muted-foreground text-sm">
                No proxies yet.{' '}
                <Link to="/proxies/new" className="underline">
                  Create one →
                </Link>{' '}
                and come back.
              </p>
            )}
            {proxies.data && proxies.data.length > 0 && (
              <RadioGroup value={proxyId} onValueChange={setProxyId}>
                {proxies.data.map((p) => (
                  <div key={p.id} className="flex items-center gap-3 rounded-md border p-3">
                    <RadioGroupItem id={`px-${p.id}`} value={p.id} />
                    <Label htmlFor={`px-${p.id}`} className="flex-1 cursor-pointer">
                      <div className="font-medium">{p.label}</div>
                      <div className="text-xs text-muted-foreground">
                        {p.type} · {p.host}:{p.port}
                      </div>
                    </Label>
                  </div>
                ))}
              </RadioGroup>
            )}
            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button onClick={() => setStep(3)} disabled={proxyId === ''}>
                Next
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 3 && (
        <Card>
          <CardHeader>
            <CardTitle>Review</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div>
              <strong>Name:</strong> {name}
            </div>
            <div>
              <strong>Profile:</strong>{' '}
              {profiles.data?.find((p) => p.id === profileId)?.name ?? profileId}
            </div>
            <div>
              <strong>Proxy:</strong>{' '}
              {proxies.data?.find((p) => p.id === proxyId)?.label ?? proxyId}
            </div>
            {create.isError && (
              <p className="text-destructive">
                {(create.error as { response?: { data?: { error?: { message?: string } } } })
                  .response?.data?.error?.message ?? 'Create failed'}
              </p>
            )}
            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep(2)}>
                Back
              </Button>
              <Button onClick={submit} disabled={create.isPending}>
                {create.isPending ? 'Creating…' : 'Create'}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};
