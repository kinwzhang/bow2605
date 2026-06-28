"""Static checks for the frontend JS modules.

These don't require a browser — they parse the import lists of each module
and verify that every helper they use (apiGet, apiPost, etc.) is actually
imported. Catches the round-2 20260629 issue where `apiPut` was used in
projects.js but not in its import list.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND_JS = Path(__file__).resolve().parent.parent / "frontend" / "js"

# Helper functions exported by api.js.
API_HELPERS = {"apiGet", "apiPost", "apiPatch", "apiPut", "apiDelete"}

# Files that should import from api.js. The grep below checks each one.
USES_API_FILES = ["projects.js", "stages.js", "auth.js"]


def _imports_from(text: str, source: str) -> set[str]:
    """Return the set of named imports from `./source` (or '../source')."""
    # Match: import { a, b, c } from './source.js'  (or '../source.js')
    pattern = re.compile(
        r"import\s*\{([^}]+)\}\s*from\s*['\"]\.{1,2}/" + re.escape(source) + r"['\"]",
        re.MULTILINE,
    )
    found: set[str] = set()
    for match in pattern.finditer(text):
        for name in match.group(1).split(","):
            name = name.strip()
            if name:
                found.add(name)
    return found


def _identifiers_used(text: str) -> set[str]:
    """Return the set of identifiers that look like function calls or references."""
    # Strip string literals and comments first to avoid false positives.
    cleaned = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", "''", text)
    cleaned = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', cleaned)
    cleaned = re.sub(r"`[^`\\]*(?:\\.[^`\\]*)*`", "``", cleaned)
    cleaned = re.sub(r"//[^\n]*", "", cleaned)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
    # Identifier lookalikes — word boundary, then letters/digits/underscore.
    return set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", cleaned))


@pytest.mark.parametrize("filename", USES_API_FILES)
def test_file_only_references_imported_api_helpers(filename: str) -> None:
    """Every apiGet/apiPost/... call in `filename` must come from an import."""
    path = FRONTEND_JS / filename
    assert path.exists(), f"missing frontend file: {path}"
    text = path.read_text(encoding="utf-8")

    imports = _imports_from(text, "api.js")
    used = _identifiers_used(text) & API_HELPERS
    missing = used - imports

    assert not missing, (
        f"{filename} uses api helpers that are not imported from api.js: "
        f"{sorted(missing)}. Add them to the import statement."
    )


def test_api_js_exports_every_helper() -> None:
    """If api.js stops exporting apiPut, every consumer above would break."""
    path = FRONTEND_JS / "api.js"
    text = path.read_text(encoding="utf-8")
    declared = _imports_from(text, "state.js")  # not used, but a sanity parse
    exported = set(re.findall(r"export\s+const\s+(\w+)\s*=", text))
    missing = API_HELPERS - exported
    assert not missing, f"api.js no longer exports: {sorted(missing)}"


def test_no_inline_event_handlers_in_frontend_html() -> None:
    """Inline onclick= handlers were removed in Phase 5; regression guard."""
    index_html = (FRONTEND_JS.parent / "index.html").read_text(encoding="utf-8")
    assert "onclick=" not in index_html, (
        "index.html has inline onclick= — should use data-* + event delegation"
    )


def test_stage_status_is_auto_derived() -> None:
    """Round 4 of 20260629: stage status is auto-derived from blockers/sub-items,
    not user-settable. The footer should show a non-interactive badge; the
    derive + reconcile helpers should exist.
    """
    stages_js = (FRONTEND_JS / "stages.js").read_text(encoding="utf-8")

    # Helpers exist.
    assert "function deriveStageStatus" in stages_js, (
        "stages.js must define deriveStageStatus()"
    )
    assert "function reconcileStageStatus" in stages_js, (
        "stages.js must define reconcileStageStatus()"
    )

    # The legacy manual API is gone.
    assert "data-stage-status" not in stages_js, (
        "stages.js still uses data-stage-status — manual stage status is no longer allowed."
    )
    assert "pillBtn(s, s.id, '', '')" not in stages_js, (
        "stage footer should no longer render a portal pill (status is auto-derived)."
    )

    # reconcileStageStatus must be called after every blocker/sub-item mutation.
    # All six mutation functions should mention reconcileStageStatus.
    for fn in ("addBQ", "delBQ", "addSub", "delSub"):
        # Each function body calls reconcileStageStatus at least once.
        assert f"reconcileStageStatus" in stages_js
    # applyStatus and applyDeep should also reconcile when bqid is set.
    assert "reconcileStageStatus(stage)" in stages_js