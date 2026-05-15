import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ProxyTable } from '@/components/proxies/ProxyTable';
import { useProxiesQuery } from '@/lib/queries';
import { Plus } from 'lucide-react';

export const ProxiesIndex = (): JSX.Element => {
  const q = useProxiesQuery();
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Proxies</h1>
        <Button asChild><Link to="/proxies/new"><Plus className="mr-2 h-4 w-4" />New proxy</Link></Button>
      </div>
      {q.isLoading && <p className="text-muted-foreground">Loading…</p>}
      {q.data && q.data.length === 0 && <p className="text-muted-foreground">No proxies yet.</p>}
      {q.data && q.data.length > 0 && (
        <div className="rounded-lg border">
          <ProxyTable proxies={q.data} />
        </div>
      )}
    </div>
  );
};
