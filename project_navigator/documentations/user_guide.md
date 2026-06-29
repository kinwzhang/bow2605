# User Guide

How to use Project Navigator day-to-day.

## Sign in

1. Open `http://localhost:5000/` — you'll land on the login page.
2. Enter your username and password (or use the demo account: `demo` / `demo1234`).
3. To create a new account, click **Create an account** below the form.

Sessions last 30 days; if you sign out manually you stay signed out until you
sign in again.

## Layout

```
┌────────────────────────────────────────────────────────────┐
│ Project Navigator  ▸  Bow2605              demo ▾          │ ← branded header
├──────────┬─────────────────────────────────────────────────┤
│ Projects │ Ultimate goal                                   │
│          │ ─ Click to set your north star…                 │
│ + New    │                                                  │
│          │ Stages                              + Add stage │
│ • Bow2605│ ┌──────────────────────────────────────────────┐ │
│ • Side   │ │ 1 ▾ Plan        ⊘2  ⚑1  ●Active            │ │
│ • Other  │ │    Blockers & questions …                   │ │
│          │ │    Ideas & thinking …                       │ │
│ [collapse]│ └──────────────────────────────────────────────┘ │
└──────────┴─────────────────────────────────────────────────┘
```

- **Header**: product name on the left, current project name next to it, your
  username on the right with a dropdown to switch users.
- **Sidebar** (left): list of your projects. Click to switch; hover for rename
  (`✎`) and delete (`×`). Collapse with `‹` in the sidebar header; the
  collapse state is remembered in your browser.
- **Main**: the goal bar, stages toolbar, and stage list — same as the legacy
  app, but backed by the server now.

## Stages

- **Add** a stage with `+ Add stage`; type the name, press Enter or click Add.
- **Rename** / delete by expanding the stage and using the footer buttons.
- **Status is auto-derived** from the stage's blockers and sub-items (see
  the rollup rule below). It is shown as a read-only badge on the stage
  header and footer.
- **Expand / collapse** a stage by clicking its header (the `▾` rotates).
- **Reorder**: not yet supported via drag; editing is by delete + re-create.

### Stage status rollup rule

The stage status is recomputed every time a blocker or sub-item changes.
It's a rollup of all blocker + sub-item statuses, with **priority order**
(first match wins):

`todo` > `active` > `blocked` > `review` > `park` > (all `done`) > `nice`

| Priority | Condition                                          | Stage status |
|---------:|----------------------------------------------------|--------------|
| 1 (top)  | Any blocker or sub-item is `todo`                  | `todo`       |
| 2        | Any item is `active`                                | `active`     |
| 3        | Any item is `blocked`                              | `blocked`    |
| 4        | Any item is `review`                               | `review`     |
| 5        | Any item is `park` (display: "Parked")             | `park`       |
| 6        | All blockers and sub-items are `done`              | `done`       |
| 7        | Any item is `nice` (display: "Nice to have")       | `nice`       |
| (fallback) | All items are `solve` (neutral)                  | `active`     |

`todo` wins because if any blocker or sub-item hasn't started, the stage
as a whole is still in planning — even if other items are deep into
`active` or `done`.

Items in `solve` are **neutral** — the deep-coupling rule converts them
to `todo` on patch, so an "all solve" state in the DB becomes "all todo"
in practice. The fallback only triggers for synthetic states the
backend can't currently produce.

You cannot set stage status manually once any blocker or sub-item exists;
the API will reject the change with `400 validation`. Empty stages can be
renamed but their status remains whatever they were created with.

## Blockers & questions

Each stage has a *Blockers & questions* subsection. Click `+` on a blocker to
expand it (sub-items + add input).

- **Set status** via the colored pill (click to open the dropdown).
  - **Blocker with no sub-items** shows: `To Do`, `Active`, `Blocked`,
    `Done` + a separator + `⚑ Going too deep?`. The status is
    user-controlled.
  - **Blocker with sub-items** shows the auto-derived status as a
    read-only badge (the same priority rule as the stage — see below).
    Change sub-item statuses to change the blocker.
- **"Too deep" mode**: click the pill and choose `⚑ Going too deep?` to switch
  to a deep status palette (`Park`, `Review`, `Nice to have`, `To Solve →normal`).
  The row gets an amber border + background. Available only on blockers
  without sub-items.
- **Back to normal**: from a deep pill, choose `↩ Back to normal`.
- **Solve**: from a deep pill, choose `To Solve →normal` — this both marks
  the blocker as solved (`status='todo'`) and removes the deep flag.

### Blocker status rollup rule

A blocker with sub-items is auto-derived using the same priority order as
the stage (first-match-wins):

`todo` > `active` > `blocked` > `review` > `park` > (all `done`) > `nice`

| Priority | Condition                          | Blocker status |
|---------:|------------------------------------|----------------|
| 1 (top)  | Any sub-item is `todo`             | `todo`         |
| 2        | Any sub-item is `active`           | `active`       |
| 3        | Any sub-item is `blocked`          | `blocked`      |
| 4        | Any sub-item is `review`           | `review`       |
| 5        | Any sub-item is `park`             | `park`         |
| 6        | All sub-items are `done`           | `done`         |
| 7        | Any sub-item is `nice`             | `nice`         |
| (fallback) | All sub-items are `solve`      | `active`       |

Sub-items without their own children are user-controlled via the
dropdown. Without sub-items, the blocker status is also user-controlled.

## Ideas

Each stage also has an *Ideas & thinking* subsection. It's a flat text log —
no status, no nesting. Just append thoughts.

## Projects

- **New project**: click `+ New project` in the sidebar; type a name, press
  Enter or click Create.
- **Rename**: hover the project row in the sidebar, click `✎`, type the new
  name.
- **Delete**: hover the project row, click `×`, confirm. This cascades through
  every stage, blocker, sub-item, and idea in that project.
- **Switch**: click any other project in the sidebar to make it the active one.
  The active project is remembered across reloads.

## Switching users

Click your username in the header → **Switch user…**. You'll be logged out and
returned to the sign-in page. (User accounts don't have a switch-without-logout
flow in this prototype; see `plan_and_design/04_roadmap.md` Phase 7.)

## Data persistence

Every mutation is written through to the server immediately. The server validates
status values; invalid statuses are rejected and the local UI rolls back on the
next snapshot reload.

There is no undo in this prototype. Mistakes are permanent.

## Keyboard

- **Enter** in any input field submits (e.g. creates a stage / blocker / idea).
- **Escape** in the new-stage input cancels.
- **Click** outside any open portal menu to close it.