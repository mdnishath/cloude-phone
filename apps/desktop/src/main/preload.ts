import { contextBridge, ipcRenderer } from 'electron';
import type { ApiBridge, IpcChannel, IpcContract } from '../shared/ipc-types';

const api: ApiBridge = {
  invoke: <K extends IpcChannel>(channel: K, ...args: IpcContract[K]['args']) =>
    ipcRenderer.invoke(channel, ...args) as Promise<IpcContract[K]['result']>,
};

contextBridge.exposeInMainWorld('api', api);
