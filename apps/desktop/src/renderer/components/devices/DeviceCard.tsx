import { Link } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StateBadge } from './StateBadge';
import { formatRelativeTime } from '@/lib/format';
import type { Device, DeviceProfile } from '@/lib/queries';

interface Props {
  device: Device;
  profile: DeviceProfile | undefined;
}

export const DeviceCard = ({ device, profile }: Props): JSX.Element => (
  <Link to={`/devices/${device.id}`} className="block">
    <Card className="hover:bg-accent/30 transition-colors">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle>{device.name}</CardTitle>
            <CardDescription>
              {profile ? `${profile.manufacturer} ${profile.model} · ${profile.screen_width}×${profile.screen_height}` : '…'}
            </CardDescription>
          </div>
          <StateBadge state={device.state} />
        </div>
      </CardHeader>
      <CardContent className="text-xs text-muted-foreground">
        {device.started_at && device.state === 'running'
          ? `Running since ${formatRelativeTime(device.started_at)}`
          : device.stopped_at
          ? `Stopped ${formatRelativeTime(device.stopped_at)}`
          : `Created ${formatRelativeTime(device.created_at)}`}
      </CardContent>
    </Card>
  </Link>
);
