import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Check, X, Trash2 } from 'lucide-react';
import { useDeleteProxy } from '@/lib/queries';
import type { Proxy } from '@/lib/queries';

export const ProxyTable = ({ proxies }: { proxies: Proxy[] }): JSX.Element => {
  const del = useDeleteProxy();
  return (
    <table className="w-full text-sm">
      <thead className="text-left text-muted-foreground border-b">
        <tr>
          <th className="py-2 px-3">Label</th>
          <th className="py-2 px-3">Type</th>
          <th className="py-2 px-3">Endpoint</th>
          <th className="py-2 px-3">Password</th>
          <th className="py-2 px-3" />
        </tr>
      </thead>
      <tbody>
        {proxies.map((p) => (
          <tr key={p.id} className="border-b last:border-b-0">
            <td className="py-2 px-3 font-medium">{p.label}</td>
            <td className="py-2 px-3">{p.type}</td>
            <td className="py-2 px-3 font-mono">
              {p.host}:{p.port}
            </td>
            <td className="py-2 px-3">
              {p.has_password ? (
                <Check className="h-4 w-4 text-emerald-600" />
              ) : (
                <X className="h-4 w-4 text-muted-foreground" />
              )}
            </td>
            <td className="py-2 px-3 text-right">
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button size="icon" variant="ghost">
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogTitle>Delete proxy &quot;{p.label}&quot;?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Devices currently using this proxy will keep running, but you can&apos;t create
                    new devices against it.
                  </AlertDialogDescription>
                  <div className="flex justify-end gap-2">
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={() => del.mutate(p.id)}>Delete</AlertDialogAction>
                  </div>
                </AlertDialogContent>
              </AlertDialog>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
