# M526–M527 / M541–M545 — Erge 2015 citation record correction and M416 equation re-check

## Two distinct publications

| Paper | Venue | DOI | Access |
|---|---|---|---|
| Erge, Ozbayoglu, Miska, Yu, Takach, Saasen, May — laminar-to-turbulent transition of yield-power-law fluids in annuli | J. Pet. Sci. Eng. 128 (2015) 128–139 | 10.1016/j.petrol.2015.02.007 | Paywalled; no lawful open full text found |
| Erge et al. — annular frictional pressure losses of yield-power-law fluids (eccentricity / rotation; exact title to be confirmed from the publisher) | SPE Drilling & Completion 30(3) (2015) 257–271 | 10.2118/167950-PA | Paywalled |

They are separate papers and must not be cited interchangeably. The bibliographic summary of SPE 167950-PA also
mentions critical Reynolds-number correlations (onset / offset of transition, concentric and eccentric) and a
modified stability criterion, and BoreTHM (Apache-2.0, `fluids.transition_band`) cites SPE Drill. Complet. 30(3)
eqs. 17–18 for the coefficients DrillMaster uses. **Which paper holds the coefficients is unresolved.**

## M416 coefficients (unchanged numbers)

Re1 = 2100·[N^0.331·(1 + 1.402κ − 0.977κ²) − 0.019·e·N^−0.868·κ]; Re2 = 2900·N^(−0.039·Re1^0.307), with N
restricted to 0.15 < N < 0.4 for Re2. DrillMaster implements e = 0 only. Line-by-line comparison against the
secondary source: identical (tests/test_m482_erge_secondary_consistency.py). Comparison against a primary paper:
**NOT POSSIBLE** (no lawful access).

## Correction applied (M541)

* `core/hydraulics_hb_slot.UNVERIFIED_CRITERIA["erge-2015"]` now names both candidate papers with DOIs and states
  that the attribution is unresolved. This note is shown in summaries and stored in the case note only; replayed
  results and all numbers are unchanged, so no new method version is needed and old cases replay unchanged.
* The method-catalogue reference for M416 states "NOT VERIFIED — primary paper unresolved".
* Erge 2015 stays **NOT VERIFIED** (M542–M545: no version change, no coefficient change).
