import { contextBridge } from 'electron';

contextBridge.exposeInMainWorld('api', {
  // Filled in by Task 2 (IPC contract). Empty placeholder so the renderer can
  // boot and we can verify the dev window opens.
});
