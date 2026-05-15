import { createApi } from './api';
import { useAuthStore, saveAuth, clearAuth } from '@/stores/auth';
import { useSettingsStore } from '@/stores/settings';
import type { AxiosInstance } from 'axios';

let instance: AxiosInstance | null = null;

export const getApi = (): AxiosInstance => {
  if (instance) return instance;
  instance = createApi({
    baseURL: useSettingsStore.getState().prefs.backendUrl,
    getTokens: () => useAuthStore.getState().tokens,
    setTokens: (t) => {
      void saveAuth(t);
    },
    clearTokens: () => {
      void clearAuth();
    },
  });
  // Reconfigure baseURL whenever settings change.
  useSettingsStore.subscribe((state) => {
    if (instance) instance.defaults.baseURL = state.prefs.backendUrl;
  });
  return instance;
};
