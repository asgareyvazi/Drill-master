# M329, D90, D91 and M352: evidence notes

All data is SYNTHETIC. The label is unchanged: **UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED**.

## M329: architecture comparison as a table and an export (roadmap P4); D90

**Commit `1d391fd`.**

- **Matching** (`core/architecture_diff.py`):
  - Identical duplicates are matched first.
  - The remaining components of the same kind and name are matched in stored order and flagged `ambiguous`. The table says so; it never claims a certain pairing.
- **Table** (`tabs/well_architecture_panel.py`): columns are Status, Kind, Name, Occurrence, Field, Older, Newer and Ambiguous.
- **Export** (`export_comparison()`, CSV):
  - Carries both revision SHA-256s, so a reader can tie the file to the two frozen revisions.
  - Any cell starting with `=`, `+`, `-` or `@` is prefixed with `'`, which neutralises formula injection.
- **D90:** `_binding_label` showed a changed reference binding as "unknown → unknown". It now names the reference set, version and item of each side.
- **Tests:** `tests/test_m311_architecture_diff.py` and `tests/test_m329_architecture_diff_table_export.py`. The AD-* mutants, including `AD-identical-ignores-changes` (a survivor of run 1, now killed), are in `m327_mutation_catalogue.md`.
- **Limitation:** a comparison of stored component records. It does not judge whether either architecture is correct.

## D91: Windows-only test tool encoding defect

**Commit `b18706d`.**

- **Cause:** `tools/quality/ux_startup_m115.py` printed its JSON summary, which contains non-ASCII characters, to `sys.stdout`. On a Windows runner a piped stdout uses the ANSI code page, so the tool raised `UnicodeEncodeError` after writing its JSON file. This made three `test_m115_ux_startup` tests fail on every Windows leg of the PySide evaluation, including the 6.8.1.1 baseline. It was therefore a pre-existing defect, not a candidate regression.
- **Fix:** the tool writes UTF-8 bytes through `sys.stdout.buffer`.
- **Evidence:** PySide evaluation runs `45024680781` and `45115378469`. The UI subset is green on all Windows legs.
- **Scope:** a test tool only. The release bundle does not contain it.

## M352: large-font pre-push guard (A-9, roadmap R6)

**Commit `3293c3d`.**

- **Tool:** `tools/quality/prepush_guard_m352.py`.

  | Mode | What it does |
  |---|---|
  | `--check` | Measures every panel |
  | `--changed` | Runs the repo-wide guard tests (`test_model_registry`, the release-boundary imports and m112), plus the panels whose sources differ from upstream (`--base` to override) |
  | `--write` | Records the budgets |

- **Hook:** `tools/hooks/pre-push`. It is enabled per clone with `git config core.hooksPath tools/hooks` and is opt-in; a hook cannot be forced on a clone.
- **Method:**
  1. Scale the application font by 1.8.
  2. Build each panel on a throw-away SYNTHETIC database.
  3. `show()` it and process events.
  4. Read `minimumSizeHint().width()`.

  **Unshown size hints are stale.** With the M320 E header-row regression in place, the unshown panel still read 1275 px (no change visible) and the shown panel read 1487 px. The `3293c3d` commit message quotes "995 px unshown"; that figure is wrong, and 1275 px is the measured value. The M334 width test now measures a shown panel for the same reason.
- **Budgets** (`docs/engineering/large_font_budget_m352.json`, fingerprint `Sans Serif|16.2pt|641px`):

  | Panel | Budget at 1.8× | Hard limit |
  |---|---|---|
  | knowledge_assistant | 1275 px | 1300 px (Windows M49) |
  | well_architecture_panel | 1333 px | — |
  | calculation_history | 2076 px | — |

  - The M334 record-navigation row is visible in the knowledge panel and the panel still measures 1275 px with long file names.
- **Proof that it catches A-9:** `tests/test_m352_prepush_guard.py` puts the two M320 E buttons back into the header row. The panel then measures 1487 px, and the guard reports both "exceeds its budget" and "Windows limit 1300".
- **Limitation:** a ratchet on Linux fonts. It detects widening; it does not prove the Windows width, which only the Windows CI job measures. Budgets compare only on the same font fingerprint, otherwise the guard prints NOT COMPARABLE (exit 0, or 2 with `M352_REQUIRE_COMPARABLE=1`).
