import { app, safeStorage } from 'electron';
import { readFileSync, writeFileSync, existsSync, unlinkSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import type { TokenPair } from '../shared/ipc-types';

const tokensFile = (): string => join(app.getPath('userData'), 'auth.bin');

export const loadTokens = (): TokenPair | null => {
  const path = tokensFile();
  if (!existsSync(path)) return null;
  try {
    const encrypted = readFileSync(path);
    if (!safeStorage.isEncryptionAvailable()) return null;
    const plaintext = safeStorage.decryptString(encrypted);
    const parsed = JSON.parse(plaintext) as TokenPair;
    if (typeof parsed.access === 'string' && typeof parsed.refresh === 'string') return parsed;
    return null;
  } catch {
    return null;
  }
};

export const saveTokens = (tokens: TokenPair): void => {
  if (!safeStorage.isEncryptionAvailable()) {
    throw new Error('OS encryption is not available; refusing to write plaintext tokens.');
  }
  const path = tokensFile();
  mkdirSync(dirname(path), { recursive: true });
  const encrypted = safeStorage.encryptString(JSON.stringify(tokens));
  writeFileSync(path, encrypted, { mode: 0o600 });
};

export const clearTokens = (): void => {
  const path = tokensFile();
  if (existsSync(path)) unlinkSync(path);
};
