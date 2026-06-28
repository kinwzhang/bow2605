# 03 — Frontend Architecture

## 1. Goals

- Preserve the **focus-tool aesthetic** of `project_navigator.html` (Notion-inspired, neutral palette, no chrome).
- No build step, no framework, no external libraries.
- Replace the monolithic inline script with **ES modules** so each concern lives in its own file.
- Add a left sidebar (collapsible) and a branded header without disturbing the existing render behavior.

## 2. File Layout (recap from `00_overview.md`)

```
frontend/
├── index.html                  # app shell
├── login.html                  # auth page
├── css/
│   ├── main.css                # existing palette + stage/blocker/idea styles
│   ├── sidebar.css             # left project list
│   └── header.css              # branded top bar
└── js/
    ├── api.js                  # fetch() wrapper
    ├── state.js                # S cache + openStages/openBQ
    ├── auth.js                 # login/logout/me, session bootstrap
    ├── projects.js             # sidebar logic
    ├── stages.js               # stage/blocker/idea render + actions
    └── app.js                  # bootstrap, project routing
```

All JS files use `<script type="module">`. Each module exports named functions; no default exports to keep imports explicit.

## 3. Page Skeletons

### 3.1 `frontend/index.html`

```
┌────────────────────────────────────────────────────────────┐
│ header.css                                                 │
│ ┌────────────────────────────────────────────────────────┐ │
│ │ Project Navigator  ▸  Bow2605             [kin ▾] [↪] │ │  ← header
│ └────────────────────────────────────────────────────────┘ │
│ ┌──────────┬─────────────────────────────────────────────┐ │
│ │ sidebar  │ main                                        │ │
│ │          │ ┌─────────────────────────────────────────┐ │ │
│ │ + New    │ │ Ultimate goal                           │ │ │
│ │          │ │ ▸ Click to set your north star…         │ │ │
│ │ • Bow2605│ ├─────────────────────────────────────────┤ │ │
│ │ • Side…  │ │ Stages                          [+ Add] │ │ │
│ │ • Impor… │ │                                          │ │
│ │          │ │ 1 ▾ Plan        ⊘2  ⚑1  ●Active  ▾     │ │
│ │          │ │   …stages, blockers, ideas, sub-items…  │ │
│ │          │ │                                          │ │
│ │          │ └─────────────────────────────────────────┘ │ │
│ └──────────┴─────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

- **Header** (sticky, 56px): product name on the left (`Project Navigator`), project breadcrumb in the middle (`▸ Bow2605`), user switcher + logout on the right.
- **Sidebar** (240px expanded / 48px collapsed): project list with `+ New project` button at top, project rows below, collapse toggle at the bottom.
- **Main**: the existing app, refactored to live inside `#mainContent`. Goal bar, stages toolbar, stage list, portal menu.

### 3.2 `frontend/login.html`

```
┌──────────────────────────────────────────────┐
│  Project Navigator                           │
│  Sign in                                     │
│  ┌────────────────────────────────────────┐  │
│  │ Username [_________________]           │  │
│  │ Password [_________________]           │  │
│  │ [Sign in]   New here? Register         │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

A register toggle on the same form (single-page swap, not a separate route).

## 4. Module Responsibilities

### 4.1 `api.js`

Thin wrapper around `fetch()`.

```js
export async function apiGet(path);
export async function apiPost(path, body);
export async function apiPatch(path, body);
export async function apiPut(path, body);
export async function apiDelete(path);
```

- Sets `Content-Type: application/json` and `credentials: 'same-origin'`.
- Attaches `X-CSRF-Token` from the in-memory `csrf` constant on every mutating call.
- On `401`, calls `auth.onUnauthenticated()` which redirects to `login.html`.
- Throws an `ApiError` with `{ status, code, message }` on non-2xx responses.

### 4.2 `state.js`

Owns the in-memory cache that the renderer reads.

```js
export const S = { goal: '', stages: [] };
export const openStages = {};
export const openBQ = {};
export let csrf = null;
export function setCsrf(value) { csrf = value; }

export function hydrateFromSnapshot(snapshot) { ... }
export function clearCache() { ... }
```

`hydrateFromSnapshot` is called after every successful project load or switch.

### 4.3 `auth.js`

- `bootstrap()` — called from `app.js` on page load. Calls `GET /api/auth/me`. On `200`, populates the header (username) and returns the payload. On `401`, redirects to `login.html`.
- `login(username, password)` — `POST /api/auth/login`. On success, stores `csrf` and returns `{ user, active_project_id, projects }`.
- `register(username, password)` — `POST /api/auth/register`. Followed by `login()`.
- `logout()` — `POST /api/auth/logout`, then `window.location = '/login.html'`.
- `switchUser()` — same as `logout()` (delegated to the user switcher UI in the header).
- `onUnauthenticated()` — internal, called by `api.js` on `401`.

### 4.4 `projects.js`

Renders the sidebar and reacts to user actions.

```js
export async function loadAndRenderSidebar();    // GET /api/projects
export async function createProject(name, description);
export async function renameProject(id, name);
export async function deleteProject(id);
export async function selectProject(id);          // PUT active, then load snapshot
```

Sidebar DOM structure:

```html
<aside id="sidebar" class="open">
  <button id="newProjectBtn">+ New project</button>
  <ul id="projectList">
    <li data-pid="abc" class="active">Bow2605</li>
    <li data-pid="def">Side project</li>
  </ul>
  <button id="collapseBtn" title="Collapse">‹</button>
</aside>
```

Collapse behavior: toggle `aside.open` class, swap the chevron, persist the collapsed state in `localStorage` under `pnav5_sidebar_collapsed`. The main pane's grid `template-columns` switches from `240px 1fr` to `48px 1fr`.

A "New project" inline input appears at the top of the list, mirroring the existing `add-stage-card` pattern. Rename uses a contenteditable span or a prompt() — `prompt()` is acceptable for the prototype.

### 4.5 `stages.js`

Lifts the existing render and mutation logic out of `project_navigator.html` with minimal changes. Public surface:

```js
export async function loadActiveProject();       // GET snapshot for active project
export function renderGoal();
export function renderStages();
export function applyStatus(val);                // status pill callback
export function applyDeep(val);
export function addBQ(sid);
export function delBQ(sid, bqid, ev);
export function toggleBQ(sid, bqid);
export function addSub(sid, bqid);
export function delSub(sid, bqid, subid);
export function addIdea(sid);
export function delIdea(sid, iid);
export function showAdd();
export function cancelAdd();
export function confirmAdd();
export function toggleStage(id);
export function setStageStatus(id, st);
export function deleteStage(id);
export function editGoal();
export function saveGoal();
export function cancelGoal();
```

The portal menu (`openPortalMenu`, `closePortalMenu`, `applyStatus`, `applyDeep`) is moved here unchanged.

The render pipeline is the same as the existing file: mutate `S` → API call (optimistic) → `renderStages()`. The `persist()` function becomes a no-op local stub that calls the appropriate `apiPost` / `apiPatch` / `apiDelete` and rolls back on failure.

### 4.6 `app.js`

```js
import * as auth from './auth.js';
import * as projects from './projects.js';
import * as stages from './stages.js';
import { apiGet } from './api.js';
import { hydrateFromSnapshot } from './state.js';

(async function main() {
  const me = await auth.bootstrap();        // redirects to login.html on 401
  await projects.loadAndRenderSidebar();   // paints project list
  await stages.loadActiveProject();        // paints main content
  // wire global event listeners (sidebar collapse, header user switcher, …)
})();
```

`loadActiveProject` reads `me.active_project_id`, calls `GET /api/projects/<pid>/snapshot`, then `hydrateFromSnapshot`, then `renderGoal()` and `renderStages()`.

## 5. State Management

- **One source of truth per project**: `S` in `state.js`. Replaced wholesale on project switch via `hydrateFromSnapshot`. Not mutated in-place across switches.
- **UI-only state** (collapsed sidebar, expanded stages, expanded blockers) lives outside `S`:
  - `openStages`, `openBQ` (existing): in-memory only, re-initialized to all-false on project switch. (Could be persisted per project later.)
  - `pnav5_sidebar_collapsed`: `localStorage`, single boolean.
- **Optimistic writes**: `addBQ` etc. push into `S` immediately, then call the API. On failure, the next `loadActiveProject` reconciles.

## 6. CSS Strategy

Three small stylesheets, no preprocessor:

- `main.css` — copy the contents of the existing `<style>` block, minus the portal menu positioning (moves to `header.css` because the portal is shared).
- `sidebar.css` — defines `aside#sidebar` grid placement, project rows, collapse transition.
- `header.css` — defines the top bar, breadcrumb, user switcher, and the portal menu (single source for `z-index: 9999`).

Layout uses CSS Grid on the body:

```css
body {
  display: grid;
  grid-template-rows: 56px 1fr;
  grid-template-columns: 240px 1fr;
  grid-template-areas:
    "header header"
    "sidebar main";
}
body.sidebar-collapsed { grid-template-columns: 48px 1fr; }
```

The `.app` wrapper inside `main` keeps its existing `max-width: 760px` to preserve reading width.

## 7. User Switcher

A simple dropdown in the header, mirrors the existing portal menu pattern (single shared element, positioned by JS):

- Trigger: `[kin ▾]` button in the top right.
- Items:
  - Current user (non-interactive header line)
  - "Switch user…" → calls `auth.switchUser()` (logs out, redirects to login)
  - "Register new account" → toggles the login form's mode without leaving the page

For the prototype, "switching users" = logging out. A future enhancement could allow listing other registered users and switching without a password re-prompt (out of scope).

## 8. Persistence of the Active Project

- On login: server returns `active_project_id` (defaults to the user's most-recent project, or `null` if none).
- On project select: frontend calls `PUT /api/projects/<pid>/active` → server stores `user.active_project_id`.
- On app load: `GET /api/auth/me` returns the stored `active_project_id`, and the frontend loads that project's snapshot.
- If the active project no longer exists (deleted in another tab), the server returns `null` and the frontend prompts the user to pick another (or auto-selects the first project).

## 9. Render Flow (after refactor)

```
User action in main pane (e.g. add stage)
   │
   ▼
Mutate S in state.js (optimistic)
   │
   ▼
renderStages() in stages.js (synchronous, instant)
   │
   ▼
fire-and-forget apiPost('/api/projects/<pid>/stages', body)
   │
   ├── 2xx: nothing to do
   ├── 409 collision: regenerate id, retry once
   └── other failure: schedule a snapshot reload to reconcile
                       (or show a small error toast)

Sidebar selection
   │
   ▼
apiPut('/api/projects/<pid>/active', {})
   │
   ▼
apiGet('/api/projects/<pid>/snapshot')
   │
   ▼
hydrateFromSnapshot() → clears S, fills from response
   │
   ▼
renderGoal() + renderStages()
```

## 10. Accessibility Notes (lightweight)

- Sidebar rows are real `<button>`s inside a `<ul>` for keyboard navigation.
- The header user switcher is a `<button aria-haspopup="menu" aria-expanded="…">`.
- The portal menu uses `role="menu"` and each item `role="menuitem"` (cosmetic for the prototype; no full keyboard nav in Phase 7).
- Color contrast already meets AA on the existing palette per `ANALYSIS.md`; new sidebar/header styles inherit the same palette tokens.

## 11. Out of Scope (Frontend)

- Drag-to-reorder for projects or stages (deferred — `position` column exists for when it's added).
- Inline editing of stage names (currently requires delete + recreate; deferred).
- Real-time sync across tabs (no `BroadcastChannel` / SSE for the prototype).
- Service worker / PWA shell.