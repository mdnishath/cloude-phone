import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { create } from 'zustand';
import { useAuthStore } from '@/stores/auth';
import { useSettingsStore } from '@/stores/settings';

interface WsState {
  connected: number; // count of active subscriptions
  reconnecting: boolean;
  setConnected: (n: number) => void;
  setReconnecting: (r: boolean) => void;
}

export const useWsStore = create<WsState>((set) => ({
  connected: 0,
  reconnecting: false,
  setConnected: (n) => set({ connected: n }),
  setReconnecting: (r) => set({ reconnecting: r }),
}));

interface DeviceStatusMessage {
  device_id?: string;
  state?: string;
  state_reason?: string | null;
  adb_host_port?: number | null;
  heartbeat?: boolean;
}

const httpToWs = (url: string): string => url.replace(/^http/, 'ws');

export const useDeviceStatusWS = (deviceId: string | undefined): void => {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!deviceId) return;
    const token = useAuthStore.getState().tokens?.access;
    const backend = useSettingsStore.getState().prefs.backendUrl;
    if (!token) return;

    let attempt = 0;
    let ws: WebSocket | null = null;
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const open = (): void => {
      ws = new WebSocket(
        `${httpToWs(backend)}/ws/devices/${deviceId}/status?token=${encodeURIComponent(token)}`
      );

      ws.onopen = () => {
        attempt = 0;
        useWsStore.setState((s) => ({ connected: s.connected + 1, reconnecting: false }));
      };

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data) as DeviceStatusMessage;
          if (msg.heartbeat) return;
          queryClient.setQueryData<
            | { state?: string; state_reason?: string | null; adb_host_port?: number | null }
            | undefined
          >(['device', deviceId], (prev) =>
            prev
              ? {
                  ...prev,
                  state: msg.state ?? prev.state,
                  state_reason: msg.state_reason ?? prev.state_reason,
                  adb_host_port: msg.adb_host_port ?? prev.adb_host_port,
                }
              : prev
          );
          void queryClient.invalidateQueries({ queryKey: ['devices'] });
        } catch {
          /* ignore malformed */
        }
      };

      ws.onclose = () => {
        useWsStore.setState((s) => ({ connected: Math.max(0, s.connected - 1) }));
        if (cancelled) return;
        useWsStore.setState({ reconnecting: true });
        attempt += 1;
        const delayMs = Math.min(30_000, 1000 * 2 ** Math.min(attempt - 1, 4));
        reconnectTimer = setTimeout(open, delayMs);
      };
    };

    open();
    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [deviceId, queryClient]);
};
