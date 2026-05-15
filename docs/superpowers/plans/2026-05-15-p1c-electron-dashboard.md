# P1c — Electron Desktop Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `apps/desktop/` Electron + React + TypeScript dashboard that lets you log in / redeem an invite, manage devices and proxies, and watch live state transitions over the P1a+P1b backend.

**Architecture:** electron-vite project with two TypeScript processes — `main` (window lifecycle, safeStorage for auth tokens, electron-store for prefs, typed IPC) and `renderer` (React 18 + React Router 6 + TanStack Query for server state + Zustand for local state + Tailwind + shadcn/ui). One typed IPC contract in `src/shared/ipc-types.ts` keeps the two sides in sync. The renderer reaches the backend over HTTP and subscribes to `/ws/devices/{id}/status` for live updates; backend URL is editable in Settings (default `http://localhost:8000`).

**Tech Stack:** Node 20, Electron 30, electron-vite 2, electron-builder 24, electron-store 9, React 18, React Router 6, TanStack Query 5, Zustand 4, Axios 1.7, Tailwind 3.4, shadcn/ui (Radix primitives), react-hook-form 7, zod 3, Vitest 1.6, @testing-library/react 15, msw 2.

**Source spec:** [docs/superpowers/specs/2026-05-15-p1c-electron-dashboard-design.md](../specs/2026-05-15-p1c-electron-dashboard-design.md).

**TDD policy in this plan:** Pure logic gets red-green TDD (state machine, axios interceptor, format helpers, IPC contract types). UI components get tests written alongside (Vitest + Testing Library), not strict red-first. Wiring/composition tasks (Router, AppShell, navigation) get a manual smoke step in dev mode instead of a separate test.

**Always-green discipline:** After every task, `npm run dev` should still open a window and not crash. Each task says how to smoke that.

---

## File Structure (target after P1c)

```
apps/desktop/
├── package.json
├── electron-builder.yml
├── electron.vite.config.ts
├── tsconfig.json, tsconfig.node.json, tsconfig.web.json
├── tailwind.config.ts, postcss.config.cjs
├── components.json
├── .eslintrc.cjs, .prettierrc, .gitignore
├── resources/icon.ico, icon.png
├── src/
│   ├── shared/ipc-types.ts
│   ├── main/{main.ts, preload.ts, secure-storage.ts, prefs-store.ts, ipc.ts}
│   └── renderer/
│       ├── index.html, main.tsx, App.tsx
│       ├── styles/index.css
│       ├── routes/{Login,Redeem,DevicesIndex,DeviceDetail,DeviceNew,ProxiesIndex,ProxyNew,Settings}.tsx
│       ├── components/
│       │   ├── ui/  (shadcn primitives)
│       │   ├── layout/{AppShell,Sidebar,ProtectedRoute}.tsx
│       │   ├── devices/{DeviceCard,StateBadge,DeviceWizard,DeviceActions,AdbInfoCard,StreamPlaceholder}.tsx
│       │   ├── proxies/{ProxyTable,ProxyForm}.tsx
│       │   └── feedback/{Toaster,ConnectionBanner}.tsx
│       ├── lib/{api,auth,ws,queries,state-machine,format,utils}.ts
│       └── stores/{auth,settings}.ts
└── tests/
    ├── setup.ts
    ├── mocks/handlers.ts            (msw)
    ├── unit/{state-machine,format,api}.test.ts
    └── component/{ProxyForm,DeviceActions,LoginForm}.test.tsx
```

---

## Task 0: Scaffold `apps/desktop/` with electron-vite

**Files:**
- Create: `apps/desktop/package.json`
- Create: `apps/desktop/tsconfig.json`, `tsconfig.node.json`, `tsconfig.web.json`
- Create: `apps/desktop/electron.vite.config.ts`
- Create: `apps/desktop/src/main/main.ts`, `src/main/preload.ts`
- Create: `apps/desktop/src/renderer/index.html`, `src/renderer/main.tsx`, `src/renderer/App.tsx`
- Create: `apps/desktop/.gitignore`

- [ ] **Step 1:** Make directories

```bash
mkdir -p apps/desktop/src/main apps/desktop/src/preload apps/desktop/src/renderer apps/desktop/src/shared apps/desktop/resources apps/desktop/tests
```

- [ ] **Step 2:** Write `apps/desktop/package.json`

```json
{
  "name": "cloude-desktop",
  "version": "0.1.0",
  "private": true,
  "description": "Cloude Phone desktop dashboard",
  "main": "./out/main/main.js",
  "scripts": {
    "dev": "electron-vite dev",
    "build": "electron-vite build && tsc --noEmit -p tsconfig.web.json && tsc --noEmit -p tsconfig.node.json",
    "lint": "eslint . --ext .ts,.tsx --max-warnings 0",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "test": "vitest run",
    "test:watch": "vitest",
    "package": "electron-vite build && electron-builder --win --publish never"
  },
  "dependencies": {
    "electron-store": "9.2.0"
  },
  "devDependencies": {
    "electron": "30.0.9",
    "electron-vite": "2.2.0",
    "electron-builder": "24.13.3",
    "vite": "5.2.11",
    "typescript": "5.4.5",
    "@types/node": "20.12.12"
  }
}
```

- [ ] **Step 3:** Write `apps/desktop/tsconfig.json`

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.node.json" },
    { "path": "./tsconfig.web.json" }
  ]
}
```

- [ ] **Step 4:** Write `apps/desktop/tsconfig.node.json`

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "esModuleInterop": true,
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "skipLibCheck": true,
    "types": ["node"]
  },
  "include": ["src/main/**/*", "src/preload/**/*", "src/shared/**/*", "electron.vite.config.ts"]
}
```

- [ ] **Step 5:** Write `apps/desktop/tsconfig.web.json`

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "esModuleInterop": true,
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "skipLibCheck": true,
    "useDefineForClassFields": true,
    "isolatedModules": true,
    "resolveJsonModule": true,
    "allowSyntheticDefaultImports": true,
    "baseUrl": "./src/renderer",
    "paths": {
      "@/*": ["./*"]
    },
    "types": ["vite/client"]
  },
  "include": ["src/renderer/**/*", "src/shared/**/*"]
}
```

- [ ] **Step 6:** Write `apps/desktop/electron.vite.config.ts`

```ts
import { defineConfig, externalizeDepsPlugin } from 'electron-vite';
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
    resolve: { alias: { '@': resolve(__dirname, 'src/renderer') } },
    build: {
      outDir: 'out/renderer',
      rollupOptions: { input: resolve(__dirname, 'src/renderer/index.html') },
    },
  },
});
```

- [ ] **Step 7:** Write `apps/desktop/src/main/main.ts`

```ts
import { app, BrowserWindow } from 'electron';
import { join } from 'node:path';

const createWindow = (): void => {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 720,
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/preload.js'),
      sandbox: false,
    },
  });
  if (process.env.ELECTRON_RENDERER_URL) {
    void win.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    void win.loadFile(join(__dirname, '../renderer/index.html'));
  }
};

void app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
```

- [ ] **Step 8:** Write `apps/desktop/src/main/preload.ts`

```ts
import { contextBridge } from 'electron';

contextBridge.exposeInMainWorld('api', {
  // Filled in by Task 2 (IPC contract). Empty placeholder so the renderer can
  // boot and we can verify the dev window opens.
});
```

- [ ] **Step 9:** Write `apps/desktop/src/renderer/index.html`

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Cloude Phone</title>
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; connect-src 'self' http://localhost:* ws://localhost:* http://127.0.0.1:* ws://127.0.0.1:*; style-src 'self' 'unsafe-inline';" />
  </head>
  <body>
    <div id="root">Loading…</div>
    <script type="module" src="./main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 10:** Write `apps/desktop/src/renderer/main.tsx`

```tsx
import { App } from './App';
import { createRoot } from 'react-dom/client';

const el = document.getElementById('root');
if (!el) throw new Error('root element missing');
createRoot(el).render(<App />);
```

- [ ] **Step 11:** Write `apps/desktop/src/renderer/App.tsx`

```tsx
export const App = (): JSX.Element => (
  <div style={{ padding: 24, fontFamily: 'sans-serif' }}>
    <h1>Cloude Phone</h1>
    <p>Scaffold OK. Replace with router in Task 9.</p>
  </div>
);
```

- [ ] **Step 12:** Write `apps/desktop/.gitignore`

```
node_modules/
out/
dist/
.vite/
.turbo/
*.local
*.log
```

- [ ] **Step 13:** Install React + electron-vite plumbing

```bash
cd apps/desktop && npm install --silent
npm install --silent --save react@18.3.1 react-dom@18.3.1
npm install --silent --save-dev @types/react@18.3.2 @types/react-dom@18.3.0 @vitejs/plugin-react@4.3.0
```

Add `@vitejs/plugin-react` to the renderer config — open `electron.vite.config.ts` and replace the `renderer` block with:
```ts
  renderer: {
    root: 'src/renderer',
    plugins: [require('@vitejs/plugin-react')()],
    resolve: { alias: { '@': resolve(__dirname, 'src/renderer') } },
    build: {
      outDir: 'out/renderer',
      rollupOptions: { input: resolve(__dirname, 'src/renderer/index.html') },
    },
  },
```
(Switch the import at the top to ESM if needed: `import react from '@vitejs/plugin-react';` and use `plugins: [react()]`.)

- [ ] **Step 14:** Smoke — open the window once

```bash
cd apps/desktop && npm run dev
```
Expected: a window titled "Cloude Phone" opens, shows the heading and placeholder paragraph. Close it (Ctrl-C in the terminal).

- [ ] **Step 15:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): scaffold electron-vite + react skeleton"
```

---

## Task 1: Tailwind CSS + shadcn/ui base setup

**Files:**
- Create: `apps/desktop/tailwind.config.ts`, `postcss.config.cjs`
- Create: `apps/desktop/src/renderer/styles/index.css`
- Create: `apps/desktop/src/renderer/lib/utils.ts`
- Create: `apps/desktop/components.json`
- Modify: `apps/desktop/src/renderer/main.tsx` (import styles)
- Modify: `apps/desktop/src/renderer/App.tsx` (use a styled button)

- [ ] **Step 1:** Install deps

```bash
cd apps/desktop && npm install --silent --save-dev tailwindcss@3.4.3 postcss@8.4.38 autoprefixer@10.4.19
npm install --silent --save class-variance-authority@0.7.0 clsx@2.1.1 tailwind-merge@2.3.0 lucide-react@0.378.0
npm install --silent --save @radix-ui/react-slot@1.0.2
```

- [ ] **Step 2:** Write `apps/desktop/postcss.config.cjs`

```cjs
module.exports = {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
```

- [ ] **Step 3:** Write `apps/desktop/tailwind.config.ts`

```ts
import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: ['class'],
  content: ['./src/renderer/**/*.{ts,tsx,html}'],
  theme: {
    container: { center: true, padding: '2rem', screens: { '2xl': '1400px' } },
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: { DEFAULT: 'hsl(var(--primary))', foreground: 'hsl(var(--primary-foreground))' },
        secondary: { DEFAULT: 'hsl(var(--secondary))', foreground: 'hsl(var(--secondary-foreground))' },
        destructive: { DEFAULT: 'hsl(var(--destructive))', foreground: 'hsl(var(--destructive-foreground))' },
        muted: { DEFAULT: 'hsl(var(--muted))', foreground: 'hsl(var(--muted-foreground))' },
        accent: { DEFAULT: 'hsl(var(--accent))', foreground: 'hsl(var(--accent-foreground))' },
        card: { DEFAULT: 'hsl(var(--card))', foreground: 'hsl(var(--card-foreground))' },
      },
      borderRadius: { lg: 'var(--radius)', md: 'calc(var(--radius) - 2px)', sm: 'calc(var(--radius) - 4px)' },
    },
  },
  plugins: [],
};

export default config;
```

- [ ] **Step 4:** Write `apps/desktop/src/renderer/styles/index.css`

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --primary: 222.2 47.4% 11.2%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 222.2 84% 4.9%;
    --radius: 0.5rem;
  }
  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    --card: 222.2 84% 4.9%;
    --card-foreground: 210 40% 98%;
    --primary: 210 40% 98%;
    --primary-foreground: 222.2 47.4% 11.2%;
    --secondary: 217.2 32.6% 17.5%;
    --secondary-foreground: 210 40% 98%;
    --muted: 217.2 32.6% 17.5%;
    --muted-foreground: 215 20.2% 65.1%;
    --accent: 217.2 32.6% 17.5%;
    --accent-foreground: 210 40% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 210 40% 98%;
    --border: 217.2 32.6% 17.5%;
    --input: 217.2 32.6% 17.5%;
    --ring: 212.7 26.8% 83.9%;
  }
  body { @apply bg-background text-foreground; font-family: ui-sans-serif, system-ui, sans-serif; }
}
```

- [ ] **Step 5:** Write `apps/desktop/src/renderer/lib/utils.ts`

```ts
import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export const cn = (...inputs: ClassValue[]): string => twMerge(clsx(inputs));
```

- [ ] **Step 6:** Write `apps/desktop/components.json` (shadcn config)

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/renderer/styles/index.css",
    "baseColor": "slate",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils"
  }
}
```

- [ ] **Step 7:** Add a shadcn `Button` component directly (we won't run shadcn CLI; we'll write the source ourselves to keep the dependency tree minimal). Create `apps/desktop/src/renderer/components/ui/button.tsx`:

```tsx
import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 rounded-md px-3',
        lg: 'h-11 rounded-md px-8',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  }
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  }
);
Button.displayName = 'Button';
```

- [ ] **Step 8:** Update `apps/desktop/src/renderer/main.tsx` to import styles. Replace existing content with:

```tsx
import './styles/index.css';
import { App } from './App';
import { createRoot } from 'react-dom/client';

const el = document.getElementById('root');
if (!el) throw new Error('root element missing');
createRoot(el).render(<App />);
```

- [ ] **Step 9:** Replace `apps/desktop/src/renderer/App.tsx` to render the Button:

```tsx
import { Button } from '@/components/ui/button';

export const App = (): JSX.Element => (
  <div className="p-6 space-y-4">
    <h1 className="text-2xl font-semibold">Cloude Phone</h1>
    <p className="text-muted-foreground">Tailwind + shadcn smoke. Replace with router in Task 9.</p>
    <Button>Primary</Button>
    <Button variant="outline">Outline</Button>
    <Button variant="destructive">Destructive</Button>
  </div>
);
```

- [ ] **Step 10:** Smoke

```bash
cd apps/desktop && npm run dev
```
Expected: window opens, heading + paragraph styled, three buttons render with correct colors. Close it.

- [ ] **Step 11:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): tailwind + shadcn base (Button) + theme tokens"
```

---

## Task 2: Shared IPC types + preload + typed `window.api`

**Files:**
- Create: `apps/desktop/src/shared/ipc-types.ts`
- Modify: `apps/desktop/src/main/preload.ts`
- Create: `apps/desktop/src/renderer/types/window.d.ts`

- [ ] **Step 1:** Write the shared contract — `apps/desktop/src/shared/ipc-types.ts`

```ts
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
  'auth:save':      { args: [TokenPair]; result: void };
  'auth:clear':     { args: []; result: void };
  'prefs:get':      { args: []; result: Prefs };
  'prefs:set':      { args: [Partial<Prefs>]; result: Prefs };
  'app:openExternal': { args: [string]; result: void };
}

export type IpcChannel = keyof IpcContract;

export interface ApiBridge {
  invoke<K extends IpcChannel>(channel: K, ...args: IpcContract[K]['args']): Promise<IpcContract[K]['result']>;
}
```

- [ ] **Step 2:** Update preload — overwrite `apps/desktop/src/main/preload.ts`

```ts
import { contextBridge, ipcRenderer } from 'electron';
import type { ApiBridge, IpcChannel, IpcContract } from '../shared/ipc-types';

const api: ApiBridge = {
  invoke: <K extends IpcChannel>(channel: K, ...args: IpcContract[K]['args']) =>
    ipcRenderer.invoke(channel, ...args) as Promise<IpcContract[K]['result']>,
};

contextBridge.exposeInMainWorld('api', api);
```

- [ ] **Step 3:** Declare the `window.api` global for the renderer — create `apps/desktop/src/renderer/types/window.d.ts`

```ts
import type { ApiBridge } from '@/../shared/ipc-types';

declare global {
  interface Window {
    api: ApiBridge;
  }
}

export {};
```

- [ ] **Step 4:** Verify the renderer typechecks against the contract. Update `App.tsx` to add a smoke that compiles but does nothing at runtime (the handler doesn't exist yet — call it from a button click that's disabled):

```tsx
import { Button } from '@/components/ui/button';

export const App = (): JSX.Element => {
  const handleBoot = async (): Promise<void> => {
    // Will start working after Tasks 3-4 register handlers
    const result = await window.api.invoke('auth:bootstrap');
    console.log('bootstrap', result);
  };
  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Cloude Phone</h1>
      <p className="text-muted-foreground">IPC contract wired. Handlers land in Tasks 3-4.</p>
      <Button onClick={handleBoot}>Test IPC (will throw until Task 3)</Button>
    </div>
  );
};
```

- [ ] **Step 5:** Typecheck

```bash
cd apps/desktop && npx tsc --noEmit -p tsconfig.web.json
```
Expected: no errors.

- [ ] **Step 6:** Smoke

```bash
cd apps/desktop && npm run dev
```
Expected: window opens. Click "Test IPC" — DevTools console shows an error like `No handler registered for 'auth:bootstrap'`. That's expected; we wire the handler next.

- [ ] **Step 7:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): typed IPC contract + preload bridge"
```

---

## Task 3: Main process — secure-storage wrapper + auth IPC handlers (TDD on shape)

**Files:**
- Create: `apps/desktop/src/main/secure-storage.ts`
- Create: `apps/desktop/src/main/ipc.ts`
- Modify: `apps/desktop/src/main/main.ts` (register handlers)

- [ ] **Step 1:** Write `apps/desktop/src/main/secure-storage.ts`

```ts
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
```

- [ ] **Step 2:** Write `apps/desktop/src/main/ipc.ts`

```ts
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
```

- [ ] **Step 3:** Register handlers — modify `apps/desktop/src/main/main.ts`. Replace the entire file with:

```ts
import { app, BrowserWindow } from 'electron';
import { join } from 'node:path';
import { registerAuthIpc } from './ipc';

const createWindow = (): void => {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 720,
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/preload.js'),
      sandbox: false,
    },
  });
  if (process.env.ELECTRON_RENDERER_URL) {
    void win.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    void win.loadFile(join(__dirname, '../renderer/index.html'));
  }
};

void app.whenReady().then(() => {
  registerAuthIpc();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
```

- [ ] **Step 4:** Smoke

```bash
cd apps/desktop && npm run dev
```
Click the "Test IPC" button — DevTools console should now print `bootstrap { hasToken: false, tokens: null }`. Open DevTools (`Ctrl+Shift+I`).

- [ ] **Step 5:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): main-process auth IPC + safeStorage token persistence"
```

---

## Task 4: Main process — prefs-store + prefs IPC handlers

**Files:**
- Create: `apps/desktop/src/main/prefs-store.ts`
- Modify: `apps/desktop/src/main/ipc.ts` (add prefs handlers)
- Modify: `apps/desktop/src/main/main.ts` (call register)

- [ ] **Step 1:** Write `apps/desktop/src/main/prefs-store.ts`

```ts
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
```

- [ ] **Step 2:** Add prefs handlers to `apps/desktop/src/main/ipc.ts`. Replace the whole file with:

```ts
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
```

- [ ] **Step 3:** Update `apps/desktop/src/main/main.ts` to import `registerIpc` instead of `registerAuthIpc`. Find and replace:

```ts
import { registerAuthIpc } from './ipc';
```
with:
```ts
import { registerIpc } from './ipc';
```
And:
```ts
  registerAuthIpc();
```
with:
```ts
  registerIpc();
```

- [ ] **Step 4:** Smoke — update `App.tsx` temporarily to test prefs:

```tsx
import { Button } from '@/components/ui/button';
import { useEffect, useState } from 'react';

export const App = (): JSX.Element => {
  const [info, setInfo] = useState<string>('…');
  useEffect(() => {
    (async () => {
      const prefs = await window.api.invoke('prefs:get');
      const auth = await window.api.invoke('auth:bootstrap');
      setInfo(`backend=${prefs.backendUrl} theme=${prefs.theme} hasToken=${auth.hasToken}`);
    })().catch((e) => setInfo(`error: ${String(e)}`));
  }, []);
  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Cloude Phone</h1>
      <p className="text-muted-foreground">{info}</p>
      <Button onClick={() => void window.api.invoke('prefs:set', { backendUrl: 'http://localhost:9999' }).then((p) => setInfo(`updated: ${p.backendUrl}`))}>
        Set backend → 9999
      </Button>
    </div>
  );
};
```

Run `npm run dev`. Expected: page shows `backend=http://localhost:8000 theme=system hasToken=false`. Click button → flips to 9999. Restart app → still 9999 (prefs persisted). Manually edit `%APPDATA%/cloude-desktop/prefs.json` (or whatever path electron-store uses) if needed to reset.

- [ ] **Step 5:** Reset the pref so we don't carry weird URL forward:

In DevTools console run: `await window.api.invoke('prefs:set', { backendUrl: 'http://localhost:8000' })`.

- [ ] **Step 6:** Revert `App.tsx` to the Task 2 version (keep IPC test button removed; we'll wire real screens in Task 10). Replace `App.tsx` with:

```tsx
export const App = (): JSX.Element => (
  <div className="p-6 space-y-4">
    <h1 className="text-2xl font-semibold">Cloude Phone</h1>
    <p className="text-muted-foreground">IPC + prefs wired. Router lands in Task 9.</p>
  </div>
);
```

- [ ] **Step 7:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): electron-store prefs (backendUrl, theme) + IPC"
```

---

## Task 5: Zustand stores — auth + settings

**Files:**
- Create: `apps/desktop/src/renderer/stores/auth.ts`
- Create: `apps/desktop/src/renderer/stores/settings.ts`

- [ ] **Step 1:** Install Zustand

```bash
cd apps/desktop && npm install --silent --save zustand@4.5.2
```

- [ ] **Step 2:** Write `apps/desktop/src/renderer/stores/auth.ts`

```ts
import { create } from 'zustand';
import type { TokenPair } from '@/../shared/ipc-types';

export interface UserPublic {
  id: string;
  email: string;
  role: 'admin' | 'user';
  quota_instances: number;
  created_at: string;
}

export type AuthStatus = 'loading' | 'authed' | 'anonymous';

interface AuthState {
  status: AuthStatus;
  tokens: TokenPair | null;
  user: UserPublic | null;
  setTokens: (tokens: TokenPair | null) => void;
  setUser: (user: UserPublic | null) => void;
  setStatus: (status: AuthStatus) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  status: 'loading',
  tokens: null,
  user: null,
  setTokens: (tokens) => set({ tokens }),
  setUser: (user) => set({ user }),
  setStatus: (status) => set({ status }),
}));

export const bootstrapAuth = async (): Promise<void> => {
  const result = await window.api.invoke('auth:bootstrap');
  if (result.hasToken && result.tokens) {
    useAuthStore.setState({ tokens: result.tokens, status: 'authed' });
  } else {
    useAuthStore.setState({ status: 'anonymous' });
  }
};

export const saveAuth = async (tokens: TokenPair): Promise<void> => {
  await window.api.invoke('auth:save', tokens);
  useAuthStore.setState({ tokens, status: 'authed' });
};

export const clearAuth = async (): Promise<void> => {
  await window.api.invoke('auth:clear');
  useAuthStore.setState({ tokens: null, user: null, status: 'anonymous' });
};
```

- [ ] **Step 3:** Write `apps/desktop/src/renderer/stores/settings.ts`

```ts
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
```

- [ ] **Step 4:** Bootstrap both stores on app load. Update `apps/desktop/src/renderer/main.tsx`:

```tsx
import './styles/index.css';
import { App } from './App';
import { createRoot } from 'react-dom/client';
import { bootstrapAuth } from './stores/auth';
import { bootstrapSettings } from './stores/settings';

const el = document.getElementById('root');
if (!el) throw new Error('root element missing');

Promise.all([bootstrapSettings(), bootstrapAuth()]).finally(() => {
  createRoot(el).render(<App />);
});
```

- [ ] **Step 5:** Smoke — show store contents temporarily in `App.tsx`:

```tsx
import { useAuthStore } from '@/stores/auth';
import { useSettingsStore } from '@/stores/settings';

export const App = (): JSX.Element => {
  const status = useAuthStore((s) => s.status);
  const backend = useSettingsStore((s) => s.prefs.backendUrl);
  const theme = useSettingsStore((s) => s.prefs.theme);
  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Cloude Phone</h1>
      <p className="text-muted-foreground">
        auth.status={status} backend={backend} theme={theme}
      </p>
    </div>
  );
};
```

Run `npm run dev`. Expected: page shows `auth.status=anonymous backend=http://localhost:8000 theme=system`. If dark theme is your OS default, the body should now have a dark background.

- [ ] **Step 6:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): zustand auth + settings stores with IPC bootstrap"
```

---

## Task 6: Axios client + 401 refresh interceptor (TDD)

**Files:**
- Create: `apps/desktop/src/renderer/lib/api.ts`
- Create: `apps/desktop/tests/unit/api.test.ts`
- Create: `apps/desktop/vitest.config.ts`
- Create: `apps/desktop/tests/setup.ts`

- [ ] **Step 1:** Install testing + axios deps

```bash
cd apps/desktop && npm install --silent --save axios@1.7.2
npm install --silent --save-dev vitest@1.6.0 jsdom@24.0.0 @testing-library/react@15.0.7 @testing-library/jest-dom@6.4.2 @testing-library/user-event@14.5.2 msw@2.3.0
```

- [ ] **Step 2:** Write `apps/desktop/vitest.config.ts`

```ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': resolve(__dirname, 'src/renderer'), '@shared': resolve(__dirname, 'src/shared') } },
  test: {
    environment: 'jsdom',
    setupFiles: ['tests/setup.ts'],
    globals: true,
  },
});
```

- [ ] **Step 3:** Write `apps/desktop/tests/setup.ts`

```ts
import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
});

// Stub window.api for tests that don't use msw.
const noop = async (): Promise<unknown> => undefined;
(globalThis as unknown as { window: typeof window }).window = (globalThis as unknown as { window: typeof window }).window ?? ({} as typeof window);
(window as unknown as { api: { invoke: typeof noop } }).api = { invoke: noop };
```

- [ ] **Step 4:** Write the failing test — `apps/desktop/tests/unit/api.test.ts`

```ts
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { createApi } from '@/lib/api';

const tokens: { access: string; refresh: string } = { access: 'old-access', refresh: 'good-refresh' };

const baseURL = 'http://test.local';
let saved: typeof tokens | null = null;
let cleared = false;

const server = setupServer(
  http.get(`${baseURL}/api/v1/me`, ({ request }) => {
    const auth = request.headers.get('authorization');
    if (auth === 'Bearer good-access' || auth === 'Bearer fresh-access') {
      return HttpResponse.json({ id: '1', email: 'a@b', role: 'user', quota_instances: 3, created_at: '2026-01-01' });
    }
    return new HttpResponse(JSON.stringify({ error: { code: 'unauthorized', message: 'bad token' } }), {
      status: 401,
      headers: { 'content-type': 'application/json' },
    });
  }),
  http.post(`${baseURL}/api/v1/auth/refresh`, async ({ request }) => {
    const body = (await request.json()) as { refresh: string };
    if (body.refresh === 'good-refresh') {
      return HttpResponse.json({ access: 'fresh-access', refresh: 'fresh-refresh', token_type: 'bearer' });
    }
    return new HttpResponse(null, { status: 401 });
  })
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => { saved = null; cleared = false; server.resetHandlers(); });
afterAll(() => server.close());

const api = createApi({
  baseURL,
  getTokens: () => tokens,
  setTokens: (t) => { saved = t; Object.assign(tokens, t); },
  clearTokens: () => { cleared = true; },
});

describe('createApi', () => {
  it('attaches Authorization on every request', async () => {
    Object.assign(tokens, { access: 'good-access', refresh: 'good-refresh' });
    const r = await api.get('/api/v1/me');
    expect(r.status).toBe(200);
  });

  it('refreshes once on 401 and retries successfully', async () => {
    Object.assign(tokens, { access: 'old-access', refresh: 'good-refresh' });
    const r = await api.get('/api/v1/me');
    expect(r.status).toBe(200);
    expect(saved?.access).toBe('fresh-access');
  });

  it('clears tokens on second 401', async () => {
    Object.assign(tokens, { access: 'old-access', refresh: 'bad-refresh' });
    await expect(api.get('/api/v1/me')).rejects.toMatchObject({ response: { status: 401 } });
    expect(cleared).toBe(true);
  });
});
```

- [ ] **Step 5:** Run — confirm FAIL

```bash
cd apps/desktop && npm run test
```
Expected: `tests/unit/api.test.ts > createApi > attaches Authorization on every request` fails with import error (`@/lib/api` not found).

- [ ] **Step 6:** Implement `apps/desktop/src/renderer/lib/api.ts`

```ts
import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';
import type { TokenPair } from '@/../shared/ipc-types';

export interface ApiOptions {
  baseURL: string;
  getTokens: () => TokenPair | null;
  setTokens: (tokens: TokenPair) => void;
  clearTokens: () => void;
}

interface RetryFlag extends InternalAxiosRequestConfig {
  __retried?: boolean;
}

export const createApi = ({ baseURL, getTokens, setTokens, clearTokens }: ApiOptions): AxiosInstance => {
  const instance = axios.create({ baseURL, headers: { 'content-type': 'application/json' } });

  instance.interceptors.request.use((config) => {
    const tokens = getTokens();
    if (tokens) {
      config.headers.set('Authorization', `Bearer ${tokens.access}`);
    }
    return config;
  });

  instance.interceptors.response.use(
    (r) => r,
    async (error: { config?: RetryFlag; response?: { status?: number } }) => {
      const original = error.config;
      if (!original || original.__retried) throw error;
      if (error.response?.status !== 401) throw error;

      original.__retried = true;
      const tokens = getTokens();
      if (!tokens) {
        clearTokens();
        throw error;
      }
      try {
        const refreshed = await axios.post<{ access: string; refresh: string }>(
          `${baseURL}/api/v1/auth/refresh`,
          { refresh: tokens.refresh }
        );
        const newTokens: TokenPair = { access: refreshed.data.access, refresh: refreshed.data.refresh };
        setTokens(newTokens);
        original.headers.set('Authorization', `Bearer ${newTokens.access}`);
        return instance.request(original);
      } catch (refreshErr) {
        clearTokens();
        throw error;
      }
    }
  );

  return instance;
};
```

- [ ] **Step 7:** Run — confirm PASS

```bash
cd apps/desktop && npm run test
```
Expected: `3 passed`.

- [ ] **Step 8:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): axios client with 401-refresh interceptor (msw tested)"
```

---

## Task 7: State-machine predicates + format helpers (TDD)

**Files:**
- Create: `apps/desktop/src/renderer/lib/state-machine.ts`
- Create: `apps/desktop/src/renderer/lib/format.ts`
- Create: `apps/desktop/tests/unit/state-machine.test.ts`
- Create: `apps/desktop/tests/unit/format.test.ts`

- [ ] **Step 1:** Write failing tests — `apps/desktop/tests/unit/state-machine.test.ts`

```ts
import { describe, expect, it } from 'vitest';
import { canDelete, canStart, canStop, type DeviceState } from '@/lib/state-machine';

describe('state machine guards', () => {
  it.each<[DeviceState, boolean]>([
    ['stopped', true], ['error', true],
    ['running', false], ['creating', false], ['stopping', false], ['deleted', false],
  ])('canStart(%s) === %s', (state, expected) => { expect(canStart(state)).toBe(expected); });

  it.each<[DeviceState, boolean]>([
    ['running', true], ['creating', true],
    ['stopped', false], ['error', false], ['stopping', false], ['deleted', false],
  ])('canStop(%s) === %s', (state, expected) => { expect(canStop(state)).toBe(expected); });

  it.each<[DeviceState, boolean]>([
    ['running', true], ['creating', true], ['stopped', true], ['error', true], ['stopping', true],
    ['deleted', false],
  ])('canDelete(%s) === %s', (state, expected) => { expect(canDelete(state)).toBe(expected); });
});
```

- [ ] **Step 2:** Write failing tests — `apps/desktop/tests/unit/format.test.ts`

```ts
import { describe, expect, it } from 'vitest';
import { humanizeState, formatRelativeTime } from '@/lib/format';

describe('humanizeState', () => {
  it.each([
    ['creating', 'Creating'],
    ['running', 'Running'],
    ['stopping', 'Stopping'],
    ['stopped', 'Stopped'],
    ['error', 'Error'],
    ['deleted', 'Deleted'],
  ])('"%s" -> "%s"', (input, expected) => {
    expect(humanizeState(input)).toBe(expected);
  });
});

describe('formatRelativeTime', () => {
  it('returns "just now" for recent times', () => {
    const ts = new Date(Date.now() - 5_000).toISOString();
    expect(formatRelativeTime(ts)).toBe('just now');
  });
  it('returns "5m ago" for ~5-minute-old times', () => {
    const ts = new Date(Date.now() - 5 * 60_000).toISOString();
    expect(formatRelativeTime(ts)).toBe('5m ago');
  });
  it('returns "2h ago" for ~2-hour-old times', () => {
    const ts = new Date(Date.now() - 2 * 3600_000).toISOString();
    expect(formatRelativeTime(ts)).toBe('2h ago');
  });
});
```

- [ ] **Step 3:** Run — confirm FAIL

```bash
cd apps/desktop && npm run test
```
Expected: 5 failing tests (4 in state-machine, 7 in format — all "module not found" / "imported binding not exported").

- [ ] **Step 4:** Implement `apps/desktop/src/renderer/lib/state-machine.ts`

```ts
export type DeviceState = 'creating' | 'running' | 'stopping' | 'stopped' | 'error' | 'deleted';

export const canStart = (state: DeviceState): boolean =>
  state === 'stopped' || state === 'error';

export const canStop = (state: DeviceState): boolean =>
  state === 'running' || state === 'creating';

export const canDelete = (state: DeviceState): boolean =>
  state !== 'deleted';
```

- [ ] **Step 5:** Implement `apps/desktop/src/renderer/lib/format.ts`

```ts
export const humanizeState = (state: string): string =>
  state.length === 0 ? state : state[0]!.toUpperCase() + state.slice(1);

export const formatRelativeTime = (iso: string): string => {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffSec = Math.floor((now - then) / 1000);
  if (diffSec < 15) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
};
```

- [ ] **Step 6:** Run — confirm PASS

```bash
cd apps/desktop && npm run test
```
Expected: all tests pass (3 from Task 6 + state-machine + format).

- [ ] **Step 7:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): state-machine predicates + format helpers"
```

---

## Task 8: TanStack Query setup + query/mutation hooks

**Files:**
- Create: `apps/desktop/src/renderer/lib/queries.ts`
- Create: `apps/desktop/src/renderer/lib/api-client.ts`
- Modify: `apps/desktop/src/renderer/main.tsx` (QueryClientProvider)

- [ ] **Step 1:** Install TanStack Query

```bash
cd apps/desktop && npm install --silent --save @tanstack/react-query@5.40.0
```

- [ ] **Step 2:** Write `apps/desktop/src/renderer/lib/api-client.ts` — the singleton API instance the app uses

```ts
import { createApi } from './api';
import { useAuthStore, saveAuth, clearAuth } from '@/stores/auth';
import { useSettingsStore } from '@/stores/settings';
import type { AxiosInstance } from 'axios';

let instance: AxiosInstance | null = null;

export const getApi = (): AxiosInstance => {
  if (instance) return instance;
  instance = createApi({
    baseURL: useSettingsStore.getState().prefs.backendUrl,
    getTokens: () => useAuthStore.getState().tokens,
    setTokens: (t) => { void saveAuth(t); },
    clearTokens: () => { void clearAuth(); },
  });
  // Reconfigure baseURL whenever settings change.
  useSettingsStore.subscribe((state) => {
    if (instance) instance.defaults.baseURL = state.prefs.backendUrl;
  });
  return instance;
};
```

- [ ] **Step 3:** Write `apps/desktop/src/renderer/lib/queries.ts`

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getApi } from './api-client';
import type { DeviceState } from './state-machine';

export interface DeviceProfile {
  id: string;
  name: string;
  android_version: string;
  screen_width: number;
  screen_height: number;
  screen_dpi: number;
  ram_mb: number;
  cpu_cores: number;
  manufacturer: string;
  model: string;
  is_public: boolean;
}

export interface Proxy {
  id: string;
  label: string;
  type: 'socks5' | 'http';
  host: string;
  port: number;
  username: string | null;
  has_password: boolean;
  created_at: string;
}

export interface Device {
  id: string;
  name: string;
  profile_id: string;
  proxy_id: string | null;
  state: DeviceState;
  state_reason: string | null;
  adb_host_port: number | null;
  created_at: string;
  started_at: string | null;
  stopped_at: string | null;
}

export interface UserPublic {
  id: string;
  email: string;
  role: 'admin' | 'user';
  quota_instances: number;
  created_at: string;
}

export interface AdbInfo { host: string; port: number; command: string }

export const useMeQuery = () =>
  useQuery({
    queryKey: ['me'],
    queryFn: async () => (await getApi().get<UserPublic>('/api/v1/me')).data,
  });

export const useDevicesQuery = () =>
  useQuery({
    queryKey: ['devices'],
    queryFn: async () => (await getApi().get<Device[]>('/api/v1/devices')).data,
    refetchOnWindowFocus: true,
  });

export const useDeviceQuery = (id: string | undefined) =>
  useQuery({
    queryKey: ['device', id],
    queryFn: async () => (await getApi().get<Device>(`/api/v1/devices/${id}`)).data,
    enabled: !!id,
  });

export const useProfilesQuery = () =>
  useQuery({
    queryKey: ['profiles'],
    queryFn: async () => (await getApi().get<DeviceProfile[]>('/api/v1/device-profiles')).data,
  });

export const useProxiesQuery = () =>
  useQuery({
    queryKey: ['proxies'],
    queryFn: async () => (await getApi().get<Proxy[]>('/api/v1/proxies')).data,
  });

export const useAdbInfoQuery = (id: string | undefined) =>
  useQuery({
    queryKey: ['adb-info', id],
    queryFn: async () => (await getApi().get<AdbInfo>(`/api/v1/devices/${id}/adb-info`)).data,
    enabled: !!id,
  });

interface CreateProxyBody {
  label: string; type: 'socks5' | 'http'; host: string; port: number;
  username?: string | null; password?: string | null;
}

export const useCreateProxy = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: CreateProxyBody) => (await getApi().post<Proxy>('/api/v1/proxies', body)).data,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['proxies'] }); },
  });
};

export const useDeleteProxy = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => { await getApi().delete(`/api/v1/proxies/${id}`); },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['proxies'] }); },
  });
};

interface CreateDeviceBody { name: string; profile_id: string; proxy_id: string }

export const useCreateDevice = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: CreateDeviceBody) => (await getApi().post<Device>('/api/v1/devices', body)).data,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['devices'] }); },
  });
};

const deviceAction = (verb: 'start' | 'stop') => () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => (await getApi().post<Device>(`/api/v1/devices/${id}/${verb}`)).data,
    onSuccess: (_data, id) => {
      void qc.invalidateQueries({ queryKey: ['devices'] });
      void qc.invalidateQueries({ queryKey: ['device', id] });
    },
  });
};

export const useStartDevice = deviceAction('start');
export const useStopDevice = deviceAction('stop');

export const useDeleteDevice = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => { await getApi().delete(`/api/v1/devices/${id}`); },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['devices'] }); },
  });
};

interface AuthResponse { access: string; refresh: string; token_type: string }

export const useLoginMutation = () =>
  useMutation({
    mutationFn: async (body: { email: string; password: string }) =>
      (await getApi().post<AuthResponse>('/api/v1/auth/login', body)).data,
  });

export const useRedeemInviteMutation = () =>
  useMutation({
    mutationFn: async (body: { token: string; email: string; password: string }) =>
      (await getApi().post<AuthResponse>('/api/v1/auth/redeem-invite', body)).data,
  });
```

- [ ] **Step 4:** Wrap app in `QueryClientProvider`. Update `apps/desktop/src/renderer/main.tsx`:

```tsx
import './styles/index.css';
import { App } from './App';
import { createRoot } from 'react-dom/client';
import { bootstrapAuth } from './stores/auth';
import { bootstrapSettings } from './stores/settings';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 0, refetchOnWindowFocus: false } },
});

const el = document.getElementById('root');
if (!el) throw new Error('root element missing');

Promise.all([bootstrapSettings(), bootstrapAuth()]).finally(() => {
  createRoot(el).render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  );
});
```

- [ ] **Step 5:** Typecheck

```bash
cd apps/desktop && npx tsc --noEmit -p tsconfig.web.json
```
Expected: no errors.

- [ ] **Step 6:** Smoke — `npm run dev` opens, no console errors.

- [ ] **Step 7:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): tanstack query setup + queries/mutations for all resources"
```

---

## Task 9: Router + AppShell + ProtectedRoute

**Files:**
- Create: `apps/desktop/src/renderer/components/layout/AppShell.tsx`
- Create: `apps/desktop/src/renderer/components/layout/Sidebar.tsx`
- Create: `apps/desktop/src/renderer/components/layout/ProtectedRoute.tsx`
- Create: `apps/desktop/src/renderer/routes/Login.tsx`, `Redeem.tsx`, `DevicesIndex.tsx`, `DeviceDetail.tsx`, `DeviceNew.tsx`, `ProxiesIndex.tsx`, `ProxyNew.tsx`, `Settings.tsx` (skeletons)
- Modify: `apps/desktop/src/renderer/App.tsx`

- [ ] **Step 1:** Install router

```bash
cd apps/desktop && npm install --silent --save react-router-dom@6.23.1
```

- [ ] **Step 2:** Write `apps/desktop/src/renderer/components/layout/ProtectedRoute.tsx`

```tsx
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import type { ReactNode } from 'react';

export const ProtectedRoute = ({ children }: { children: ReactNode }): JSX.Element => {
  const status = useAuthStore((s) => s.status);
  if (status === 'loading') return <div className="p-6">Loading…</div>;
  if (status === 'anonymous') return <Navigate to="/login" replace />;
  return <>{children}</>;
};
```

- [ ] **Step 3:** Write `apps/desktop/src/renderer/components/layout/Sidebar.tsx`

```tsx
import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { Settings as SettingsIcon, Smartphone, Server } from 'lucide-react';

const items = [
  { to: '/devices', icon: Smartphone, label: 'Devices' },
  { to: '/proxies', icon: Server, label: 'Proxies' },
  { to: '/settings', icon: SettingsIcon, label: 'Settings' },
];

export const Sidebar = (): JSX.Element => (
  <nav className="w-56 border-r bg-card p-3 flex flex-col gap-1">
    <div className="px-3 py-2 text-lg font-semibold">Cloude Phone</div>
    {items.map(({ to, icon: Icon, label }) => (
      <NavLink
        key={to}
        to={to}
        className={({ isActive }) =>
          cn(
            'flex items-center gap-2 rounded-md px-3 py-2 text-sm',
            isActive ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50'
          )
        }
      >
        <Icon className="h-4 w-4" />
        {label}
      </NavLink>
    ))}
  </nav>
);
```

- [ ] **Step 4:** Write `apps/desktop/src/renderer/components/layout/AppShell.tsx`

```tsx
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { useSettingsStore } from '@/stores/settings';

export const AppShell = (): JSX.Element => {
  const backend = useSettingsStore((s) => s.prefs.backendUrl);
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <header className="flex items-center justify-between border-b px-4 py-2 text-sm">
          <span className="text-muted-foreground">Backend:</span>
          <span className="font-mono">{backend}</span>
        </header>
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
```

- [ ] **Step 5:** Write skeleton routes. For each of the 8 files below, write the indicated content:

`apps/desktop/src/renderer/routes/Login.tsx`:
```tsx
export const Login = (): JSX.Element => <div>Login screen (Task 10)</div>;
```

`apps/desktop/src/renderer/routes/Redeem.tsx`:
```tsx
export const Redeem = (): JSX.Element => <div>Redeem screen (Task 11)</div>;
```

`apps/desktop/src/renderer/routes/DevicesIndex.tsx`:
```tsx
export const DevicesIndex = (): JSX.Element => <div>Devices index (Task 12)</div>;
```

`apps/desktop/src/renderer/routes/DeviceDetail.tsx`:
```tsx
export const DeviceDetail = (): JSX.Element => <div>Device detail (Task 13)</div>;
```

`apps/desktop/src/renderer/routes/DeviceNew.tsx`:
```tsx
export const DeviceNew = (): JSX.Element => <div>Create device wizard (Task 14)</div>;
```

`apps/desktop/src/renderer/routes/ProxiesIndex.tsx`:
```tsx
export const ProxiesIndex = (): JSX.Element => <div>Proxies index (Task 15)</div>;
```

`apps/desktop/src/renderer/routes/ProxyNew.tsx`:
```tsx
export const ProxyNew = (): JSX.Element => <div>New proxy (Task 16)</div>;
```

`apps/desktop/src/renderer/routes/Settings.tsx`:
```tsx
export const Settings = (): JSX.Element => <div>Settings (Task 17)</div>;
```

- [ ] **Step 6:** Replace `apps/desktop/src/renderer/App.tsx` with the router

```tsx
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { ProtectedRoute } from '@/components/layout/ProtectedRoute';
import { Login } from '@/routes/Login';
import { Redeem } from '@/routes/Redeem';
import { DevicesIndex } from '@/routes/DevicesIndex';
import { DeviceDetail } from '@/routes/DeviceDetail';
import { DeviceNew } from '@/routes/DeviceNew';
import { ProxiesIndex } from '@/routes/ProxiesIndex';
import { ProxyNew } from '@/routes/ProxyNew';
import { Settings } from '@/routes/Settings';

export const App = (): JSX.Element => (
  <HashRouter>
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/redeem" element={<Redeem />} />
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/devices" replace />} />
        <Route path="/devices" element={<DevicesIndex />} />
        <Route path="/devices/new" element={<DeviceNew />} />
        <Route path="/devices/:id" element={<DeviceDetail />} />
        <Route path="/proxies" element={<ProxiesIndex />} />
        <Route path="/proxies/new" element={<ProxyNew />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  </HashRouter>
);
```

- [ ] **Step 7:** Smoke

```bash
cd apps/desktop && npm run dev
```
Expected: window opens. Status is `anonymous` (Task 5 bootstrap), so ProtectedRoute redirects to `/login`. You see "Login screen (Task 10)". Manually edit the URL via DevTools `location.hash = '#/devices'` — should redirect back to `/login` because status is anonymous. Good.

- [ ] **Step 8:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): router + AppShell + ProtectedRoute + route skeletons"
```

---

## Task 10: Login screen + component test

**Files:**
- Create: `apps/desktop/src/renderer/components/ui/input.tsx`
- Create: `apps/desktop/src/renderer/components/ui/label.tsx`
- Create: `apps/desktop/src/renderer/components/ui/form.tsx` (minimal, no shadcn CLI)
- Modify: `apps/desktop/src/renderer/routes/Login.tsx`
- Create: `apps/desktop/tests/component/LoginForm.test.tsx`

- [ ] **Step 1:** Install form deps

```bash
cd apps/desktop && npm install --silent --save react-hook-form@7.51.5 @hookform/resolvers@3.4.2 zod@3.23.8
```

- [ ] **Step 2:** Write `apps/desktop/src/renderer/components/ui/input.tsx`

```tsx
import * as React from 'react';
import { cn } from '@/lib/utils';

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background',
        'placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      {...props}
    />
  )
);
Input.displayName = 'Input';
```

- [ ] **Step 3:** Write `apps/desktop/src/renderer/components/ui/label.tsx`

```tsx
import * as React from 'react';
import { cn } from '@/lib/utils';

export const Label = React.forwardRef<HTMLLabelElement, React.LabelHTMLAttributes<HTMLLabelElement>>(
  ({ className, ...props }, ref) => (
    <label
      ref={ref}
      className={cn('text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70', className)}
      {...props}
    />
  )
);
Label.displayName = 'Label';
```

- [ ] **Step 4:** Replace `apps/desktop/src/renderer/routes/Login.tsx`

```tsx
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useLoginMutation } from '@/lib/queries';
import { saveAuth } from '@/stores/auth';
import { Link, useNavigate } from 'react-router-dom';

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

type FormValues = z.infer<typeof schema>;

export const Login = (): JSX.Element => {
  const navigate = useNavigate();
  const mutation = useLoginMutation();
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { email: '', password: '' } });

  const onSubmit = form.handleSubmit(async (values) => {
    const tokens = await mutation.mutateAsync(values);
    await saveAuth({ access: tokens.access, refresh: tokens.refresh });
    navigate('/devices', { replace: true });
  });

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 rounded-lg border p-6 bg-card">
        <h1 className="text-2xl font-semibold">Sign in</h1>
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="username" {...form.register('email')} />
          {form.formState.errors.email && (
            <p className="text-sm text-destructive">{form.formState.errors.email.message}</p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="current-password" {...form.register('password')} />
          {form.formState.errors.password && (
            <p className="text-sm text-destructive">{form.formState.errors.password.message}</p>
          )}
        </div>
        {mutation.isError && (
          <p className="text-sm text-destructive" role="alert">
            {(mutation.error as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error?.message ?? 'Login failed'}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={mutation.isPending}>
          {mutation.isPending ? 'Signing in…' : 'Sign in'}
        </Button>
        <p className="text-sm text-center text-muted-foreground">
          Have an invite token? <Link to="/redeem" className="underline">Redeem →</Link>
        </p>
      </form>
    </div>
  );
};
```

- [ ] **Step 5:** Write `apps/desktop/tests/component/LoginForm.test.tsx`

```tsx
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Login } from '@/routes/Login';

vi.mock('@/lib/api-client', () => {
  return {
    getApi: () => ({
      post: vi.fn().mockResolvedValue({ data: { access: 'a', refresh: 'r', token_type: 'bearer' } }),
    }),
  };
});

vi.mock('@/stores/auth', () => ({
  saveAuth: vi.fn().mockResolvedValue(undefined),
  useAuthStore: { getState: () => ({ tokens: null }) },
}));

const renderLogin = (): void => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: 0 } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    </QueryClientProvider>
  );
};

beforeEach(() => { vi.clearAllMocks(); });

describe('Login form', () => {
  it('rejects empty email', async () => {
    renderLogin();
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));
    expect(await screen.findByText(/Invalid email/i)).toBeInTheDocument();
  });

  it('submits with valid input', async () => {
    renderLogin();
    await userEvent.type(screen.getByLabelText(/email/i), 'a@b.com');
    await userEvent.type(screen.getByLabelText(/password/i), 'pw');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));
    // No error after submit
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
```

- [ ] **Step 6:** Run

```bash
cd apps/desktop && npm run test
```
Expected: all tests pass (api + state-machine + format + LoginForm).

- [ ] **Step 7:** Smoke — `npm run dev`. App opens to `/login`. Type valid email + password, submit → if backend is up, you'll be redirected to `/devices`. (If no backend yet, just verify form validation shows the email-required error on empty submit.)

- [ ] **Step 8:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): Login screen + zod validation + component test"
```

---

## Task 11: Redeem invite screen

**Files:**
- Modify: `apps/desktop/src/renderer/routes/Redeem.tsx`

- [ ] **Step 1:** Replace the file

```tsx
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useRedeemInviteMutation } from '@/lib/queries';
import { saveAuth } from '@/stores/auth';
import { Link, useNavigate } from 'react-router-dom';

const schema = z.object({
  token: z.string().min(10).max(128),
  email: z.string().email(),
  password: z.string().min(8).max(128),
});

type FormValues = z.infer<typeof schema>;

export const Redeem = (): JSX.Element => {
  const navigate = useNavigate();
  const mutation = useRedeemInviteMutation();
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { token: '', email: '', password: '' } });

  const onSubmit = form.handleSubmit(async (values) => {
    const tokens = await mutation.mutateAsync(values);
    await saveAuth({ access: tokens.access, refresh: tokens.refresh });
    navigate('/devices', { replace: true });
  });

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 rounded-lg border p-6 bg-card">
        <h1 className="text-2xl font-semibold">Redeem invite</h1>
        <div className="space-y-2">
          <Label htmlFor="token">Invite token</Label>
          <Input id="token" {...form.register('token')} />
          {form.formState.errors.token && (
            <p className="text-sm text-destructive">{form.formState.errors.token.message}</p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" {...form.register('email')} />
          {form.formState.errors.email && (
            <p className="text-sm text-destructive">{form.formState.errors.email.message}</p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">Choose a password</Label>
          <Input id="password" type="password" {...form.register('password')} />
          {form.formState.errors.password && (
            <p className="text-sm text-destructive">{form.formState.errors.password.message}</p>
          )}
        </div>
        {mutation.isError && (
          <p className="text-sm text-destructive" role="alert">
            {(mutation.error as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error?.message ?? 'Redeem failed'}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={mutation.isPending}>
          {mutation.isPending ? 'Redeeming…' : 'Redeem'}
        </Button>
        <p className="text-sm text-center text-muted-foreground">
          Already have an account? <Link to="/login" className="underline">Sign in →</Link>
        </p>
      </form>
    </div>
  );
};
```

- [ ] **Step 2:** Smoke — visit `/redeem` (from `/login` page click "Redeem →"). Submit with empty fields → validation errors. With valid + working invite from `make_invite.py` → land on `/devices`.

- [ ] **Step 3:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): Redeem invite screen"
```

---

## Task 12: Devices index — grid + DeviceCard + StateBadge

**Files:**
- Create: `apps/desktop/src/renderer/components/devices/StateBadge.tsx`
- Create: `apps/desktop/src/renderer/components/devices/DeviceCard.tsx`
- Create: `apps/desktop/src/renderer/components/ui/card.tsx`
- Modify: `apps/desktop/src/renderer/routes/DevicesIndex.tsx`

- [ ] **Step 1:** Write `apps/desktop/src/renderer/components/ui/card.tsx`

```tsx
import * as React from 'react';
import { cn } from '@/lib/utils';

export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('rounded-lg border bg-card text-card-foreground shadow-sm', className)} {...props} />
  )
);
Card.displayName = 'Card';

export const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex flex-col space-y-1.5 p-6', className)} {...props} />
  )
);
CardHeader.displayName = 'CardHeader';

export const CardTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn('text-lg font-semibold leading-none tracking-tight', className)} {...props} />
  )
);
CardTitle.displayName = 'CardTitle';

export const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn('text-sm text-muted-foreground', className)} {...props} />
  )
);
CardDescription.displayName = 'CardDescription';

export const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('p-6 pt-0', className)} {...props} />
  )
);
CardContent.displayName = 'CardContent';

export const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex items-center p-6 pt-0', className)} {...props} />
  )
);
CardFooter.displayName = 'CardFooter';
```

- [ ] **Step 2:** Write `apps/desktop/src/renderer/components/devices/StateBadge.tsx`

```tsx
import { cn } from '@/lib/utils';
import { humanizeState } from '@/lib/format';
import type { DeviceState } from '@/lib/state-machine';

const styles: Record<DeviceState, string> = {
  creating:  'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  running:   'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
  stopping:  'bg-amber-500/15 text-amber-700 dark:text-amber-300',
  stopped:   'bg-slate-500/15 text-slate-700 dark:text-slate-300',
  error:     'bg-red-500/15 text-red-700 dark:text-red-300',
  deleted:   'bg-zinc-700/15 text-zinc-700 dark:text-zinc-400',
};

export const StateBadge = ({ state }: { state: DeviceState }): JSX.Element => (
  <span className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium', styles[state])}>
    {humanizeState(state)}
  </span>
);
```

- [ ] **Step 3:** Write `apps/desktop/src/renderer/components/devices/DeviceCard.tsx`

```tsx
import { Link } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StateBadge } from './StateBadge';
import { formatRelativeTime } from '@/lib/format';
import type { Device, DeviceProfile } from '@/lib/queries';

interface Props {
  device: Device;
  profile: DeviceProfile | undefined;
}

export const DeviceCard = ({ device, profile }: Props): JSX.Element => (
  <Link to={`/devices/${device.id}`} className="block">
    <Card className="hover:bg-accent/30 transition-colors">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle>{device.name}</CardTitle>
            <CardDescription>
              {profile ? `${profile.manufacturer} ${profile.model} · ${profile.screen_width}×${profile.screen_height}` : '…'}
            </CardDescription>
          </div>
          <StateBadge state={device.state} />
        </div>
      </CardHeader>
      <CardContent className="text-xs text-muted-foreground">
        {device.started_at && device.state === 'running'
          ? `Running since ${formatRelativeTime(device.started_at)}`
          : device.stopped_at
          ? `Stopped ${formatRelativeTime(device.stopped_at)}`
          : `Created ${formatRelativeTime(device.created_at)}`}
      </CardContent>
    </Card>
  </Link>
);
```

- [ ] **Step 4:** Replace `apps/desktop/src/renderer/routes/DevicesIndex.tsx`

```tsx
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { DeviceCard } from '@/components/devices/DeviceCard';
import { useDevicesQuery, useProfilesQuery } from '@/lib/queries';
import { Plus } from 'lucide-react';

export const DevicesIndex = (): JSX.Element => {
  const devicesQ = useDevicesQuery();
  const profilesQ = useProfilesQuery();
  const profilesById = new Map(profilesQ.data?.map((p) => [p.id, p]));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Devices</h1>
        <Button asChild>
          <Link to="/devices/new"><Plus className="mr-2 h-4 w-4" />Create device</Link>
        </Button>
      </div>
      {devicesQ.isLoading && <p className="text-muted-foreground">Loading…</p>}
      {devicesQ.isError && (
        <p className="text-destructive">
          Failed to load devices: {(devicesQ.error as Error).message}
        </p>
      )}
      {devicesQ.data && devicesQ.data.length === 0 && (
        <p className="text-muted-foreground">No devices yet. Click "Create device" to spawn one.</p>
      )}
      {devicesQ.data && devicesQ.data.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {devicesQ.data.map((d) => (
            <DeviceCard key={d.id} device={d} profile={profilesById.get(d.profile_id)} />
          ))}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 5:** Smoke — log in / redeem so you reach `/devices`. Either you'll see "No devices yet" or any existing devices in the DB. Status badges should render.

- [ ] **Step 6:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): Devices index — grid + DeviceCard + StateBadge"
```

---

## Task 13: Device detail — state, profile, proxy, ADB info, actions

**Files:**
- Create: `apps/desktop/src/renderer/components/devices/DeviceActions.tsx`
- Create: `apps/desktop/src/renderer/components/devices/AdbInfoCard.tsx`
- Create: `apps/desktop/src/renderer/components/devices/StreamPlaceholder.tsx`
- Create: `apps/desktop/src/renderer/components/ui/alert-dialog.tsx` (minimal)
- Modify: `apps/desktop/src/renderer/routes/DeviceDetail.tsx`
- Create: `apps/desktop/tests/component/DeviceActions.test.tsx`

- [ ] **Step 1:** Install Radix alert-dialog

```bash
cd apps/desktop && npm install --silent --save @radix-ui/react-alert-dialog@1.0.5
```

- [ ] **Step 2:** Write `apps/desktop/src/renderer/components/ui/alert-dialog.tsx`

```tsx
import * as React from 'react';
import * as AlertDialogPrimitive from '@radix-ui/react-alert-dialog';
import { cn } from '@/lib/utils';
import { buttonVariants } from '@/components/ui/button-variants';

export const AlertDialog = AlertDialogPrimitive.Root;
export const AlertDialogTrigger = AlertDialogPrimitive.Trigger;
export const AlertDialogPortal = AlertDialogPrimitive.Portal;

export const AlertDialogOverlay = React.forwardRef<
  React.ElementRef<typeof AlertDialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Overlay
    ref={ref}
    className={cn('fixed inset-0 z-50 bg-black/50', className)}
    {...props}
  />
));
AlertDialogOverlay.displayName = AlertDialogPrimitive.Overlay.displayName;

export const AlertDialogContent = React.forwardRef<
  React.ElementRef<typeof AlertDialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Content>
>(({ className, ...props }, ref) => (
  <AlertDialogPortal>
    <AlertDialogOverlay />
    <AlertDialogPrimitive.Content
      ref={ref}
      className={cn(
        'fixed left-1/2 top-1/2 z-50 grid w-full max-w-lg -translate-x-1/2 -translate-y-1/2 gap-4 border bg-background p-6 shadow-lg rounded-lg',
        className
      )}
      {...props}
    />
  </AlertDialogPortal>
));
AlertDialogContent.displayName = AlertDialogPrimitive.Content.displayName;

export const AlertDialogTitle = AlertDialogPrimitive.Title;
export const AlertDialogDescription = AlertDialogPrimitive.Description;

export const AlertDialogAction = React.forwardRef<
  React.ElementRef<typeof AlertDialogPrimitive.Action>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Action>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Action ref={ref} className={cn(buttonVariants(), className)} {...props} />
));
AlertDialogAction.displayName = AlertDialogPrimitive.Action.displayName;

export const AlertDialogCancel = React.forwardRef<
  React.ElementRef<typeof AlertDialogPrimitive.Cancel>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Cancel>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Cancel ref={ref} className={cn(buttonVariants({ variant: 'outline' }), 'mt-2 sm:mt-0', className)} {...props} />
));
AlertDialogCancel.displayName = AlertDialogPrimitive.Cancel.displayName;
```

- [ ] **Step 3:** Extract button variants so AlertDialog can reuse — create `apps/desktop/src/renderer/components/ui/button-variants.ts`

```ts
import { cva } from 'class-variance-authority';

export const buttonVariants = cva(
  'inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 rounded-md px-3',
        lg: 'h-11 rounded-md px-8',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  }
);
```

Then REPLACE the entire contents of `apps/desktop/src/renderer/components/ui/button.tsx` (the version from Task 1) with this version that imports from the new variants file:
```tsx
import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';
import { buttonVariants } from './button-variants';

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  }
);
Button.displayName = 'Button';
```

- [ ] **Step 4:** Write `apps/desktop/src/renderer/components/devices/DeviceActions.tsx`

```tsx
import { Button } from '@/components/ui/button';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogTitle, AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { canStart, canStop, canDelete } from '@/lib/state-machine';
import type { Device } from '@/lib/queries';
import { useDeleteDevice, useStartDevice, useStopDevice } from '@/lib/queries';
import { useNavigate } from 'react-router-dom';
import { Play, Square, Trash2 } from 'lucide-react';

export const DeviceActions = ({ device }: { device: Device }): JSX.Element => {
  const navigate = useNavigate();
  const start = useStartDevice();
  const stop = useStopDevice();
  const del = useDeleteDevice();

  return (
    <div className="flex gap-2">
      <Button onClick={() => start.mutate(device.id)} disabled={!canStart(device.state) || start.isPending}>
        <Play className="mr-2 h-4 w-4" />Start
      </Button>
      <Button variant="outline" onClick={() => stop.mutate(device.id)} disabled={!canStop(device.state) || stop.isPending}>
        <Square className="mr-2 h-4 w-4" />Stop
      </Button>
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="destructive" disabled={!canDelete(device.state)}>
            <Trash2 className="mr-2 h-4 w-4" />Delete
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogTitle>Delete this device?</AlertDialogTitle>
          <AlertDialogDescription>
            This stops the Android container, removes the per-device volume, and deletes the record. Apps and data inside the device are gone permanently.
          </AlertDialogDescription>
          <div className="flex justify-end gap-2">
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                del.mutate(device.id, { onSuccess: () => navigate('/devices', { replace: true }) });
              }}
            >
              Delete
            </AlertDialogAction>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
```

- [ ] **Step 5:** Write `apps/desktop/src/renderer/components/devices/AdbInfoCard.tsx`

```tsx
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Copy } from 'lucide-react';
import type { Device } from '@/lib/queries';

export const AdbInfoCard = ({ device }: { device: Device }): JSX.Element | null => {
  if (device.state !== 'running' || device.adb_host_port === null) return null;
  const adbCmd = `adb connect localhost:${device.adb_host_port}`;
  const scrcpyCmd = `scrcpy -s localhost:${device.adb_host_port}`;
  const copy = (s: string): void => { void navigator.clipboard.writeText(s); };

  return (
    <Card>
      <CardHeader>
        <CardTitle>ADB / scrcpy</CardTitle>
        <CardDescription>Use these commands from a terminal on this machine.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="flex items-center gap-2">
          <code className="flex-1 rounded bg-muted px-3 py-2 font-mono text-sm">{adbCmd}</code>
          <Button size="icon" variant="outline" onClick={() => copy(adbCmd)}><Copy className="h-4 w-4" /></Button>
        </div>
        <div className="flex items-center gap-2">
          <code className="flex-1 rounded bg-muted px-3 py-2 font-mono text-sm">{scrcpyCmd}</code>
          <Button size="icon" variant="outline" onClick={() => copy(scrcpyCmd)}><Copy className="h-4 w-4" /></Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Install scrcpy from{' '}
          <button
            className="underline"
            onClick={() => void window.api.invoke('app:openExternal', 'https://github.com/Genymobile/scrcpy/releases')}
          >
            github.com/Genymobile/scrcpy/releases
          </button>
          .
        </p>
      </CardContent>
    </Card>
  );
};
```

- [ ] **Step 6:** Write `apps/desktop/src/renderer/components/devices/StreamPlaceholder.tsx`

```tsx
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export const StreamPlaceholder = (): JSX.Element => (
  <Card>
    <CardHeader>
      <CardTitle>Live screen</CardTitle>
      <CardDescription>Coming in P1d. For now, use scrcpy on your machine via the command above.</CardDescription>
    </CardHeader>
    <CardContent>
      <Button disabled>Open screen</Button>
    </CardContent>
  </Card>
);
```

- [ ] **Step 7:** Replace `apps/desktop/src/renderer/routes/DeviceDetail.tsx`

```tsx
import { Link, useParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StateBadge } from '@/components/devices/StateBadge';
import { DeviceActions } from '@/components/devices/DeviceActions';
import { AdbInfoCard } from '@/components/devices/AdbInfoCard';
import { StreamPlaceholder } from '@/components/devices/StreamPlaceholder';
import { useDeviceQuery, useProfilesQuery, useProxiesQuery } from '@/lib/queries';
import { ArrowLeft } from 'lucide-react';

export const DeviceDetail = (): JSX.Element => {
  const { id } = useParams<{ id: string }>();
  const deviceQ = useDeviceQuery(id);
  const profilesQ = useProfilesQuery();
  const proxiesQ = useProxiesQuery();

  if (deviceQ.isLoading) return <p>Loading…</p>;
  if (deviceQ.isError || !deviceQ.data) {
    return (
      <div className="space-y-4">
        <Button asChild variant="outline"><Link to="/devices"><ArrowLeft className="mr-2 h-4 w-4" />Back</Link></Button>
        <p className="text-destructive">Device not found.</p>
      </div>
    );
  }
  const d = deviceQ.data;
  const profile = profilesQ.data?.find((p) => p.id === d.profile_id);
  const proxy = proxiesQ.data?.find((p) => p.id === d.proxy_id);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button asChild variant="outline" size="sm"><Link to="/devices"><ArrowLeft className="mr-2 h-4 w-4" />Back</Link></Button>
          <h1 className="text-2xl font-semibold">{d.name}</h1>
          <StateBadge state={d.state} />
        </div>
        <DeviceActions device={d} />
      </div>

      {d.state === 'error' && d.state_reason && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm">
          <strong>Error:</strong> {d.state_reason}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
            <CardDescription>{profile ? `${profile.manufacturer} ${profile.model}` : '…'}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {profile && (
              <>
                <div>Resolution: {profile.screen_width}×{profile.screen_height} @ {profile.screen_dpi}dpi</div>
                <div>RAM: {profile.ram_mb} MB · CPUs: {profile.cpu_cores}</div>
                <div>Android: {profile.android_version}</div>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Proxy</CardTitle>
            <CardDescription>{proxy ? proxy.label : '…'}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {proxy && (
              <>
                <div>Type: {proxy.type}</div>
                <div>Endpoint: {proxy.host}:{proxy.port}</div>
                <div>Auth: {proxy.has_password ? 'password configured' : 'no password'}</div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <AdbInfoCard device={d} />
      <StreamPlaceholder />
    </div>
  );
};
```

- [ ] **Step 8:** Write `apps/desktop/tests/component/DeviceActions.test.tsx`

```tsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DeviceActions } from '@/components/devices/DeviceActions';
import type { Device } from '@/lib/queries';

vi.mock('@/lib/api-client', () => ({ getApi: () => ({ post: vi.fn(), delete: vi.fn() }) }));

const makeDevice = (state: Device['state']): Device => ({
  id: 'id1', name: 'd', profile_id: 'p', proxy_id: 'r', state,
  state_reason: null, adb_host_port: 40000, created_at: '2026', started_at: null, stopped_at: null,
});

const renderWith = (device: Device): void => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: 0 } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DeviceActions device={device} />
      </MemoryRouter>
    </QueryClientProvider>
  );
};

describe('DeviceActions enablement', () => {
  it('Start enabled only for stopped/error', () => {
    renderWith(makeDevice('stopped'));
    expect(screen.getByRole('button', { name: /start/i })).not.toBeDisabled();
    cleanup();
    renderWith(makeDevice('running'));
    expect(screen.getByRole('button', { name: /start/i })).toBeDisabled();
  });

  it('Stop enabled only for running/creating', () => {
    renderWith(makeDevice('running'));
    expect(screen.getByRole('button', { name: /stop/i })).not.toBeDisabled();
    cleanup();
    renderWith(makeDevice('stopped'));
    expect(screen.getByRole('button', { name: /stop/i })).toBeDisabled();
  });
});

import { cleanup } from '@testing-library/react';
```

- [ ] **Step 9:** Run

```bash
cd apps/desktop && npm run test
```
Expected: all tests pass.

- [ ] **Step 10:** Smoke — log in, click on a device card → DeviceDetail renders. ADB card only appears when state=running.

- [ ] **Step 11:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): Device detail with state-machine actions + ADB info + stream placeholder"
```

---

## Task 14: Create-device wizard (3 steps in one page)

**Files:**
- Create: `apps/desktop/src/renderer/components/ui/radio-group.tsx`
- Modify: `apps/desktop/src/renderer/routes/DeviceNew.tsx`

- [ ] **Step 1:** Install Radix radio group

```bash
cd apps/desktop && npm install --silent --save @radix-ui/react-radio-group@1.1.3
```

- [ ] **Step 2:** Write `apps/desktop/src/renderer/components/ui/radio-group.tsx`

```tsx
import * as React from 'react';
import * as RadioGroupPrimitive from '@radix-ui/react-radio-group';
import { Circle } from 'lucide-react';
import { cn } from '@/lib/utils';

export const RadioGroup = React.forwardRef<
  React.ElementRef<typeof RadioGroupPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Root>
>(({ className, ...props }, ref) => (
  <RadioGroupPrimitive.Root ref={ref} className={cn('grid gap-2', className)} {...props} />
));
RadioGroup.displayName = 'RadioGroup';

export const RadioGroupItem = React.forwardRef<
  React.ElementRef<typeof RadioGroupPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Item>
>(({ className, ...props }, ref) => (
  <RadioGroupPrimitive.Item
    ref={ref}
    className={cn('aspect-square h-4 w-4 rounded-full border border-primary text-primary shadow focus:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50', className)}
    {...props}
  >
    <RadioGroupPrimitive.Indicator className="flex items-center justify-center">
      <Circle className="h-2 w-2 fill-current text-current" />
    </RadioGroupPrimitive.Indicator>
  </RadioGroupPrimitive.Item>
));
RadioGroupItem.displayName = 'RadioGroupItem';
```

- [ ] **Step 3:** Replace `apps/desktop/src/renderer/routes/DeviceNew.tsx`

```tsx
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useProfilesQuery, useProxiesQuery, useCreateDevice } from '@/lib/queries';
import { ArrowLeft } from 'lucide-react';

export const DeviceNew = (): JSX.Element => {
  const navigate = useNavigate();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [name, setName] = useState('');
  const [profileId, setProfileId] = useState('');
  const [proxyId, setProxyId] = useState('');

  const profiles = useProfilesQuery();
  const proxies = useProxiesQuery();
  const create = useCreateDevice();

  const submit = (): void => {
    create.mutate(
      { name, profile_id: profileId, proxy_id: proxyId },
      { onSuccess: (d) => navigate(`/devices/${d.id}`, { replace: true }) }
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <Button asChild variant="outline" size="sm"><Link to="/devices"><ArrowLeft className="mr-2 h-4 w-4" />Back</Link></Button>
        <h1 className="text-2xl font-semibold">Create device — Step {step} of 3</h1>
      </div>

      {step === 1 && (
        <Card>
          <CardHeader><CardTitle>Basics</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Device name</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
            </div>
            <div className="space-y-2">
              <Label>Profile</Label>
              {profiles.isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}
              {profiles.data && (
                <RadioGroup value={profileId} onValueChange={setProfileId}>
                  {profiles.data.map((p) => (
                    <div key={p.id} className="flex items-center gap-3 rounded-md border p-3">
                      <RadioGroupItem id={`prof-${p.id}`} value={p.id} />
                      <Label htmlFor={`prof-${p.id}`} className="flex-1 cursor-pointer">
                        <div className="font-medium">{p.name}</div>
                        <div className="text-xs text-muted-foreground">{p.manufacturer} {p.model} · {p.screen_width}×{p.screen_height} · {p.ram_mb}MB</div>
                      </Label>
                    </div>
                  ))}
                </RadioGroup>
              )}
            </div>
            <div className="flex justify-end">
              <Button onClick={() => setStep(2)} disabled={name.length === 0 || profileId === ''}>Next</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 2 && (
        <Card>
          <CardHeader><CardTitle>Proxy</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {proxies.isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}
            {proxies.data && proxies.data.length === 0 && (
              <p className="text-muted-foreground text-sm">
                No proxies yet. <Link to="/proxies/new" className="underline">Create one →</Link> and come back.
              </p>
            )}
            {proxies.data && proxies.data.length > 0 && (
              <RadioGroup value={proxyId} onValueChange={setProxyId}>
                {proxies.data.map((p) => (
                  <div key={p.id} className="flex items-center gap-3 rounded-md border p-3">
                    <RadioGroupItem id={`px-${p.id}`} value={p.id} />
                    <Label htmlFor={`px-${p.id}`} className="flex-1 cursor-pointer">
                      <div className="font-medium">{p.label}</div>
                      <div className="text-xs text-muted-foreground">{p.type} · {p.host}:{p.port}</div>
                    </Label>
                  </div>
                ))}
              </RadioGroup>
            )}
            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep(1)}>Back</Button>
              <Button onClick={() => setStep(3)} disabled={proxyId === ''}>Next</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 3 && (
        <Card>
          <CardHeader><CardTitle>Review</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div><strong>Name:</strong> {name}</div>
            <div><strong>Profile:</strong> {profiles.data?.find((p) => p.id === profileId)?.name ?? profileId}</div>
            <div><strong>Proxy:</strong> {proxies.data?.find((p) => p.id === proxyId)?.label ?? proxyId}</div>
            {create.isError && (
              <p className="text-destructive">
                {(create.error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message ?? 'Create failed'}
              </p>
            )}
            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep(2)}>Back</Button>
              <Button onClick={submit} disabled={create.isPending}>{create.isPending ? 'Creating…' : 'Create'}</Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};
```

- [ ] **Step 4:** Smoke — `npm run dev`, log in, click "Create device", go through 3 steps. If you have at least one profile + proxy, you can create; the new device appears with state=creating; you're routed to `/devices/<new-id>` which polls for the state.

- [ ] **Step 5:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): Create device wizard (3 steps)"
```

---

## Task 15: Proxies index — table + delete

**Files:**
- Create: `apps/desktop/src/renderer/components/proxies/ProxyTable.tsx`
- Modify: `apps/desktop/src/renderer/routes/ProxiesIndex.tsx`

- [ ] **Step 1:** Write `apps/desktop/src/renderer/components/proxies/ProxyTable.tsx`

```tsx
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogTitle, AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Check, X, Trash2 } from 'lucide-react';
import { useDeleteProxy } from '@/lib/queries';
import type { Proxy } from '@/lib/queries';

export const ProxyTable = ({ proxies }: { proxies: Proxy[] }): JSX.Element => {
  const del = useDeleteProxy();
  return (
    <table className="w-full text-sm">
      <thead className="text-left text-muted-foreground border-b">
        <tr>
          <th className="py-2 px-3">Label</th>
          <th className="py-2 px-3">Type</th>
          <th className="py-2 px-3">Endpoint</th>
          <th className="py-2 px-3">Password</th>
          <th className="py-2 px-3" />
        </tr>
      </thead>
      <tbody>
        {proxies.map((p) => (
          <tr key={p.id} className="border-b last:border-b-0">
            <td className="py-2 px-3 font-medium">{p.label}</td>
            <td className="py-2 px-3">{p.type}</td>
            <td className="py-2 px-3 font-mono">{p.host}:{p.port}</td>
            <td className="py-2 px-3">
              {p.has_password ? <Check className="h-4 w-4 text-emerald-600" /> : <X className="h-4 w-4 text-muted-foreground" />}
            </td>
            <td className="py-2 px-3 text-right">
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button size="icon" variant="ghost"><Trash2 className="h-4 w-4" /></Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogTitle>Delete proxy "{p.label}"?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Devices currently using this proxy will keep running, but you can't create new devices against it.
                  </AlertDialogDescription>
                  <div className="flex justify-end gap-2">
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={() => del.mutate(p.id)}>Delete</AlertDialogAction>
                  </div>
                </AlertDialogContent>
              </AlertDialog>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};
```

- [ ] **Step 2:** Replace `apps/desktop/src/renderer/routes/ProxiesIndex.tsx`

```tsx
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ProxyTable } from '@/components/proxies/ProxyTable';
import { useProxiesQuery } from '@/lib/queries';
import { Plus } from 'lucide-react';

export const ProxiesIndex = (): JSX.Element => {
  const q = useProxiesQuery();
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Proxies</h1>
        <Button asChild><Link to="/proxies/new"><Plus className="mr-2 h-4 w-4" />New proxy</Link></Button>
      </div>
      {q.isLoading && <p className="text-muted-foreground">Loading…</p>}
      {q.data && q.data.length === 0 && <p className="text-muted-foreground">No proxies yet.</p>}
      {q.data && q.data.length > 0 && (
        <div className="rounded-lg border">
          <ProxyTable proxies={q.data} />
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 3:** Smoke — visit `/proxies`. Empty state shows. After creating one in Task 16, the row appears with the password indicator.

- [ ] **Step 4:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): Proxies index — ProxyTable + delete confirm"
```

---

## Task 16: New proxy form + component test

**Files:**
- Create: `apps/desktop/src/renderer/components/proxies/ProxyForm.tsx`
- Create: `apps/desktop/src/renderer/components/ui/select.tsx`
- Modify: `apps/desktop/src/renderer/routes/ProxyNew.tsx`
- Create: `apps/desktop/tests/component/ProxyForm.test.tsx`

- [ ] **Step 1:** Install Radix select

```bash
cd apps/desktop && npm install --silent --save @radix-ui/react-select@2.0.0
```

- [ ] **Step 2:** Write a minimal `apps/desktop/src/renderer/components/ui/select.tsx`

```tsx
import * as React from 'react';
import * as SelectPrimitive from '@radix-ui/react-select';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

export const Select = SelectPrimitive.Root;
export const SelectValue = SelectPrimitive.Value;
export const SelectTrigger = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      'flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm',
      'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
      className
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild><ChevronDown className="h-4 w-4 opacity-50" /></SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
));
SelectTrigger.displayName = SelectPrimitive.Trigger.displayName;

export const SelectContent = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={ref}
      className={cn('z-50 max-h-96 min-w-[8rem] overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md', className)}
      {...props}
    >
      <SelectPrimitive.Viewport className="p-1">{children}</SelectPrimitive.Viewport>
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
));
SelectContent.displayName = SelectPrimitive.Content.displayName;

export const SelectItem = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    className={cn(
      'relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none',
      'focus:bg-accent focus:text-accent-foreground data-[disabled]:opacity-50',
      className
    )}
    {...props}
  >
    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
      <SelectPrimitive.ItemIndicator><Check className="h-4 w-4" /></SelectPrimitive.ItemIndicator>
    </span>
    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
));
SelectItem.displayName = SelectPrimitive.Item.displayName;
```

- [ ] **Step 3:** Note — `bg-popover` and `text-popover-foreground` aren't yet in the theme. Add them. Update `apps/desktop/tailwind.config.ts` — in the `colors` extend block, add:
```ts
        popover: { DEFAULT: 'hsl(var(--popover))', foreground: 'hsl(var(--popover-foreground))' },
```
And update `apps/desktop/src/renderer/styles/index.css` — add to `:root`:
```css
    --popover: 0 0% 100%;
    --popover-foreground: 222.2 84% 4.9%;
```
And to `.dark`:
```css
    --popover: 222.2 84% 4.9%;
    --popover-foreground: 210 40% 98%;
```

- [ ] **Step 4:** Write `apps/desktop/src/renderer/components/proxies/ProxyForm.tsx`

```tsx
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useCreateProxy } from '@/lib/queries';

const schema = z.object({
  label: z.string().min(1).max(120),
  type: z.enum(['socks5', 'http']),
  host: z.string().min(1).max(255),
  port: z.coerce.number().int().min(1).max(65535),
  username: z.string().max(255).optional(),
  password: z.string().max(512).optional(),
});

type FormValues = z.infer<typeof schema>;

export const ProxyForm = ({ onCreated }: { onCreated?: (proxyId: string) => void }): JSX.Element => {
  const create = useCreateProxy();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { label: '', type: 'socks5', host: '', port: 1080, username: '', password: '' },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    const proxy = await create.mutateAsync({
      label: values.label,
      type: values.type,
      host: values.host,
      port: values.port,
      username: values.username || null,
      password: values.password || null,
    });
    onCreated?.(proxy.id);
  });

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="label">Label</Label>
        <Input id="label" {...form.register('label')} />
        {form.formState.errors.label && <p className="text-sm text-destructive">{form.formState.errors.label.message}</p>}
      </div>
      <div className="space-y-2">
        <Label>Type</Label>
        <Controller
          name="type"
          control={form.control}
          render={({ field }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="socks5">SOCKS5</SelectItem>
                <SelectItem value="http">HTTP CONNECT</SelectItem>
              </SelectContent>
            </Select>
          )}
        />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div className="col-span-2 space-y-2">
          <Label htmlFor="host">Host</Label>
          <Input id="host" {...form.register('host')} />
          {form.formState.errors.host && <p className="text-sm text-destructive">{form.formState.errors.host.message}</p>}
        </div>
        <div className="space-y-2">
          <Label htmlFor="port">Port</Label>
          <Input id="port" type="number" {...form.register('port')} />
          {form.formState.errors.port && <p className="text-sm text-destructive">{form.formState.errors.port.message}</p>}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-2">
          <Label htmlFor="username">Username (optional)</Label>
          <Input id="username" {...form.register('username')} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">Password (optional)</Label>
          <Input id="password" type="password" {...form.register('password')} />
        </div>
      </div>
      {create.isError && (
        <p className="text-sm text-destructive" role="alert">
          {(create.error as { response?: { data?: { error?: { message?: string } } } }).response?.data?.error?.message ?? 'Create failed'}
        </p>
      )}
      <Button type="submit" disabled={create.isPending}>{create.isPending ? 'Creating…' : 'Create proxy'}</Button>
    </form>
  );
};
```

- [ ] **Step 5:** Replace `apps/desktop/src/renderer/routes/ProxyNew.tsx`

```tsx
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ProxyForm } from '@/components/proxies/ProxyForm';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowLeft } from 'lucide-react';

export const ProxyNew = (): JSX.Element => {
  const navigate = useNavigate();
  return (
    <div className="space-y-4 max-w-2xl">
      <div className="flex items-center gap-4">
        <Button asChild variant="outline" size="sm"><Link to="/proxies"><ArrowLeft className="mr-2 h-4 w-4" />Back</Link></Button>
        <h1 className="text-2xl font-semibold">New proxy</h1>
      </div>
      <Card>
        <CardHeader><CardTitle>Configure</CardTitle></CardHeader>
        <CardContent>
          <ProxyForm onCreated={() => navigate('/proxies', { replace: true })} />
        </CardContent>
      </Card>
    </div>
  );
};
```

- [ ] **Step 6:** Write `apps/desktop/tests/component/ProxyForm.test.tsx`

```tsx
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProxyForm } from '@/components/proxies/ProxyForm';

const postMock = vi.fn();
vi.mock('@/lib/api-client', () => ({ getApi: () => ({ post: postMock }) }));

beforeEach(() => { postMock.mockReset(); });

const renderForm = (onCreated?: (id: string) => void): void => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: 0 } } });
  render(
    <QueryClientProvider client={qc}>
      <ProxyForm onCreated={onCreated} />
    </QueryClientProvider>
  );
};

describe('ProxyForm', () => {
  it('rejects port > 65535', async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText(/label/i), 'l');
    await userEvent.type(screen.getByLabelText(/^host/i), 'h');
    const port = screen.getByLabelText(/port/i);
    await userEvent.clear(port);
    await userEvent.type(port, '99999');
    await userEvent.click(screen.getByRole('button', { name: /create proxy/i }));
    expect(await screen.findByText(/65535/)).toBeInTheDocument();
    cleanup();
  });

  it('submits with valid values', async () => {
    postMock.mockResolvedValueOnce({ data: { id: 'p1', label: 'l', type: 'socks5', host: 'h', port: 1080, username: null, has_password: false, created_at: '2026' } });
    const onCreated = vi.fn();
    renderForm(onCreated);
    await userEvent.type(screen.getByLabelText(/label/i), 'my-proxy');
    await userEvent.type(screen.getByLabelText(/^host/i), 'h.example.com');
    await userEvent.click(screen.getByRole('button', { name: /create proxy/i }));
    await vi.waitFor(() => expect(onCreated).toHaveBeenCalledWith('p1'));
    expect(postMock).toHaveBeenCalledWith('/api/v1/proxies', expect.objectContaining({ label: 'my-proxy', host: 'h.example.com' }));
  });
});
```

- [ ] **Step 7:** Run tests + smoke

```bash
cd apps/desktop && npm run test
npm run dev
```
Expected: all tests pass. In the app, create a proxy via /proxies/new with valid creds; it appears in the index table.

- [ ] **Step 8:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): New proxy form + ProxyForm component test"
```

---

## Task 17: Settings screen — backend URL + theme + logout

**Files:**
- Modify: `apps/desktop/src/renderer/routes/Settings.tsx`

- [ ] **Step 1:** Replace the file

```tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { useSettingsStore, updateSettings } from '@/stores/settings';
import { clearAuth } from '@/stores/auth';
import { useQueryClient } from '@tanstack/react-query';

export const Settings = (): JSX.Element => {
  const navigate = useNavigate();
  const prefs = useSettingsStore((s) => s.prefs);
  const queryClient = useQueryClient();
  const [url, setUrl] = useState(prefs.backendUrl);
  const [testResult, setTestResult] = useState<'idle' | 'ok' | 'fail' | 'pending'>('idle');

  const onSaveUrl = async (): Promise<void> => {
    await updateSettings({ backendUrl: url });
    queryClient.clear();
  };

  const onTest = async (): Promise<void> => {
    setTestResult('pending');
    try {
      const r = await fetch(`${url.replace(/\/$/, '')}/healthz`);
      setTestResult(r.ok ? 'ok' : 'fail');
    } catch {
      setTestResult('fail');
    }
  };

  const onLogout = async (): Promise<void> => {
    await clearAuth();
    queryClient.clear();
    navigate('/login', { replace: true });
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <Card>
        <CardHeader>
          <CardTitle>Backend</CardTitle>
          <CardDescription>The Cloude Phone API base URL. Default <code>http://localhost:8000</code>.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="url">URL</Label>
            <div className="flex gap-2">
              <Input id="url" value={url} onChange={(e) => setUrl(e.target.value)} />
              <Button variant="outline" onClick={onTest}>Test</Button>
            </div>
            {testResult === 'ok' && <p className="text-sm text-emerald-600">Reachable ✓</p>}
            {testResult === 'fail' && <p className="text-sm text-destructive">Unreachable ✗</p>}
            {testResult === 'pending' && <p className="text-sm text-muted-foreground">Testing…</p>}
          </div>
          <Button onClick={onSaveUrl} disabled={url === prefs.backendUrl}>Save</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Theme</CardTitle></CardHeader>
        <CardContent>
          <RadioGroup
            value={prefs.theme}
            onValueChange={(v) => void updateSettings({ theme: v as 'system' | 'light' | 'dark' })}
            className="flex gap-6"
          >
            <div className="flex items-center gap-2"><RadioGroupItem id="th-sys" value="system" /><Label htmlFor="th-sys">System</Label></div>
            <div className="flex items-center gap-2"><RadioGroupItem id="th-light" value="light" /><Label htmlFor="th-light">Light</Label></div>
            <div className="flex items-center gap-2"><RadioGroupItem id="th-dark" value="dark" /><Label htmlFor="th-dark">Dark</Label></div>
          </RadioGroup>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Account</CardTitle></CardHeader>
        <CardContent>
          <Button variant="destructive" onClick={onLogout}>Log out</Button>
        </CardContent>
      </Card>
    </div>
  );
};
```

- [ ] **Step 2:** Smoke — visit `/settings`. Change theme — body switches color immediately. Click Test with running backend — shows ✓. Change URL to something bogus and Test — shows ✗. Log out → redirected to `/login`.

- [ ] **Step 3:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): Settings screen (backend URL, theme, logout)"
```

---

## Task 18: WebSocket live updates — `useDeviceStatusWS` + ConnectionBanner

**Files:**
- Create: `apps/desktop/src/renderer/lib/ws.ts`
- Create: `apps/desktop/src/renderer/components/feedback/ConnectionBanner.tsx`
- Modify: `apps/desktop/src/renderer/routes/DeviceDetail.tsx` (use the hook)
- Modify: `apps/desktop/src/renderer/components/layout/AppShell.tsx` (mount banner)

- [ ] **Step 1:** Write `apps/desktop/src/renderer/lib/ws.ts`

```ts
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
      ws = new WebSocket(`${httpToWs(backend)}/ws/devices/${deviceId}/status?token=${encodeURIComponent(token)}`);

      ws.onopen = () => {
        attempt = 0;
        useWsStore.setState((s) => ({ connected: s.connected + 1, reconnecting: false }));
      };

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data) as DeviceStatusMessage;
          if (msg.heartbeat) return;
          queryClient.setQueryData<{ state?: string; state_reason?: string | null; adb_host_port?: number | null } | undefined>(
            ['device', deviceId],
            (prev) => (prev ? { ...prev, state: msg.state ?? prev.state, state_reason: msg.state_reason ?? prev.state_reason, adb_host_port: msg.adb_host_port ?? prev.adb_host_port } : prev)
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
```

- [ ] **Step 2:** Write `apps/desktop/src/renderer/components/feedback/ConnectionBanner.tsx`

```tsx
import { useWsStore } from '@/lib/ws';

export const ConnectionBanner = (): JSX.Element | null => {
  const reconnecting = useWsStore((s) => s.reconnecting);
  if (!reconnecting) return null;
  return (
    <div className="bg-amber-500/15 text-amber-700 dark:text-amber-300 px-4 py-1 text-xs">
      Live updates reconnecting…
    </div>
  );
};
```

- [ ] **Step 3:** Modify `apps/desktop/src/renderer/components/layout/AppShell.tsx` — mount the banner under the header. Replace its main body:

```tsx
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { useSettingsStore } from '@/stores/settings';
import { ConnectionBanner } from '@/components/feedback/ConnectionBanner';

export const AppShell = (): JSX.Element => {
  const backend = useSettingsStore((s) => s.prefs.backendUrl);
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <header className="flex items-center justify-between border-b px-4 py-2 text-sm">
          <span className="text-muted-foreground">Backend:</span>
          <span className="font-mono">{backend}</span>
        </header>
        <ConnectionBanner />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
```

- [ ] **Step 4:** Wire the hook into DeviceDetail. Open `apps/desktop/src/renderer/routes/DeviceDetail.tsx` and at the top of the component (just after `const deviceQ = ...`), add:

```tsx
  useDeviceStatusWS(id);
```
And add the import at top:
```tsx
import { useDeviceStatusWS } from '@/lib/ws';
```

- [ ] **Step 5:** Smoke — open DeviceDetail for a creating device. State should flip from `creating` to `running` live (within ~10s of the worker doing the spawn) without manual refresh.

- [ ] **Step 6:** Commit

```bash
git add apps/desktop
git commit -m "feat(desktop): useDeviceStatusWS + ConnectionBanner live state updates"
```

---

## Task 19: ESLint + Prettier + final lint pass

**Files:**
- Create: `apps/desktop/.eslintrc.cjs`
- Create: `apps/desktop/.prettierrc`
- Modify: anything ESLint flags

- [ ] **Step 1:** Install lint deps

```bash
cd apps/desktop && npm install --silent --save-dev eslint@8.57.0 @typescript-eslint/parser@7.10.0 @typescript-eslint/eslint-plugin@7.10.0 eslint-plugin-react@7.34.2 eslint-plugin-react-hooks@4.6.2 eslint-plugin-react-refresh@0.4.7 prettier@3.2.5
```

- [ ] **Step 2:** Write `apps/desktop/.eslintrc.cjs`

```cjs
module.exports = {
  root: true,
  env: { browser: true, node: true, es2022: true },
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module', ecmaFeatures: { jsx: true } },
  plugins: ['@typescript-eslint', 'react', 'react-hooks', 'react-refresh'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react/recommended',
    'plugin:react-hooks/recommended',
  ],
  settings: { react: { version: 'detect' } },
  rules: {
    'react/react-in-jsx-scope': 'off',
    'react/prop-types': 'off',
    '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    'react-refresh/only-export-components': 'off',
  },
  ignorePatterns: ['out/', 'dist/', 'node_modules/', '*.config.ts', '*.config.cjs'],
};
```

- [ ] **Step 3:** Write `apps/desktop/.prettierrc`

```json
{ "semi": true, "singleQuote": true, "trailingComma": "es5", "printWidth": 100, "arrowParens": "always" }
```

- [ ] **Step 4:** Run lint + typecheck + tests; fix what's flagged

```bash
cd apps/desktop && npm run lint
npx tsc --noEmit -p tsconfig.web.json
npx tsc --noEmit -p tsconfig.node.json
npm run test
```
Expected: all clean. If lint flags anything, fix in-line (typical: missing return types, unused imports, missing dep arrays). Re-run.

- [ ] **Step 5:** Run prettier

```bash
cd apps/desktop && npm run format
```

- [ ] **Step 6:** Commit (only if anything changed)

```bash
git add apps/desktop
git status   # if no changes, skip
git commit -m "chore(desktop): lint + format clean"
```

---

## Task 20: electron-builder packaging + icon

**Files:**
- Create: `apps/desktop/electron-builder.yml`
- Create: `apps/desktop/resources/icon.png` + `icon.ico` (placeholder allowed)

- [ ] **Step 1:** Create a placeholder icon. Use a Python one-liner to generate a 256×256 PNG so the build doesn't fail:

```bash
cd apps/desktop && python -c "
from PIL import Image, ImageDraw, ImageFont
img = Image.new('RGB', (256, 256), '#0f172a')
d = ImageDraw.Draw(img)
try:
    f = ImageFont.truetype('arial.ttf', 140)
except OSError:
    f = ImageFont.load_default()
d.text((48, 40), 'CP', fill='#e2e8f0', font=f)
img.save('resources/icon.png')
"
```
If PIL isn't installed: `python -m pip install --quiet Pillow` first.

- [ ] **Step 2:** Convert PNG to ICO with PIL too:

```bash
cd apps/desktop && python -c "
from PIL import Image
Image.open('resources/icon.png').save('resources/icon.ico', sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)])
"
```

- [ ] **Step 3:** Write `apps/desktop/electron-builder.yml`

```yaml
appId: com.cloude.phone.desktop
productName: Cloude Phone
copyright: Copyright © 2026 cloude-phone
directories:
  buildResources: resources
  output: dist
files:
  - out/**/*
  - package.json
asar: true
win:
  target:
    - nsis
  icon: resources/icon.ico
nsis:
  oneClick: false
  perMachine: false
  allowToChangeInstallationDirectory: true
  createDesktopShortcut: true
  createStartMenuShortcut: true
  shortcutName: Cloude Phone
publish: null
```

- [ ] **Step 4:** Run the packaging build

```bash
cd apps/desktop && npm run package
```
Expected: `dist/Cloude Phone Setup 0.1.0.exe` is produced (~70-150 MB). Build takes 1-3 minutes.

- [ ] **Step 5:** Smoke-install the produced `.exe` manually (double-click in Explorer) → finish wizard → launch from Start Menu shortcut. App opens to `/login`. Close it.

- [ ] **Step 6:** Add `dist/` to `.gitignore` (already in Task 0 step 12, but double-check). Commit just the builder config + resources:

```bash
git add apps/desktop/electron-builder.yml apps/desktop/resources
git commit -m "feat(desktop): electron-builder NSIS config + placeholder icon"
```

---

## Task 21: README — quick start for the desktop app

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Replace the "Current phase" block. Find the lines starting with `## Current phase: P1b` and the block that follows up to (but not including) `## Phases ahead`. Replace with:

```markdown
## Current phase: P1c (Electron Desktop Dashboard)

P1c adds `apps/desktop/` — a native Windows dashboard built with Electron + React + TypeScript + Tailwind + shadcn/ui. It connects to the P1a+P1b backend over HTTP and subscribes to `/ws/devices/{id}/status` for live state updates. Auth tokens persist in the OS keychain via Electron `safeStorage`. Backend URL is editable in Settings (default `http://localhost:8000`). No backend changes in P1c; the only thing the dashboard can't do is show the device's screen — that's P1d.

Full task list: [P1c plan](docs/superpowers/plans/2026-05-15-p1c-electron-dashboard.md). Design: [P1c spec](docs/superpowers/specs/2026-05-15-p1c-electron-dashboard-design.md).

### Run the dashboard locally

Prereqs: the backend is already up (`docker compose up -d` per P1a/P1b). Then:

```bash
cd apps/desktop
npm install
npm run dev
```

A native window opens on `/login`. Mint an invite from the api container (`docker compose exec api python scripts/make_invite.py --role admin --ttl-hours 24`) and redeem it in the UI. Create a proxy, then create a device — watch the state go `creating → running` live.

### Build an installer

```bash
cd apps/desktop && npm run package
# -> dist/Cloude Phone Setup 0.1.0.exe
```
```

- [ ] **Step 2:** Update "Phases ahead" — replace the P1c/P1d lines with:

```markdown
- **P1c** (this phase) — Electron desktop dashboard (login, devices, proxies, settings) connected to P1a+P1b backend with live WS updates.
- **P1d** — Live device screen inside the dashboard (scrcpy / streaming bridge).
```

- [ ] **Step 3:** Commit

```bash
git add README.md
git commit -m "docs: README — P1c desktop dashboard quick start"
```

---

## Task 22: P1c closeout — placeholder scan, full test sweep, tag, push

**Files:** none — verification + tag.

- [ ] **Step 1:** Placeholder scan

```bash
git grep -nE "TBD|TODO|FIXME|XXX|placeholder" -- 'apps/desktop/**' ':!apps/desktop/src/renderer/components/devices/StreamPlaceholder.tsx' ':!apps/desktop/src/renderer/types/window.d.ts'
```
Expected: empty. The `StreamPlaceholder.tsx` filename itself is the only legitimate "placeholder" — filtered above.

- [ ] **Step 2:** Final test + lint + typecheck sweep

```bash
cd apps/desktop
npm run test
npm run lint
npx tsc --noEmit -p tsconfig.web.json
npx tsc --noEmit -p tsconfig.node.json
```
Expected: all green. Counts: ~3 (api) + ~3 (state-machine) + ~7 (format) + ~2 (DeviceActions) + ~2 (LoginForm) + ~2 (ProxyForm) = at least 18 tests passing.

- [ ] **Step 3:** Manual smoke checklist (record outcomes inline below):

1. Backend is up (`docker compose ps` → 4 services healthy with the migration applied).
2. `cd apps/desktop && npm run dev` opens window on `/login`.
3. Mint invite from api container; redeem in UI → land on `/devices`.
4. Create proxy via `/proxies/new`.
5. Create device via 3-step wizard → state goes `creating → running` live without manual refresh.
6. On device detail, copy `adb connect` command; in a terminal run it → device shows.
7. Stop the device → state goes `stopped` live.
8. Delete the device → it disappears from the index.
9. Settings: change backend URL to wrong port → Test shows ✗; revert → ✓.
10. Toggle theme: System / Light / Dark — body color changes immediately.
11. Log out → bounced to `/login`; relaunch dev → still on `/login` (no auto-rehydrate).

- [ ] **Step 4:** Tag + push

```bash
cd /e/cloude-phone/.claude/worktrees/festive-lewin-e65748
git tag p1c-complete
git push origin claude/festive-lewin-e65748
git push origin p1c-complete
```

- [ ] **Step 5:** Update the open PR with a P1c progress comment:

```bash
gh pr comment 2 --body "P1c — Electron desktop dashboard — complete on this branch. Tag p1c-complete pushed. Plan: docs/superpowers/plans/2026-05-15-p1c-electron-dashboard.md, design: docs/superpowers/specs/2026-05-15-p1c-electron-dashboard-design.md."
```

---

## Completion criteria (from spec)

1. ✅ `apps/desktop/` scaffolded with electron-vite + React + TS + Tailwind + shadcn — Tasks 0-1
2. ✅ All 8 screens implemented and reachable — Tasks 9-17
3. ✅ Auth tokens persist across restart via safeStorage — Task 3
4. ✅ Backend URL editable in Settings, hot reconfigure — Tasks 4, 17, 8 (subscriber)
5. ✅ Device state changes live via WebSocket — Task 18
6. ✅ Stream-placeholder section on device detail — Task 13 (StreamPlaceholder)
7. ✅ Unit + component tests pass; eslint + tsc + format clean — Tasks 6, 7, 10, 13, 16, 19
8. ✅ `npm run package` produces working `.exe` — Task 20
9. ✅ Manual smoke checklist green on your machine — Task 22 step 3
10. ✅ Git tag `p1c-complete` pushed — Task 22 step 4

---

*End of P1c plan.*
