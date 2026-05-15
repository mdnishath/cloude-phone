import { create } from 'zustand';
import type { TokenPair } from '@/../shared/ipc-types';

export interface UserPublic {
  id: string;
  email: string;
  role: 'admin' | 'user';
  quota_instances: number;
  created_at: string;
}

export type AuthStatus = 'loading' | 'authed' | 'anonymous';

interface AuthState {
  status: AuthStatus;
  tokens: TokenPair | null;
  user: UserPublic | null;
  setTokens: (tokens: TokenPair | null) => void;
  setUser: (user: UserPublic | null) => void;
  setStatus: (status: AuthStatus) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  status: 'loading',
  tokens: null,
  user: null,
  setTokens: (tokens) => set({ tokens }),
  setUser: (user) => set({ user }),
  setStatus: (status) => set({ status }),
}));

export const bootstrapAuth = async (): Promise<void> => {
  const result = await window.api.invoke('auth:bootstrap');
  if (result.hasToken && result.tokens) {
    useAuthStore.setState({ tokens: result.tokens, status: 'authed' });
  } else {
    useAuthStore.setState({ status: 'anonymous' });
  }
};

export const saveAuth = async (tokens: TokenPair): Promise<void> => {
  await window.api.invoke('auth:save', tokens);
  useAuthStore.setState({ tokens, status: 'authed' });
};

export const clearAuth = async (): Promise<void> => {
  await window.api.invoke('auth:clear');
  useAuthStore.setState({ tokens: null, user: null, status: 'anonymous' });
};
