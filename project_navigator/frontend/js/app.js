// app.js — bootstrap.
//
// Phase 7: full app shell wiring. Flow:
//   1. auth.bootstrap() — GET /api/auth/me; redirect to /login.html if 401.
//   2. Wire the sidebar and header (includes theme).
//   3. Load the sidebar (project list + active highlight).
//   4. Load the active project's snapshot into the main pane.

import { hydrateFromSnapshot, setCurrentProject, setActiveProjectId,
  setCurrentUser, activeProjectId,
} from './state.js';
import { renderAll } from './stages.js';
import { bootstrap as authBootstrap } from './auth.js';
import { init as themeInit } from './theme.js';
import { applyI18n } from './i18n.js';
import {
  loadAndRenderSidebar, loadActiveProject, wireSidebar, wireHeader,
  updateBreadcrumb,
} from './projects.js';

(async function main() {
  themeInit();
  applyI18n();

  const me = await authBootstrap();
  if (me === null) return; // redirecting to login

  wireSidebar();
  wireHeader();

  await loadAndRenderSidebar();
  await loadActiveProject();
  updateBreadcrumb();
})();

window.addEventListener('langchange', () => {
  applyI18n();
  renderAll();
  updateBreadcrumb();
});