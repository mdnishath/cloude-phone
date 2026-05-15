import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useLoginMutation } from '@/lib/queries';
import { saveAuth } from '@/stores/auth';
import { Link, useNavigate } from 'react-router-dom';

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

type FormValues = z.infer<typeof schema>;

export const Login = (): JSX.Element => {
  const navigate = useNavigate();
  const mutation = useLoginMutation();
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { email: '', password: '' } });

  const onSubmit = form.handleSubmit(async (values) => {
    const tokens = await mutation.mutateAsync(values);
    await saveAuth({ access: tokens.access, refresh: tokens.refresh });
    navigate('/devices', { replace: true });
  });

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 rounded-lg border p-6 bg-card">
        <h1 className="text-2xl font-semibold">Sign in</h1>
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="username" {...form.register('email')} />
          {form.formState.errors.email && (
            <p className="text-sm text-destructive">{form.formState.errors.email.message}</p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="current-password" {...form.register('password')} />
          {form.formState.errors.password && (
            <p className="text-sm text-destructive">{form.formState.errors.password.message}</p>
          )}
        </div>
        {mutation.isError && (
          <p className="text-sm text-destructive" role="alert">
            {(mutation.error as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error?.message ?? 'Login failed'}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={mutation.isPending}>
          {mutation.isPending ? 'Signing in…' : 'Sign in'}
        </Button>
        <p className="text-sm text-center text-muted-foreground">
          Have an invite token? <Link to="/redeem" className="underline">Redeem →</Link>
        </p>
      </form>
    </div>
  );
};
