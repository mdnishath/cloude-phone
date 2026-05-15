import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
});

// Stub window.api for tests that don't use msw.
const noop = async (): Promise<unknown> => undefined;
(globalThis as unknown as { window: typeof window }).window = (globalThis as unknown as { window: typeof window }).window ?? ({} as typeof window);
(window as unknown as { api: { invoke: typeof noop } }).api = { invoke: noop };
