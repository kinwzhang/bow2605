// stages.js — render + actions, lifted from the legacy project_navigator.html.
//
// Phase 6: every mutation calls the real backend API. Mutations are
// optimistic: the local S cache is updated, the UI re-renders, then the
// API call is fired. A failure surfaces via api.js → ApiError → reload.

import {
  S, openStages, openBQ, currentProject, activeProjectId,
  ST_CLS, ST_LBL, esc,
} from './state.js';
import { apiGet, apiPost, apiPatch, apiPut, apiDelete, ApiError } from './api.js';

function pid() { return activeProjectId; }

const NORM = [
  { v: 'todo',    l: 'To Do' },
  { v: 'active',  l: 'Active' },
  { v: 'blocked', l: 'Blocked' },
  { v: 'done',    l: 'Done' },
];
const DEEP = [
  { v: 'park',   l: 'Park' },
  { v: 'review', l: 'Review' },
  { v: 'nice',   l: 'Nice to have' },
  { v: 'solve',  l: 'To Solve →normal' },
];

let _menuCtx = null; // { sid, bqid, subid }

// ── Persistence ───────────────────────────────────────────────────────────
// Phase 5: no-op. Real backend calls land in Phase 6+.
function persist() { /* no-op stub */ }

// ── Goal ──────────────────────────────────────────────────────────────────

export function editGoal() {
  document.getElementById('goalEdit').style.display = 'block';
  const t = document.getElementById('goalInput');
  t.value = S.goal;
  t.focus();
}

export function saveGoal() {
  S.goal = document.getElementById('goalInput').value.trim();
  document.getElementById('goalEdit').style.display = 'none';
  renderGoal();
  apiPut(`/api/projects/${pid()}/goal`, { text: S.goal }).catch((e) => {
    console.error('saveGoal failed', e);
    alert(`Save failed: ${e.message}`);
  });
}

export function cancelGoal() {
  document.getElementById('goalEdit').style.display = 'none';
}

export function renderGoal() {
  const d = document.getElementById('goalDisp');
  const ic = document.getElementById('goalIcon');
  if (S.goal) {
    d.textContent = S.goal;
    d.className = '';
    ic.textContent = '✎';
  } else {
    d.textContent = 'Click to set your north star…';
    d.className = 'ph';
    ic.textContent = '';
  }
}

// ── Portal dropdown ───────────────────────────────────────────────────────

function getItem(sid, bqid, subid) {
  const stage = S.stages.find((x) => x.id === sid);
  if (!stage) return null;
  if (!bqid) return stage;
  const bq = stage.blockers.find((x) => x.id === bqid);
  if (!bq) return null;
  if (!subid) return bq;
  return bq.items.find((x) => x.id === subid) || null;
}

export function openPortalMenu(btnEl, sid, bqid, subid) {
  const pm = document.getElementById('portalMenu');
  const item = getItem(sid, bqid, subid);
  if (!item) return;

  // Stages have no `deep` mode — they get the 4 normal statuses only and
  // no "Going too deep?" toggle.
  const isStage = !bqid;
  const statuses = (!isStage && item.deep) ? DEEP : NORM;

  let html = statuses
    .map((s) => `<button class="pmitem" data-status="${s.v}">${s.l}</button>`)
    .join('');

  if (!isStage) {
    html += item.deep
      ? `<button class="pmitem sep-back" data-deep="false">↩ Back to normal</button>`
      : `<button class="pmitem sep" data-deep="true">⚑ Going too deep?</button>`;
  }

  pm.innerHTML = html;
  _menuCtx = { sid, bqid: bqid || null, subid: subid || null };

  pm.querySelectorAll('.pmitem').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.dataset.status) applyStatus(btn.dataset.status);
      else if (btn.dataset.deep) applyDeep(btn.dataset.deep === 'true');
    });
  });

  // Position the menu just below the pill that triggered it. The menu is
  // position:fixed, so coordinates are viewport-relative (no scrollY).
  const rect = btnEl.getBoundingClientRect();
  pm.style.display = 'block';
  const pmW = pm.offsetWidth;
  const pmH = pm.offsetHeight;
  let left = rect.left;
  if (left + pmW > window.innerWidth - 8) left = window.innerWidth - pmW - 8;
  // Flip upward if there isn't room below the trigger.
  let top = rect.bottom + 4;
  if (top + pmH > window.innerHeight - 8) top = rect.top - pmH - 4;
  pm.style.top = top + 'px';
  pm.style.left = left + 'px';
}

export function closePortalMenu() {
  document.getElementById('portalMenu').style.display = 'none';
  _menuCtx = null;
}

document.addEventListener('click', (e) => {
  const pm = document.getElementById('portalMenu');
  if (pm.style.display === 'block' && !pm.contains(e.target)) closePortalMenu();
});

export function applyStatus(val) {
  if (!_menuCtx) return;
  const { sid, bqid, subid } = _menuCtx;
  const item = getItem(sid, bqid, subid);
  if (!item) return;

  // 'solve' is only emitted from the deep toggle, which only appears for
  // blockers / sub-items. For stages (bqid is null), val is always one of
  // the 4 normal stage statuses.
  if (bqid && val === 'solve') {
    item.deep = false;
    item.status = 'todo';
  } else {
    item.status = val;
  }
  closePortalMenu();
  // For blocker/sub-item status changes, re-derive the parent stage's
  // auto-status so the header badge stays in sync.
  if (bqid) {
    const stage = S.stages.find((x) => x.id === sid);
    if (stage) reconcileStageStatus(stage);
  }
  renderStages();
  _patchItemStatus(sid, bqid, subid, { status: val });
}

export function applyDeep(val) {
  if (!_menuCtx) return;
  const { sid, bqid, subid } = _menuCtx;
  const item = getItem(sid, bqid, subid);
  if (!item) return;
  item.deep = val;
  item.status = val ? 'park' : 'todo';
  closePortalMenu();
  if (bqid) {
    const stage = S.stages.find((x) => x.id === sid);
    if (stage) reconcileStageStatus(stage);
  }
  renderStages();
  _patchItemStatus(sid, bqid, subid, { deep: val });
}

function _patchItemStatus(sid, bqid, subid, body) {
  // Routes:
  //   subid set → /subitems/<subid>
  //   bqid set  → /blockers/<bqid>
  //   neither   → /stages/<sid>  (stage-level status change)
  let url;
  if (subid) {
    url = `/api/projects/${pid()}/subitems/${subid}`;
  } else if (bqid) {
    url = `/api/projects/${pid()}/blockers/${bqid}`;
  } else {
    url = `/api/projects/${pid()}/stages/${sid}`;
  }
  apiPatch(url, body).catch((e) => {
    console.error('patch failed', e);
    alert(`Update failed: ${e.message}`);
  });
}

// ── Blockers / sub-items / ideas ──────────────────────────────────────────

export function addBQ(sid) {
  const inp = document.getElementById('bi-' + sid);
  const v = inp.value.trim();
  if (!v) return;
  const id = _uid();
  const stage = S.stages.find((x) => x.id === sid);
  stage.blockers.push({
    id, text: v, status: 'todo', deep: false, items: [],
  });
  reconcileStageStatus(stage);
  inp.value = '';
  renderStages();
  apiPost(`/api/projects/${pid()}/stages/${sid}/blockers`, {
    id, text: v, status: 'todo', deep: false,
  }).catch((e) => console.error('addBQ failed', e));
}

export function delBQ(sid, bqid, e) {
  e.stopPropagation();
  const s = S.stages.find((x) => x.id === sid);
  s.blockers = s.blockers.filter((x) => x.id !== bqid);
  reconcileStageStatus(s);
  renderStages();
  apiDelete(`/api/projects/${pid()}/blockers/${bqid}`).catch((e2) => {
    console.error('delBQ failed', e2);
  });
}

export function toggleBQ(sid, bqid) {
  const k = sid + '_' + bqid;
  openBQ[k] = !openBQ[k];
  renderStages();
}

export function addSub(sid, bqid) {
  const inp = document.getElementById('si-' + bqid);
  const v = inp.value.trim();
  if (!v) return;
  const id = _uid();
  const stage = S.stages.find((x) => x.id === sid);
  const bq = stage.blockers.find((x) => x.id === bqid);
  bq.items.push({ id, text: v, status: 'todo', deep: false });
  reconcileStageStatus(stage);
  inp.value = '';
  renderStages();
  apiPost(`/api/projects/${pid()}/blockers/${bqid}/items`, {
    id, text: v, status: 'todo', deep: false,
  }).catch((e) => console.error('addSub failed', e));
}

export function delSub(sid, bqid, subid) {
  const stage = S.stages.find((x) => x.id === sid);
  const bq = stage.blockers.find((x) => x.id === bqid);
  bq.items = bq.items.filter((x) => x.id !== subid);
  reconcileStageStatus(stage);
  renderStages();
  apiDelete(`/api/projects/${pid()}/subitems/${subid}`).catch((e) => {
    console.error('delSub failed', e);
  });
}

export function addIdea(sid) {
  const inp = document.getElementById('ii-' + sid);
  const v = inp.value.trim();
  if (!v) return;
  const id = _uid();
  S.stages.find((x) => x.id === sid).ideas.push({ id, text: v });
  inp.value = '';
  renderStages();
  apiPost(`/api/projects/${pid()}/stages/${sid}/ideas`, {
    id, text: v,
  }).catch((e) => console.error('addIdea failed', e));
}

export function delIdea(sid, iid) {
  const s = S.stages.find((x) => x.id === sid);
  s.ideas = s.ideas.filter((x) => x.id !== iid);
  renderStages();
  apiDelete(`/api/projects/${pid()}/ideas/${iid}`).catch((e) => {
    console.error('delIdea failed', e);
  });
}

// ── Stage CRUD ────────────────────────────────────────────────────────────

export function showAdd() {
  document.getElementById('addCard').style.display = 'block';
  document.getElementById('newName').focus();
}

export function cancelAdd() {
  document.getElementById('addCard').style.display = 'none';
}

export function confirmAdd() {
  const v = document.getElementById('newName').value.trim();
  if (!v) return;
  const id = _uid();
  S.stages.push({ id, name: v, status: 'todo', blockers: [], ideas: [] });
  openStages[id] = true;
  document.getElementById('newName').value = '';
  document.getElementById('addCard').style.display = 'none';
  renderStages();
  apiPost(`/api/projects/${pid()}/stages`, { id, name: v, status: 'todo' })
    .catch((e) => console.error('confirmAdd failed', e));
}

export function toggleStage(id) {
  openStages[id] = !openStages[id];
  renderStages();
}

export function deleteStage(id) {
  if (!confirm('Delete this stage and all its content?')) return;
  S.stages = S.stages.filter((x) => x.id !== id);
  renderStages();
  apiDelete(`/api/projects/${pid()}/stages/${id}`).catch((e) => {
    console.error('deleteStage failed', e);
  });
}

// ── Render helpers ────────────────────────────────────────────────────────

function _uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
}

// ── Stage status auto-derivation ──────────────────────────────────────────
// Mirrors backend.models.derive_stage_status. Stage status is a rollup of
// its blockers + sub-items:
//   - no items  → no derivation (status is whatever it was)
//   - all done  → 'done'
//   - any deep  → 'blocked' (park/review/nice/solve)
//   - otherwise → 'active'
// Called after every blocker/sub-item mutation. Re-render reads stage.status,
// so the header badge and any downstream UI update automatically.

const DEEP_STATUSES_FOR_DERIVE = new Set(['park', 'review', 'nice', 'solve']);

function deriveStageStatus(stage) {
  const items = [];
  for (const bq of (stage.blockers || [])) {
    items.push(bq);
    for (const it of (bq.items || [])) items.push(it);
  }
  if (!items.length) return null;
  const statuses = items.map((i) => i.status);
  if (statuses.every((s) => s === 'done')) return 'done';
  if (statuses.some((s) => DEEP_STATUSES_FOR_DERIVE.has(s))) return 'blocked';
  return 'active';
}

function reconcileStageStatus(stage) {
  const derived = deriveStageStatus(stage);
  if (derived !== null) stage.status = derived;
}

function pillBtn(item, sid, bqid, subid) {
  const cl = ST_CLS[item.status] || 'st-todo';
  const lbl = ST_LBL[item.status] || 'To Do';
  const bqidAttr = bqid || '';
  const subidAttr = subid || '';
  return `<button class="spill ${cl}" data-portal="${sid}|${bqidAttr}|${subidAttr}">${lbl} ▾</button>`;
}

function renderBQ(s) {
  if (!s.blockers.length) return '<div class="hint">No blockers or questions.</div>';
  return s.blockers.map((bq) => {
    const expanded = !!openBQ[s.id + '_' + bq.id];
    const deepBadge = bq.deep ? '<span class="deep-badge">Too deep</span>' : '';
    const subRows = bq.items
      .map(
        (sub) => `
      <div class="sub-item">
        <span class="sub-item-text">${esc(sub.text)}</span>
        ${sub.deep ? '<span class="deep-badge" style="font-size:9px">Too deep</span>' : ''}
        ${pillBtn(sub, s.id, bq.id, sub.id)}
        <button class="btn-del" data-del-sub="${s.id}|${bq.id}|${sub.id}">×</button>
      </div>`,
      )
      .join('');
    const expandBody = expanded
      ? `
      <div class="sub-items">${subRows || '<div class="hint" style="font-size:12px">No sub-items.</div>'}</div>
      <div class="add-sub">
        <input id="si-${bq.id}" placeholder="Add a sub-item…"
          data-add-sub-enter="${s.id}|${bq.id}" />
        <button data-add-sub="${s.id}|${bq.id}">Add</button>
      </div>`
      : '';
    return `<div class="bq-item${bq.deep ? ' deep' : ''}">
      <div class="bq-hdr">
        <button class="bq-toggle" data-toggle-bq="${s.id}|${bq.id}">${expanded ? '▾' : '▸'}</button>
        <span class="bq-text">${esc(bq.text)}</span>
        <div class="bq-controls">
          ${deepBadge}
          ${pillBtn(bq, s.id, bq.id, '')}
          <button class="btn-del" data-del-bq="${s.id}|${bq.id}">×</button>
        </div>
      </div>
      ${expandBody}
    </div>`;
  }).join('');
}

function renderIdeas(s) {
  if (!s.ideas.length) return '<div class="hint">No ideas noted yet.</div>';
  return s.ideas
    .map(
      (i) => `
    <div class="idea-row">
      <span style="flex:1">${esc(i.text)}</span>
      <button class="btn-del" data-del-idea="${s.id}|${i.id}">×</button>
    </div>`,
    )
    .join('');
}

export function renderStages() {
  const el = document.getElementById('stageList');
  const empty = document.getElementById('emptyMsg');
  const toolbar = document.querySelector('.toolbar');
  const noProjectMsg = document.getElementById('noProjectMsg');

  // Hide the stage-creation UI entirely when there's no active project —
  // otherwise clicking "+ Add stage" would POST to /api/projects/null/stages.
  const hasProject = !!activeProjectId;
  if (toolbar) toolbar.style.display = hasProject ? '' : 'none';
  if (noProjectMsg) {
    noProjectMsg.style.display = hasProject ? 'none' : 'block';
    // Wire the "+ New project" hint to open the sidebar's new-project form.
    const focusEl = noProjectMsg.querySelector('[data-focus-new]');
    if (focusEl) {
      focusEl.style.cursor = 'pointer';
      focusEl.style.color = 'var(--accent)';
      focusEl.onclick = () => {
        const btn = document.getElementById('sidebar-new-btn');
        if (btn) btn.click();
      };
    }
  }

  if (!hasProject) {
    el.innerHTML = '';
    empty.style.display = 'none';
    return;
  }
  if (!S.stages.length) {
    el.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  el.innerHTML = S.stages
    .map((s, idx) => {
      const isOpen = !!openStages[s.id];
      const bCnt = s.blockers.length;
      const iCnt = (s.ideas || []).length;
      const deepCnt = s.blockers.filter((b) => b.deep).length;
      const stageBadgeCls = {
        todo: 'st-todo', active: 'st-active', blocked: 'st-blocked', done: 'st-done',
      }[s.status];
      const stageBadgeLbl = {
        todo: '○ To do', active: '● Active', blocked: '⊘ Blocked', done: '✓ Done',
      }[s.status];

      const body = isOpen
        ? `
      <div class="stage-body">
        <div class="subsec">
          <div class="subsec-lbl lbl-block">⊘ Blockers &amp; questions</div>
          ${renderBQ(s)}
          <div class="add-row">
            <input id="bi-${s.id}" placeholder="Add a blocker or question…"
              data-add-bq-enter="${s.id}" />
            <button data-add-bq="${s.id}">Add</button>
          </div>
        </div>
        <div class="subsec">
          <div class="subsec-lbl lbl-idea">✦ Ideas &amp; thinking</div>
          ${renderIdeas(s)}
          <div class="add-row">
            <input id="ii-${s.id}" placeholder="Log an idea or thought…"
              data-add-idea-enter="${s.id}" />
            <button data-add-idea="${s.id}">Add</button>
          </div>
        </div>
        <div class="stage-ftr">
          <div class="status-btns">
            <span class="spill ${stageBadgeCls}" style="pointer-events:none" title="Auto-derived from blockers and sub-items">${stageBadgeLbl}</span>
          </div>
          <button class="btn-ghost" style="color:var(--text-3);font-size:12px" data-del-stage="${s.id}">Delete stage</button>
        </div>
      </div>`
        : '';

      return `<div class="stage-card">
      <div class="stage-hdr" data-toggle-stage="${s.id}">
        <span class="stage-num" style="font-size:11px;font-weight:700;color:var(--text-3);min-width:18px">${idx + 1}</span>
        <span class="stage-name" style="flex:1;font-size:14px;font-weight:500">${esc(s.name)}</span>
        ${bCnt ? `<span class="cnt cnt-b">⊘ ${bCnt}</span>` : ''}
        ${deepCnt ? `<span class="cnt" style="background:var(--amber-bg);color:var(--amber)">⚑ ${deepCnt}</span>` : ''}
        ${iCnt ? `<span class="cnt cnt-i">✦ ${iCnt}</span>` : ''}
        <span class="spill ${stageBadgeCls}" style="pointer-events:none">${stageBadgeLbl}</span>
        <span class="chevron${isOpen ? ' open' : ''}">▾</span>
      </div>
      ${body}
    </div>`;
    })
    .join('');

  // Delegate events so re-renders don't lose handlers.
  el.onclick = (ev) => {
    const t = ev.target.closest('[data-portal]');
    if (t) {
      ev.stopPropagation();
      const [sid, bqid, subid] = t.dataset.portal.split('|');
      openPortalMenu(t, sid, bqid || null, subid || null);
      return;
    }
    const delSubEl = ev.target.closest('[data-del-sub]');
    if (delSubEl) {
      const [sid, bqid, subid] = delSubEl.dataset.delSub.split('|');
      delSub(sid, bqid, subid);
      return;
    }
    const delBqEl = ev.target.closest('[data-del-bq]');
    if (delBqEl) {
      const [sid, bqid] = delBqEl.dataset.delBq.split('|');
      delBQ(sid, bqid, ev);
      return;
    }
    const toggleBqEl = ev.target.closest('[data-toggle-bq]');
    if (toggleBqEl) {
      const [sid, bqid] = toggleBqEl.dataset.toggleBq.split('|');
      toggleBQ(sid, bqid);
      return;
    }
    const addBqEl = ev.target.closest('[data-add-bq]');
    if (addBqEl) {
      addBQ(addBqEl.dataset.addBq);
      return;
    }
    const addSubEl = ev.target.closest('[data-add-sub]');
    if (addSubEl) {
      const [sid, bqid] = addSubEl.dataset.addSub.split('|');
      addSub(sid, bqid);
      return;
    }
    const addIdeaEl = ev.target.closest('[data-add-idea]');
    if (addIdeaEl) {
      addIdea(addIdeaEl.dataset.addIdea);
      return;
    }
    const delIdeaEl = ev.target.closest('[data-del-idea]');
    if (delIdeaEl) {
      const [sid, iid] = delIdeaEl.dataset.delIdea.split('|');
      delIdea(sid, iid);
      return;
    }
    const delStageEl = ev.target.closest('[data-del-stage]');
    if (delStageEl) {
      deleteStage(delStageEl.dataset.delStage);
      return;
    }
    const toggleStageEl = ev.target.closest('[data-toggle-stage]');
    if (toggleStageEl) {
      toggleStage(toggleStageEl.dataset.toggleStage);
      return;
    }
  };
}

// Re-attach Enter-key handlers after each render by attaching to the stage
// list with delegation. Cheaper than rebuilding listeners on every input.
document.addEventListener('keydown', (ev) => {
  if (ev.key !== 'Enter' || ev.target.tagName !== 'INPUT') return;
  const t = ev.target;
  if (t.dataset.addBqEnter) { addBQ(t.dataset.addBqEnter); ev.preventDefault(); return; }
  if (t.dataset.addSubEnter) {
    const [sid, bqid] = t.dataset.addSubEnter.split('|');
    addSub(sid, bqid);
    ev.preventDefault();
    return;
  }
  if (t.dataset.addIdeaEnter) { addIdea(t.dataset.addIdeaEnter); ev.preventDefault(); return; }
});

// Wire up the chrome (goal bar, add-stage card) once at module load. These
// elements live outside the re-rendered stage list, so a single delegated
// listener on document is sufficient.
document.addEventListener('click', (ev) => {
  if (ev.target.closest('[data-edit-goal]')) editGoal();
  else if (ev.target.closest('[data-save-goal]')) saveGoal();
  else if (ev.target.closest('[data-cancel-goal]')) cancelGoal();
  else if (ev.target.closest('[data-show-add]')) showAdd();
  else if (ev.target.closest('[data-confirm-add]')) confirmAdd();
  else if (ev.target.closest('[data-cancel-add]')) cancelAdd();
});

document.addEventListener('keydown', (ev) => {
  if (ev.target.id === 'newName') {
    if (ev.key === 'Enter') { confirmAdd(); ev.preventDefault(); }
    else if (ev.key === 'Escape') { cancelAdd(); ev.preventDefault(); }
  }
});

export function renderAll() {
  renderGoal();
  renderStages();
}