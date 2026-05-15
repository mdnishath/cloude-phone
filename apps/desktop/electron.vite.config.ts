import { defineConfig, externalizeDepsPlugin } from 'electron-vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: { outDir: 'out/main', rollupOptions: { input: resolve(__dirname, 'src/main/main.ts') } },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: { outDir: 'out/preload', rollupOptions: { input: resolve(__dirname, 'src/main/preload.ts') } },
  },
  renderer: {
    root: 'src/renderer',
    plugins: [react()],
    resolve: { alias: { '@': resolve(__dirname, 'src/renderer') } },
    build: {
      outDir: 'out/renderer',
      rollupOptions: { input: resolve(__dirname, 'src/renderer/index.html') },
    },
  },
});
