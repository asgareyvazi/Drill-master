> **HISTORICAL MISSION RECORD (Mission 29 evidence).** This file is preserved unedited as the evidence it produced. Its counts, hashes and verdicts describe the tree at that time and are superseded by the Mission 33 re-adjudication — see [M33_SEMANTIC_AUDIT.md](../../../M33_SEMANTIC_AUDIT.md) and [M33_RELEASE_CERTIFICATION.md](../../../M33_RELEASE_CERTIFICATION.md).

# Mission 29 evidence boundaries

Main report: `../2026-09-23_M29_RELEASE_CLOSURE.md`.

- `final-source-gate.txt`: actual clean full gate at implementation `beaf9635ffb7bcecf16b3320b138077c7ef8e6c8`, command exit 0. It includes collection, 1687-pass/3-skip/20-warning execution and installed-wheel smoke.
- `full-gate-first-attempt.txt`: retained failed run at `8a20cb9`, not current results.
- `source-manifest.json`: 352 current source/test/config/build/asset fingerprints, excluding audit/history/Markdown. It is not a claim of semantic completeness.
- `risky-site-inventory.json`, `site-adjudications.json`, `inventory-runner.py`: 2259 selected syntax sites; only 27 have hash-bound, individually reasoned adjudications. **2232 NOT-REVIEWED**. The AST patterns do not catch every possible convenience/default or dynamic consumer.
- `model-inventory.json`: 62 canonical model scope/FK/scalar-default records; not 62 certified models.
- `domain-matrix.json`: 69 partial domain rows. `scope-consumer-index.json`: 118 W10/W11/W12/W16 source locations, not completed transitive scope certification.
- `mutation-controls.json` and named logs: 14 actual negative controls, each exit 1 with source hash restored. `mutation-wheel.json`: removing ui packaging fails both focused test and real clean-staged wheel gate. Do not run mutation scripts alongside other tests, editing or servers.
- `isolated-imports.json`: 174 actual fresh subprocess imports, all exit 0; optional capability execution is not implied. `environment.json`: exact Python/platform/tool versions and installed freeze.
- `real-pdf-*`: real readable input, actual MinerU pipeline attempt environment-blocked; not an absent document or accepted PDF pipeline.
- `publication-attempt.txt`, `github-api-response.json`: actual push exit 128 / API authentication 401. Cached branch refs are not current remote truth while authentication is broken.
- `recovery-file-inventory.json`: the 83 recovered paths. Recovery/hash/applicability evidence is not original ancestry or proof of correctness.
- `definition-review.json`: no production class/function names removed by M29 relative to recovery; not a proof of external compatibility.

Text logs have trailing whitespace normalized for Git diff hygiene. Result text, warnings and failure details are retained. No mutation is present in the committed product source. Evidence/documentation updates after the final implementation do not pretend to be another full pytest run.
