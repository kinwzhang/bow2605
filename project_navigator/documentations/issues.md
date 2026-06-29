# Issues & Fix Log

A running log of bugs found in the field and how they were resolved. Each
entry links to the original issue report and the commit that fixed it.

| Date       | Issue                                          | Fixed in       |
|------------|------------------------------------------------|----------------|
| 2026-06-29 | [CSRF 403, layout width, status dropdown, stage status dropdown, auto-derive stage status, new derivation priority, todo is highest priority](issues/20260629.md) | `fb36569`, `88ffcec`, `975b667`, `aa26da0`, `1c5d1cd`, `7f73ec9`, `80af10b`, `fd313b3` |

## How to add a new entry

1. Save the issue report in `requirements/YYYYMMDD_*` (matches the convention
   used by `requirements/20260628_new_feature.md`).
2. Append a row to the table above.
3. Write `documentations/issues/YYYYMMDD.md` with: symptom, root cause,
   fix, regression test, and verification.
4. Reference the commit hash once the fix lands.