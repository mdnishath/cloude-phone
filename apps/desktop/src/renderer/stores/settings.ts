import { create } from 'zustand';
import type { Prefs } from '@/../shared/ipc-types';

interface SettingsState {
  prefs: Prefs;
  setPrefs: (next: Prefs) => void;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  prefs: { backendUrl: 'http://localhost:8000', theme: 'system' },
  setPrefs: (next) => set({ prefs: next }),
}));

export const bootstrapSettings = async (): Promise<void> => {
  const prefs = await window.api.invoke('prefs:get');
  useSettingsStore.setState({ prefs });
  applyTheme(prefs.theme);
};

export const updateSettings = async (partial: Partial<Prefs>): Promise<Prefs> => {
  const next = await window.api.invoke('prefs:set', partial);
  useSettingsStore.setState({ prefs: next });
  applyTheme(next.theme);
  return next;
};

const applyTheme = (theme: Prefs['theme']): void => {
  const root = document.documentElement;
  const wantDark =
    theme === 'dark' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  root.classList.toggle('dark', wantDark);
};
