import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { DeviceCard } from '@/components/devices/DeviceCard';
import { useDevicesQuery, useProfilesQuery } from '@/lib/queries';
import { Plus } from 'lucide-react';

export const DevicesIndex = (): JSX.Element => {
  const devicesQ = useDevicesQuery();
  const profilesQ = useProfilesQuery();
  const profilesById = new Map(profilesQ.data?.map((p) => [p.id, p]));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Devices</h1>
        <Button asChild>
          <Link to="/devices/new">
            <Plus className="mr-2 h-4 w-4" />
            Create device
          </Link>
        </Button>
      </div>
      {devicesQ.isLoading && <p className="text-muted-foreground">Loading…</p>}
      {devicesQ.isError && (
        <p className="text-destructive">
          Failed to load devices: {(devicesQ.error as Error).message}
        </p>
      )}
      {devicesQ.data && devicesQ.data.length === 0 && (
        <p className="text-muted-foreground">
          No devices yet. Click &quot;Create device&quot; to spawn one.
        </p>
      )}
      {devicesQ.data && devicesQ.data.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {devicesQ.data.map((d) => (
            <DeviceCard key={d.id} device={d} profile={profilesById.get(d.profile_id)} />
          ))}
        </div>
      )}
    </div>
  );
};
