export interface TokenPair {
  access: string;
  refresh: string;
}

export interface AuthBootstrapResult {
  hasToken: boolean;
  tokens: TokenPair | null;
}

export interface Prefs {
  backendUrl: string;
  theme: 'system' | 'light' | 'dark';
}

export interface IpcContract {
  'auth:bootstrap': { args: []; result: AuthBootstrapResult };
  'auth:save': { args: [TokenPair]; result: void };
  'auth:clear': { args: []; result: void };
  'prefs:get': { args: []; result: Prefs };
  'prefs:set': { args: [Partial<Prefs>]; result: Prefs };
  'app:openExternal': { args: [string]; result: void };
}

export type IpcChannel = keyof IpcContract;

export interface ApiBridge {
  invoke<K extends IpcChannel>(
    channel: K,
    ...args: IpcContract[K]['args']
  ): Promise<IpcContract[K]['result']>;
}
