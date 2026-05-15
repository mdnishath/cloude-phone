import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ProxyForm } from '@/components/proxies/ProxyForm';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowLeft } from 'lucide-react';

export const ProxyNew = (): JSX.Element => {
  const navigate = useNavigate();
  return (
    <div className="space-y-4 max-w-2xl">
      <div className="flex items-center gap-4">
        <Button asChild variant="outline" size="sm"><Link to="/proxies"><ArrowLeft className="mr-2 h-4 w-4" />Back</Link></Button>
        <h1 className="text-2xl font-semibold">New proxy</h1>
      </div>
      <Card>
        <CardHeader><CardTitle>Configure</CardTitle></CardHeader>
        <CardContent>
          <ProxyForm onCreated={() => navigate('/proxies', { replace: true })} />
        </CardContent>
      </Card>
    </div>
  );
};
