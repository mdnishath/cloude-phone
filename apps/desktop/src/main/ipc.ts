import { ipcMain, shell } from 'electron';
import { clearTokens, loadTokens, saveTokens } from './secure-storage';
import { getPrefs, setPrefs } from './prefs-store';
import type { Prefs, TokenPair } from '../shared/ipc-types';

export const registerIpc = (): void => {
  ipcMain.handle('auth:bootstrap', () => {
    const tokens = loadTokens();
    return { hasToken: tokens !== null, tokens };
  });
  ipcMain.handle('auth:save', (_e, tokens: TokenPair) => {
    saveTokens(tokens);
  });
  ipcMain.handle('auth:clear', () => {
    clearTokens();
  });
  ipcMain.handle('prefs:get', () => getPrefs());
  ipcMain.handle('prefs:set', (_e, partial: Partial<Prefs>) => setPrefs(partial));
  ipcMain.handle('app:openExternal', (_e, url: string) => {
    void shell.openExternal(url);
  });
};
