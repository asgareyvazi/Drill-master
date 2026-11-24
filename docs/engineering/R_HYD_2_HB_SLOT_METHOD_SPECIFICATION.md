# R-HYD-2 — Herschel-Bulkley annular friction loss, narrow-slot model (M415 specification)

Status: **IMPLEMENTED — SCREENING — NOT APPROVED — OWNER REVIEW REQUIRED.** Method `m416.hb_slot_annulus`,
version `M416 Herschel-Bulkley slot annulus v1`, module `core/hydraulics_hb_slot.py`, W13 Hydraulics toolbar
button **🧮 HB Annulus (R-HYD-2)** (dialog `dialogs/engineering_service_dialog.py`). Calculation cases are saved
with an inputs SHA-256 and replay through `core/history_replay.py` (generic service adapter).

## 1. Scope

| Item | Decision |
|---|---|
| Geometry | One concentric annulus section: Do (hole / casing ID, in), Di (pipe OD, in), length L (ft). |
| Idealisation | Narrow slot of gap δ = (Do − Di)/2, hydraulic diameter Dh = Do − Di, V = Q / (π/4 (Do² − Di²)). Used only for κ = Di/Do ≥ 0.3. The Newtonian slot under-predicts the exact concentric flow rate by 2.25 % at κ = 0.3, 0.78 % at 0.5 and 0.21 % at 0.7 (independently checked against the exact annulus solution, test `test_the_slot_idealisation_bound_holds…` and benchmark R5). |
| Rheology | τ = τ0 + K γ̇ⁿ, with τ0 ≥ 0, K > 0 and 0.1 ≤ n ≤ 1. All three are declared (lbf/100 ft², lbf·sⁿ/100 ft²). They are never fitted from θ600/θ300 inside this method: the fit is a separate, unapproved step (`core/mud_engineering.py` still reports HB as NOT ASSESSED). |
| Regimes | Laminar (exact slot solution), transitional (linear blend), turbulent (Colebrook on Re_G). |
| Not modelled | Eccentricity, pipe rotation, pipe movement (see surge/swab), cuttings, tool joints, temperature and pressure effects on rheology, wall slip. Not API RP 13D. |

## 2. Equations (clean-room; references are method references only)

* **Laminar slot.** The momentum balance gives τ(y) = G·y. From this, the mean velocity is
  V(τw) = δ/(2τw²) · K^(−1/n) · S^((n+1)/n) · n · [S/(2n+1) + τ0/(n+1)], with S = τw − τ0.
  This is solved for τw by bisection to relative 1e-15.
  The limits are checked independently: Newtonian (plane Poiseuille), power-law, Bingham (Buckingham slot form) and
  general HB (Simpson quadrature of the velocity profile).
  Reference: Founargiotakis, Kelessidis & Maglione 2008, *Can. J. Chem. Eng.* 86:676.
* **Generalised Reynolds number.**
  * Local n′ = d ln τw / d ln(12V/Dh), computed analytically.
  * K′ = τw / (12V/Dh)^n′.
  * Re_G = ρV^(2−n′)Dh^n′ / (K′·12^(n′−1)) = 12ρV²/τw,lam.
  * Laminar Fanning factor f = 24/Re_G.
* **Transition band (declared; there is no default):**
  * `founargiotakis-2008`: Re1 = 3250 − 1150n′, Re2 = 4150 − 1150n′.
  * `erge-2015` (concentric, e = 0):
    * Re1 = 2100·n′^0.331·(1 + 1.402κ − 0.977κ²), valid for 0.1 < n′ < 1.
    * Re2 = 2900·n′^(−0.039·Re1^0.307), fitted at κ = 0.5 for 0.15 < n′ < 0.4.
    * A flow at or above Re1 with n′ outside that range is **NOT ASSESSED** (no extrapolation). κ ≠ 0.5 gives a warning.
    * The equations were taken from the BoreTHM (Apache-2.0) docstring citation and were not re-checked against the paper. This is a stated verification gap.
* **Turbulent.**
  * Colebrook (1939): 1/√f_D = −2·log10(ε/(3.7Dh) + 2.51/(Re√f_D)), with Fanning = f_D/4.
  * It is solved by fixed-point iteration to 1e-12, and is NOT ASSESSED if it does not converge in 100 iterations.
  * Applying a Newtonian correlation at Re_G is a stated approximation.
* **Transitional.**
  * f = f_lam(Re1) + (f_turb(Re2) − f_lam(Re1))·(Re_G − Re1)/(Re2 − Re1), so each correlation is used only at its own end of the band.
  * When Re2 < 4000, the warning "Colebrook evaluated below 4000" is raised.
* **Pressure gradient.** dp/dL = 2fρV²/Dh (= 4τw/Dh in laminar flow).
* **Zero flow.** This is a value, not missing data: regime NO FLOW, 0 psi of friction. The yield onset 4τ0L/Dh is reported separately.

## 3. Units

The calculation runs in SI internally, using exact definitions:
- in = 0.0254 m and ft = 0.3048 m
- US gal = 3.785411784 L and lb = 0.45359237 kg
- lbf = 4.4482216152605 N, so 1 psi = 6894.757293168361 Pa and 1 lbf/100 ft² = 0.4788025898 Pa.

Every input and result carries its unit (`UNITS`, `RESULT_FIELDS`), and replay tolerances are declared per unit (M388).

## 4. Validation and refusals

- Missing input → NOT ASSESSED (it is never defaulted).
- Non-finite, negative or inconsistent geometry (Di ≥ Do) → refused with the reason.
- n outside 0.1–1 → NOT ASSESSED.
- κ < 0.3 → NOT ASSESSED.
- An unknown transition criterion is refused.

## 5. Verification (input class: SYNTHETIC)

* Tests: `tests/test_m415_m427_engineering_services.py`, covering the R-HYD-2 group, replay, tampering, the W13 dialog, catalogue and units.
* Benchmarks: `tools/quality/benchmark_m412.py`, cases R1–R8, Z1 and Z2, plus status checks S1–S3. Expected values come from closed forms, quadrature or a bisection Colebrook — never from the module.
* Mutation: `tools/quality/mutation_m401_m460.py`, mutants HB-*.
* Duplication: `core/hydraulics_engine.py` and `core/w13_hydraulics.py` still refuse HB and contain no slot or Colebrook code (asserted by a test).

## 6. Open items

* Owner approval is required before any operational use.
* The Erge equations have not been verified against the original paper.
* No field data comparison has been made.
* The HB fit from Fann readings is not part of this method.
