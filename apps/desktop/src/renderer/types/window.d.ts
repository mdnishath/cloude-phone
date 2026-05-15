import type { ApiBridge } from '@/../shared/ipc-types';

declare global {
  interface Window {
    api: ApiBridge;
  }
}

export {};
