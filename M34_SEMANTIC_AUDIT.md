# M34 — Semantic Audit

**Scope:** every occurrence the fresh sweep can see in the final source tree, adjudicated one record at a
time, carried against the M33 inventory without trusting it, and reported with its open register intact.

* Source of truth: `docs/audits/m34-evidence/m34-ledger.json` (11 554 records) — this document is a projection
  of it, generated numbers included (`m34-ledger-summary.json`, `m34-reconciliation.json`,
  `m34-closure-invariants.json`).
* Every terminal verdict names a fact and the file/line it came from. Nothing was closed by pattern, by
  bucket, by root cause or by "the same fix covers it".

---

## 1. The inventory at a glance

| | |
|---|---|
| Items | **11 554** |
| VERIFIED-CORRECT | 7 333 |
| INTENTIONAL-BY-DESIGN | 2 880 |
| UNDER-REVIEW | **1 224** (HIGH 371, CRITICAL 0) |
| DEFECT-FIXED | 51 |
| REMOVED-WITH-EVIDENCE | 49 |
| EXTERNAL-ACCEPTANCE-ONLY | 17 |
| EVIDENCE-INCOMPLETE | **0** |

Origin of the population: 8 933 M33 records carried because the file's sha256 still equals the hash M33
recorded, 1 M33 forensics record that never had a line, and 2 620 genuinely new sweep hits. **3 182** sweep hits
were already held by an M33 record at the same `(path, family, line)` and are de-duplicated, not re-counted.

M33's transitions, measured (not asserted): `UNDER-REVIEW` 2 837 → **1 248 VERIFIED-CORRECT**,
**519 INTENTIONAL-BY-DESIGN**, **1 070 still open**; `EVIDENCE-INCOMPLETE` 4 → **4 VERIFIED-CORRECT**;
every already-terminal M33 verdict (VC 3 712, INT 2 264, DF 51, RW 49, EXAC 17) carried unchanged.

**One sweep-precision correction worth stating plainly.** 1 483 of the records this mission adjudicated turned
out to be *prose* — the pattern occurs inside a comment or a docstring, so there is no runtime subject. They
are recorded as VERIFIED-CORRECT with rule `R-PROSE` and the reason stated on the record. That is a fix to the
sweep's precision, not a mass closure: no executable occurrence was dispositioned this way.

---

## 2. Per-family closure

| family | total | VERIFIED | INTENTIONAL | UNDER-REVIEW | DEFECT-FIXED | REMOVED | EXT-ONLY |
|---|---|---|---|---|---|---|---|
| if-not-falsy | 4 209 | 3 213 | 444 | 552 | 0 | 0 | 0 |
| session-lifecycle | 1 282 | 1 256 | 0 | 26 | 0 | 0 | 0 |
| return-none-false | 1 255 | 558 | 697 | 0 | 0 | 0 | 0 |
| get-default | 1 065 | 530 | 465 | 18 | 4 | 48 | 0 |
| broad-except | 877 | 215 | 573 | 89 | 0 | 0 | 0 |
| plan-actual | 410 | 360 | 0 | 50 | 0 | 0 | 0 |
| orm-single-fetch | 376 | 352 | 4 | 20 | 0 | 0 | 0 |
| typed-exception | 371 | 58 | 158 | 155 | 0 | 0 | 0 |
| default-zero-param | 350 | 13 | 290 | 47 | 0 | 0 | 0 |
| snapshot-serialize | 343 | 327 | 0 | 16 | 0 | 0 | 0 |
| or-zero | 236 | 39 | 96 | 55 | 46 | 0 | 0 |
| currency-arithmetic | 206 | 206 | 0 | 0 | 0 | 0 | 0 |
| pass-statement | 132 | 0 | 34 | 98 | 0 | 0 | 0 |
| or-constant | 110 | 0 | 71 | 38 | 0 | 1 | 0 |
| setvalue-zero | 77 | 5 | 45 | 26 | 1 | 0 | 0 |
| numeric-coalesce | 65 | 37 | 3 | 25 | 0 | 0 | 0 |
| shell-subprocess | 41 | 41 | 0 | 0 | 0 | 0 | 0 |
| raw-sql-text | 40 | 40 | 0 | 0 | 0 | 0 | 0 |
| float-or-zero-strict | 29 | 26 | 0 | 3 | 0 | 0 | 0 |
| temp-file | 27 | 25 | 0 | 2 | 0 | 0 | 0 |
| skip-call | 25 | 25 | 0 | 0 | 0 | 0 | 0 |
| test-skip | 17 | 0 | 0 | 0 | 0 | 0 | 17 |
| float-int-or-zero | 9 | 6 | 0 | 3 | 0 | 0 | 0 |
| sum-or-zero | 2 | 1 | 0 | 1 | 0 | 0 | 0 |

---

## 3. What the terminal verdicts rest on (the fact sources)

Non-repeating examples, one per fact source, all readable in the ledger's `evidence` field:

| Fact source | Example record |
|---|---|
| Declared parameter default | `if not model:` in `set_selected_model` — the callers (`dialogs/excel_import_dialog.py:545`, `:580`) pass Qt text, empty when nothing is selected → text/optional contract |
| Declared return annotation | `resolution.accepted` is a `@property -> bool` (`core/combo_identity.py:100`) |
| Class/dataclass field | `result.missing` is declared `bool` on `NormalizationResult` (`core/value_normalizer.py:57`) |
| Docstring contract | `Args:` sections that state `dict`/`str`/`Optional` for a parameter that has no annotation |
| Caller contract | call sites classified across the repository; a text caller set resolves the parameter, a numeric caller set keeps it open |
| Initialisation state | `self.db = None` in `__init__` then `if not self.db:` — falsy means "not initialised", which is what the test asks |
| Identifier vs measurement key | `row.get("id")` is an identity presence test; `filtered.get("depth")` is a measured quantity and stays open |
| Cleanup/advisory function | `except OSError: pass` inside `close()`/`cleanup()`/`_safe_*`/a docstring that says "best effort" |
| Guarded execution | a stored SQL string executed only when present (`if object_sql: connection.execute(object_sql)`) |
| Consumer analysis | a default used as a counter seed (`results.get(key, 0) + amount`) is the additive identity, not a fabricated measurement |
| Declared text field | `ReviewItem.file: str = ""` (`core/import_quality.py`) — an empty string is that field's absence state |
| Prose | the pattern occurs in a comment or docstring (`R-PROSE`) |

**Known-good families closed by contract, not by mood:** `currency-arithmetic` 206/206 VERIFIED (every mixed-currency
sum is guarded by an explicit currency contract — no unlabelled total survives), `shell-subprocess` 41/41 VERIFIED
(all shell calls use list-argument form with no `shell=True`), `raw-sql-text` 40/40 VERIFIED (every raw SQL string
is parameterised), `session-lifecycle` 1 256/1 282 terminal (ownership is explicit; 26 remain open and are named
below), `snapshot-serialize` 327/343 terminal.

---

## 4. The open register (1 224 items, 371 HIGH, 0 CRITICAL)

Each open item names what is missing. The distribution, from `m34-closure-invariants.json`:

| rule | open | priority | the missing fact |
|---|---|---|---|
| `R-TRUTH-UNKNOWN` | 367 | MEDIUM | the subject of the falsy test has no annotation, no binding, no documented type and no resolvable caller contract in this repository |
| `R-DEF-UNKNOWN` | 152 | MEDIUM | the default's consumer path is outside the classified set (not arithmetic, not display, not a declared field, not a return) |
| `R-EXC-PASS` | 98 | HIGH | a `pass`-only handler on a path that is neither cleanup/advisory nor test scaffolding, and nothing logs, records or reports the failure |
| `R-TRUTH-NUMERIC` | 88 | HIGH | the tested value is numeric (a real 0 is falsy) and no `None` guard, `is None` test or declared optionality exists nearby |
| `R-PASS-EXC` | 74 | HIGH | `pass` inside an `except` whose try-body is not recognisably a cleanup or advisory probe |
| `R-EXC-OTHER` | 60 | MEDIUM | a handler body that neither raises, logs, records, returns an explicit state, nor matches a known advisory pattern |
| `R-EXC-SILENT-RETURN` | 52 | HIGH | the handler returns a sentinel with no log, no recorded status and no declared contract |
| `R-DEF-RETURN-NUM` | 52 | HIGH/MEDIUM | a numeric default is handed to the caller with no declared meaning for it |
| `R-PLAN-OTHER` | 48 | MEDIUM | a plan/actual expression whose base values' provenance (recorded vs derived vs absent) is not visible locally |
| `R-NUM-UNKNOWN` | 45 | MEDIUM | a numeric default whose consumer arithmetic cannot be classified |
| `R-EXC-CONTINUE` | 35 | MEDIUM | a handler that skips an item silently on an unclassified path |
| `R-SESSION-OTHER` | 26 | MEDIUM | a session-related statement that is neither creation with ownership nor a close |
| `R-SPIN-ZERO` | 26 | MEDIUM | `setValue(0)` outside construction/reset/load — 0 may be a real measured zero or a fabricated one |
| `R-PASS-OTHER` | 23 | MEDIUM | a bare `pass` whose function context does not classify it |
| `R-DEF-VALUE-PATH` | 21 | HIGH | a default that flows into arithmetic without a domain declaration |
| `R-SEL-UNPROVEN` | 20 | MEDIUM | a single-row fetch whose absence handling is not visible in the enclosing function |
| `R-SNAP-SERIAL-DEFAULT` | 16 | MEDIUM | a serialised snapshot field defaulted without a declared absence state |
| `R-RED-UNPROVEN` | 14 | MEDIUM | a reduction over values whose completeness is not proven |
| remaining 11 rules | 79 | MEDIUM/HIGH | each record states its own missing fact |

**Interpretation.** These are not "unknown unknowns": each is a concrete question about a concrete line, and the
question is stated on the record. They are open because the fact needed to answer them is *not present in this
repository* — it is a domain decision (is a legitimate 0 possible for this field? is this swallowed failure
allowed to be invisible to the operator?) or an external input. Closing them by assumption is exactly what this
mission forbids.

**Why they cannot be closed from the repository alone.** The repository defines the *engineering* contract in
some places (validators with explicit ranges, canonical schema fields with `critical` flags, declared dataclass
types), and those places were used. Where the code carries no such statement — a bare numeric parameter, a
handler with no reporter, a snapshot field with no declared absence state — the missing fact is a product
decision, and it is recorded as such rather than invented.

---

## 5. Parts F–N: what was actually audited

| Part | Domain | Result |
|---|---|---|
| **E/F** | engine defaults and the Qt 99.99 clamp | Root-caused and classified — see `M34_ROOT_CAUSES.md`. `casing.py`, `torque_drag.py`, `torque_drag_persistence.py`, `data_quality.py` and the W3 derived-value displays each carry their verdict with evidence. |
| **G** | time semantics (`None` / `0` / negative / malformed / bool / partial / missing) | Covered by the `or-zero`, `numeric-coalesce`, `get-default` and `return-none-false` families plus the M32 fixes 004–006; the time-coverage metric reports `unknown`, NPT derivation skips unrecorded durations, and the legacy validator reports an incomplete 24 h. Two tests pin both branches. |
| **H** | engineering input contracts | All deterministic engines were swept for "plausible number as default": `default-zero-param` 350 records (290 INTENTIONAL with the declared default named, 47 open) and `numeric-coalesce` 65 (37 terminal). Every open record names the missing domain declaration. |
| **I** | UI/persistence boundary | `setvalue-zero` 77 (45 INTENTIONAL, 26 open), `get-default` 1 065, `snapshot-serialize` 343. The M32-FIX-008 contract (an untouched derived field persists `None`, not 0) is verified and mutation-tested. |
| **J** | exporter comparison | `core/professional_export.py` verified for the blank-duration contract and mutation-tested; the multipart exporter set is covered by the `get-default` / `snapshot-serialize` families. |
| **K** | snapshot/historical integrity | `snapshot-serialize` 327/343 terminal; the 16 open records are listed with their missing declaration. |
| **L** | `data_quality` | M33's fix verified by probe + test + mutant; the metric reports `unknown` with `value=None` when any duration is unrecorded. |
| **M** | false-success paths | The exception families were re-swept with try-body context: handlers that protect cleanup and advisory probes are INTENTIONAL with the call named; handlers that swallow on a path with a caller-visible success signal stay open and HIGH (98 + 74 + 52). **No item was closed by "it is only a log".** |

---

## 6. Test integrity

* Vacuous assertions and skips were swept: `skip-call` 25/25 resolved (17 `EXTERNAL-ACCEPTANCE-ONLY` with the
  external input named in the call itself, 8 inside prose or scaffolding) and every skip in the suite is
  keyed to a stated external dependency; **no skip was converted into a green pass** and no failed import was
  turned into a skip.
* `assert True`-style records do not exist in the ledger (family `assert-true` produced no executable hits).
* The four skips the suite actually reports are the DDR xlsx/PDF acceptance inputs, the MinerU integration input
  and the Windows bundle — all external, all named in the report.
* Mutation control is the strongest available statement about test strength: 16 mutants designed from the fix
  contracts, **15 killed**, 1 documented equivalent survivor (`M34-M-DURATIONORZERO`: `x or 0` inside the
  `duration is not None` branch can only differ for `0.0`, where it is identical). The harness requires an
  exactly-once anchor match, aborts on restore mismatch, and left every touched file byte-identical
  (`harness_self_check.all_restored = true`).

---

## 7. What this audit does *not* claim

* It does not claim semantic closure: **1 224 items remain open** and the closure gate is false by construction.
* It does not claim that a green suite implies correctness: the suite passes (1 814 passed / 0 failed / 0 errors /
  4 external skips) while 371 HIGH items remain open by our own criteria.
* It does not claim Windows, native Qt, installer or real-production-document acceptance: no such run happened
  here, and every affected item is marked external.
* It does not claim that a report number is evidence: M30/M31/M32/M33 counts are handled as claims, and the only
  numbers used are the ones this mission re-derived (`m34-reconciliation.json`).
