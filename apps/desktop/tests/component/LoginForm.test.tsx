import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Login } from '@/routes/Login';

vi.mock('@/lib/api-client', () => {
  return {
    getApi: () => ({
      post: vi.fn().mockResolvedValue({ data: { access: 'a', refresh: 'r', token_type: 'bearer' } }),
    }),
  };
});

vi.mock('@/stores/auth', () => ({
  saveAuth: vi.fn().mockResolvedValue(undefined),
  useAuthStore: { getState: () => ({ tokens: null }) },
}));

const renderLogin = (): void => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: 0 } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    </QueryClientProvider>
  );
};

beforeEach(() => { vi.clearAllMocks(); });

describe('Login form', () => {
  it('rejects empty email', async () => {
    renderLogin();
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));
    expect(await screen.findByText(/Invalid email/i)).toBeInTheDocument();
  });

  it('submits with valid input', async () => {
    renderLogin();
    await userEvent.type(screen.getByLabelText(/email/i), 'a@b.com');
    await userEvent.type(screen.getByLabelText(/password/i), 'pw');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
