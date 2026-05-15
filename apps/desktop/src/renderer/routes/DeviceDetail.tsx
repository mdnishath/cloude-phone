import { Link, useParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StateBadge } from '@/components/devices/StateBadge';
import { DeviceActions } from '@/components/devices/DeviceActions';
import { AdbInfoCard } from '@/components/devices/AdbInfoCard';
import { StreamPlaceholder } from '@/components/devices/StreamPlaceholder';
import { useDeviceQuery, useProfilesQuery, useProxiesQuery } from '@/lib/queries';
import { useDeviceStatusWS } from '@/lib/ws';
import { ArrowLeft } from 'lucide-react';

export const DeviceDetail = (): JSX.Element => {
  const { id } = useParams<{ id: string }>();
  const deviceQ = useDeviceQuery(id);
  const profilesQ = useProfilesQuery();
  const proxiesQ = useProxiesQuery();
  useDeviceStatusWS(id);

  if (deviceQ.isLoading) return <p>Loading…</p>;
  if (deviceQ.isError || !deviceQ.data) {
    return (
      <div className="space-y-4">
        <Button asChild variant="outline"><Link to="/devices"><ArrowLeft className="mr-2 h-4 w-4" />Back</Link></Button>
        <p className="text-destructive">Device not found.</p>
      </div>
    );
  }
  const d = deviceQ.data;
  const profile = profilesQ.data?.find((p) => p.id === d.profile_id);
  const proxy = proxiesQ.data?.find((p) => p.id === d.proxy_id);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button asChild variant="outline" size="sm"><Link to="/devices"><ArrowLeft className="mr-2 h-4 w-4" />Back</Link></Button>
          <h1 className="text-2xl font-semibold">{d.name}</h1>
          <StateBadge state={d.state} />
        </div>
        <DeviceActions device={d} />
      </div>

      {d.state === 'error' && d.state_reason && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm">
          <strong>Error:</strong> {d.state_reason}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
            <CardDescription>{profile ? `${profile.manufacturer} ${profile.model}` : '…'}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {profile && (
              <>
                <div>Resolution: {profile.screen_width}×{profile.screen_height} @ {profile.screen_dpi}dpi</div>
                <div>RAM: {profile.ram_mb} MB · CPUs: {profile.cpu_cores}</div>
                <div>Android: {profile.android_version}</div>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Proxy</CardTitle>
            <CardDescription>{proxy ? proxy.label : '…'}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {proxy && (
              <>
                <div>Type: {proxy.type}</div>
                <div>Endpoint: {proxy.host}:{proxy.port}</div>
                <div>Auth: {proxy.has_password ? 'password configured' : 'no password'}</div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <AdbInfoCard device={d} />
      <StreamPlaceholder />
    </div>
  );
};
