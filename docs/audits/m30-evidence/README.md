> **HISTORICAL MISSION RECORD (Mission 30 evidence).** This file is preserved unedited as the evidence it produced. Its counts, hashes and verdicts describe the tree at that time and are superseded by the Mission 33 re-adjudication — see [M33_SEMANTIC_AUDIT.md](../../../M33_SEMANTIC_AUDIT.md) and [M33_RELEASE_CERTIFICATION.md](../../../M33_RELEASE_CERTIFICATION.md).

# M30 reproducible evidence — incomplete semantic audit

The primary reports are at repository root: M30_SEMANTIC_AUDIT.md, M30_DOMAIN_MATRIX.md, M30_ROOT_CAUSES.md and M30_RELEASE_CERTIFICATION.md. The verdict is NOT RELEASE-CERTIFIABLE — EVIDENCE INCOMPLETE, not successful completion of Mission30.

## What the files prove

- `baseline-gate.txt`: independent execution of recovered M29 content at 964e922 (1687 pass / 3 skip).
- `final-gate-e2eeb35.txt`: exact application/source SHA, clean-tree check, lock/pip/compile/lint/test counts and clean staged installed-wheel smoke (1729 pass / 3 skip / 1732 collected; 236.34s).
- `*-before.txt`: recorded failures before selected repairs. Selections overlap; do not sum them as unique defects.
- `inventory.json`, `inventory-summary.json`: unique baseline ordinals and explicit audit boundaries; 41 reviewed, 40 closed, 2191 unread. G placeholders are not substantive review.
- `fresh-risky-site-inventory.json`, `sweep-comparison.json`: same-pattern scan and multiplicity-preserving comparison; no automatically inherited approvals.
- `fresh-sweep.json`: broader AST candidate scan with a different file/category scope, not a safety classification.
- `fresh-source-manifest.json`: 353 final application/test/config/asset fingerprints, excluding historical/report documentation.
- `final-source-and-controls-check.json`: all 353 fingerprints unchanged; all 24 focused negative-control source hashes match final source after restoration.
- `m29-replay-mutation-controls.json`, `new-controls.json`, associated logs: actual pytest exit 1 and source restoration per control.
- `mutation-wheel.json`: omitted UI package fails focused and installed-wheel verification; pyproject restored.
- `branches.json`, initial Git records, tree/hash/patch verification: content identity and ancestry boundaries, not invented historical commits.
- `ruff-*.json.gz`: diagnostic locations and conservative categories. These are not individual semantic approvals. Root and gate scopes differ.
- `documentation-claim-queue.json`: candidate claims and unverified body text, not completed claim-by-claim review.
- `native-qt.txt`, `real-pdf.txt`: actual environment failures, not successful native GUI or MinerU integrations.
- `input-assets.json`: actual workbook/PDF identity; the PDF was read from the retained unmerged branch, not added again to this branch.
- `push-source.txt`: initial push rejected for missing GitHub App workflows permission.
- `current-ci.json`: latest final-source CI API query failed HTTP 401. Earlier no-run result concerned 9d511cd; do not call final-source CI green or definitely no-run.

## Reproduction constraints

Commands in the source-gate log were actually executed. Source was Linux/Python 3.11.2 with locked dependencies and explicit Qt library stubs; those stubs are not bundled into the application or claimed as native verification. Real Qt requires the platform libraries. Optional real Windows/MinerU/production-DB acceptance requires the actual environments/assets and is not supplied by this archive.

Mutation runners are stored as `.py.txt` so evidence scripts do not enter ordinary Python/lint/application discovery. Python can execute them by filename from the checkout root. Review the hardcoded `/home/user/m30-*`, `.venv` and Qt environment paths first. Each runner mutates one source file at a time and restores it in `finally`; keep a clean source tree, and rerun positive tests afterward. Never commit mutants.

The same-pattern runner needs its output directory and an empty `site-adjudications.json` (`[]`) before invocation; this intentionally avoids inheriting M29 approvals. The ledger runner's approvals are the explicitly written occurrence reviews, not an automated semantic classifier. Its remaining routing/prioritization is triage only.

Reporting commits necessarily follow the tested source commit. The accompanying publication-state artifact records final delivery HEAD/tree, cleanliness, remote failure and patch applicability. A later verification log, if provided separately, does not retroactively change the SHA/timing of `final-gate-e2eeb35.txt`.

## Raw log preservation

Some raw logs contain trailing spaces (including captured Git diffs and pytest traceback formatting). They are stored losslessly as `.txt.gz`, rather than editing the evidence bytes to pass diff whitespace checks. `compressed-logs.json` maps original names to stored names and records original uncompressed SHA-256. References to the original `.txt` names resolve through that map.
