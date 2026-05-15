import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useRedeemInviteMutation } from '@/lib/queries';
import { saveAuth } from '@/stores/auth';
import { Link, useNavigate } from 'react-router-dom';

const schema = z.object({
  token: z.string().min(10).max(128),
  email: z.string().email(),
  password: z.string().min(8).max(128),
});

type FormValues = z.infer<typeof schema>;

export const Redeem = (): JSX.Element => {
  const navigate = useNavigate();
  const mutation = useRedeemInviteMutation();
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { token: '', email: '', password: '' } });

  const onSubmit = form.handleSubmit(async (values) => {
    const tokens = await mutation.mutateAsync(values);
    await saveAuth({ access: tokens.access, refresh: tokens.refresh });
    navigate('/devices', { replace: true });
  });

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 rounded-lg border p-6 bg-card">
        <h1 className="text-2xl font-semibold">Redeem invite</h1>
        <div className="space-y-2">
          <Label htmlFor="token">Invite token</Label>
          <Input id="token" {...form.register('token')} />
          {form.formState.errors.token && (
            <p className="text-sm text-destructive">{form.formState.errors.token.message}</p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" {...form.register('email')} />
          {form.formState.errors.email && (
            <p className="text-sm text-destructive">{form.formState.errors.email.message}</p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">Choose a password</Label>
          <Input id="password" type="password" {...form.register('password')} />
          {form.formState.errors.password && (
            <p className="text-sm text-destructive">{form.formState.errors.password.message}</p>
          )}
        </div>
        {mutation.isError && (
          <p className="text-sm text-destructive" role="alert">
            {(mutation.error as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error?.message ?? 'Redeem failed'}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={mutation.isPending}>
          {mutation.isPending ? 'Redeeming…' : 'Redeem'}
        </Button>
        <p className="text-sm text-center text-muted-foreground">
          Already have an account? <Link to="/login" className="underline">Sign in →</Link>
        </p>
      </form>
    </div>
  );
};
