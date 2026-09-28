# P6 p6-batch-010 — class class E (dialog date parse, release-gate return-code checks, test-oracle guards, theme/acceptance helpers): E:9

records **9** over **9** sites · DUPLICATE/FALSE-POSITIVE: 4 · INTENTIONAL: 3 · VERIFIED-CORRECT: 2

## INV34-006370 — `tabs/w9_Services_Widget.py:671`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `EquipmentDialog.load_equipment_data`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** A stored service date ('%Y-%m-%d' string) is parsed back into the dialog's date widget; on an unparseable/partial value the widget keeps its current (default) contents, so no date is invented for a malformed legacy row. The typed guard matches the only failures the parse can raise (`strptime` -> ValueError, a missing attribute -> AttributeError) and the following fields are loaded independently (673-682), so a bad date cannot abort the rest of the load.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006523 — `tests/test_m29_release_closure.py:83`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `test_required_eleven_pair_plan_matrix`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Test-oracle arithmetic in `test_required_eleven_pair_plan_matrix`: the matrix at 54-68 contains (0, 0), and the branch structure decides every other p == 0 case before this line (`elif p == 0 and a != 0: assert scalar.variance_pct is None and scalar.status == "unavailable"`, 80-81). So `expected = (a - p) / abs(p) * 100 if p else 0` (83) is reached with p == 0 only for (0, 0), where 0% is the correct relative variance (planned and actual are both zero) - and it also avoids a ZeroDivisionError. The guard therefore cannot mask a failing case: (0, 100) is asserted as None/unavailable one branch above.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006524 — `tests/test_m30_semantic_regressions.py:177`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `test_backup_source_disappearing_does_not_create_empty_success.disappear`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Rule mis-fire, not a behaviour to adjudicate: `first` is a boolean one-shot flag inside the monkeypatched `sqlite3.connect` (`first = True` ... `if first: first = False; source.unlink()`, 174-179), not a numeric quantity; the guard makes the disappearing-source condition fire once.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006718 — `ui/utils.py:130`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `broad-exception` (HIGH, class E)
- **Symbol:** `_darken_color`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** A theme helper ('رنگ hex را تیره‌تر می‌کند' = 'darkens a hex colour'): the failure mode is a colour token that is not a 6-digit hex value, in which case the caller's own token is returned unchanged - presentation only, no measurement, no persistence, and it cannot invent a colour. Residual (recorded, cosmetic): after `hex_color.lstrip('#')` a value that fails the hex parse is returned without its leading '#', exactly as in the sibling helper `HomeTab.darken_color` (adjudicated as INV34-004079 in p6-batch-009). Site: ui/utils.py:121-131.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006762 — `verify_release.py:296`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `verify_wheel`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for verify_release.py:294-297 - the same fail-closed test on the `pip install --target` result, already adjudicated under INV34-006764: a failed install must not be smoke-tested as an installed package
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006763 — `verify_release.py:277`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `verify_wheel`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for verify_release.py:276-278 - the same fail-closed test on the `python -m build --wheel` result, already adjudicated under INV34-006764: a failed wheel build must not be verified as a wheel
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006764 — `verify_release.py:266`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `verify_wheel`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `_run(...)` returns a `subprocess.CompletedProcess`, so the subject is its exit status: zero means 'the command succeeded', a non-zero value means 'the command failed' (negative for a signalled process). `if rc:` is therefore exactly the fail-closed test - it proceeds only on a successful command - and no read of the value can be confused with 'absent number', because the value is always set by the call itself. In this same file the explicit form is used where the success set is wider ('if debt.returncode not in (0, 1) or defects.returncode:', verify_lint, 254). Site: `git ls-files -z` (265-267) - an inventory failure must abort the wheel check rather than build from an unknown source set.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008485 — `tabs/w9_Services_Widget.py:672`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `EquipmentDialog.load_equipment_data`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w9_Services_Widget.py:671/672 - the `pass` line of INV34-006370's handler, already adjudicated under INV34-006370: the date widget keeps its default
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008562 — `tools/real_user_acceptance.py:159`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `run`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** This `pass` is the *expected* path of a negative acceptance assertion: the probe tries to save an invalid date and raises `AssertionError('Invalid date was accepted')` if the write is accepted; reaching the handler means the database refused it. Nothing is hidden - the assert immediately below (160) proves the previously stored value survived (`assert db.get_well_by_id(well)["spud_date"] == date(2026, 9, 1)`), so an accepted-but-silent write could not pass this probe.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

