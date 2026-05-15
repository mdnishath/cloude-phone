import { Button } from '@/components/ui/button';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogTitle, AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { canStart, canStop, canDelete } from '@/lib/state-machine';
import type { Device } from '@/lib/queries';
import { useDeleteDevice, useStartDevice, useStopDevice } from '@/lib/queries';
import { useNavigate } from 'react-router-dom';
import { Play, Square, Trash2 } from 'lucide-react';

export const DeviceActions = ({ device }: { device: Device }): JSX.Element => {
  const navigate = useNavigate();
  const start = useStartDevice();
  const stop = useStopDevice();
  const del = useDeleteDevice();

  return (
    <div className="flex gap-2">
      <Button onClick={() => start.mutate(device.id)} disabled={!canStart(device.state) || start.isPending}>
        <Play className="mr-2 h-4 w-4" />Start
      </Button>
      <Button variant="outline" onClick={() => stop.mutate(device.id)} disabled={!canStop(device.state) || stop.isPending}>
        <Square className="mr-2 h-4 w-4" />Stop
      </Button>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="destructive" disabled={!canDelete(device.state)}>
            <Trash2 className="mr-2 h-4 w-4" />Delete
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogTitle>Delete this device?</AlertDialogTitle>
          <AlertDialogDescription>
            This stops the Android container, removes the per-device volume, and deletes the record. Apps and data inside the device are gone permanently.
          </AlertDialogDescription>
          <div className="flex justify-end gap-2">
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                del.mutate(device.id, { onSuccess: () => navigate('/devices', { replace: true }) });
              }}
            >
              Delete
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
