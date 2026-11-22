# M326 — D63 / D74 lifecycle tests (retain policy kept while the owner decision is pending)

**Status:** D63 is BLOCKED BY OWNER DECISION (pin ≥ 6.8.2; package in `m324_pyside_upgrade_decision.md`). D74 policy is IMPLEMENTED — PARTIALLY QUALIFIED. The product keeps the **RETAIN** policy on the pinned PySide6 6.8.1.1.

New file `tests/test_m326_window_lifecycle.py` adds 4 tests. Each one opens and closes **real MainWindows** on SYNTHETIC file databases in a **subprocess** (`tools/quality/d63_window_release_probe.py`), so a native crash fails the test instead of killing the test runner.

| Test | What it proves |
|---|---|
| `test_the_lock_pin_and_the_retain_policy_agree_while_the_owner_decision_is_pending` | The `requirements-lock.txt` pin (6.8.1.1) maps to `release=False`. If the pin changes, this test fails with an instruction to record the owner approval and close D63 / D74. |
| `test_product_policy_closes_real_windows_without_a_crash_and_retains_them_on_the_pinned_pyside` | 3 real windows are closed under the product policy: rc 0, all 3 retained on 6.8.1.1, and the applied policy is printed by the window itself. |
| `test_the_operator_can_force_retention_of_real_windows` | `DRILLMASTER_RETAIN_CLOSED_WINDOWS=1` keeps the closed windows alive. |
| `test_retained_windows_cost_is_bounded_and_stated` | The retention cost is linear: 1 window = 9,601 live widgets, and 3 windows ≤ 3 × that + 5 %. |

## Sensitivity check (mutation by hand, then restored)

`FIXED_PYSIDE = (6, 8, 1)` releases windows on the crashing pin:
- the lock guard **fails** deterministically;
- the product-lifecycle test **fails 3 / 3** with `rc=-11` (SIGSEGV) at 3 windows. With 2 windows the crash did not fire, so the test uses 3.

`core/qt_lifetime.py` was restored byte-identical (`git diff` empty).

## Limitation

On 6.8.1.1 the freed-window crash is non-deterministic: 4 / 5 runs in M324 and 3 / 3 here. The deterministic protection is the lock-pin guard. The release path on a fixed PySide6 is exercised only by the isolated M324 evaluation (local probe on 6.8.2.1 / 6.8.3, and the CI workflow), not by the product suite.

Retained windows cost memory for the rest of the session. That is the accepted price until the owner approves the pin.
