import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProxyForm } from '@/components/proxies/ProxyForm';

const postMock = vi.fn();
vi.mock('@/lib/api-client', () => ({ getApi: () => ({ post: postMock }) }));

beforeEach(() => { postMock.mockReset(); });

const renderForm = (onCreated?: (id: string) => void): void => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: 0 } } });
  render(
    <QueryClientProvider client={qc}>
      <ProxyForm onCreated={onCreated} />
    </QueryClientProvider>
  );
};

describe('ProxyForm', () => {
  it('rejects port > 65535', async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText(/label/i), 'l');
    await userEvent.type(screen.getByLabelText(/^host/i), 'h');
    const port = screen.getByLabelText(/port/i);
    await userEvent.clear(port);
    await userEvent.type(port, '99999');
    await userEvent.click(screen.getByRole('button', { name: /create proxy/i }));
    expect(await screen.findByText(/65535/)).toBeInTheDocument();
    cleanup();
  });

  it('submits with valid values', async () => {
    postMock.mockResolvedValueOnce({ data: { id: 'p1', label: 'l', type: 'socks5', host: 'h', port: 1080, username: null, has_password: false, created_at: '2026' } });
    const onCreated = vi.fn();
    renderForm(onCreated);
    await userEvent.type(screen.getByLabelText(/label/i), 'my-proxy');
    await userEvent.type(screen.getByLabelText(/^host/i), 'h.example.com');
    await userEvent.click(screen.getByRole('button', { name: /create proxy/i }));
    await vi.waitFor(() => expect(onCreated).toHaveBeenCalledWith('p1'));
    expect(postMock).toHaveBeenCalledWith('/api/v1/proxies', expect.objectContaining({ label: 'my-proxy', host: 'h.example.com' }));
  });
});
