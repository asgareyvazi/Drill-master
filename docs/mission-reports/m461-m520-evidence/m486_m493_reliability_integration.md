# M486–M493: Reliability and integration (Phase F)

**PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.** Input class: SYNTHETIC. Linux offscreen runs are
not Windows acceptance.

| Mission | Item | Outcome |
|---|---|---|
| M486 | `BL-M408` (`test_m129`) status | 20/20 isolated repeats of `tests/test_m129_surveys_anticollision.py` passed (16 tests each). The file also passed in the full sharded run at `44d3fb4`. **Not reproduced; still OPEN.** Closing it needs N clean CI runs and is the owner's call. |
| M487 | D88 suite profile | `m487_suite_profile.md`, from the full 8-shard run at `44d3fb4`: 6229 tests, 454 files, 2608 s summed test time. The 10 slowest files carry 21.9 % of the time. An LPT file-level split balances at ratio 1.000 for both 2 and 3 groups. **No workflow change; the 60 min timeout is kept.** D88 stays BLOCKED BY OWNER DECISION. |
| M488 | Consistency | `tests/test_m488_integration_consistency.py`: every case service in the catalogue has a replay adapter whose current version contains the catalogue version; no adapter is missing from the catalogue; ids are unique; `violations()` is empty; `OWNER_APPROVALS` is empty; the five SHA-checked services share one contract. |
| M489 | Well context | Every service's `save_case` takes `well_id` as keyword-only. The six W13 service-dialog entry points pass `current_well_id` (static check). The M415 and M475 dialog tests check that a saved case carries the selected well. |
| M490 | Replay | The five generic services (M416, M420, M423, M427, M475) each refuse a forged inputs SHA with `IntegrityError`. MATCH / DIFFERENT / UNREADABLE / NOT_REPRODUCIBLE are tested per service (`test_m415_m427_*`, `test_m475_*`). |
| M491 | Security | **Finding fixed.** The summaries of the three calculation dialogs (`engineering_service_dialog`, `mse_drilloff_dialog`, `well_control_volumetric_dialog`) were QLabels in AutoText mode. They echo typed text in error reasons, so markup such as `<img src=…>` could render as rich text. All three are now `Qt.PlainText`, and the test types markup and checks that it is shown literally. Mutants ESD-, MDD- and VMD-rich-text-summary are killed. |
| M492 | E2E | Real-UI journeys from this delivery: `test_m467_eowr_mainwindow_journey` (EOWR, MainWindow), `test_m472_citation_mainwindow_journey` (citations, MainWindow), and the M475 W13 dialog run → save → replay. All passed in the full run. |
| M493 | Windows gate (static only) | `.github/workflows/windows-release-gate.yml` is unchanged (windows-2022, 60 min, pinned Inno Setup). Windows CI for `f7075a0` (run `45578429709`) is SUCCESS, 31m12s. This is a CI regression gate, **not Windows desktop acceptance** (P17 NOT RUN). |

## M486 detail

The command was run 20 times; each run collected 16 tests and passed:

```
python -m pytest -p no:cacheprovider -W ignore -q tests/test_m129_surveys_anticollision.py
```

## Full suite (input to M487 and M494)

The full 8-shard run at `44d3fb4` (`m494_full_suite_44d3fb4.txt`): 6229 collected, 6225 passed, 0 failed, 0 errors,
4 skipped. The 4 skips stay NOT RUN. Total 2677 s. Every shard was OK.
