// state.js — in-memory cache + open-state maps + status enum mirrors.
//
// One source of truth per project. Replaced wholesale on project switch via
// hydrateFromSnapshot(). UI-only state (collapsed stages/blockers) lives
// outside S so it can reset cleanly between projects.

export const S = { goal: '', stages: [] };
export const openStages = {};
export const openBQ = {};

// CSRF token; mutated by api.js on every /me response and login/register.
export let csrf = null;
export function setCsrf(token) { csrf = token; }

// Active project id; null = no project selected.
export let activeProjectId = null;
export function setActiveProjectId(id) { activeProjectId = id; }

// Current project metadata (id, name, description).
export let currentProject = null;
export function setCurrentProject(p) { currentProject = p; }

// User info.
export let currentUser = null;
export function setCurrentUser(u) { currentUser = u; }

export function hydrateFromSnapshot(snapshot) {
  S.goal = (snapshot && snapshot.goal && snapshot.goal.text) || '';
  S.stages = (snapshot && Array.isArray(snapshot.stages)) ? snapshot.stages : [];
  // Reset transient open-state maps; the user will re-open what they need.
  for (const k of Object.keys(openStages)) delete openStages[k];
  for (const k of Object.keys(openBQ)) delete openBQ[k];
}

export function clearCache() {
  S.goal = '';
  S.stages = [];
  currentProject = null;
  activeProjectId = null;
  for (const k of Object.keys(openStages)) delete openStages[k];
  for (const k of Object.keys(openBQ)) delete openBQ[k];
}

// Status enum mirrors — kept in sync with backend STAGE_STATUSES / ITEM_STATUSES.
export const STAGE_STATUSES = ['todo', 'active', 'blocked', 'done'];
export const ITEM_STATUSES = ['todo', 'active', 'blocked', 'done', 'park', 'review', 'nice', 'solve'];

export const ST_CLS = {
  todo: 'st-todo', active: 'st-active', blocked: 'st-blocked', done: 'st-done',
  park: 'st-park', review: 'st-review', nice: 'st-nice', solve: 'st-solve',
};
export const ST_LBL = {
  todo: 'To Do', active: 'Active', blocked: 'Blocked', done: 'Done',
  park: 'Park', review: 'Review', nice: 'Nice to have', solve: 'To Solve',
};

// Client-side id generator (matches legacy uid()).
export function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
}

export function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}