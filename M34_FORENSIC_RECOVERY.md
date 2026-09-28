# M34 — Forensic Recovery & Method

**Mission:** *Forensic Recovery of Mission 33, Remaining Semantic Closure, Evidence Reconciliation and
Release-Candidate Assembly.*
**Rule that governs every page:** no earlier report is a source of truth. Precedence is
**filesystem → git → source → tests → artifacts → runtime → evidence → reports**. Counts, SHAs, branches and
statuses are re-derived here from the repository itself; anything that could not be re-derived is recorded as
`UNRESOLVED` rather than inherited.

---

## 1. Pre-flight reality (Part A)

| Item | Value (measured, not quoted) |
|---|---|
| Branch | `arena/01a0c945-drill-master` |
| HEAD | `c28bbef37cbac9de7abcfa693e7e21f678fa74ab` |
| HEAD tree | `7e16996cdcc1bce4a79fed8823371c20c74eef15` |
| `HEAD^` | **UNRESOLVED** — shallow clone, only `{02053eb, c28bbef}` present; ancestry is not fabricated |
| Worktree | 89 modified tracked / 251 untracked files / 0 deleted / 0 staged |
| Diff hash | tracked-file diff sha256 `79c05d864f8b900e…` (540 741 B) — **equal to the hash M33's own final staging record captured**, so the worktree is byte-identical to the state M33 left behind; nothing was lost between sessions |
| `git diff --check` | clean (no whitespace errors) |
| Stash / reflog | stash empty; reflog contains only clone, checkout and branch creation — **no commit was ever made on this branch** |
| Remote | `github.com/asgareyvazi/Drill-master` (public). Branches: `arena/01a056c5` `02dd3e14`, `arena/01a085e0` `c28bbef`, `arena/01a0801f` `b05ea768`, `arena/01a05747` `c7e7697f`, `arena/01a07094` `ad7ea0db`, `drill-Master` `02053eb` (default) |
| This session's branch on the remote | **ABSENT (404)** → `arena/01a0c945-drill-master` is a **LOCAL-ONLY BRANCH — NOT SYNCHRONIZED TO GITHUB** |
| Unresolvable remote SHAs | `a9d7dede…` (M33's claimed commit), `dc5939c8…` (M33's claimed tree), `beaf963…`, `fb857d7…`, `0bbcbd4…`, `716e8f…`, `e2eeb35…`, `6187130…`, `6bbd53e…`, `9ac747b…` → **UNRESOLVED**; `964e922a221870b3844fc9469544c4862ab67fbb` exists on the remote (M30 commit, parent `c28bbef`) but is not fetchable as a ref locally → **UNRESOLVED locally** |

Evidence: `docs/audits/m34-evidence/M34_PREWORKSPACE_MANIFEST.json` (per-file sha256/size/mtime for the 89 + 230
files as captured at session start) and `m34-git-cleanliness.json` (the same population re-captured after all
of M34's work).

---

## 2. Environment reconstruction (the sandbox was re-provisioned)

M33's session tooling and `/tmp` artifacts were destroyed between sessions. Everything M34 needed was rebuilt,
and — this time — **inside the repository**, so the next session inherits it:

| Component | Location | State |
|---|---|---|
| Analysis toolchain | `tools/m34/` (in-repo, durable) | `common.py` (AST index, context fingerprints), `repoindex.py` (definitions/callers/assignments/properties/class fields), `sweep34.py` (fresh sweep), `rules34.py` + `domain_rules34.py` (per-item rules), `adjudicate34.py` (ledger), `reverify_fixes34.py`, `mutate34.py`, `release34.py`, `audit34.py`, `stats34.py` |
| Verification virtualenv | `/home/user/verify-venv` | rebuilt from `requirements-lock.txt`: **26/26 pins exact**, `pip check` clean; dev tools: pytest 9.1.1, ruff 0.16.6, build 1.6.1 |
| Headless Qt | `/tmp/qtstub/` | symbol-complete **fail-loud** stubs for `libGL.so.1` (44 symbols), `libEGL.so.1` (28), `libxkbcommon.so.0` (47), `libdbus-1.so.3` (115): any real call aborts the process rather than returning a fabricated success. `libfontconfig.so.1` is a documented **graceful-failure** stub because Qt genuinely calls `FcInit` at startup — font metrics/enumeration are therefore unavailable and any text-geometry claim is classified as stub-affected |
| Qt behaviour reproduced | offscreen | `QDoubleSpinBox()` default maximum is **99.99**; `setValue(150)` silently leaves **99.99** — independently reproduced in this mission, not quoted from M33 |

---

## 3. Method: from sweep to ledger

1. **Fresh sweep** (`tools/m34/sweep34.py` → `m34-fresh-sweep.json`): 336 source files, **5 802 hits** across
   21 pattern families — session-lifecycle 1 282, if-not-falsy 1 033, return-none-false 739, broad-except 632,
   plan-actual 410, snapshot-serialize 343, get-default 258, orm-single-fetch 230, currency-arithmetic 206,
   pass-statement 130, or-zero 124, default-zero-param 101, setvalue-zero 76, numeric-coalesce 65,
   shell-subprocess 41, raw-sql-text 40, float-or-zero-strict 29, temp-file 27, skip-call 25,
   float-int-or-zero 9, sum-or-zero 2.
2. **Carry the M33 population** by identity, not by trust: an M33 record is carried only when the file's sha256
   still equals the hash M33 recorded (**8 933** records), plus **1** M33 forensics record that never had a line
   (`INV34-008933`, `core/engineering/engines/casing.py`, the fabricated-echo defect M33 fixed). Where a
   carried record's file changed, the record is **not** carried silently.
3. **De-duplicate**: **3 182** sweep hits were already held by an M33 record at the same `(path, family, line)`
   and are not re-counted. **2 620** sweep hits are genuinely new to the inventory.
4. **Adjudicate per item** — terminal states are `VERIFIED-CORRECT`, `DEFECT-FIXED`, `INTENTIONAL-BY-DESIGN`,
   `DUPLICATE-DEAD-WITH-EVIDENCE`, `ACCEPTED-LIMITATION`, `EXTERNAL-ACCEPTANCE-ONLY`, `REMOVED-WITH-EVIDENCE`;
   non-terminal are `UNDER-REVIEW` and `EVIDENCE-INCOMPLETE`. A rule may only reach a terminal verdict from a
   *fact*: a declared annotation, a parameter default, a class/dataclass field, a docstring contract, a caller
   contract, a property return type, an initialisation `None`, an identifier-vs-measurement key semantics, a
   cleanup/advisory function contract, or an explicit guard in the surrounding source.
5. **Re-adjudicate the inherited open items** with those facts (**2 837** items): 756 → VERIFIED-CORRECT,
   578 → INTENTIONAL-BY-DESIGN, 1 503 remain open. Nothing is closed by pattern, by bucket or by root-cause
   association; the M33 evidence of a re-adjudicated item is retained under `m33_evidence` on the record.

Result: **11 554 items** (`m34-ledger.json`, 11 554 records; `m34-reconciliation.json` holds the comparison).

---

## 4. What "terminal" means here, and what it must never mean

* A terminal verdict always names the *fact* and the *place* it came from (file and line of the declaration,
  caller or guard). Spot-check any record in `m34-ledger.json` — the `evidence` field is the argument.
* A line that moved is not a fix: carried records are keyed by `(path, family, line, normative text)` with the
  file hash, and a record whose file changed is re-examined instead of inherited.
* A green test suite is not semantic closure: the suite is evidence for the fixes it tests, and every fix was
  additionally attacked by a mutant (Part O, `m34-mutation-controls.json`).
* A count that fell is not a disposal: the deltas between M30/M31/M32/M33/M34 are enumerated per class
  (`NEW`, `CARRIED-FORWARD-SAME-FILE-HASH`, `DUPLICATE-OF-M33-RECORD`, `FIXED`, `REMOVED-WITH-EVIDENCE`,
  `INTENTIONAL`, `EXTERNAL`, `OPEN`) in `m34-reconciliation.json`.

---

## 5. Deliverables of this mission

| Artifact | What it contains |
|---|---|
| `M34_FORENSIC_RECOVERY.md` | this document — pre-flight, environment, method |
| `M34_M33_RECOVERY.md` | the mandatory M33 recovery report: changed / tested / claimed / verified / invalidated / remains |
| `M34_SEMANTIC_AUDIT.md` | sweep, ledger, re-adjudication, per-family closure, open register, test integrity, mutation controls |
| `M34_DOMAIN_MATRIX.md` | the 69-domain projection of the ledger, reconciled to the item total |
| `M34_ROOT_CAUSES.md` | root causes: engine defaults, Qt clamp, missing-vs-zero, failure-as-zero, ownership, packaging |
| `M34_RELEASE_CERTIFICATION.md` | closure and blocker gates, verification stages, external boundary, verdict |
| `M34_INVENTORY_LEDGER.json` | invariant projection and hash pin of the per-item ledger |
| `M34_EVIDENCE_INDEX.md` | every evidence file, its hash, what it proves and how to reproduce it |
| `M34_AUDIT_ANSWERS.md` | the 60 required questions answered from the artifacts above |
| `docs/audits/m34-evidence/` | the evidence itself: manifest, sweep, ledger, fix re-verification, mutation controls, wheel/lock, commit staging simulation, domain matrix, invariants, doc audit, git cleanliness, reconciliation |
| `tools/m34/` | the toolchain that produced all of it, in-repo so it survives the session |
