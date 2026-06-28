# Project Navigator — Analysis Report

A behavioral analysis of `project_navigator.html` and a proposed SQLite backend architecture for data persistence.

---

## 1. Application Overview

**Project Navigator** is a single-file, single-page hierarchical planning tool that helps a user break down an "ultimate goal" into ordered stages, each containing blockers/questions and ideas. The interface is deliberately minimal (Notion-inspired, neutral palette) and is designed as a **focus tool**, not a full project-management suite.

### Tech Stack
- **Frontend**: Vanilla HTML + CSS + JavaScript (no framework, no build step)
- **Storage**: `localStorage` only (key: `pnav5`)
- **No network calls**, no external libraries

---

## 2. Data Model

The entire app state lives in one in-memory object `S`:

```js
S = {
  goal: string,
  stages: [
    {
      id: string,
      name: string,
      status: 'todo' | 'active' | 'blocked' | 'done',
      blockers: [
        {
          id: string,
          text: string,
          status: 'todo' | 'active' | 'blocked' | 'done' | 'park' | 'review' | 'nice' | 'solve',
          deep: boolean,                 // "going too deep" flag
          items: [                       // sub-items
            { id, text, status, deep }
          ]
        }
      ],
      ideas: [
        { id, text }
      ]
    }
  ]
}
```

### Entity Hierarchy
```
Goal (1)
 └── Stage (1..N, ordered)
      ├── Blockers/Questions (0..N)
      │    └── Sub-items (0..N)
      └── Ideas (0..N)
```

### ID Generation
`uid()` returns `Date.now().toString(36) + Math.random().toString(36).slice(2,5)` — a 10–12 character base36 string, unique enough for client-side use but not cryptographically secure.

---

## 3. Feature Behavior

### 3.1 Goal Management
- **Display mode**: a clickable bar with placeholder text `"Click to set your north star…"` until set.
- **Edit mode**: clicking the bar reveals a `<textarea>` + Save/Cancel buttons.
- **Persistence**: save trims whitespace, writes `S.goal`, persists to localStorage, re-renders.

### 3.2 Stages
| Action | Trigger |
|--------|---------|
| Add | "+ Add stage" toolbar button → inline input card → Enter/Add |
| Expand/Collapse | Click stage header (chevron rotates) |
| Set status | Footer pills: `To do / Active / Blocked / Done` |
| Delete | "Delete stage" button (confirm dialog) |

**Header badges** (always visible, even when collapsed):
- `⊘ N` — blocker count (red badge)
- `⚑ N` — "too deep" count (amber badge)
- `✦ N` — idea count (purple badge)
- `● ○ ✓ ⊘` — current stage status pill

### 3.3 Blockers & Questions
- Each blocker is a collapsible row with text + status pill + delete button.
- Expanding reveals sub-items and an "Add sub-item" input.
- **"Too deep" mode**: a special state triggered from the portal menu (`⚑ Going too deep?`). When active:
  - Amber border + background highlight on the row
  - Status switches to `park` automatically
  - The status pill offers a different palette (Park / Review / Nice to have / To Solve)
  - "To Solve → normal" demotes the item back to `todo` and clears the `deep` flag
  - "↩ Back to normal" clears `deep` and resets status to `todo`

### 3.4 Ideas
- Flat list per stage, no status, no nesting — purely a text log.

### 3.5 Portal Dropdown
A **single shared** dropdown element (`#portalMenu`) positioned at the body level with `z-index: 9999`. Its position is computed dynamically from the triggering button's `getBoundingClientRect()`. It closes on outside-click (delegated `document` listener).

This pattern is used for every status pill (stage, blocker, sub-item) to keep the DOM lightweight.

### 3.6 Persistence
- Every mutation: modify `S` → `persist()` → `renderStages()`.
- `persist()` = `localStorage.setItem('pnav5', JSON.stringify(S))`.
- `load()` runs on page init, populates `S`, then renders.
- No conflict resolution, no undo, no versioning.

---

## 4. Render Flow

```
User action
   │
   ▼
Mutate S (in-memory)
   │
   ▼
persist() → localStorage
   │
   ▼
renderStages()  ← re-renders entire stage list
                       (also clears/restores openStages / openBQ maps)
```

The full re-render strategy is simple but loses transient UI state (focus, caret position) — mitigated by rebuilding input elements after each render.

---

## 5. Identified Limitations

| Limitation | Impact |
|------------|--------|
| Single-device only (localStorage) | No sync, no backup |
| No multi-user support | Personal use only |
| No history / undo | Mistakes are permanent |
| Full re-render on every change | Loses focus/caret mid-typing |
| IDs collide on rapid creation | `Date.now()` resolution is millisecond |
| No data validation on load | Corrupted JSON could break the app |

---

## 6. Backend Plan — SQLite Persistence

### 6.1 Tech Stack
- **Language**: Python
- **Framework**: Flask (minimal, single-file friendly)
- **DB**: SQLite (`project_navigator.db`)
- **API**: REST/JSON

### 6.2 Database Schema

```sql
-- Single-row goal table (id constrained to 1)
CREATE TABLE goal (
    id    INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    text  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE stage (
    id       TEXT PRIMARY KEY,                       -- matches uid() format
    name     TEXT NOT NULL,
    status   TEXT NOT NULL DEFAULT 'todo'
              CHECK (status IN ('todo','active','blocked','done')),
    position INTEGER NOT NULL DEFAULT 0,             -- display order
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE blocker (
    id        TEXT PRIMARY KEY,
    stage_id  TEXT NOT NULL REFERENCES stage(id) ON DELETE CASCADE,
    text      TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'todo',
    deep      INTEGER NOT NULL DEFAULT 0,
    position  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE sub_item (
    id         TEXT PRIMARY KEY,
    blocker_id TEXT NOT NULL REFERENCES blocker(id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'todo',
    deep       INTEGER NOT NULL DEFAULT 0,
    position   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE idea (
    id       TEXT PRIMARY KEY,
    stage_id TEXT NOT NULL REFERENCES stage(id) ON DELETE CASCADE,
    text     TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);

-- Indexes for cascade lookups
CREATE INDEX idx_blocker_stage   ON blocker(stage_id);
CREATE INDEX idx_subitem_blocker ON sub_item(blocker_id);
CREATE INDEX idx_idea_stage      ON idea(stage_id);
```

### 6.3 API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET`    | `/api/goal` | Fetch goal text |
| `PUT`    | `/api/goal` | Update goal text |
| `GET`    | `/api/stages` | Full snapshot (stages + blockers + items + ideas) |
| `POST`   | `/api/stages` | Create a stage |
| `PATCH`  | `/api/stages/<id>` | Update stage name/status |
| `DELETE` | `/api/stages/<id>` | Delete stage (cascade) |
| `POST`   | `/api/stages/<id>/blockers` | Add blocker |
| `PATCH`  | `/api/blockers/<id>` | Update blocker (incl. `deep`) |
| `DELETE` | `/api/blockers/<id>` | Delete blocker |
| `POST`   | `/api/blockers/<id>/items` | Add sub-item |
| `PATCH`  | `/api/subitems/<id>` | Update sub-item |
| `DELETE` | `/api/subitems/<id>` | Delete sub-item |
| `POST`   | `/api/stages/<id>/ideas` | Add idea |
| `DELETE` | `/api/ideas/<id>` | Delete idea |

### 6.4 Component Layout

```
project_navigator/
├── project_navigator.html      # existing frontend
├── ANALYSIS.md                 # this file
└── backend/
    ├── app.py                  # Flask routes + app factory
    ├── database.py             # SQLite connection + schema init
    ├── models.py               # Data-access layer (CRUD helpers)
    ├── serializers.py          # JSON ↔ DB row conversion
    └── migrations/
        └── 001_init.sql        # initial schema
```

### 6.5 Frontend Integration
- Replace `localStorage.setItem` / `getItem` calls with `fetch('/api/...')`.
- Keep the existing `S` in-memory object as the cache; `persist()` becomes an async write-through.
- `load()` becomes an async hydration from `GET /api/stages`.
- Status values must be validated server-side (rejected if not in allowed set).
- IDs remain client-generated (`uid()`) for offline-first semantics.

### 6.6 Open Decisions
- **Authentication**: skip for now (single-user local tool); add a simple token later if exposing to network.
- **Optimistic vs pessimistic writes**: recommend optimistic for UX parity with current app.
- **Migration strategy**: lightweight SQL files numbered sequentially, applied at boot.