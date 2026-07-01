import { t } from './i18n.js';
import {
  S, openStages, openBQ, currentProject, activeProjectId,
  ST_CLS, ST_LBL, STAGE_DERIVE_PRIORITY, esc,
} from './state.js';
import { apiGet, apiPost, apiPatch, apiPut, apiDelete, ApiError } from './api.js';

function pid() { return activeProjectId; }

const NORM = [
  { v: 'todo',    l: () => t('status.todo', 'To Do') },
  { v: 'active',  l: () => t('status.active', 'Active') },
  { v: 'blocked', l: () => t('status.blocked', 'Blocked') },
  { v: 'done',    l: () => t('status.done', 'Done') },
];
const DEEP = [
  { v: 'park',   l: () => t('status.park', 'Park') },
  { v: 'review', l: () => t('status.review', 'Review') },
  { v: 'nice',   l: () => t('status.nice', 'Nice to have') },
  { v: 'solve',  l: () => t('status.solve', 'To Solve \u2192normal') },
];

let _menuCtx = null;
let _editCtx = null;
let _dragSrc = null;

function _uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
}

function _ts(ts) {
  if (!ts) return '';
  const d = new Date(ts + 'Z');
  if (isNaN(d.getTime())) return '';
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function _patchUrl(sid, bqid, subid, isIdea) {
  if (isIdea) return `/api/projects/${pid()}/ideas/${subid}`;
  if (subid) return `/api/projects/${pid()}/subitems/${subid}`;
  if (bqid) return `/api/projects/${pid()}/blockers/${bqid}`;
  return `/api/projects/${pid()}/stages/${sid}`;
}

function _patch(sid, bqid, subid, body, isIdea) {
  apiPatch(_patchUrl(sid, bqid, subid, isIdea), body).catch((e) => {
    console.error('patch failed', e);
    alert(`Update failed: ${e.message}`);
  });
}

function getItem(sid, bqid, subid) {
  const stage = S.stages.find((x) => x.id === sid);
  if (!stage) return null;
  if (!bqid) return stage;
  const bq = stage.blockers.find((x) => x.id === bqid);
  if (!bq) return null;
  if (!subid) return bq;
  return bq.items.find((x) => x.id === subid) || null;
}

// ── Inline editing ────────────────────────────────────────────────────────

export function startEdit(el, sid, bqid, subid) {
  if (_editCtx) return;
  const item = getItem(sid, bqid, subid);
  if (!item) return;
  const field = subid || bqid ? 'text' : 'name';
  const currentVal = item[field] || '';
  const inp = document.createElement('input');
  inp.className = 'inline-edit-input';
  inp.value = currentVal;
  inp.dataset.editSid = sid;
  inp.dataset.editBqid = bqid || '';
  inp.dataset.editSubid = subid || '';
  const parent = el.parentNode;
  el.style.display = 'none';
  parent.insertBefore(inp, el.nextSibling);
  inp.focus();
  inp.select();
  _editCtx = { sid, bqid, subid, field, el, inp };
  inp.addEventListener('blur', () => saveEdit());
}

function cancelEdit() {
  if (!_editCtx) return;
  const { el, inp } = _editCtx;
  inp.remove();
  el.style.display = '';
  _editCtx = null;
}

function saveEdit() {
  if (!_editCtx) return;
  const { sid, bqid, subid, field, el, inp } = _editCtx;
  const val = inp.value.trim();
  const item = getItem(sid, bqid, subid);
  inp.remove();
  el.style.display = '';
  _editCtx = null;
  if (!val || val === item[field]) return;
  item[field] = val;
  renderStages();
  _patch(sid, bqid, subid, { [field]: val });
}

// ── Note toggle/edit ──────────────────────────────────────────────────────

const _openNotes = {};

export function toggleNote(sid, bqid, subid, isIdea) {
  const key = isIdea ? `idea|${sid}|${subid}` : [sid, bqid || '', subid || ''].join('|');
  _openNotes[key] = !_openNotes[key];
  renderStages();
}

function _getItemForNote(sid, bqid, subid, isIdea) {
  if (isIdea) {
    const stage = S.stages.find((x) => x.id === sid);
    if (!stage) return null;
    return stage.ideas.find((x) => x.id === subid) || null;
  }
  return getItem(sid, bqid, subid);
}

function _noteKey(sid, bqid, subid, isIdea) {
  return isIdea ? `idea|${sid}|${subid}` : [sid, bqid || '', subid || ''].join('|');
}

function renderNote(sid, bqid, subid, isIdea) {
  const item = _getItemForNote(sid, bqid, subid, isIdea);
  if (!item) return '';
  const key = _noteKey(sid, bqid, subid, isIdea);
  const isOpen = !!_openNotes[key];
  const note = item.note || '';
  const typeAttr = isIdea ? 'idea' : (bqid ? (subid ? 'sub' : 'bq') : 'stage');
  const noteBtn = `<button class="btn-note" data-toggle-note="${sid}|${bqid || ''}|${subid || ''}|${typeAttr}" title="${t('note.edit', 'Edit note')}">${note ? '\u270E' : '+'}</button>`;
  if (!isOpen) return noteBtn;
  const noteHtml = `
    <div class="note-area" data-note-area="${key}">
      <textarea class="note-input" data-note-text="${sid}|${bqid || ''}|${subid || ''}|${typeAttr}" placeholder="${t('note.ph', 'Write a note\u2026')}">${esc(note)}</textarea>
      <div class="note-actions">
        <button class="btn-note-save" data-note-save="${sid}|${bqid || ''}|${subid || ''}|${typeAttr}">${t('note.save', 'Save note')}</button>
        <button class="btn-note-cancel" data-note-cancel="${key}">${t('note.cancel', 'Cancel')}</button>
      </div>
    </div>`;
  return noteBtn + noteHtml;
}

function saveNote(sid, bqid, subid, typeAttr) {
  const isIdea = typeAttr === 'idea';
  const item = _getItemForNote(sid, bqid, subid, isIdea);
  if (!item) return;
  const key = _noteKey(sid, bqid, subid, isIdea);
  const textarea = document.querySelector(`[data-note-text="${sid}|${bqid || ''}|${subid || ''}|${typeAttr}"]`);
  if (!textarea) return;
  const val = textarea.value;
  item.note = val;
  _openNotes[key] = false;
  renderStages();
  _patch(sid, bqid, subid, { note: val }, isIdea);
}

function cancelNote(key) {
  _openNotes[key] = false;
  renderStages();
}

// ── Timestamp display ─────────────────────────────────────────────────────

function _tsInline(item) {
  const ts = item.updated_at || item.status_changed_at || item.created_at;
  return ts ? `<span class="ts-inline">${_ts(ts)}</span>` : '';
}

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
    ic.textContent = '\u270E';
  } else {
    d.textContent = t('goal.ph', 'Click to set your north star\u2026');
    d.className = 'ph';
    ic.textContent = '';
  }
}

// ── Portal dropdown ───────────────────────────────────────────────────────

export function openPortalMenu(btnEl, sid, bqid, subid) {
  const pm = document.getElementById('portalMenu');
  const item = getItem(sid, bqid, subid);
  if (!item) return;

  const isStage = !bqid;
  const statuses = (!isStage && item.deep) ? DEEP : NORM;

  let html = statuses
    .map((s) => `<button class="pmitem" data-status="${s.v}">${s.l()}</button>`)
    .join('');

  if (!isStage) {
    html += item.deep
      ? `<button class="pmitem sep-back" data-deep="false">${t('deep.back', '\u21A9 Back to normal')}</button>`
      : `<button class="pmitem sep" data-deep="true">${t('deep.go', '\u2691 Going too deep?')}</button>`;
  }

  pm.innerHTML = html;
  _menuCtx = { sid, bqid: bqid || null, subid: subid || null };

  pm.querySelectorAll('.pmitem').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.dataset.status) applyStatus(btn.dataset.status);
      else if (btn.dataset.deep) applyDeep(btn.dataset.deep === 'true');
    });
  });

  const rect = btnEl.getBoundingClientRect();
  pm.style.display = 'block';
  const pmW = pm.offsetWidth;
  const pmH = pm.offsetHeight;
  let left = rect.left;
  if (left + pmW > window.innerWidth - 8) left = window.innerWidth - pmW - 8;
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

  if (bqid && val === 'solve') {
    item.deep = false;
    item.status = 'todo';
  } else {
    item.status = val;
  }
  closePortalMenu();
  if (subid) {
    const stage = S.stages.find((x) => x.id === sid);
    const blocker = stage && stage.blockers.find((b) => b.id === bqid);
    if (blocker) reconcileBlockerStatus(blocker);
  }
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
  if (subid) {
    const stage = S.stages.find((x) => x.id === sid);
    const blocker = stage && stage.blockers.find((b) => b.id === bqid);
    if (blocker) reconcileBlockerStatus(blocker);
  }
  if (bqid) {
    const stage = S.stages.find((x) => x.id === sid);
    if (stage) reconcileStageStatus(stage);
  }
  renderStages();
  _patchItemStatus(sid, bqid, subid, { deep: val });
}

function _patchItemStatus(sid, bqid, subid, body) {
  _patch(sid, bqid, subid, body);
}

// ── Drag and Drop ─────────────────────────────────────────────────────────

function handleDragStart(e) {
  const el = e.target.closest('[data-draggable]');
  if (!el) return;
  _dragSrc = el.dataset.draggable;
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', _dragSrc);
  el.classList.add('dragging');
}

function handleDragOver(e) {
  const el = e.target.closest('[data-draggable]');
  if (!el || !_dragSrc) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  document.querySelectorAll('.drag-over').forEach((x) => x.classList.remove('drag-over'));
  el.classList.add('drag-over');
}

function handleDragEnd(e) {
  document.querySelectorAll('.dragging, .drag-over').forEach((x) => x.classList.remove('dragging', 'drag-over'));
  _dragSrc = null;
}

function handleDrop(e) {
  const target = e.target.closest('[data-draggable]');
  if (!target || !_dragSrc) return;
  e.preventDefault();
  const srcType = _dragSrc.split('|')[0];
  const tgtType = target.dataset.draggable.split('|')[0];
  if (srcType !== tgtType) return;

  const srcParts = _dragSrc.split('|');
  const tgtParts = target.dataset.draggable.split('|');

  if (srcType === 'stage') {
    const srcIdx = S.stages.findIndex((s) => s.id === srcParts[1]);
    const tgtIdx = S.stages.findIndex((s) => s.id === tgtParts[1]);
    if (srcIdx < 0 || tgtIdx < 0 || srcIdx === tgtIdx) return;
    const [stage] = S.stages.splice(srcIdx, 1);
    S.stages.splice(tgtIdx, 0, stage);
    renderStages();
    S.stages.forEach((s, i) => {
      if (s.position !== i) {
        s.position = i;
        _patch(s.id, null, null, { position: i });
      }
    });
  } else if (srcType === 'blocker') {
    const stage = S.stages.find((s) => s.id === srcParts[1]);
    const tgtStage = S.stages.find((s) => s.id === tgtParts[1]);
    if (!stage || !tgtStage || srcParts[1] !== tgtParts[1]) return;
    const srcIdx = stage.blockers.findIndex((b) => b.id === srcParts[2]);
    const tgtIdx = tgtStage.blockers.findIndex((b) => b.id === tgtParts[2]);
    if (srcIdx < 0 || tgtIdx < 0 || srcIdx === tgtIdx) return;
    const [blocker] = stage.blockers.splice(srcIdx, 1);
    tgtStage.blockers.splice(tgtIdx, 0, blocker);
    renderStages();
    tgtStage.blockers.forEach((b, i) => {
      if (b.position !== i) {
        b.position = i;
        _patch(b.stage_id || tgtStage.id, b.id, null, { position: i });
      }
    });
  } else if (srcType === 'sub') {
    const stage = S.stages.find((s) => s.id === srcParts[1]);
    if (!stage) return;
    const blocker = stage.blockers.find((b) => b.id === srcParts[2]);
    const tgtBlocker = stage.blockers.find((b) => b.id === tgtParts[2]);
    if (!blocker || !tgtBlocker || srcParts[2] !== tgtParts[2]) return;
    const srcIdx = blocker.items.findIndex((i) => i.id === srcParts[3]);
    const tgtIdx = tgtBlocker.items.findIndex((i) => i.id === tgtParts[3]);
    if (srcIdx < 0 || tgtIdx < 0 || srcIdx === tgtIdx) return;
    const [item] = blocker.items.splice(srcIdx, 1);
    tgtBlocker.items.splice(tgtIdx, 0, item);
    renderStages();
    tgtBlocker.items.forEach((it, i) => {
      if (it.position !== i) {
        it.position = i;
        _patch(srcParts[1], it.blocker_id || tgtBlocker.id, it.id, { position: i });
      }
    });
  }
}

// ── Blockers / sub-items / ideas ──────────────────────────────────────────

export function addBQ(sid) {
  const inp = document.getElementById('bi-' + sid);
  const v = inp.value.trim();
  if (!v) return;
  const id = _uid();
  const stage = S.stages.find((x) => x.id === sid);
  stage.blockers.push({
    id, text: v, status: 'todo', deep: false, items: [], note: '',
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
  bq.items.push({ id, text: v, status: 'todo', deep: false, note: '' });
  reconcileBlockerStatus(bq);
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
  reconcileBlockerStatus(bq);
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
  S.stages.find((x) => x.id === sid).ideas.push({ id, text: v, note: '' });
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
  S.stages.push({ id, name: v, status: 'todo', blockers: [], ideas: [], note: '' });
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
  if (!confirm(t('stage.delete_confirm', 'Delete this stage and all its content?'))) return;
  S.stages = S.stages.filter((x) => x.id !== id);
  renderStages();
  apiDelete(`/api/projects/${pid()}/stages/${id}`).catch((e) => {
    console.error('deleteStage failed', e);
  });
}

// ── Render helpers ────────────────────────────────────────────────────────

function statusBadge(item) {
  const cl = ST_CLS[item.status] || 'st-todo';
  const lbl = t('status.' + item.status, 'To Do');
  return `<span class="spill ${cl}" style="pointer-events:none" title="Auto-derived">${lbl}</span>`;
}

function deriveStageStatus(stage) {
  const items = [];
  for (const bq of (stage.blockers || [])) {
    items.push(bq);
    for (const it of (bq.items || [])) items.push(it);
  }
  if (!items.length) return null;
  const statuses = items.map((i) => i.status);
  for (const candidate of STAGE_DERIVE_PRIORITY) {
    if (candidate === 'done') {
      if (statuses.every((s) => s === 'done')) return 'done';
    } else if (statuses.includes(candidate)) {
      return candidate;
    }
  }
  return 'active';
}

function reconcileStageStatus(stage) {
  const derived = deriveStageStatus(stage);
  if (derived !== null) stage.status = derived;
}

function deriveBlockerStatus(blocker) {
  const items = blocker.items || [];
  if (!items.length) return null;
  const statuses = items.map((i) => i.status);
  for (const candidate of STAGE_DERIVE_PRIORITY) {
    if (candidate === 'done') {
      if (statuses.every((s) => s === 'done')) return 'done';
    } else if (statuses.includes(candidate)) {
      return candidate;
    }
  }
  return 'active';
}

function reconcileBlockerStatus(blocker) {
  const derived = deriveBlockerStatus(blocker);
  if (derived !== null) blocker.status = derived;
}

function pillBtn(item, sid, bqid, subid) {
  const cl = ST_CLS[item.status] || 'st-todo';
  const lbl = t('status.' + item.status, 'To Do');
  const bqidAttr = bqid || '';
  const subidAttr = subid || '';
  return `<button class="spill ${cl}" data-portal="${sid}|${bqidAttr}|${subidAttr}">${lbl} ▾</button>`;
}

function renderBQ(s, stageIdx) {
  if (!s.blockers.length) return `<div class="hint">${t('bq.none', 'No blockers or questions.')}</div>`;
  return s.blockers.map((bq, bqIdx) => {
    const expanded = !!openBQ[s.id + '_' + bq.id];
    const bqIndex = `${stageIdx + 1}.${bqIdx + 1}`;
    const deepBadge = bq.deep ? `<span class="deep-badge">${t('bq.too_deep', 'Too deep')}</span>` : '';
    const subRows = bq.items
      .map(
        (sub, subIdx) => `
      <div class="sub-item" data-draggable="sub|${s.id}|${bq.id}|${sub.id}" draggable="true">
        <span class="drag-handle" title="${t('dnd.drag', 'Drag to reorder')}">⠿</span>
        <span class="item-idx">${bqIndex}.${subIdx + 1}</span>
        <span class="sub-item-text" data-edit-text="${s.id}|${bq.id}|${sub.id}">${esc(sub.text)}</span>
        ${sub.deep ? `<span class="deep-badge" style="font-size:9px">${t('bq.too_deep', 'Too deep')}</span>` : ''}
        ${renderNote(s.id, bq.id, sub.id, false)}
        ${_tsInline(sub)}
        ${pillBtn(sub, s.id, bq.id, sub.id)}
        <button class="btn-del" data-del-sub="${s.id}|${bq.id}|${sub.id}">×</button>
      </div>`,
      )
      .join('');
    const statusPill = (bq.items && bq.items.length > 0)
      ? statusBadge(bq)
      : pillBtn(bq, s.id, bq.id, '');
    const expandBody = expanded
      ? `
      <div class="sub-items">${subRows || `<div class="hint" style="font-size:12px">${t('sub.none', 'No sub-items.')}</div>`}</div>
      <div class="add-sub">
        <input id="si-${bq.id}" placeholder="${t('sub.ph', 'Add a sub-item\u2026')}"
          data-add-sub-enter="${s.id}|${bq.id}" />
        <button data-add-sub="${s.id}|${bq.id}">${t('sub.add', 'Add')}</button>
      </div>`
      : '';
    const noteHtml = renderNote(s.id, bq.id, null, false);
    return `<div class="bq-item${bq.deep ? ' deep' : ''}" data-draggable="blocker|${s.id}|${bq.id}" draggable="true">
      <div class="bq-hdr">
        <span class="drag-handle" title="${t('dnd.drag', 'Drag to reorder')}">⠿</span>
        <button class="bq-toggle" data-toggle-bq="${s.id}|${bq.id}">${expanded ? '▾' : '▸'}</button>
        <span class="bq-idx">${bqIndex}</span>
        <span class="bq-text" data-edit-text="${s.id}|${bq.id}|">${esc(bq.text)}</span>
        <div class="bq-controls">
          ${_tsInline(bq)}
          ${deepBadge}
          ${noteHtml}
          ${statusPill}
          <button class="btn-del" data-del-bq="${s.id}|${bq.id}">×</button>
        </div>
      </div>
      ${expandBody}
    </div>`;
  }).join('');
}

function renderIdeas(s) {
  if (!s.ideas.length) return `<div class="hint">${t('idea.none', 'No ideas noted yet.')}</div>`;
  return s.ideas
    .map(
      (i) => `
    <div class="idea-row">
      <span style="flex:1"><span class="item-idx">✦</span><span class="idea-text" data-edit-text="${s.id}||${i.id}">${esc(i.text)}</span></span>
      ${_tsInline(i)}
      ${renderNote(s.id, null, i.id, true)}
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

  const hasProject = !!activeProjectId;
  if (toolbar) toolbar.style.display = hasProject ? '' : 'none';
  if (noProjectMsg) {
    noProjectMsg.style.display = hasProject ? 'none' : 'block';
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
        park: 'st-park', review: 'st-review', nice: 'st-nice',
      }[s.status];
      const stageBadgeLbl = {
        todo: t('status.to_do', '\u25CB To do'),
        active: t('status.is_active', '\u25CF Active'),
        blocked: t('status.is_blocked', '\u2298 Blocked'),
        done: t('status.is_done', '\u2713 Done'),
        park: t('status.is_park', '\u2691 Parked'),
        review: t('status.is_review', '\u25D0 Review'),
        nice: t('status.is_nice', '\u2726 Nice to have'),
      }[s.status];
      const noteHtml = renderNote(s.id, null, null, false);

      const body = isOpen
        ? `
      <div class="stage-body">
        <div class="subsec">
          <div class="subsec-lbl lbl-block">${t('bq.header', '\u2298 Blockers & questions')}</div>
          ${renderBQ(s, idx)}
          <div class="add-row">
            <input id="bi-${s.id}" placeholder="${t('bq.add_ph', 'Add a blocker or question\u2026')}"
              data-add-bq-enter="${s.id}" />
            <button data-add-bq="${s.id}">${t('bq.add', 'Add')}</button>
          </div>
        </div>
        <div class="subsec">
          <div class="subsec-lbl lbl-idea">${t('idea.header', '\u2726 Ideas & thinking')}</div>
          ${renderIdeas(s)}
          <div class="add-row">
            <input id="ii-${s.id}" placeholder="${t('idea.ph', 'Log an idea or thought\u2026')}"
              data-add-idea-enter="${s.id}" />
            <button data-add-idea="${s.id}">${t('idea.add', 'Add')}</button>
          </div>
        </div>
        <div class="stage-ftr">
          <div class="status-btns">
            <span class="spill ${stageBadgeCls}" style="pointer-events:none" title="Auto-derived from blockers and sub-items">${stageBadgeLbl}</span>
          </div>
          <button class="btn-ghost" style="color:var(--text-3);font-size:12px" data-del-stage="${s.id}">${t('stage.delete', 'Delete stage')}</button>
        </div>
      </div>`
        : '';

      return `<div class="stage-card" data-draggable="stage|${s.id}" draggable="true">
      <div class="stage-hdr" data-toggle-stage="${s.id}">
        <span class="drag-handle" title="${t('dnd.drag', 'Drag to reorder')}">⠿</span>
        <span class="stage-num" style="font-size:11px;font-weight:700;color:var(--text-3);min-width:18px">${idx + 1}</span>
        <span class="stage-name" data-edit-text="${s.id}||" style="flex:1;font-size:14px;font-weight:500">${esc(s.name)}</span>
        ${_tsInline(s)}
        ${noteHtml}
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
    const toggleNoteEl = ev.target.closest('[data-toggle-note]');
    if (toggleNoteEl) {
      const parts = toggleNoteEl.dataset.toggleNote.split('|');
      const sid = parts[0], bqid = parts[1], subid = parts[2], typeAttr = parts[3];
      toggleNote(sid, bqid || null, subid || null, typeAttr === 'idea');
      return;
    }
    const noteSaveEl = ev.target.closest('[data-note-save]');
    if (noteSaveEl) {
      const parts = noteSaveEl.dataset.noteSave.split('|');
      const sid = parts[0], bqid = parts[1], subid = parts[2], typeAttr = parts[3] || 'stage';
      saveNote(sid, bqid || null, subid || null, typeAttr);
      return;
    }
    const noteCancelEl = ev.target.closest('[data-note-cancel]');
    if (noteCancelEl) {
      cancelNote(noteCancelEl.dataset.noteCancel);
      return;
    }
  };

  el.ondblclick = (ev) => {
    const editTextEl = ev.target.closest('[data-edit-text]');
    if (editTextEl) {
      const [sid, bqid, subid] = editTextEl.dataset.editText.split('|');
      startEdit(editTextEl, sid, bqid || null, subid || null);
      return;
    }
  };
}

document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && _editCtx) {
    cancelEdit();
    ev.preventDefault();
    return;
  }
  if (ev.key === 'Enter' && _editCtx && !ev.shiftKey) {
    saveEdit();
    ev.preventDefault();
    return;
  }
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

document.addEventListener('dragstart', handleDragStart);
document.addEventListener('dragover', handleDragOver);
document.addEventListener('dragend', handleDragEnd);
document.addEventListener('drop', handleDrop);

export function renderAll() {
  renderGoal();
  renderStages();
}
