# History purge plan — OWNER-GATED, NOT EXECUTED

**Status: prepared, not run.** Rewriting history of a public repository with
nine branches is irreversible for everyone who has cloned it. It requires the
explicit approval of the repository owner. Nothing in this document has been
executed; M43 removed the sensitive content from the **current tree of the M43
working branch only**.

> **Correction (M43 release hardening, 2026-10-20).** The default branch
> `drill-Master` (tip `e3fa42a`, last merged PR #4) was never updated with the
> M43 remediation. Its **current tree still contains the real workbook** (blob
> `b581f873…`) and 11 other protected blobs, so anyone browsing the public
> repository can download it today. See section 0 — that step needs no history
> rewrite and should happen first.
>
> **Correction (M43 continuation, 2026-10-20).** The default branch also holds
> a **second real daily drilling report**, a PDF uploaded directly to
> `drill-Master` by commit `02053eb` (blob `e91e0b68…`, 740,510 bytes). The
> 17-blob inventory below missed it because its token scan cannot read PDF
> text; it is now the 18th protected blob. Its contents were not opened.

## 0. Containment before any rewrite (owner, normal commit)

Bring the remediation onto the default branch with an ordinary, reviewable
commit. This is **not** a history rewrite and removes nothing from history — it
only stops the default branch from serving the files in its current tree. It is
an owner action: the agent session that prepared it may push only its own
working branch, so no containment branch or pull request exists yet.
**Containment is not done until the owner merges it.**

Do **not** merge the whole M43 working branch for this (135+ unrelated
commits). Use the narrow, scripted commit instead:
[`tools/privacy/contain_default_branch.sh`](../../tools/privacy/contain_default_branch.sh).

| Property | Value |
|---|---|
| Base | `drill-Master` tip `e3fa42a3257e981d9bdf9d012c97919e3352a53a` (script refuses any other HEAD) |
| Result tree (reproducible; the commit ID varies with author/time) | `7f3c9ca4f68d24724123de5bcd1109aee671c3c2` (script refuses to finish on any other tree) |
| Diff | 23 files: 2 deleted (both real DDRs), 2 added (synthetic fixture, `REDACTION_NOTICE.md`), 19 modified — 11 redacted data/doc/code files, 7 workbook-reading tests pointed at the fixture, `.gitignore` |
| Privacy check of the result (M43 policy) | 849 files, **0 findings** (before: 131 findings in 13 paths) |
| Protected blobs in the result tree | **0 of 18** (before: 13) |
| The nine DDR/fixture test files on the result | 245 passed, 1 skipped (Windows bundle) — identical to the unmodified tip |

Owner steps:

```bash
git fetch origin drill-Master arena/72010272-drill-master
git worktree add --detach ../dm-containment e3fa42a3257e981d9bdf9d012c97919e3352a53a
cd ../dm-containment
bash ../Drill-master/tools/privacy/contain_default_branch.sh   # prints commit + tree, never pushes
python ../Drill-master/tools/privacy/privacy_check.py --root .  # expect 0 findings
git push origin HEAD:refs/heads/privacy/default-branch-containment
# open a pull request privacy/default-branch-containment -> drill-Master, review, merge
```

After the merge, verify the tree of the new `drill-Master` tip contains none
of the 18 blobs (section 6 loop, run against `git ls-tree -r origin/drill-Master`).
History still holds everything until section 5 is carried out.

## 1. Scope

| Object | Paths | Action | Current-tree state |
|---|---|---|---|
| Real DDR workbook | `08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx` (blob `b581f873fdeda00be03018d8474e596182ee6866`) | delete from all commits | removed (M43) |
| Real DDR PDF (`drill-Master` only) | `12 - DDR OEOC-201 AZNS-166 2025-Nov-07 (1404.08.16).pdf` (blob `e91e0b6899268c37455c93c6132620b012ed6112`; only in commits `02053eb` and `e3fa42a`) | delete from all commits | never on the M43 branch; still on `drill-Master` |
| Full dump of that workbook (shipped package data) | `templates/OEOC_DDR_full_extraction.json` (pre-M43 blob `d385f86b18858e97d443221419b25f5a4e89bbcd` and any earlier versions) | replace protected tokens in every version | de-identified (M43) |
| Coordinates in evidence | `docs/review_audit_2026-09.json`, `docs/REVIEW_AUDIT_2026-09.md`, `docs/audits/2026-09-08-ddr/evidence/golden-a.json`, `…/followup/golden-a-import.json`, `…/real-user-acceptance/production.json`, `…/real-user-acceptance/review-classification.csv`, `docs/audits/2026-09-08-ddr/review-classification-65.csv`, `core/canonical_mapper.py` | replace protected tokens in every version | redacted (M43) |
| Personal profile path | `tools/mineru_integration.py` | replace in every version | replaced (M43) |
| Equipment (bit) serial numbers, as text | `docs/audits/2026-09-08-ddr/evidence/golden-a.json`, `…/followup/golden-a-import.json`, `…/followup/golden-a-lifecycle.json` (`serial no` / `serial_number` fields), and the M43-era `templates/OEOC_DDR_full_extraction.json` (blob `da9e6ecdb31b55448cda438d8bdd548ff3b54a23`, as numbers) | replace protected tokens in every version | redacted / replaced (M43 release hardening) |
| Equipment serial numbers inside a zipped workbook | M43-era `tests/fixtures/synthetic_ddr_golden_a.xlsx` (blob `d6c49cd4834cc252c0232d13bd1f0e8735f61558`, numeric cells `DDR Data!N52:N53`) | substitute the whole blob (section 5 c) — `--replace-text` cannot see inside a zip | replaced by blob `b82c1e6486800b9e5ba761cc37b2dd1ee8fa08e8` (M43 release hardening) |

Branches: all nine (`drill-Master` — the default — and eight `arena/*`
branches). Tags: none. Forks: none at the time of writing (re-check).

### Verified inventory (2026-10-20, full history, read-only)

Measured on a full (unshallowed) fetch of all nine branches plus the four
pull-request refs. Every unique blob was scanned — Office files with their XML
members expanded — for the denylisted identity tokens (by salted digest), the
workbook's coordinate values and the equipment serial numbers. Only counts and
object IDs were recorded; no value was printed.

| Measure | Result |
|---|---|
| Commits reachable from any branch | 454 |
| Unique blobs scanned | 3,778 |
| Blobs with protected content | 17 (listed in section 6) |
| Commits whose tree holds at least one of them | 300 |
| Earliest affected commit | `7589803` (2026-08-29) |
| Branch tips still holding protected blobs | `drill-Master` 12, `arena/01a0ec23` 12, `arena/01a0c945` 12, `arena/01a085e0` 12, `arena/01a0801f` 12, `arena/01a07094` 6, `arena/01a056c5` 2, `arena/01a05747` 2; the M43 working branch 0 after the release-hardening commit |
| Added in the continuation audit | the DDR PDF blob `e91e0b68…` (found by file name; PDF text is not scannable) → **18 protected blobs**; it adds no new commits or branches beyond `drill-Master` |
| Pull-request refs `refs/pull/1-4/head` | add no commits beyond the branches, but #2-#4 point at affected trees and survive a force-push (GitHub Support, section 5) |

### Non-text blobs (continuation audit, 2026-10-20)

The token scan reads text and expanded Office XML only. Every other binary
type in history was checked separately (counts and IDs only):

| Type | Blobs in history | Check | Result |
|---|---|---|---|
| `.xlsx` | 19 | XML members expanded (inventory above) | protected: the real workbook and the M43-era fixture `d6c49cd4…` |
| `.pdf` | 1 | — (text not extractable by the scanner) | it is the real DDR `e91e0b68…`; deleted whole by step (a) |
| `.gz` | 8 (`docs/audits/m30-evidence/`) | decompressed in memory, scanned | 0 protected findings (6 email-rule hits are Python decorators such as `@pytest.mark.parametrize`) |
| `.png` | 2 (`docs/audits/2026-09-08-ddr/evidence/…`) | reviewed visually | no names, serials or absolute coordinates (an empty "insufficient data" plot and a plot of small relative offsets) |

## 2. Required approvals

1. Repository owner: written approval of this plan, the exact token list and
   the timing window.
2. Confirmation that no one else holds work based on the old history (or that
   they will rebase onto the rewritten branches).
3. Approval to contact GitHub Support to purge cached views and pull-request
   refs (GitHub keeps them after a force-push).

## 3. Dry-run inventory (safe, read-only)

```bash
git clone --mirror https://github.com/asgareyvazi/Drill-master.git dm-audit.git
cd dm-audit.git
git log --all --format='%h %ad %s' --date=short -- '08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx'
git log --all --format='%h %ad %s' --date=short -- '12 - DDR OEOC-201 AZNS-166 2025-Nov-07 (1404.08.16).pdf'   # expect 02053eb (and the e3fa42a merge)
git rev-list --objects --all | grep -F '08-DDR'                       # every blob of the workbook
git log --all --format=%h -- templates/OEOC_DDR_full_extraction.json | wc -l
# token presence across all history, counting only (the token file is private):
while IFS= read -r t; do printf '%s… ' "${t:0:2}"; git grep -c -F -e "$t" $(git rev-list --all) -- 2>/dev/null | wc -l; done < /secure/private-tokens.txt
```

## 4. Backup and recovery

```bash
git clone --mirror https://github.com/asgareyvazi/Drill-master.git drill-master-BACKUP-$(date +%Y%m%d).git
tar -czf drill-master-BACKUP.tgz drill-master-BACKUP-*.git
# store the archive encrypted, offline, access-restricted: it contains the sensitive data
```

Recovery, if the rewrite must be abandoned before anyone fetches it: push the
backup mirror back (`git push --mirror` from the backup). After others have
fetched the rewritten history, recovery means re-coordinating every clone.

## 5. Procedure (after approval)

Tool: [`git-filter-repo`](https://github.com/newren/git-filter-repo) (reviewed
version pinned by the operator).

```bash
python -m pip install git-filter-repo==2.47.0
git clone --mirror https://github.com/asgareyvazi/Drill-master.git dm-rewrite.git
cd dm-rewrite.git

# One invocation does all three operations; git-filter-repo expects a fresh
# clone and refuses a second pass, so do not split it (and never add --force
# to get past that check — start again from a new mirror instead).
#
# (a) --invert-paths/--path: delete both real DDR files from every commit
# (b) --replace-text: replace protected tokens in every text blob.
#     /secure/replacements.txt is PRIVATE, one rule per line, e.g.
#       literal:<protected token>==>[REDACTED]
#       regex:\b<digits>\b==>[REDACTED:serial]        (numeric tokens: serials, coordinates)
#     Cover every printed form of each numeric token found in the dry run
#     (integer, "<n>.0", thousands separators) — see section 9.
# (c) --blob-callback: --replace-text cannot edit inside a zipped .xlsx, so the
#     M43-era fixture blob is substituted by ID with the sanitized committed one
git cat-file blob b82c1e6486800b9e5ba761cc37b2dd1ee8fa08e8 > /secure/fixture-sanitized.xlsx
git filter-repo \
  --invert-paths \
    --path '08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx' \
    --path '12 - DDR OEOC-201 AZNS-166 2025-Nov-07 (1404.08.16).pdf' \
  --replace-text /secure/replacements.txt \
  --blob-callback '
if blob.original_id == b"d6c49cd4834cc252c0232d13bd1f0e8735f61558":
    blob.data = open("/secure/fixture-sanitized.xlsx", "rb").read()
'
```

Then verify (section 6) **before** pushing, and only then:

```bash
git push --force --mirror origin        # owner only, during the agreed window
```

Afterwards:

1. Ask GitHub Support to remove cached views and dereferenced objects for the
   repository (see GitHub Docs, "Removing sensitive data from a repository").
2. Ask every collaborator to re-clone; old clones must not be pushed back.
3. Re-run the CI gates on the new tip of `drill-Master` and of the active
   branch; commit SHAs change, so every SHA-pinned record in `docs/audits/` will
   refer to the pre-rewrite history (record that in a dated note; do not edit
   the records).

## 6. Verification after the rewrite (before pushing)

```bash
git log --all --oneline -- '08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx'   # must print nothing
git log --all --oneline -- '12 - DDR OEOC-201 AZNS-166 2025-Nov-07 (1404.08.16).pdf'   # must print nothing
git cat-file -e b581f873fdeda00be03018d8474e596182ee6866 2>/dev/null && echo LEAK || echo ok
git cat-file -e d385f86b18858e97d443221419b25f5a4e89bbcd 2>/dev/null && echo LEAK || echo ok
git count-objects -v && git gc --prune=now --aggressive
while IFS= read -r t; do git grep -q -F -e "$t" $(git rev-list --all) -- && echo "LEAK ${t:0:2}…"; done < /secure/private-tokens.txt
python tools/privacy/privacy_check.py     # on a checkout of each rewritten branch
# none of the 18 protected blobs measured on 2026-10-20 may survive:
for b in 23b89651cc7b280b4fb8a42ca5f86b6bea3f2ea9 2f587b5201084eb534bf6a63fe44f154e85046e4 \
         58fcce3bc40a20a27e803932c515a0041144f35d 6065ca1010f49272b8b41d6378e105e71705c504 \
         698f5df9af6e4b6b5d8ecad4e7491e707265b52c 70af909853a72b99634922ff45d97f8f6e715560 \
         7af4e0263a5ebd187cd3fb251d23ba8c6c4c3215 8126acb5ae865655bde58fa5fa00096178087d58 \
         8d1cf96321c4579b07448bec925f0fe0504da990 a8171976f21db97441546819d6c19cfaacc38e1c \
         b581f873fdeda00be03018d8474e596182ee6866 d385f86b18858e97d443221419b25f5a4e89bbcd \
         d6c49cd4834cc252c0232d13bd1f0e8735f61558 d841758ad753c0a69f44b0fdaf86b92bfafac709 \
         da9e6ecdb31b55448cda438d8bdd548ff3b54a23 fc284c769b57828ea433ccfa2026d36b4bfd4e13 \
         ffcfb7c2520770dbdf476960dd36afcc6235cb33 e91e0b6899268c37455c93c6132620b012ed6112; do
  git cat-file -e "$b" 2>/dev/null && echo "LEAK $b"
done
# git grep does not look inside zipped Office files: run the privacy check's
# scanner over every historical .xlsx blob as well (it expands the XML members)
```

After pushing, fetch a fresh clone and repeat the checks; ask GitHub Support to
confirm the purge of cached objects.

## 7. Credentials

No credential, token or private key was found in the tracked tree (pattern
scan, M43). If one is ever found — in the tree or in history — **rotate it
first** (revoke at the issuer, issue a new one, update the secret store, verify
the old one is rejected) and only then clean history. A purge does not make an
exposed credential safe; rotation does.

## 8. Risks

- Every commit SHA changes: release evidence, CI run records and audit reports
  that cite SHAs will refer to history that no longer exists on the remote.
- Open pull requests and Arena session branches must be rebased or recreated.
- Copies outside GitHub (clones, CI caches, artifact uploads, search engines)
  are not reached by a rewrite.

## 9. Plan audit and operator checklist (M43 continuation, 2026-10-20)

Audit of this plan against the measured history (read-only; nothing executed):

| Check | Finding | Change made |
|---|---|---|
| Every real DDR file is deleted | the PDF on `drill-Master` was missing | added to sections 1, 3, 5 (a) and 6 |
| Every protected blob is checked after the rewrite | 17 of 18 were listed | PDF blob added to the section 6 loop |
| Binary blobs the token scan cannot read | `.pdf`, `.gz`, `.png` were unchecked | audited (table under section 1) |
| Numeric cells inside zipped workbooks | `--replace-text` cannot reach them | the only affected `.xlsx` other than the deleted workbook (`d6c49cd4…`) is substituted by blob ID |
| Multi-pass filter-repo | a second pass on the same clone is refused | procedure is one invocation |
| Serial / coordinate forms | numeric tokens can be printed as integers, as `<n>.0` floats, or with thousands separators | operator must count each form in the dry run and cover each with a rule (below) |

Operator checklist (owner, in this order):

1. [ ] Containment (section 0) merged; `drill-Master` tree holds 0 of the 18 blobs.
2. [ ] Written approvals (section 2), including GitHub Support contact.
3. [ ] Encrypted offline backup mirror made and test-restored (section 4).
4. [ ] Private token list and `/secure/replacements.txt` prepared off-repository;
       for every numeric token, the dry run lists the count of each printed form
       and every form with a non-zero count has a rule.
5. [ ] Dry run (section 3) counts recorded (counts only).
6. [ ] Single filter-repo invocation (section 5) on a fresh mirror.
7. [ ] Section 6 verification: no path, no blob of the 18, no token; privacy
       check on every rewritten branch; scanner run over every historical
       `.xlsx` blob.
8. [ ] Force-push in the agreed window (owner only); GitHub Support asked to
       drop cached views and the `refs/pull/2-4/head` objects.
9. [ ] Fresh clone re-verified; collaborators re-clone; CI re-run on the new
       tips; dated note that pre-rewrite SHAs in `docs/audits/` no longer resolve.

