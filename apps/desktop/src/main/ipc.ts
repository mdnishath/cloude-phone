import { ipcMain, shell } from 'electron';
import { clearTokens, loadTokens, saveTokens } from './secure-storage';
import type { TokenPair } from '../shared/ipc-types';

export const registerAuthIpc = (): void => {
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
  ipcMain.handle('app:openExternal', (_e, url: string) => {
    void shell.openExternal(url);
  });
};
