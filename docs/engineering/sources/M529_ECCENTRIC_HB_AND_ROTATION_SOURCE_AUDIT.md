# M529 — eccentric Herschel-Bulkley annulus and pipe rotation: source audit (M480 / M481)

| Source | Access | Content | Classification |
|---|---|---|---|
| Krishna, S. et al. 2025, "Semi-analytical modeling and physical insights into eccentric annular flow of Herschel–Bulkley fluids", Eur. Phys. J. Plus 140:1115, DOI 10.1140/epjp/s13360-025-07054-w | Open access (Springer), full text read in part (sections 2–3) | Steady laminar HB flow; slot-like Cartesian momentum balance; eq. (10) solved by a binomial expansion **truncated at third order** to give velocity eq. (11); flow eq. (12) Q = 2π∫₀^{h(θ)} u(y,θ)·y dy; closed-form eq. (13) with constants C1, C2 fixed "by applying no-slip" in an appendix (Mathematica); gap h(θ) from Iyoho & Azar 1981 (eq. 14); validated on a 5 m flow loop (ID 90 mm / OD 70 mm, inner pipe closed, not rotating) | EQUATIONS — NOT IMPLEMENTED (see below) |
| Kelessidis et al. 2011, J. Pet. Sci. Eng. 77:305, DOI 10.1016/j.petrol.2011.04.004 | Paywalled; abstract only | Eccentric annulus HB flow (CFD / experiments) | ABSTRACT ONLY — BLOCKED |
| Torsvik 2026, OMAE2026-181498, DOI 10.1115/omae2026-181498 | Not found by search on 2026-10-13 | — | NOT FOUND — BLOCKED |
| Erge et al. 2015, SPE Drill. Complet. 30(3) 257–271, DOI 10.2118/167950-PA | Paywalled | Per the bibliographic summary: critical Reynolds numbers for onset/offset of transition in concentric and eccentric annuli, modified stability criterion; BoreTHM (Apache-2.0) transcribes eqs. 17–18 | SECONDARY ONLY — NOT VERIFIED |
| Fredrickson & Bird 1958, Ind. Eng. Chem. 50(3):347; Hanks 1979, Ind. Eng. Chem. Fundam. 18(3):191 | Classical, method references | Exact concentric annulus for Bingham / power-law (FB) and yield-pseudoplastic (Hanks) fluids | Problem statement reproduced by **clean-room derivation** in M538 — no equation or table copied |

## Why Krishna 2025 is not implemented

1. The velocity profile is a third-order truncation of a binomial series in (∂p/∂x)·y/(C1 − τ0); its accuracy
   degrades as that ratio approaches 1, i.e. near the walls of wide gaps — the error bound is not stated.
2. Eq. (12) weights the slot velocity by y (distance from the wall) with a factor 2π, mixing a Cartesian slot
   profile with a cylindrical area element; the published closed form (13) inherits this. We could not reconcile it
   with ∫u dA for the eccentric geometry without the appendix derivation.
3. C1 and C2 are determined numerically in an appendix; the closed form is not self-contained.
4. Rotation is not modelled (inner pipe closed and stationary).

A narrow-slot eccentric HB model is therefore **not** shipped. "Concentric → eccentric" extension remains
forbidden.

## What was implemented instead (M536–M540)

* **M538 `m538.hb_annulus_exact`** — exact laminar HB flow in a concentric annulus for 0.01 ≤ κ ≤ 0.99, i.e. the
  wide annuli that M416 refuses (κ < 0.3). Clean-room derivation in
  `docs/engineering/M536_M540_HB_EXACT_ANNULUS_METHOD_SPECIFICATION.md`; validated against independent references
  (Newtonian Lamb closed form, a Bingham closed-form velocity formulation, the HB parallel-plate limit, the power-law
  scale law). Laminar only; Re_G ≥ Re1 (Founargiotakis 2008) is refused.
* **Eccentricity (M480)** — BLOCKED: no verifiable open-access HB eccentric closed form.
* **Rotation and combined effects (M481)** — BLOCKED: no source accessed with rotation equations.
