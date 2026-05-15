import Store from 'electron-store';
import type { Prefs } from '../shared/ipc-types';

const DEFAULTS: Prefs = { backendUrl: 'http://localhost:8000', theme: 'system' };

const store = new Store<Prefs>({ name: 'prefs', defaults: DEFAULTS });

export const getPrefs = (): Prefs => ({
  backendUrl: store.get('backendUrl', DEFAULTS.backendUrl),
  theme: store.get('theme', DEFAULTS.theme),
});

export const setPrefs = (partial: Partial<Prefs>): Prefs => {
  if (partial.backendUrl !== undefined) store.set('backendUrl', partial.backendUrl);
  if (partial.theme !== undefined) store.set('theme', partial.theme);
  return getPrefs();
};
