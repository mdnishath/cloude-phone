import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useCreateProxy } from '@/lib/queries';

const schema = z.object({
  label: z.string().min(1).max(120),
  type: z.enum(['socks5', 'http']),
  host: z.string().min(1).max(255),
  port: z.coerce.number().int().min(1).max(65535),
  username: z.string().max(255).optional(),
  password: z.string().max(512).optional(),
});

type FormValues = z.infer<typeof schema>;

export const ProxyForm = ({
  onCreated,
}: {
  onCreated?: (proxyId: string) => void;
}): JSX.Element => {
  const create = useCreateProxy();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { label: '', type: 'socks5', host: '', port: 1080, username: '', password: '' },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    const proxy = await create.mutateAsync({
      label: values.label,
      type: values.type,
      host: values.host,
      port: values.port,
      username: values.username || null,
      password: values.password || null,
    });
    onCreated?.(proxy.id);
  });

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="label">Label</Label>
        <Input id="label" {...form.register('label')} />
        {form.formState.errors.label && (
          <p className="text-sm text-destructive">{form.formState.errors.label.message}</p>
        )}
      </div>
      <div className="space-y-2">
        <Label>Type</Label>
        <Controller
          name="type"
          control={form.control}
          render={({ field }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="socks5">SOCKS5</SelectItem>
                <SelectItem value="http">HTTP CONNECT</SelectItem>
              </SelectContent>
            </Select>
          )}
        />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div className="col-span-2 space-y-2">
          <Label htmlFor="host">Host</Label>
          <Input id="host" {...form.register('host')} />
          {form.formState.errors.host && (
            <p className="text-sm text-destructive">{form.formState.errors.host.message}</p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="port">Port</Label>
          <Input id="port" type="number" {...form.register('port')} />
          {form.formState.errors.port && (
            <p className="text-sm text-destructive">{form.formState.errors.port.message}</p>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-2">
          <Label htmlFor="username">Username (optional)</Label>
          <Input id="username" {...form.register('username')} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">Password (optional)</Label>
          <Input id="password" type="password" {...form.register('password')} />
        </div>
      </div>
      {create.isError && (
        <p className="text-sm text-destructive" role="alert">
          {(create.error as { response?: { data?: { error?: { message?: string } } } }).response
            ?.data?.error?.message ?? 'Create failed'}
        </p>
      )}
      <Button type="submit" disabled={create.isPending}>
        {create.isPending ? 'Creating…' : 'Create proxy'}
      </Button>
    </form>
  );
};
