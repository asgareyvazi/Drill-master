# Contributing to DrillMaster

## Setup

Python 3.10–3.13 (CI uses 3.11, 3.12 and 3.13).

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install -r requirements-lock.txt pytest==9.1.1 ruff==0.16.6 build==1.6.1
```

Headless Linux needs the system OpenGL runtime (`libgl1`) for the Qt tests and
`QT_QPA_PLATFORM=offscreen`.

## The gate every change must pass

```bash
python verify_release.py --allow-dirty   # development run of the CI gate
```

CI runs `python verify_release.py --expected-sha "$GITHUB_SHA"` on Linux for
3.11/3.12/3.13. It checks dependencies, resources and the version, applies
the lint policy, compiles the sources, runs the full test suite and builds and
smoke-starts the wheel. Policy enforced along the way:

- `ruff` E722 (bare except) and F821 (undefined name) must be zero;
- total ruff debt over `core dialogs tabs tests` must not exceed
  `.github/ruff-debt-ceiling.txt`;
- unexplained silent exception handlers must not exceed
  `.github/exception-silent-ceiling.json`
  (`python tools/quality/exception_scan.py --check .github/exception-silent-ceiling.json`,
  enforced by `tests/test_exception_scan.py`);
- `tools/privacy/privacy_check.py` must report no findings (enforced by
  `tests/test_privacy_check.py`).

Ceilings are ratchets: lower them in the same commit that lowers the measured
count; never raise them.

## Rules

- **No real data.** Never commit a real daily drilling report, PDF, database,
  log or screenshot of operational data, personnel names or coordinates. Build
  fixtures with `tests/create_fixtures.py` or `tools/privacy/sanitize_ddr_workbook.py`
  and allowlist them by hash (`docs/privacy/PRIVACY_CHECK.md`). Do not upload
  real reports to external services.
- **No secrets.** No passwords, tokens, keys or certificates in code, tests,
  logs or commit messages. Development fixture passwords are refused in
  production mode by design.
- **Tests are not weakened.** Do not delete, skip, xfail or relax a test, or
  change an engineering threshold, without evidence and a written reason.
- **Engineering methods** require an exact published reference and a golden
  test; screening calculations are not labelled validated.
- **Schema changes** are additive and idempotent, bump
  `DatabaseManager.schema_version`, and add an upgrade test; `tests/test_model_registry.py`
  must keep fresh and upgraded databases identical. The ORM is declared only in
  `core/database.py`.
- **Claims match evidence.** Documentation states what was verified, by what,
  and what was not run.

## Commits and branches

Use conventional commits (`fix(scope): …`, `feat(scope): …`, `test(…)`,
`docs(…)`), one purpose per commit. Do not force-push shared branches or
rewrite history; history rewrites, release signing, licence selection and
acceptance sign-off are owner decisions.
