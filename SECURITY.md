# Security policy

## Status

DrillMaster has **no supported release** yet. Builds are **UNSIGNED** and have
not completed Windows or field acceptance (see `PRODUCTION_READINESS.md`).
Security fixes are made on the active development branch.

## Reporting a vulnerability

Please do **not** open a public issue containing exploit details, credentials
or real operational data (daily reports, personnel names, coordinates).

- Preferred: GitHub private vulnerability reporting ("Report a vulnerability"
  on the repository's Security tab). *At the time of writing this is not
  enabled on the repository; enabling it is an owner action (Settings → Code
  security → Private vulnerability reporting).*
- Until it is enabled: open a public issue that says only that you have a
  security report and how to reach you, and the maintainer will arrange a
  private channel.

Include the affected commit SHA, the steps to reproduce with synthetic data,
and the impact you observed. Expect an acknowledgement, a fix or mitigation on
the development branch, and credit if you want it. No timelines are promised
for an unreleased project.

## Scope and current security model (summary)

| Area | Current behaviour | Limits |
|---|---|---|
| Accounts | bcrypt password hashes (verification fails closed); persistent per-account lockout with exponential backoff, configurable, audited, admin unlock; production mode refuses development passwords and non-bcrypt stored hashes at startup and at login | single local application, no network service; no unlock or user-management UI yet |
| Authorization | role and permission model in `core/permissions.py`, enforced in the UI and, after login, for every ORM mutation in the data layer (`core/authorization.py`); denials audited | reads are not role-restricted; code with direct file access is not restricted |
| Data at rest | local SQLite database in the user data directory (`DRILLMASTER_DATA_DIR` overrides) | **not encrypted**; protect it with OS account and disk encryption |
| Privacy | `tools/privacy/privacy_check.py` gates the tracked tree; real DDRs are never committed | real data remains in Git history until the owner-gated purge (`docs/privacy/HISTORY_PURGE_PLAN.md`) |
| Supply chain | pinned lock file; CI actions pinned by full commit SHA | builds are unsigned (SmartScreen warnings expected) |

Out of scope: social engineering, physical access to an unlocked workstation,
and vulnerabilities in third-party dependencies without a DrillMaster-specific
exploit path (report those upstream).

Details, trust boundary and test evidence: `docs/SECURITY_MODEL.md`.
