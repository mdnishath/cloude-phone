# P1c — Electron Desktop Dashboard (Design)

**Status:** Brainstorm complete; awaiting user review of this spec before writing the implementation plan.
**Depends on:** P1a (REST + WS contracts, JWT auth, invite flow) and P1b (real device spawn) — both complete on this branch.
**Repo location:** `apps/desktop/`.

## Goal

A native desktop dashboard for the Cloude Phone single-user (you), running on Windows, that connects over the network to the P1a+P1b backend. Lets you log in / redeem an invite, manage your devices (list, create via wizard, start / stop / delete), manage proxies (CRUD), and watch device-state transitions live via the existing `/ws/devices/{id}/status` WebSocket. Auth tokens persist in the OS keychain via Electron `safeStorage` so the app stays logged in across restarts. Backend URL is configurable from a Settings screen (defaults to `http://localhost:8000`).

After P1c, the only thing you can't do from the dashboard is see the device's screen — that's [P1d](#future-phases). Everything else — create, control, configure — works fully from inside the app.

## Non-goals (deferred)

- **Live screen streaming** — placeholder section on the device-detail page; the actual scrcpy/ws-scrcpy integration lands in P1d.
- **Admin panel** — user list / mint invite UI / audit log viewer is P2. For P1c you continue using `make_invite.py` from the api container to mint invites.
- **Auto-update** — manual `.exe` install in P1c; electron-builder's auto-updater is P2.
- **Cross-platform builds** — Windows-only `.exe` first. electron-builder makes macOS/Linux easy to add later; not in P1c.
- **Multi-account / multi-backend** — single backend URL at a time; change in Settings. No fast-switching UI.
- **Notifications outside the app** — toast notifications inside the window only; no native OS notifications, no tray icon.
- **Local device action shortcuts** — no global hotkeys, no system tray. Plain window.

## Architecture

### Process model

Two processes, both TypeScript:

**Main process** (`src/main/`) — small. Owns:
- App / window lifecycle and a single-instance lock (clicking the icon twice focuses the existing window).
- Auth-token storage via Electron `safeStorage` (encrypted at rest by the OS keychain). The renderer needs the token string in-memory to set `Authorization: Bearer` on HTTP calls and to include `?token=` on the WS URL — that's unavoidable. What `safeStorage` buys is **at-rest** encryption: the token is never written to disk in plaintext. IPC channels (`auth:bootstrap`, `auth:save`, `auth:clear`) are the only way the renderer interacts with disk-resident tokens; the renderer never touches the filesystem directly.
- Non-secret preferences via `electron-store` (backend URL, theme).
- Native dialogs (none in P1c, but the surface exists).
- IPC handler registration. All IPC channels are typed via a shared `IpcContract` interface so renderer and main can't drift.

**Renderer process** (`src/renderer/`) — the actual app. Owns:
- React 18 + React Router 6 for navigation.
- TanStack Query (React Query) for **all server state** — devices, profiles, proxies, /me. Cache, refetch-on-window-focus, mutation invalidation.
- Zustand for **light client state** — auth (current user + cached token mirror), settings (loaded once at boot via IPC).
- Tailwind CSS + shadcn/ui components for styling/primitives. System theme by default with explicit light/dark override.
- A `useDeviceStatusWS(deviceId)` hook that opens `ws://<backend>/ws/devices/<id>/status?token=<access>`, dispatches messages into the TanStack Query cache via `queryClient.setQueryData`, and reconnects with exponential backoff (1s, 2s, 5s, cap 30s).

### File layout

```
apps/desktop/
├── package.json
├── electron-builder.yml
├── electron.vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
├── tailwind.config.ts
├── postcss.config.cjs
├── components.json                       (shadcn/ui config)
├── .eslintrc.cjs
├── .gitignore                            (dist/, out/, node_modules/, .vite/)
├── resources/
│   ├── icon.ico
│   └── icon.png
├── src/
│   ├── shared/
│   │   └── ipc-types.ts                  shared main↔renderer IPC contract
│   ├── main/
│   │   ├── main.ts                       app + BrowserWindow + single-instance
│   │   ├── preload.ts                    contextBridge exposing window.api
│   │   ├── secure-storage.ts             safeStorage wrapper for tokens
│   │   ├── prefs-store.ts                electron-store wrapper (backend url, theme)
│   │   └── ipc.ts                        ipcMain.handle('auth:save', ...), etc
│   └── renderer/
│       ├── main.tsx                      React root, QueryClient + Zustand providers
│       ├── App.tsx                       <Router> + <AppShell> + route table
│       ├── styles/index.css              Tailwind base + shadcn theme tokens
│       ├── routes/
│       │   ├── Login.tsx
│       │   ├── Redeem.tsx
│       │   ├── DevicesIndex.tsx
│       │   ├── DeviceDetail.tsx
│       │   ├── DeviceNew.tsx
│       │   ├── ProxiesIndex.tsx
│       │   ├── ProxyNew.tsx
│       │   └── Settings.tsx
│       ├── components/
│       │   ├── ui/                       shadcn primitives (Button, Card, Dialog, Input, Select, Toast, ...)
│       │   ├── layout/
│       │   │   ├── AppShell.tsx          sidebar + topbar + outlet
│       │   │   ├── Sidebar.tsx
│       │   │   └── ProtectedRoute.tsx    redirects to /login if no token
│       │   ├── devices/
│       │   │   ├── DeviceCard.tsx
│       │   │   ├── StateBadge.tsx        color-coded for creating/running/stopped/error/etc
│       │   │   ├── DeviceWizard.tsx      3-step create flow
│       │   │   ├── DeviceActions.tsx     start/stop/delete buttons + state-machine guards
│       │   │   ├── AdbInfoCard.tsx       copy adb / scrcpy commands
│       │   │   └── StreamPlaceholder.tsx "Live screen (P1d)" disabled section
│       │   ├── proxies/
│       │   │   ├── ProxyTable.tsx
│       │   │   └── ProxyForm.tsx
│       │   └── feedback/
│       │       ├── Toast.tsx             wraps shadcn toast
│       │       └── ConnectionBanner.tsx  "reconnecting…" / "backend unreachable"
│       ├── lib/
│       │   ├── api.ts                    Axios instance + base URL from settings + 401 interceptor
│       │   ├── auth.ts                   Zustand store, IPC bridge for token, login/logout helpers
│       │   ├── ws.ts                     useDeviceStatusWS hook
│       │   ├── queries.ts                useDevicesQuery, useDevice, useCreateDevice, ... (TanStack hooks)
│       │   ├── state-machine.ts          canStart/canStop/canDelete predicates
│       │   ├── format.ts                 humanizeState, formatBytes, formatRelativeTime
│       │   └── utils.ts                  cn(), debounce, etc
│       └── stores/
│           └── settings.ts               Zustand store for backendUrl + theme, hydrated from IPC
└── tests/
    ├── setup.ts                          Vitest setup (jsdom)
    ├── unit/
    │   ├── state-machine.test.ts
    │   ├── format.test.ts
    │   └── api.test.ts                   axios interceptor refresh behavior with msw
    └── component/
        ├── ProxyForm.test.tsx            zod validation, submit
        └── DeviceActions.test.tsx        button enablement per state
```

### Module responsibilities

Each module has one job, kept small enough to hold in context.

- `lib/api.ts` — single Axios instance. Base URL is reactive: when `useSettingsStore` changes `backendUrl`, the instance reconfigures via a `setBaseURL` setter. 401 interceptor: hit `/auth/refresh` once with the refresh token, retry the original request; on a second 401, call `useAuthStore.getState().clear()` (which IPCs main to wipe safeStorage) and route to `/login`. Error envelope unwrap helper: turns `{error:{code,message,details}}` into a typed `ApiError`.
- `lib/auth.ts` — `useAuthStore` (Zustand): `{ tokens: { access, refresh } | null, user: UserPublic | null, status: 'loading'|'authed'|'anonymous' }`. Helpers `login(email, password)`, `redeemInvite(token, email, password)`, `logout()` call the API + IPC into main.
- `lib/ws.ts` — `useDeviceStatusWS(deviceId)` opens the WS in a `useEffect`, listens for `state`/`adb_host_port`/`state_reason` updates, calls `queryClient.setQueryData(['device', deviceId], merge)`. Handles `{heartbeat: true}` (no-op). On `close`: schedule reconnect with backoff and surface a `reconnecting` state to a context banner.
- `lib/queries.ts` — wrappers around `useQuery` / `useMutation`. Every mutation invalidates the relevant list query (`['devices']` for device mutations, `['proxies']` for proxies).
- `lib/state-machine.ts` — pure predicates: `canStart(state)`, `canStop(state)`, `canDelete(state)`. Mirrors the API's guard rules so the UI doesn't show buttons that would 409.

### IPC contract (`src/shared/ipc-types.ts`)

```ts
export interface AuthBootstrapResult {
  hasToken: boolean;
  tokens?: { access: string; refresh: string };
}

export interface Prefs {
  backendUrl: string;
  theme: 'system' | 'light' | 'dark';
}

export interface IpcContract {
  'auth:bootstrap': { args: []; result: AuthBootstrapResult };
  'auth:save':      { args: [{ access: string; refresh: string }]; result: void };
  'auth:clear':     { args: []; result: void };
  'prefs:get':      { args: []; result: Prefs };
  'prefs:set':      { args: [Partial<Prefs>]; result: Prefs };
  'app:openExternal': { args: [string]; result: void };
}
```

Preload exposes a typed `window.api` mapped from this contract. Both sides import from `src/shared/ipc-types.ts` so renaming a channel breaks the build.

## Screens — UX detail

### 1. Login
- Form: email (zod: email), password (zod: min 1).
- Submit → `POST /api/v1/auth/login` → on 201, save tokens via IPC, refetch `/me`, navigate to `/devices`.
- "Have an invite token? Redeem →" link to `/redeem`.

### 2. Redeem invite
- Form: token (min 10), email (zod: email), password (min 8).
- Submit → `POST /api/v1/auth/redeem-invite` → same token-save + navigate flow.

### 3. Devices index (`/devices`)
- Grid of `DeviceCard` (3 columns on wide window, 2 on narrow). Each card:
  - Device name (large)
  - Profile model (small, e.g. "Pixel 5 · 1080×2340")
  - `StateBadge` (color-coded: gray=stopped, amber=creating/stopping, green=running, red=error, dark=deleted)
  - Last started / stopped timestamp
- Each card is a `Link to={/devices/{id}}`.
- "Create device" primary button top-right → `/devices/new`.
- Live updates: each card has its own `useDeviceStatusWS` subscription **only while the index is mounted**. Cleanup on unmount.

### 4. Device detail (`/devices/:id`)
- Header: name + `StateBadge` (live) + "Back to devices" link.
- Profile panel: model, resolution, RAM, CPU, Android version.
- Proxy panel: label, type, host:port.
- ADB info (only when `state === 'running'` and `adb_host_port !== null`):
  - `adb connect localhost:<port>` — copy-to-clipboard button.
  - `scrcpy -s localhost:<port>` — copy-to-clipboard button.
  - Small explainer: "Install scrcpy from <https://github.com/Genymobile/scrcpy/releases> and run this command in a terminal."
- Stream placeholder (P1d): card titled "Live screen", with disabled button "Open screen" and a one-liner "Coming in P1d".
- Actions row: `Start`, `Stop`, `Delete` — `<Button disabled={!canStart(state)}>` etc. Delete uses an `AlertDialog` confirm.
- Live state via `useDeviceStatusWS(id)` → toasts on transitions ("Device is now running" with port).
- State-reason banner when `state === 'error'`.

### 5. Create device wizard (`/devices/new`)
3-step wizard inside one route. Step state is React `useState`; no URL params.

- **Step 1 — Basics:** name (required) + profile (radio list of `useProfilesQuery()`).
- **Step 2 — Proxy:** radio list of `useProxiesQuery()`. Each item shows label + type + host. A "Create new proxy" button below the list opens a `<Dialog>` with `ProxyForm`; on success the new proxy is auto-selected.
- **Step 3 — Review:** read-only summary, "Create" button → `POST /api/v1/devices` → on 201 (state="creating"), navigate to `/devices/<new-id>` so the user sees the spawn progress live.
- Nav: "Back" button on steps 2 and 3; "Cancel" returns to `/devices`.

### 6. Proxies index (`/proxies`)
- Table: label, type, host:port, "Has password" (Check/X icon), Delete button.
- Empty state: "No proxies yet" + "New proxy" button.
- "New proxy" top-right → `/proxies/new`.

### 7. New proxy (`/proxies/new`)
- Form: label (1-120), type (Select: socks5/http), host (1-255), port (1-65535), username (optional), password (optional).
- Submit → `POST /api/v1/proxies` → on 201, back to `/proxies`. Password is never stored client-side; the request body carries it, the response shows `has_password=true`.

### 8. Settings (`/settings`)
- Backend URL field with "Test connection" button → `GET /healthz`. Shows ✓/✗ inline.
- Theme: Radio group (System / Light / Dark) — applies immediately via Tailwind dark-mode class on `<html>`.
- "Log out" button → confirm dialog → IPC `auth:clear` → redirect `/login`.

### App shell

- Left sidebar: nav links (Devices, Proxies, Settings) with current-route highlight.
- Top bar: backend URL pill (small, click → /settings), user email + logout dropdown.
- Bottom of window: `ConnectionBanner` reveals when any WS reconnect is in flight or backend is unreachable.

## Auth flow (full sequence)

1. App boots → main wakes safeStorage → IPC `auth:bootstrap` returns `{hasToken, tokens?}`.
2. Renderer hydrates `useAuthStore` (`status: 'loading'` → `'authed'` or `'anonymous'`).
3. `<ProtectedRoute>` redirects `'anonymous'` to `/login`. `'authed'` users on `/login` get bounced to `/devices`.
4. On login/redeem success: renderer calls `auth:save` with the new pair, refetches `/me`, navigates.
5. Every API call goes through `lib/api.ts` Axios. On 401:
   - If response code is `unauthorized` and we have a refresh token, attempt `POST /auth/refresh` with the refresh.
   - On success: update `useAuthStore` with new pair + `auth:save`, retry original request once.
   - On second failure: call `useAuthStore.getState().logout()` which calls `auth:clear` and navigates to `/login`.
6. On manual logout: same `clear` path.

## Data flow (per resource)

```
useDevicesQuery()  → GET /api/v1/devices
useDevice(id)      → GET /api/v1/devices/{id}     (refetch-on-window-focus)
useCreateDevice()  → POST .../devices             invalidates ['devices']
useStartDevice(id) → POST .../devices/{id}/start  invalidates ['devices'], ['device', id]
useStopDevice(id)  → POST .../devices/{id}/stop   invalidates same
useDeleteDevice(id)→ DELETE .../devices/{id}      invalidates ['devices']
useProfilesQuery() → GET .../device-profiles
useProxiesQuery()  → GET .../proxies
useCreateProxy()   → POST .../proxies             invalidates ['proxies']
useDeleteProxy(id) → DELETE .../proxies/{id}      invalidates ['proxies']
useMeQuery()       → GET .../me
```

Mutations show optimistic toasts; failures roll back with a red toast carrying the API error message.

## Error handling

- **Network error** (axios `ERR_NETWORK`): single red toast "Backend unreachable" + show ConnectionBanner with link to Settings.
- **API error envelope** (`{error:{code,message,details}}`): toast `error.message`. For 422 validation errors with `details.errors[]`, attach the first field error to the form field via React Hook Form's `setError`.
- **401**: handled by interceptor (above).
- **WS disconnect**: ConnectionBanner shows "Live updates reconnecting…"; on success it dismisses.
- **Token missing/expired across both access AND refresh**: forced logout, banner explaining "Session expired, please log in".

## Testing

### Unit (Vitest)
- `state-machine.test.ts` — 6 tests: every `(canStart|canStop|canDelete)(state)` for each `DeviceState` value.
- `format.test.ts` — humanizeState, formatRelativeTime, etc.
- `api.test.ts` — 401 → refresh → retry; second 401 → clear + redirect; network error → red toast.

### Component (Vitest + Testing Library + msw)
- `ProxyForm.test.tsx` — zod rejects port outside 1-65535; submit calls mutate with correct payload.
- `DeviceActions.test.tsx` — Start enabled only for stopped/error; Stop only for running/creating; Delete always present, confirms via dialog.
- `LoginForm.test.tsx` — invalid email blocks submit; valid submit triggers mutation.

### Skipped for P1c
- Spectron / Playwright e2e — brittle for Electron, slow, and the API already has its own integration test. Manual smoke checklist (below) covers the happy path.

### Manual smoke checklist (in README)
1. Bring up the backend (`docker compose up -d`), seed profiles + mint an invite.
2. `npm run dev` → app window opens on `/login`.
3. Redeem the invite → land on /devices.
4. Create a proxy.
5. Create a device with that proxy → see state go `creating → running` live without refresh.
6. Copy `adb connect` from device detail, paste in a terminal, confirm device shows.
7. Stop → state goes to `stopped` live.
8. Delete → device disappears from list.
9. Settings: change backend URL to a wrong one → "Test connection" shows ✗; change back → ✓.
10. Log out → /login; relaunch app → /login (no auto-rehydrate).

## Build & ship

- **Dev:** `npm run dev` — `electron-vite dev`, HMR for renderer + auto-reload main/preload, DevTools open by default.
- **Build:** `npm run build` — `electron-vite build` bundles main / preload / renderer into `out/`.
- **Lint/format:** `npm run lint` (eslint + tsc --noEmit), `npm run format` (prettier).
- **Package:** `npm run package` — `electron-builder --win` → `dist/Cloude Phone Setup x.y.z.exe` (NSIS installer, code signing skipped for P1c — `--publish never`).
- **Default backend URL:** `http://localhost:8000`. Bundled `app.config.ts` carries the default; user overrides in Settings (persisted via `electron-store`).
- **Versioning:** `package.json` version starts at `0.1.0`. No auto-update for P1c.
- **Icon:** simple placeholder for P1c (e.g. a square gradient with "C"). Polish later.

## Backend contract assumptions (already in place from P1a + P1b)

- `POST /api/v1/auth/login` → `{access, refresh, token_type: "bearer"}`
- `POST /api/v1/auth/refresh` → same shape
- `POST /api/v1/auth/redeem-invite` → same shape
- `GET /api/v1/me` → `UserPublic`
- `GET /api/v1/device-profiles` → `DeviceProfilePublic[]`
- `GET /api/v1/proxies`, `POST /api/v1/proxies` (body needs `password` as plain string — API encrypts it), `DELETE .../proxies/{id}`
- `GET /api/v1/devices` (list non-deleted), `GET .../devices/{id}`, `POST .../devices` (now REQUIRES `proxy_id` from P1b), `POST .../devices/{id}/start`, `.../stop`, `DELETE .../devices/{id}`, `GET .../devices/{id}/adb-info`
- `WS /ws/devices/{id}/status?token=<access>` — initial snapshot + push updates with `{device_id, state, state_reason, adb_host_port}` or `{heartbeat: true}`.
- Error envelope: `{error: {code, message, details?}}`.

No backend changes for P1c. If we discover a missing field during build (unlikely), we add the smallest possible endpoint to the existing routers — surfaced as an open question, not a unilateral change.

## Open question for your call

**Icon and branding.** P1c needs a `.ico` + `.png` for the installer + window. The default plan is a simple text-based placeholder ("CP" in a square). If you have an actual logo / brand assets you want shipped from day 1, drop them in `apps/desktop/resources/` before plan execution. If not, I'll generate a placeholder and we polish in P2.

## Completion criteria

P1c is done when:

1. `apps/desktop/` scaffolded with electron-vite + React + TS + Tailwind + shadcn; `npm run dev` opens a window successfully.
2. All 8 screens implemented (Login, Redeem, Devices index, Device detail, Device new wizard, Proxies index, Proxy new, Settings) and reachable from the sidebar / protected-route flow.
3. Auth tokens persist across app restart via safeStorage.
4. Backend URL is editable in Settings and reconfigures the API client hot (no restart).
5. Device-state changes appear live in the UI (creating → running) via WebSocket — no manual refresh needed.
6. Stream-placeholder section is present on device detail (disabled button + "P1d" copy).
7. Unit + component tests pass; eslint + tsc clean; format clean.
8. `npm run package` produces a working `.exe` installer that you can launch and use end-to-end.
9. Manual smoke checklist (above) goes green on your machine.
10. Git tag `p1c-complete`; PR / branch updated.

---

*End of P1c design.*
