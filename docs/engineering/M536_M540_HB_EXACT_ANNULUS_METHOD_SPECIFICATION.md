# M536–M540 — method specification: `m538.hb_annulus_exact`

Version `M538 Herschel-Bulkley concentric annulus exact laminar v1`. Code: `core/hydraulics_hb_annulus_exact.py`.
Label: SCREENING. Not API RP 13D. Separate from M416 (`m416.hb_slot_annulus`, unchanged).

## Scope

| Item | Supported | Refused / not assessed |
|---|---|---|
| Geometry | concentric annulus, 0.01 ≤ κ = Di/Do ≤ 0.99 | eccentricity, tool joints, washouts |
| Rheology | Herschel-Bulkley τ = τ0 + K·γ̇ⁿ, 0.1 ≤ n ≤ 1, τ0 ≥ 0 (τ0 = 0 power law, n = 1 Bingham / Newtonian) | n > 1, temperature / pressure dependence |
| Flow | laminar, steady, isothermal, incompressible, fully developed, stationary walls | Re_G ≥ Re1 (no transitional / turbulent branch), pipe rotation, axial pipe movement (surge) |
| Inputs | all declared (missing → NOT ASSESSED); non-finite, negative, Di ≥ Do → refused | defaults, inferred values |

## Derivation (clean-room)

r from the axis, x = r/Ro, κ = Ri/Ro, G = −dp/dz > 0, T = G·Ro/2.

1. Axial momentum: (1/r)·d(rτ)/dr = −G ⇒ τ(x) = T·(x − λ²/x); λ·Ro is the zero-shear radius.
2. Unsheared plug where |τ| ≤ τ0: edges x∓ = ∓b + √(b² + λ²), b = τ0/(2T). Flow requires τ0/T < 1 − κ, i.e.
   G > 4τ0/Dh (yield onset).
3. Shear rates: outer γ̇ = ((T(x − λ²/x) − τ0)/K)^(1/n) on [x+, 1]; inner γ̇ = ((T(λ²/x − x) − τ0)/K)^(1/n) on [κ, x−].
4. λ from equal plug velocity seen from both walls: ∫_{x+}^{1} γ̇_out dx = ∫_{κ}^{x−} γ̇_in dx. The difference is
   strictly decreasing in λ²; bracket [κ² + κτ0/T, 1 − τ0/T]; bisection to relative 1e-15.
5. Q = π·Ro³·[∫_{x+}^{1} x²·γ̇_out dx − ∫_{κ}^{x−} x²·γ̇_in dx] (integration by parts; the plug terms cancel).
6. Q(G) strictly increasing; G for a declared Q by bisection on log G to relative 1e-13.
7. Integrals: composite Gauss-Legendre, 32 panels × 16 nodes per region (integrands continuous, zero at the plug
   edges).

Reported: Δp = G·L, gradient, mean wall shear τw = G·Dh/4, zero-shear and plug radii, plug velocity, n' =
d ln τw / d ln V (central difference, ±1e-4 in G), Re_G = 12ρV²/τw (slot-equivalent as in M416), Re1 = 3250 − 1150n'
(Founargiotakis, Kelessidis & Maglione 2008, the laminar limit M416 uses). Zero flow → 0 psi; the yield onset
4τ0L/Dh is reported separately as information.

Method references (problem statement only; nothing copied): Fredrickson & Bird 1958, Ind. Eng. Chem. 50(3):347;
Hanks 1979, Ind. Eng. Chem. Fundam. 18(3):191.

## Independent validation (tests/test_m538_hb_annulus_exact.py, benchmark tools/quality/benchmark_m538_hb_exact.py)

| Reference | Independent of the engine because | Tolerance |
|---|---|---|
| Newtonian Lamb closed form Q = πG/(8μ)[Ro⁴ − Ri⁴ − (Ro² − Ri²)²/ln(Ro/Ri)] | analytical | 1e-9 relative |
| Bingham: closed-form velocity branches, own plug bisection, dense trapezoid of u·r | velocity (not shear-rate) formulation, different quadrature and root solve | 1e-7 relative (Q), 1e-9 (λ²) |
| HB parallel plates (κ = 0.995), closed form per unit width × π(Ro + Ri) | analytical slot solution | 2e-4 relative (curvature) |
| Power law Q ∝ G^(1/n) | exact scale invariance | 1e-9 |
| M416 slot, laminar, κ = 0.3 / 0.6 / 0.9 | different model (narrow-slot approximation) | converges: < 3 %, decreasing, < 0.1 % at 0.9 |

## Persistence, replay, UI

Immutable declared inputs with SHA-256; `save_case` (explicit `well_id`); replay through the generic
`history_replay` service adapter (`SERVICE_MODULES["m538.hb_annulus_exact"]`), tamper → IntegrityError; unit
tolerances registered (new unit `lbf/100ft²`). W13 hydraulics toolbar button "HB Annulus exact (laminar)" →
`hy_hb_exact_dialog` → `dialogs.engineering_service_dialog.hb_exact_annulus_dialog` (object prefix `m538`, nothing
defaulted, no formula in the handler). Catalogue entry `m538.hb_annulus_exact` (NOT APPROVED).

## Limitations

Laminar only; concentric only; no rotation, eccentricity, surge, temperature or pressure effects; not a
replacement for M416 in turbulent flow; not field-validated.
