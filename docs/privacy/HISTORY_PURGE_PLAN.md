# History purge plan — OWNER-GATED, NOT EXECUTED

**Status: prepared, not run.** Rewriting history of a public repository with
nine branches is irreversible for everyone who has cloned it. It requires the
explicit approval of the repository owner. Nothing in this document has been
executed; M43 removed the sensitive content from the **current tree only**.

## 1. Scope

| Object | Paths | Action | Current-tree state |
|---|---|---|---|
| Real DDR workbook | `08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx` (blob `b581f873fdeda00be03018d8474e596182ee6866`) | delete from all commits | removed (M43) |
| Full dump of that workbook (shipped package data) | `templates/OEOC_DDR_full_extraction.json` (pre-M43 blob `d385f86b18858e97d443221419b25f5a4e89bbcd` and any earlier versions) | replace protected tokens in every version | de-identified (M43) |
| Coordinates in evidence | `docs/review_audit_2026-09.json`, `docs/REVIEW_AUDIT_2026-09.md`, `docs/audits/2026-09-08-ddr/evidence/golden-a.json`, `…/followup/golden-a-import.json`, `…/real-user-acceptance/production.json`, `…/real-user-acceptance/review-classification.csv`, `docs/audits/2026-09-08-ddr/review-classification-65.csv`, `core/canonical_mapper.py` | replace protected tokens in every version | redacted (M43) |
| Personal profile path | `tools/mineru_integration.py` | replace in every version | replaced (M43) |

Branches: all nine (`drill-Master` — the default — and eight `arena/*`
branches). Tags: none. Forks: none at the time of writing (re-check).

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

# (a) delete the workbook from every commit
git filter-repo --invert-paths --path '08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx'

# (b) replace protected tokens in every text blob of every commit.
#     /secure/replacements.txt is PRIVATE, one rule per line, e.g.
#       literal:<protected token>==>[REDACTED]
#     (the same tokens as the private sanitization spec; never commit it)
git filter-repo --replace-text /secure/replacements.txt
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
git cat-file -e b581f873fdeda00be03018d8474e596182ee6866 2>/dev/null && echo LEAK || echo ok
git cat-file -e d385f86b18858e97d443221419b25f5a4e89bbcd 2>/dev/null && echo LEAK || echo ok
git count-objects -v && git gc --prune=now --aggressive
while IFS= read -r t; do git grep -q -F -e "$t" $(git rev-list --all) -- && echo "LEAK ${t:0:2}…"; done < /secure/private-tokens.txt
python tools/privacy/privacy_check.py     # on a checkout of each rewritten branch
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
