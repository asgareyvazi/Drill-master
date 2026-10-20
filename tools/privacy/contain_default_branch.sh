#!/usr/bin/env bash
# Narrow privacy containment for the default branch `drill-Master` (OWNER RUNS IT).
#
# Builds ONE commit on top of the exact default-branch tip that:
#   * deletes the two real daily drilling reports at the repository root;
#   * replaces 10 tracked files by their already-redacted versions from the M43
#     working branch (each of them was changed there ONLY by the privacy commits
#     7543f2f / 61f2b71 — checked below, the script aborts otherwise);
#   * applies only the privacy hunks of 7543f2f to core/canonical_mapper.py, the
#     eight tests that read the workbook (pointed at the synthetic fixture) and
#     .gitignore;
#   * adds the synthetic fixture and the redaction notice.
# Nothing else from the working branch is carried over.  The script contains no
# protected value: redactions come from repository objects at run time.
#
# It does NOT remove anything from Git history (see HISTORY_PURGE_PLAN.md).
# It never pushes.  Afterwards, the owner reviews and pushes, e.g.
#   git push origin HEAD:refs/heads/privacy/default-branch-containment
# and opens a pull request into drill-Master.
#
# Usage (in a clean clone):
#   git fetch origin drill-Master arena/72010272-drill-master
#   git checkout --detach origin/drill-Master
#   bash <path to this script>            # from the working branch checkout
set -euo pipefail

BASE=${BASE:-e3fa42a3257e981d9bdf9d012c97919e3352a53a}          # drill-Master tip audited 2026-10-20
SRC=${SRC:-aee2cc866fdbee0f80943f465169efd8006c2db6}           # working-branch commit holding the redacted blobs
PRIV=7543f2fcc85bc5da686898d71450f9e02440d3a9                  # privacy commit 1 (tree + tests)
PRIV2=61f2b719bf6ced931550f6b84a3a130f3e8fd07c                 # privacy commit 2 (equipment serials)
MERGE_BASE=51c0b85f79
EXPECTED_TREE=${EXPECTED_TREE:-7f3c9ca4f68d24724123de5bcd1109aee671c3c2}  # tree verified in M43 continuation (0 findings, 0 protected blobs, 245 passed)

die() { echo "containment: $*" >&2; exit 1; }

[ "$(git rev-parse HEAD)" = "$BASE" ] || die "HEAD is not the audited drill-Master tip $BASE (re-audit first)"
[ -z "$(git status --porcelain)" ] || die "working tree is not clean"
git cat-file -e "$SRC^{commit}" 2>/dev/null || die "source commit $SRC not available (fetch the working branch)"

REAL_DDRS=(
  "08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx"
  "12 - DDR OEOC-201 AZNS-166 2025-Nov-07 (1404.08.16).pdf"
)
REDACTED=(
  docs/REVIEW_AUDIT_2026-09.md
  docs/review_audit_2026-09.json
  docs/audits/2026-09-08-ddr/evidence/golden-a.json
  docs/audits/2026-09-08-ddr/evidence/followup/golden-a-import.json
  docs/audits/2026-09-08-ddr/evidence/followup/golden-a-lifecycle.json
  docs/audits/2026-09-08-ddr/evidence/real-user-acceptance/production.json
  docs/audits/2026-09-08-ddr/evidence/real-user-acceptance/review-classification.csv
  docs/audits/2026-09-08-ddr/review-classification-65.csv
  templates/OEOC_DDR_full_extraction.json
  tools/mineru_integration.py
)
HUNKS=(
  core/canonical_mapper.py
  .gitignore
  tests/test_ddr_followup_lifecycle.py
  tests/test_ddr_regression.py
  tests/test_excel_intelligence_regressions.py
  tests/test_golden_ddr.py
  tests/test_real_oeoc_golden.py
  tests/test_ddr_forensic_regressions.py
  tests/test_review_contract_certification.py
)
ADDED=(
  tests/fixtures/synthetic_ddr_golden_a.xlsx
  docs/audits/2026-09-08-ddr/REDACTION_NOTICE.md
)

# Safety: a file may be copied whole only if the default branch still has the
# merge-base version and the working branch changed it only in the privacy commits.
for f in "${REDACTED[@]}"; do
  [ "$(git rev-parse "HEAD:$f")" = "$(git rev-parse "$MERGE_BASE:$f")" ] || die "$f changed on drill-Master since the merge base"
  others=$(git log --format=%H "$MERGE_BASE..$SRC" -- "$f" | grep -v -e "^$PRIV$" -e "^$PRIV2$" || true)
  [ -z "$others" ] || die "$f was changed by non-privacy commits on the working branch: $others"
done

git rm -q -- "${REAL_DDRS[@]}"
git checkout "$SRC" -- "${REDACTED[@]}" "${ADDED[@]}"
git show "$PRIV" -- "${HUNKS[@]}" | git apply --index
# (tests/test_production_import_guarantees.py does not read the workbook on
# drill-Master, so 7543f2f's change to it is not needed there.)
# 7543f2f's ignore rules miss names written as "12 - DDR ..."; cover both forms.
printf '%s\n' '[0-9]*DDR*.xls*' '[0-9]*DDR*.pdf' >> .gitignore
git add .gitignore

git -c user.name="${GIT_AUTHOR_NAME:-$(git config user.name)}" commit -q -m "fix(privacy): remove real DDR files and redact copies (containment)

Narrow current-tree containment for the default branch: deletes the two real
daily drilling reports at the repository root, replaces ten files by their
already-redacted versions and redacts one more in place (coordinates, equipment
serials, a personal profile path, the full workbook dump), points the seven
workbook-reading tests at the synthetic fixture, and ignores DDR-named files. Nothing is removed from Git history; see
docs/privacy/HISTORY_PURGE_PLAN.md on the M43 working branch."

tree=$(git rev-parse HEAD^{tree})
echo "containment commit: $(git rev-parse HEAD)"
echo "containment tree:   $tree"
git diff --stat "$BASE" HEAD | tail -1
if [ -n "$EXPECTED_TREE" ] && [ "$tree" != "$EXPECTED_TREE" ]; then
  die "tree differs from the verified tree $EXPECTED_TREE — do not push; investigate"
fi
