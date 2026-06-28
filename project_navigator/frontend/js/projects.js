// projects.js — sidebar logic (list / create / rename / delete / select).

import {
  setActiveProjectId, setCurrentProject, currentProject,
  hydrateFromSnapshot, currentUser, activeProjectId, S,
} from './state.js';
import { apiGet, apiPost, apiPatch, apiDelete } from './api.js';
import { renderAll } from './stages.js';
import { logout } from './auth.js';

const SIDEBAR_KEY = 'pnav5_sidebar_collapsed';

let _projects = []; // last fetched list

// ── Sidebar persistence ───────────────────────────────────────────────────

function isSidebarCollapsed() {
  try { return localStorage.getItem(SIDEBAR_KEY) === '1'; }
  catch (_) { return false; }
}
function setSidebarCollapsed(flag) {
  try { localStorage.setItem(SIDEBAR_KEY, flag ? '1' : '0'); } catch (_) {}
  document.body.classList.toggle('sidebar-collapsed', flag);
  const sb = document.getElementById('sidebar');
  if (sb) sb.classList.toggle('collapsed', flag);
}

// ── Rendering ─────────────────────────────────────────────────────────────

export function renderSidebar(projects, activeId) {
  _projects = projects || [];
  const list = document.getElementById('project-list');
  if (!list) return;
  if (!_projects.length) {
    list.innerHTML = '';
    document.getElementById('sidebar-empty').hidden = false;
    return;
  }
  document.getElementById('sidebar-empty').hidden = true;
  list.innerHTML = _projects.map((p) => `
    <li data-pid="${p.id}" class="${p.id === activeId ? 'active' : ''}">
      <span class="project-name">${_esc(p.name)}</span>
      <span class="row-actions">
        <button data-action="rename" data-pid="${p.id}" title="Rename">✎</button>
        <button data-action="delete" data-pid="${p.id}" class="danger" title="Delete">×</button>
      </span>
    </li>
  `).join('');
}

function _esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Public actions ────────────────────────────────────────────────────────

export async function loadAndRenderSidebar() {
  const me = await apiGet('/api/auth/me');
  const projects = me.projects || [];
  renderSidebar(projects, me.active_project_id);
  return { projects, active_project_id: me.active_project_id };
}

export async function createProject(name) {
  const id = _uid();
  await apiPost('/api/projects', { id, name });
  await loadAndRenderSidebar();
  await selectProject(id);
}

export async function renameProject(pid, newName) {
  await apiPatch(`/api/projects/${pid}`, { name: newName });
  await loadAndRenderSidebar();
}

export async function deleteProject(pid) {
  await apiDelete(`/api/projects/${pid}`);
  // Reload sidebar (active_project_id may have rolled over).
  const { active_project_id } = await loadAndRenderSidebar();
  // Reload the main pane to reflect the (possibly new) active project.
  setActiveProjectId(active_project_id);
  await loadActiveProject();
}

export async function selectProject(pid) {
  if (pid === activeProjectId) return;
  await apiPut(`/api/projects/${pid}/active`, {});
  setActiveProjectId(pid);
  // Highlight in the sidebar.
  document.querySelectorAll('#project-list li').forEach((li) => {
    li.classList.toggle('active', li.dataset.pid === pid);
  });
  // Update the breadcrumb.
  updateBreadcrumb();
  // Reload the snapshot for the new project.
  await loadActiveProject();
}

export async function loadActiveProject() {
  if (!activeProjectId) {
    setCurrentProject(null);
    hydrateFromSnapshot({ project: null, goal: { text: '' }, stages: [] });
    renderAll();
    updateBreadcrumb();
    return;
  }
  const snapshot = await apiGet(`/api/projects/${activeProjectId}/snapshot`);
  setCurrentProject(snapshot.project);
  hydrateFromSnapshot(snapshot);
  renderAll();
  updateBreadcrumb();
}

export function updateBreadcrumb() {
  const el = document.getElementById('header-project-name');
  if (!el) return;
  if (currentProject && currentProject.name) {
    el.textContent = currentProject.name;
    el.classList.remove('empty');
  } else {
    el.textContent = '(no project)';
    el.classList.add('empty');
  }
}

function _uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
}

// ── DOM wiring ────────────────────────────────────────────────────────────

export function wireSidebar() {
  setSidebarCollapsed(isSidebarCollapsed());

  const newBtn = document.getElementById('sidebar-new-btn');
  const newForm = document.getElementById('sidebar-new-form');
  const newInput = document.getElementById('sidebar-new-input');
  const newConfirm = document.getElementById('sidebar-new-confirm');
  const newCancel = document.getElementById('sidebar-new-cancel');

  function openNewForm() {
    newForm.classList.add('open');
    newInput.value = '';
    newInput.focus();
  }
  function closeNewForm() {
    newForm.classList.remove('open');
  }

  newBtn.addEventListener('click', openNewForm);
  newCancel.addEventListener('click', closeNewForm);
  newConfirm.addEventListener('click', async () => {
    const name = newInput.value.trim();
    if (!name) return;
    newConfirm.disabled = true;
    try { await createProject(name); }
    catch (e) { alert(`Create failed: ${e.message}`); }
    finally { newConfirm.disabled = false; closeNewForm(); }
  });
  newInput.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') newConfirm.click();
    else if (ev.key === 'Escape') closeNewForm();
  });

  // Project row interactions (delegated).
  document.getElementById('project-list').addEventListener('click', async (ev) => {
    const li = ev.target.closest('li[data-pid]');
    if (!li) return;
    const pid = li.dataset.pid;

    const action = ev.target.closest('[data-action]');
    if (action) {
      ev.stopPropagation();
      if (action.dataset.action === 'rename') {
        const current = _projects.find((p) => p.id === pid);
        const next = window.prompt('Rename project', current ? current.name : '');
        if (next && next.trim()) {
          try { await renameProject(pid, next.trim()); }
          catch (e) { alert(`Rename failed: ${e.message}`); }
        }
      } else if (action.dataset.action === 'delete') {
        const current = _projects.find((p) => p.id === pid);
        if (!confirm(`Delete project "${current ? current.name : pid}" and all its content?`)) return;
        try { await deleteProject(pid); }
        catch (e) { alert(`Delete failed: ${e.message}`); }
      }
      return;
    }
    // Otherwise: select.
    try { await selectProject(pid); }
    catch (e) { alert(`Open failed: ${e.message}`); }
  });

  // Collapse toggle.
  document.getElementById('collapse-btn').addEventListener('click', () => {
    setSidebarCollapsed(!isSidebarCollapsed());
  });
}

export function wireHeader() {
  const trigger = document.getElementById('user-trigger');
  const dropdown = document.getElementById('user-dropdown');
  const nameEl = document.getElementById('user-name');

  function close() { dropdown.classList.remove('open'); }
  function open() { dropdown.classList.add('open'); }

  if (currentUser) nameEl.textContent = currentUser.username;
  trigger.textContent = `${currentUser ? currentUser.username : 'account'} ▾`;

  trigger.addEventListener('click', (ev) => {
    ev.stopPropagation();
    dropdown.classList.toggle('open');
  });
  document.addEventListener('click', (ev) => {
    if (!dropdown.contains(ev.target) && ev.target !== trigger) close();
  });

  document.getElementById('switch-user-btn').addEventListener('click', async () => {
    // "Switch user" = log out and bounce to the login screen.
    try { await logout(); } catch (_) {}
    window.location.replace('/login.html');
  });
}

export async function signOut() {
  try { await logout(); } catch (_) {}
  window.location.replace('/login.html');
}