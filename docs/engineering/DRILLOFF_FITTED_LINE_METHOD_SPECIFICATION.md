# Drill-off test — fitted two-segment line (M423 specification)

Status: **IMPLEMENTED — SCREENING — NOT APPROVED — OWNER REVIEW REQUIRED.**
- Method: `m423.drilloff_fitted`, version `M423 drill-off founder, continuous two-segment least squares v1`.
- Module: `core/drilloff_fitted.py`.
- UI: W13 Bit/MSE page button **📐 Drill-off fitted line…**.
- Separate version: M372 (`m372.mse_drilloff`) is unchanged and both remain available.

## Model

- **Fit.** ROP = a + b·WOB + c·max(WOB − W*, 0), a continuous hinge fitted by ordinary least squares at each candidate W*.
  - W* is searched over [W₍₂₎, W₍ₙ₋₁₎], so at least two steps lie on each side.
  - The search uses 200 grid points per tested interval, followed by golden-section refinement.
- **Decision (declared ratio 0 < r < 1).**
  - FOUNDER IDENTIFIED when b > 0 and b + c < r·b.
  - Otherwise NO FOUNDER IN TESTED RANGE.
- **Statistics.** The result reports:
  - R² and s = √(SSE/(n − 3));
  - the single-line SSE, for comparison;
  - flagged steps where |r_i| > 3·s₍ᵢ₎, with s₍ᵢ₎ = √((SSE − r_i²)/(n − 4)), the leave-one-out scale without leverage. The pooled s can never flag anything for n ≤ 12, which is why it is not used. Flagged steps stay in the fit.
- **Refusals.**
  - Fewer than 5 complete steps → NOT ASSESSED.
  - Duplicate WOB → refused.
  - RPM range greater than the declared tolerance → NOT ASSESSED (not a drill-off test).
  - Missing tolerance or ratio → NOT ASSESSED.
- **Limitations.**
  - Least squares is not robust: a gross outlier next to the knee can pull the breakpoint onto itself. This is covered by a test.
  - Surface WOB only; no downhole correction and no CCS correlation.
  - The fitted break is a statistical estimate. It is not claimed to be more physically accurate than M372.

## Verification (SYNTHETIC)

- Tests: `tests/test_m415_m427_engineering_services.py`, covering the exact hinge, linear data, outlier flagging, the non-robustness case, refusals, replay and the dialog.
- Benchmarks: `benchmark_m412.py` DF1, DF2 and S5.
- Mutation: DF-*.
