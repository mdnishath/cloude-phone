import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { createApi } from '@/lib/api';

const tokens: { access: string; refresh: string } = { access: 'old-access', refresh: 'good-refresh' };

const baseURL = 'http://test.local';
let saved: typeof tokens | null = null;
let cleared = false;

const server = setupServer(
  http.get(`${baseURL}/api/v1/me`, ({ request }) => {
    const auth = request.headers.get('authorization');
    if (auth === 'Bearer good-access' || auth === 'Bearer fresh-access') {
      return HttpResponse.json({ id: '1', email: 'a@b', role: 'user', quota_instances: 3, created_at: '2026-01-01' });
    }
    return new HttpResponse(JSON.stringify({ error: { code: 'unauthorized', message: 'bad token' } }), {
      status: 401,
      headers: { 'content-type': 'application/json' },
    });
  }),
  http.post(`${baseURL}/api/v1/auth/refresh`, async ({ request }) => {
    const body = (await request.json()) as { refresh: string };
    if (body.refresh === 'good-refresh') {
      return HttpResponse.json({ access: 'fresh-access', refresh: 'fresh-refresh', token_type: 'bearer' });
    }
    return new HttpResponse(null, { status: 401 });
  })
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => { saved = null; cleared = false; server.resetHandlers(); });
afterAll(() => server.close());

const api = createApi({
  baseURL,
  getTokens: () => tokens,
  setTokens: (t) => { saved = t; Object.assign(tokens, t); },
  clearTokens: () => { cleared = true; },
});

describe('createApi', () => {
  it('attaches Authorization on every request', async () => {
    Object.assign(tokens, { access: 'good-access', refresh: 'good-refresh' });
    const r = await api.get('/api/v1/me');
    expect(r.status).toBe(200);
  });

  it('refreshes once on 401 and retries successfully', async () => {
    Object.assign(tokens, { access: 'old-access', refresh: 'good-refresh' });
    const r = await api.get('/api/v1/me');
    expect(r.status).toBe(200);
    expect(saved?.access).toBe('fresh-access');
  });

  it('clears tokens on second 401', async () => {
    Object.assign(tokens, { access: 'old-access', refresh: 'bad-refresh' });
    await expect(api.get('/api/v1/me')).rejects.toMatchObject({ response: { status: 401 } });
    expect(cleared).toBe(true);
  });
});
