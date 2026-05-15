import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';
import type { TokenPair } from '@/../shared/ipc-types';

export interface ApiOptions {
  baseURL: string;
  getTokens: () => TokenPair | null;
  setTokens: (tokens: TokenPair) => void;
  clearTokens: () => void;
}

interface RetryFlag extends InternalAxiosRequestConfig {
  __retried?: boolean;
}

export const createApi = ({
  baseURL,
  getTokens,
  setTokens,
  clearTokens,
}: ApiOptions): AxiosInstance => {
  const instance = axios.create({ baseURL, headers: { 'content-type': 'application/json' } });

  instance.interceptors.request.use((config) => {
    const tokens = getTokens();
    if (tokens) {
      config.headers.set('Authorization', `Bearer ${tokens.access}`);
    }
    return config;
  });

  instance.interceptors.response.use(
    (r) => r,
    async (error: { config?: RetryFlag; response?: { status?: number } }) => {
      const original = error.config;
      if (!original || original.__retried) throw error;
      if (error.response?.status !== 401) throw error;

      original.__retried = true;
      const tokens = getTokens();
      if (!tokens) {
        clearTokens();
        throw error;
      }
      try {
        const refreshed = await axios.post<{ access: string; refresh: string }>(
          `${baseURL}/api/v1/auth/refresh`,
          { refresh: tokens.refresh }
        );
        const newTokens: TokenPair = {
          access: refreshed.data.access,
          refresh: refreshed.data.refresh,
        };
        setTokens(newTokens);
        original.headers.set('Authorization', `Bearer ${newTokens.access}`);
        return instance.request(original);
      } catch (refreshErr) {
        clearTokens();
        throw error;
      }
    }
  );

  return instance;
};
