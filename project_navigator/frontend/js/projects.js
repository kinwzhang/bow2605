// projects.js — sidebar logic (list / create / rename / delete / select).

import {
  setActiveProjectId, setCurrentProject, currentProject,
  hydrateFromSnapshot, currentUser, activeProjectId, S,
} from './state.js';
import { apiGet, apiPost, apiPatch, apiPut, apiDelete } from './api.js';
import { renderAll } from './stages.js';
import { logout, listUsers, switchUser } from './auth.js';
import { apply as applyTheme, currentTheme, currentMode } from './theme.js';
import { t, setLang, getLang, applyI18n } from './i18n.js';

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
  const btn = document.getElementById('sidebar-new-btn');
  if (btn) btn.classList.toggle('collapsed', flag);
  const collapseBtn = document.getElementById('collapse-btn');
  if (collapseBtn) {
    collapseBtn.textContent = flag ? '›' : '‹';
    collapseBtn.title = flag ? t('sidebar.expand', 'Expand sidebar') : t('sidebar.collapse', 'Collapse sidebar');
  }
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
    el.textContent = t('project.none', '(no project)');
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
        const currentName = current ? current.name : '';
        const next = window.prompt(t('project.rename', 'Rename project'), currentName);
        if (next && next.trim()) {
          try { await renameProject(pid, next.trim()); }
          catch (e) { alert(`Rename failed: ${e.message}`); }
        }
      } else if (action.dataset.action === 'delete') {
        const current = _projects.find((p) => p.id === pid);
        const msg = t('project.delete_confirm', 'Delete project "{name}" and all its content?').replace('{name}', current ? current.name : pid);
        if (!confirm(msg)) return;
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

let _dropdownDefaultHTML = '';

export function wireHeader() {
  const trigger = document.getElementById('user-trigger');
  const dropdown = document.getElementById('user-dropdown');
  const nameEl = document.getElementById('user-name');
  const themeBtn = document.getElementById('theme-toggle-btn');

  _dropdownDefaultHTML = dropdown.innerHTML;

  function close() {
    dropdown.classList.remove('open');
    _resetDropdown();
  }

  if (currentUser) nameEl.textContent = currentUser.username;
  trigger.textContent = `${currentUser ? currentUser.username : 'account'} ▾`;

  trigger.addEventListener('click', (ev) => {
    ev.stopPropagation();
    if (dropdown.classList.contains('open')) {
      close();
    } else {
      _resetDropdown();
      _syncThemeUI();
      dropdown.classList.add('open');
    }
  });
  document.addEventListener('click', (ev) => {
    if (!dropdown.contains(ev.target) && ev.target !== trigger) close();
  });

  document.getElementById('switch-user-btn').addEventListener('click', _showUserList);

  // ── Theme toggle button (header) ──────────────────────────────────────
  themeBtn.addEventListener('click', () => {
    const next = currentMode === 'light' ? 'dark' : 'light';
    applyTheme(currentTheme, next);
  });

  // ── Theme swatches (dropdown) ────────────────────────────────────────
  dropdown.querySelectorAll('.theme-swatch').forEach(el => {
    el.addEventListener('click', () => {
      applyTheme(el.dataset.theme, currentMode);
    });
  });

  // ── Theme mode buttons (dropdown) ─────────────────────────────────────
  dropdown.querySelectorAll('.theme-mode-btn').forEach(el => {
    el.addEventListener('click', () => {
      applyTheme(currentTheme, el.dataset.mode);
    });
  });

  // ── Sync theme UI on change ───────────────────────────────────────────
  window.addEventListener('themechange', _syncThemeUI);

  // ── Language toggle ───────────────────────────────────────────────────
  const langBtn = document.getElementById('lang-btn');
  if (langBtn) {
    langBtn.textContent = getLang() === 'zh-CN' ? 'EN' : '中文';
    langBtn.addEventListener('click', () => {
      const next = getLang() === 'zh-CN' ? 'en' : 'zh-CN';
      setLang(next);
      langBtn.textContent = next === 'zh-CN' ? 'EN' : '中文';
      applyI18n();
      const nameEl = document.getElementById('user-name');
      if (currentUser) nameEl.textContent = currentUser.username;
      document.getElementById('switch-user-btn').textContent = t('user.switch', 'Switch user\u2026');
      _syncThemeUI();
      // Re-cache the dropdown HTML so the cached copy reflects the new language.
      const dropdown = document.getElementById('user-dropdown');
      if (dropdown) _dropdownDefaultHTML = dropdown.innerHTML;
      // Update collapse button title.
      const collapseBtn = document.getElementById('collapse-btn');
      if (collapseBtn) {
        const collapsed = isSidebarCollapsed();
        collapseBtn.title = collapsed ? t('sidebar.expand', 'Expand sidebar') : t('sidebar.collapse', 'Collapse sidebar');
      }
      window.dispatchEvent(new CustomEvent('langchange'));
    });
  }

  _syncThemeUI();
}

function _syncThemeUI() {
  const themeBtn = document.getElementById('theme-toggle-btn');
  if (themeBtn) themeBtn.textContent = currentMode === 'light' ? '☀' : '☾';

  const dropdown = document.getElementById('user-dropdown');
  if (!dropdown) return;

  dropdown.querySelectorAll('.theme-swatch').forEach(el => {
    el.classList.toggle('active', el.dataset.theme === currentTheme);
  });
  dropdown.querySelectorAll('.theme-mode-btn').forEach(el => {
    el.classList.toggle('active', el.dataset.mode === currentMode);
  });
}

function _resetDropdown() {
  const dropdown = document.getElementById('user-dropdown');
  if (!dropdown) return;
  if (dropdown.classList.contains('switching')) {
    dropdown.innerHTML = _dropdownDefaultHTML;
    dropdown.classList.remove('switching');
  document.getElementById('switch-user-btn').textContent = t('user.switch', 'Switch user\u2026');
  document.getElementById('switch-user-btn').addEventListener('click', _showUserList);
  }
}

async function _showUserList() {
  let users;
  try { users = await listUsers(); } catch (_) { return; }
  users = users.filter(u => u.id !== (currentUser && currentUser.id));

  const dropdown = document.getElementById('user-dropdown');
  dropdown.innerHTML = `
    <div class="header-line">${t('user.switch_to', 'Switch to\u2026')}</div>
    <div class="user-switch-list">
      ${users.map(u => `<button class="user-switch-item" data-uid="${u.id}">${_esc(u.username)}</button>`).join('')}
    </div>
    <button class="sep user-switch-back">${t('user.back', '\u2190 Back')}</button>
  `;
  dropdown.classList.add('switching');

  dropdown.querySelector('.user-switch-list').addEventListener('click', async (ev) => {
    const el = ev.target.closest('.user-switch-item');
    if (!el) return;
    const uid = parseInt(el.dataset.uid, 10);
    el.disabled = true;
    try {
      await switchUser(uid);
      window.location.reload();
    } catch (e) {
      alert(`Switch failed: ${e.message}`);
      _resetDropdown();
    }
  });

  dropdown.querySelector('.user-switch-back').addEventListener('click', _resetDropdown);
}

export async function signOut() {
  try { await logout(); } catch (_) {}
  window.location.replace('/login.html');
}