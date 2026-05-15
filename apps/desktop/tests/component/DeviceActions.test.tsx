import { describe, expect, it, vi } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DeviceActions } from '@/components/devices/DeviceActions';
import type { Device } from '@/lib/queries';

vi.mock('@/lib/api-client', () => ({ getApi: () => ({ post: vi.fn(), delete: vi.fn() }) }));

const makeDevice = (state: Device['state']): Device => ({
  id: 'id1',
  name: 'd',
  profile_id: 'p',
  proxy_id: 'r',
  state,
  state_reason: null,
  adb_host_port: 40000,
  created_at: '2026',
  started_at: null,
  stopped_at: null,
});

const renderWith = (device: Device): void => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: 0 } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DeviceActions device={device} />
      </MemoryRouter>
    </QueryClientProvider>
  );
};

describe('DeviceActions enablement', () => {
  it('Start enabled only for stopped/error', () => {
    renderWith(makeDevice('stopped'));
    expect(screen.getByRole('button', { name: /start/i })).not.toBeDisabled();
    cleanup();
    renderWith(makeDevice('running'));
    expect(screen.getByRole('button', { name: /start/i })).toBeDisabled();
  });

  it('Stop enabled only for running/creating', () => {
    renderWith(makeDevice('running'));
    expect(screen.getByRole('button', { name: /stop/i })).not.toBeDisabled();
    cleanup();
    renderWith(makeDevice('stopped'));
    expect(screen.getByRole('button', { name: /stop/i })).toBeDisabled();
  });
});
