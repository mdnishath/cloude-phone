import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getApi } from './api-client';
import type { DeviceState } from './state-machine';

export interface DeviceProfile {
  id: string;
  name: string;
  android_version: string;
  screen_width: number;
  screen_height: number;
  screen_dpi: number;
  ram_mb: number;
  cpu_cores: number;
  manufacturer: string;
  model: string;
  is_public: boolean;
}

export interface Proxy {
  id: string;
  label: string;
  type: 'socks5' | 'http';
  host: string;
  port: number;
  username: string | null;
  has_password: boolean;
  created_at: string;
}

export interface Device {
  id: string;
  name: string;
  profile_id: string;
  proxy_id: string | null;
  state: DeviceState;
  state_reason: string | null;
  adb_host_port: number | null;
  created_at: string;
  started_at: string | null;
  stopped_at: string | null;
}

export interface UserPublic {
  id: string;
  email: string;
  role: 'admin' | 'user';
  quota_instances: number;
  created_at: string;
}

export interface AdbInfo {
  host: string;
  port: number;
  command: string;
}

export const useMeQuery = () =>
  useQuery({
    queryKey: ['me'],
    queryFn: async () => (await getApi().get<UserPublic>('/api/v1/me')).data,
  });

export const useDevicesQuery = () =>
  useQuery({
    queryKey: ['devices'],
    queryFn: async () => (await getApi().get<Device[]>('/api/v1/devices')).data,
    refetchOnWindowFocus: true,
  });

export const useDeviceQuery = (id: string | undefined) =>
  useQuery({
    queryKey: ['device', id],
    queryFn: async () => (await getApi().get<Device>(`/api/v1/devices/${id}`)).data,
    enabled: !!id,
  });

export const useProfilesQuery = () =>
  useQuery({
    queryKey: ['profiles'],
    queryFn: async () => (await getApi().get<DeviceProfile[]>('/api/v1/device-profiles')).data,
  });

export const useProxiesQuery = () =>
  useQuery({
    queryKey: ['proxies'],
    queryFn: async () => (await getApi().get<Proxy[]>('/api/v1/proxies')).data,
  });

export const useAdbInfoQuery = (id: string | undefined) =>
  useQuery({
    queryKey: ['adb-info', id],
    queryFn: async () => (await getApi().get<AdbInfo>(`/api/v1/devices/${id}/adb-info`)).data,
    enabled: !!id,
  });

interface CreateProxyBody {
  label: string;
  type: 'socks5' | 'http';
  host: string;
  port: number;
  username?: string | null;
  password?: string | null;
}

export const useCreateProxy = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: CreateProxyBody) =>
      (await getApi().post<Proxy>('/api/v1/proxies', body)).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['proxies'] });
    },
  });
};

export const useDeleteProxy = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await getApi().delete(`/api/v1/proxies/${id}`);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['proxies'] });
    },
  });
};

interface CreateDeviceBody {
  name: string;
  profile_id: string;
  proxy_id: string;
}

export const useCreateDevice = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: CreateDeviceBody) =>
      (await getApi().post<Device>('/api/v1/devices', body)).data,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['devices'] });
    },
  });
};

const deviceAction = (verb: 'start' | 'stop') => () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      (await getApi().post<Device>(`/api/v1/devices/${id}/${verb}`)).data,
    onSuccess: (_data, id) => {
      void qc.invalidateQueries({ queryKey: ['devices'] });
      void qc.invalidateQueries({ queryKey: ['device', id] });
    },
  });
};

export const useStartDevice = deviceAction('start');
export const useStopDevice = deviceAction('stop');

export const useDeleteDevice = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await getApi().delete(`/api/v1/devices/${id}`);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['devices'] });
    },
  });
};

interface AuthResponse {
  access: string;
  refresh: string;
  token_type: string;
}

export const useLoginMutation = () =>
  useMutation({
    mutationFn: async (body: { email: string; password: string }) =>
      (await getApi().post<AuthResponse>('/api/v1/auth/login', body)).data,
  });

export const useRedeemInviteMutation = () =>
  useMutation({
    mutationFn: async (body: { token: string; email: string; password: string }) =>
      (await getApi().post<AuthResponse>('/api/v1/auth/redeem-invite', body)).data,
  });
