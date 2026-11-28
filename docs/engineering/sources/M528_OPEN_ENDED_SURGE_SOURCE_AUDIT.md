# M528 — open-ended surge / swab: source audit (M479)

Question: is there a lawfully accessible primary source with the complete equations of a steady (or quasi-steady)
surge/swab model for an **open-ended** string (displaced fluid split between the annulus and the string bore,
equal pressure drop across both paths) for Herschel-Bulkley / yield-power-law fluids, such that DrillMaster could
implement it as a separate method without relabelling M420?

Classification scale: FULL TEXT / ABSTRACT ONLY / EQUATIONS / DATA / IMPLEMENTABLE NARROW SCOPE / BLOCKED.

| Source | Access | What it covers | Classification |
|---|---|---|---|
| He, Tang, Xiong, Wang 2016, "A numerical model for predicting surge/swab pressure of yield-power-law fluid in concentric annulus with open-ended pipe", J. Pet. Sci. Eng. 145:464–472, DOI 10.1016/j.petrol.2016.05.039 | Publisher page, paywalled; abstract read | Exact numerical YPL concentric model with open-ended pipe; regression correlations stated within ±5 % (Bingham, YPL) and ±15 % (power law) | ABSTRACT ONLY — BLOCKED for formulas. An abstract is not a formula source. |
| Tang, Ahmed, Srivastav, He 2016, J. Pet. Sci. Eng. 145:346–356 | Paywalled | Simplified YPL surge model, eccentric annuli (closed end) | ABSTRACT ONLY — not open-ended |
| He, Srivastav, Tang, Ahmed 2016, J. Nat. Gas Sci. Eng. 28:184–192 | Paywalled | Simplified YPL surge model | ABSTRACT ONLY |
| Mohammad & Belayneh 2023, "New Simple Analytical Surge/Swab Pressure Model for Power-Law and Modified Yield-Power-Law Fluid in Concentric/Eccentric Geometry", Appl. Sci. 13:12867, DOI 10.3390/app132312867 | Open access, full text (MDPI HTML). Licence statement not captured in the fetched text; MDPI articles are normally CC BY 4.0 — treat as UNCONFIRMED | Pipe moving in a fluid-filled annulus, no circulation; laminar, steady, incompressible; BCs u(Rh) = 0, u(rp) = Vp. No displacement-flow balance and no string-bore path — **open vs closed end is not modelled at all**. Exact HB eq. (7) is nonlinear; authors drop τy/k and introduce a calibration factor β* (eq. 11); eccentricity by a modified Haciislamoglu R-factor (eqs. 13–15) | EQUATIONS (empirical) — NOT an open-ended model. See defects below |
| Öner Erge, MSc thesis, METU 2016, "Modeling of surge and swab pressure of yield power law fluids" (open PDF, METU repository) | Open, full text | Concentric YPL surge/swab, CFD-validated; abstract describes the closed-end ("kapalı uçlu") case | FULL TEXT, closed-end — does not supply open-ended equations. Different person from Oney Erge (author of the 2015 transition papers). |

## Defects found in Mohammad & Belayneh 2023 (why it is not implemented)

1. The model is calibrated: β* = 15.5 (power law) and 10 (YPL) in Section 4, but 15.8 and 9.5 in Section 6 for the
   unmodified R-factor; the Discussion says "models require a calibration factor, which should be determined from
   measured data". All values are fitted to one digitised dataset (Srivastav et al. 2017, AADE-17-NTCE-075,
   e = 0.9, 0.1–0.8 ft/s, four fluids).
2. The numbering of R_PL / R_YPL is inconsistent: the Discussion assigns R_PL to eq. (14) and R_YPL to eq. (15);
   the caption of Figure 9 assigns R_PL to eq. (15) and R_YPL to eq. (14).
3. The added R-factor terms contain dimensional constants (0.045, 0.05·τy/k, 0.05·k/n) in field units, so the
   correction is unit-system dependent.
4. No flow-split / open-end physics is present, so it cannot serve M479 even if adopted.

## Decision

**M479 (open-ended surge) stays BLOCKED (M531–M535).** No lawfully accessible source provides the open-ended
equations. M420 is unchanged and keeps "open end NOT ASSESSED"; it is not relabelled.

Unblocking options, recorded in the canonical backlog:
* lawful access to He et al. 2016 (library licence) and line-by-line extraction; or
* a clean-room first-principles specification: flow split such that Δp_annulus(Q_a, moving inner wall) =
  Δp_bore(Q_b) + Δp_bit(Q_b) with Q_a + Q_b = A_steel·v_p. This needs an HB annulus solver **with a moving inner
  wall** (the M538 exact solver covers stationary walls only) and a bit-nozzle loss model with declared nozzles.
  It must be reviewed against a published open-ended dataset before release; no such dataset is lawfully
  available in this sandbox.

No paper data are shipped.
