# M113 – Unit-conversion constant inventory and versioning strategy

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED

Generated evidence: `docs/engineering/constant_inventory.json` (`python tools/quality/constant_inventory.py
--write`; `--check` fails when it is stale; `tests/test_m113_constant_inventory.py` checks it). Counts are
**code literals only** (Python NUMBER tokens in `core`, `tabs`, `dialogs`; comments and string text excluded), so a
value that appears only in a help text or comment shows 0 uses. Numbers inside f-string replacement fields
(`f"{depth * 3.28084:.1f}"`) are code and count. *Inventory v2 (M118):* v1 counted them only on Python ≥ 3.12,
whose tokenizer splits f-strings, so the CI 3.12/3.13 legs disagreed with the committed 3.11 inventory. v2 extracts
the fields on 3.11 too (cross-checked against the AST: 571 numbers in f-string fields, 0 files differing). Three
uses were added: 0.052 in the W13 tab, 3.28084 in W12, 0.3048 in `dialogs/calculator_dialog.py`. **No value was changed in M113.**

## Inconsistencies (same quantity, several literals)

| Quantity | Literals in code (uses) | Max. relative difference | Where |
|---|---|---|---|
| pcf per ppg (gal/ft³, exact 7.480519…) | 7.48052 (10), 7.48 (11), 7.4805 (1) | 6.95 × 10⁻⁵ | 7.48: kill sheet `PCF_PER_PPG`, T&D engine, W13 formation-pressure contract, W13 tab (6), calculator dialog (2); 7.48052: hydraulics engine (4), bit-hydraulics contract, `extended.py` (2), W13, W15, calculator dialog; 7.4805: `mud_volume.py` (`BBL_FT3 = 42/7.4805`) |
| ft³ per bbl (exact 5.614583…) | 5.6146 (1), 5.615 (1) | 7.12 × 10⁻⁵ | 5.6146: `mud_volume` weight-up (M107 v2); 5.615: `tabs/w3c_section_data.py` |

Both differences are below 10⁻⁴ relative — far below input uncertainty — but two screens can show values that
differ in the last printed digit for the same input. Which literal becomes authoritative is the owner decision
in the M112 pack "7.48 vs 7.48052".

## Single-literal quantities (consistent in code)

| Quantity | Literal (uses) | Note |
|---|---|---|
| gal per bbl | 42.0 (6) | bare `42` is not counted (ambiguous) |
| psi/ft per ppg | 0.052 (14) | exact 0.051948; the oilfield convention |
| psi/ft per pcf | 144.0 (2) | in² per ft² |
| ft per m | 3.28084 (54), 0.3048 (15, m per ft) | consistent: 1/0.3048 = 3.280840 |
| bbl/ft capacity constant | 1029.4 (10) | (D² − d²)/1029.4 bbl/ft |
| m per 100 ft (DLS conversion) | 30.48 (3) | |
| °F per °C | 1.8 (4) | hydraulics engine and W15 |
| lb per kg | 2.20462 (1 file, 2) | |
| fresh water | 8.33 ppg (3) | 8.33 ppg = 62.31 pcf; 62.4 pcf appears only in text |

No code literal: 25.4 mm/in, 14.5038 psi/bar, 6.894 kPa/psi, 0.006944 psi/ft per pcf, 0.1781 bbl/ft³ (text only).

## Conventions in use (both units present)

| Convention | Variant (uses, files) | Rule |
|---|---|---|
| Cost per length | per metre (15, 6) / per foot (18, 5) | every value carries its unit; cost per length is never compared across units without conversion |
| Dog-leg severity | °/30 m (68, 21) / °/100 ft (19, 7) | survey revisions store the unit; 30.48 m = 100 ft converts (≈1.6 % difference, not interchangeable) |
| Temperature | °C (18, 7) / °F (14, 2) | conversion via 1.8 and 32; no silent mixing |

## Versioning strategy (no global change)

1. A constant is part of a method's identity. Changing it creates a **new method version** (as M107 did for
   weight-up v2); the old version stays readable.
2. Stored records keep the method version they were computed with. Records without a version stay
   UNVERSIONED / NOT REPRODUCIBLE — the current constant is never assigned to them.
3. Re-runs use the stored version's constant; a re-run with a new constant is a new linked record (never an
   overwrite), and the full-field compare shows the difference.
4. A future single constant module (e.g. `core/units_constants.py`) would be introduced only after the owner
   decision, method by method, each with its goldens re-derived independently — not as a global search and
   replace.
5. This inventory is regenerated with the code; `--check` makes a new literal or a changed count visible in
   review.
