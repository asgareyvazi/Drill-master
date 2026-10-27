# Mission and audit report archive

Index of every mission report and audit record in the repository (M43, 2026-10-21).
Reports are **append-only history**: the files listed as historical are not edited,
and their verdicts describe the commit and evidence they cite at the time they were
written. Where a historical report says *certified*, *release-ready* or *closed*, that
statement is superseded for **current** status by the documents in the first table.

Current status as of this index: the installer is **UNSIGNED**; release readiness,
Windows/operator acceptance, field validation and history purge are **not** established
(see `docs/mission-reports/M43_RELEASE_HARDENING_REPORT.md`, section I).

## Current (authoritative for status)

| First committed | Report | Title |
|---|---|---|
| 2026-10-20 | [docs/mission-reports/M43_CONTINUATION_BASELINE.md](../../docs/mission-reports/M43_CONTINUATION_BASELINE.md) | M43 continuation — baseline (before any product-code change) |
| 2026-10-20 | [docs/mission-reports/M43_DATABASE_RELIABILITY_REPORT.md](../../docs/mission-reports/M43_DATABASE_RELIABILITY_REPORT.md) | M43 — Database reliability: verified backup, safe restore (Phase E/F) |
| 2026-10-20 | [docs/mission-reports/M43_RELEASE_HARDENING_REPORT.md](../../docs/mission-reports/M43_RELEASE_HARDENING_REPORT.md) | M43 — Release hardening: repository audit, privacy remediation, DB operations UX |
| 2026-10-24 | [docs/mission-reports/M44_CONNECTED_CAPABILITIES_REPORT.md](../../docs/mission-reports/M44_CONNECTED_CAPABILITIES_REPORT.md) | M44 — Connected product capabilities: operations dashboard, trajectory viewer, reviewed document import and search |
| 2026-10-25 | [docs/mission-reports/M45_DOCUMENT_TRACEABILITY_SEARCH_3D_REPORT.md](../../docs/mission-reports/M45_DOCUMENT_TRACEABILITY_SEARCH_3D_REPORT.md) | M45 — Document-to-well traceability, Persian/Arabic search normalisation and 3D survey view |
| 2026-10-25 | [docs/mission-reports/M46_DEEP_AUDIT_REGRESSION_CLOSURE_REPORT.md](../../docs/mission-reports/M46_DEEP_AUDIT_REGRESSION_CLOSURE_REPORT.md) | M46 — Deep audit, regression closure (shared-connection rollback, search parity v2, survey editor scope, test isolation), verified push |
| 2026-10-26 | [docs/mission-reports/M47_SQLITE_CONNECTION_ISOLATION_AND_SEARCH_CLOSURE_REPORT.md](../../docs/mission-reports/M47_SQLITE_CONNECTION_ISOLATION_AND_SEARCH_CLOSURE_REPORT.md) | M47 — SQLite connection isolation (per-session pool, maintenance-gate accounting), transaction safety, search span/fold v3 and link-note closure |
| 2026-10-27 | [docs/mission-reports/M48_OPERATIONS_ANALYSIS_INTEGRITY_REPORT.md](../../docs/mission-reports/M48_OPERATIONS_ANALYSIS_INTEGRITY_REPORT.md) | M48 — Operations Analysis integrity (scoped stale-free KPIs, canonical ROP, NPT coverage, transparent projection, per-currency cost, rule-based risk, evidence tab with typed export) |

## Historical (superseded for current status; content unchanged)

Dates are the first commit that added the file (full history); a date in the file
name, where present, is the audit date the report itself records.

| First committed | Report | Title |
|---|---|---|
| 2026-08-24 | [docs/AUDIT_AND_PLAN.md](../../docs/AUDIT_AND_PLAN.md) | DrillMaster - Audit کامل و نقشه فازبندی به Intelligence Platform |
| 2026-08-24 | [docs/IMPLEMENTATION_REPORT.md](../../docs/IMPLEMENTATION_REPORT.md) | DrillMaster - گزارش پیاده‌سازی Intelligence Platform |
| 2026-09-08 | [docs/REVIEW_AUDIT_2026-09.md](../../docs/REVIEW_AUDIT_2026-09.md) | ReviewItem certification audit — 2026-09-08 |
| 2026-09-08 | [docs/audits/2026-09-08-ddr/FOLLOWUP_INSPECTION.md](../../docs/audits/2026-09-08-ddr/FOLLOWUP_INSPECTION.md) | Follow-up inspection (before implementation) |
| 2026-09-08 | [docs/audits/2026-09-08-ddr/FOLLOWUP_REPORT.md](../../docs/audits/2026-09-08-ddr/FOLLOWUP_REPORT.md) | DDR lifecycle follow-up — final verification report |
| 2026-09-08 | [docs/audits/2026-09-08-ddr/MANUAL_LIFECYCLE_MATRIX.md](../../docs/audits/2026-09-08-ddr/MANUAL_LIFECYCLE_MATRIX.md) | Manual lifecycle matrix |
| 2026-09-08 | [docs/audits/2026-09-08-ddr/PRODUCTION_CREDENTIAL_LIFECYCLE_FIX.md](../../docs/audits/2026-09-08-ddr/PRODUCTION_CREDENTIAL_LIFECYCLE_FIX.md) | Production credential / reset lifecycle fix |
| 2026-09-08 | [docs/audits/2026-09-08-ddr/REPORT.md](../../docs/audits/2026-09-08-ddr/REPORT.md) | DDR forensic remediation and certification report |
| 2026-09-08 | [docs/audits/2026-09-08-ddr/REVIEW_CLASSIFICATION_65.md](../../docs/audits/2026-09-08-ddr/REVIEW_CLASSIFICATION_65.md) | Individual classification of all 65 baseline ReviewItems |
| 2026-09-09 | [docs/audits/2026-09-08-ddr/REAL_USER_ACCEPTANCE_AUDIT.md](../../docs/audits/2026-09-08-ddr/REAL_USER_ACCEPTANCE_AUDIT.md) | DrillMaster — real-user acceptance audit and remediation |
| 2026-09-09 | [docs/audits/2026-09-08-ddr/evidence/r18-r19/commands.md](../../docs/audits/2026-09-08-ddr/evidence/r18-r19/commands.md) | R18/R19 verification, 2026-09-09 |
| 2026-09-10 | [docs/audits/2026-09-09/KPI_MATRIX.md](../../docs/audits/2026-09-09/KPI_MATRIX.md) | DrillMaster — KPI Matrix (2026-09-09) |
| 2026-09-10 | [docs/audits/2026-09-09/MASTER_FORENSIC_AUDIT.md](../../docs/audits/2026-09-09/MASTER_FORENSIC_AUDIT.md) | DrillMaster — Master Forensic Audit (2026-09-09) |
| 2026-09-10 | [docs/audits/2026-09-09/PRODUCTION_ACCEPTANCE.md](../../docs/audits/2026-09-09/PRODUCTION_ACCEPTANCE.md) | DrillMaster — Production Acceptance (2026-09-09) |
| 2026-09-10 | [docs/audits/2026-09-09/SCOPE_MATRIX.md](../../docs/audits/2026-09-09/SCOPE_MATRIX.md) | DrillMaster — Scope Matrix (2026-09-09) |
| 2026-09-10 | [docs/audits/2026-09-09/VERIFICATION_PLANS.md](../../docs/audits/2026-09-09/VERIFICATION_PLANS.md) | Verification Plans — Windows GUI, Installer/Bundle, MinerU Import |
| 2026-09-10 | [docs/audits/2026-09-10_FORENSIC_REAUDIT.md](../../docs/audits/2026-09-10_FORENSIC_REAUDIT.md) | DrillMaster — Independent Forensic Re-Audit (2026-09-10) |
| 2026-09-10 | [docs/audits/2026-09-10_ZERO_SEMANTICS_IMPLEMENTATION.md](../../docs/audits/2026-09-10_ZERO_SEMANTICS_IMPLEMENTATION.md) | DrillMaster — Zero-Semantics Implementation Report (2026-09-10) |
| 2026-09-10 | [docs/audits/2026-09-11_CI_OPERATIONALIZATION.md](../../docs/audits/2026-09-11_CI_OPERATIONALIZATION.md) | CI Operationalization — Verification Phase (2026-09-11) |
| 2026-09-12 | [docs/audits/2026-09-12_BHA_BIT_FORENSIC_AUDIT.md](../../docs/audits/2026-09-12_BHA_BIT_FORENSIC_AUDIT.md) | DrillMaster — BHA / Bit Longitudinal Architecture Forensic Audit |
| 2026-09-12 | [docs/audits/2026-09-12_COST_FORENSIC_AUDIT.md](../../docs/audits/2026-09-12_COST_FORENSIC_AUDIT.md) | Cost Architecture — Forensic Audit & Canonical Ownership Certification |
| 2026-09-12 | [docs/audits/2026-09-12_DRILLING_KPI_COVERAGE_FORENSIC_AUDIT.md](../../docs/audits/2026-09-12_DRILLING_KPI_COVERAGE_FORENSIC_AUDIT.md) | DrillMaster — Drilling Engineering KPI Coverage & Data-Sufficiency Forensic Audit |
| 2026-09-12 | [docs/audits/2026-09-12_ENGINEERING_DATA_SEMANTICS_FORENSIC_AUDIT.md](../../docs/audits/2026-09-12_ENGINEERING_DATA_SEMANTICS_FORENSIC_AUDIT.md) | DrillMaster — Engineering Data Semantics & Calculation-Readiness Forensic Audit |
| 2026-09-12 | [docs/audits/2026-09-12_ENGINEERING_PERFORMANCE_COMPLETION_PASS.md](../../docs/audits/2026-09-12_ENGINEERING_PERFORMANCE_COMPLETION_PASS.md) | Engineering Performance Completion Pass |
| 2026-09-12 | [docs/audits/2026-09-12_KPI_CONSUMER_SCOPE_FORENSIC_AUDIT.md](../../docs/audits/2026-09-12_KPI_CONSUMER_SCOPE_FORENSIC_AUDIT.md) | DrillMaster — KPI Consumer Alignment & Scope-Capability Forensic Audit |
| 2026-09-12 | [docs/audits/2026-09-12_KPI_PERFORMANCE_FORENSIC_AUDIT.md](../../docs/audits/2026-09-12_KPI_PERFORMANCE_FORENSIC_AUDIT.md) | DrillMaster — KPI / Performance Architecture Forensic Audit & Canonical Intelligence Certi |
| 2026-09-12 | [docs/audits/2026-09-12_SCOPE_IDENTITY_ATTRIBUTION_PASS.md](../../docs/audits/2026-09-12_SCOPE_IDENTITY_ATTRIBUTION_PASS.md) | Scope Identity Integrity & Attribution Completion Pass |
| 2026-09-12 | [docs/audits/2026-09-12_WEIGHTED_ROP_IMPLEMENTATION_AUDIT.md](../../docs/audits/2026-09-12_WEIGHTED_ROP_IMPLEMENTATION_AUDIT.md) | Canonical Footage & Weighted ROP Engine — Implementation Audit |
| 2026-09-12 | [docs/audits/2026-09-12_WELLBORE_SCHEMA_V3.md](../../docs/audits/2026-09-12_WELLBORE_SCHEMA_V3.md) | Wellbore / Schema v3 Foundation — Forensic Report |
| 2026-09-12 | [docs/audits/2026-09-12_WELLBORE_V3_ACCEPTANCE_AUDIT.md](../../docs/audits/2026-09-12_WELLBORE_V3_ACCEPTANCE_AUDIT.md) | DrillMaster — Wellbore / Schema v3 Forensic Acceptance Audit |
| 2026-09-13 | [docs/audits/2026-09-13_CALCULATION_PERSISTENCE.md](../../docs/audits/2026-09-13_CALCULATION_PERSISTENCE.md) | Torque & Drag Calculation Persistence + Historical Reproducibility + Reference Traceabilit |
| 2026-09-13 | [docs/audits/2026-09-13_CASING_STRENGTH_CALCULATION_PERSISTENCE.md](../../docs/audits/2026-09-13_CASING_STRENGTH_CALCULATION_PERSISTENCE.md) | Casing Strength — Second Persistent Engineering Calculation (Forensic Audit + Implementati |
| 2026-09-13 | [docs/audits/2026-09-13_DRILLPIPE_CATALOG_OPERATIONALIZATION.md](../../docs/audits/2026-09-13_DRILLPIPE_CATALOG_OPERATIONALIZATION.md) | DrillPipe Reference Catalog Operationalization + Provenance Visibility |
| 2026-09-13 | [docs/audits/2026-09-13_DRILLPIPE_REFERENCE_PERSISTENCE_DECISION.md](../../docs/audits/2026-09-13_DRILLPIPE_REFERENCE_PERSISTENCE_DECISION.md) | DrillPipe Reference Persistence — Readiness Audit & Architecture Decision |
| 2026-09-13 | [docs/audits/2026-09-13_DRILLPIPE_REFERENCE_SELECTION_INTEGRATION.md](../../docs/audits/2026-09-13_DRILLPIPE_REFERENCE_SELECTION_INTEGRATION.md) | DrillPipe Reference — Deep Forensic Post-Persistence Audit + Production Selection |
| 2026-09-13 | [docs/audits/2026-09-13_DRILLPIPE_SOURCE_OF_TRUTH_CERTIFICATION.md](../../docs/audits/2026-09-13_DRILLPIPE_SOURCE_OF_TRUTH_CERTIFICATION.md) | DrillPipe Reference — Source-of-Truth Forensic Certification |
| 2026-09-13 | [docs/audits/2026-09-13_DRILLPIPE_VENDOR_IMPORT_VERTICAL_SLICE.md](../../docs/audits/2026-09-13_DRILLPIPE_VENDOR_IMPORT_VERTICAL_SLICE.md) | DrillPipe Vendor Excel → Persisted Reference Catalog — Vertical Slice + Forensics |
| 2026-09-13 | [docs/audits/2026-09-13_ENGINEERING_DATABASE_FORENSIC_AUDIT.md](../../docs/audits/2026-09-13_ENGINEERING_DATABASE_FORENSIC_AUDIT.md) | Engineering Database & Calculation Architecture — Forensic Audit + Foundation |
| 2026-09-13 | [docs/audits/2026-09-13_ENGINEERING_REFERENCE_DATA_VERIFICATION.md](../../docs/audits/2026-09-13_ENGINEERING_REFERENCE_DATA_VERIFICATION.md) | Engineering Reference-Data Architecture — Independent Verification + Repair |
| 2026-09-13 | [docs/audits/2026-09-13_IMPORT_TIME_WELLBORE_DISCRIMINATOR.md](../../docs/audits/2026-09-13_IMPORT_TIME_WELLBORE_DISCRIMINATOR.md) | Import-Time Canonical Wellbore/Section Discriminator — Forensic Pass |
| 2026-09-14 | [docs/audits/2026-09-14_CASING_REFERENCE_AUTHORITY_FORENSIC_AUDIT.md](../../docs/audits/2026-09-14_CASING_REFERENCE_AUTHORITY_FORENSIC_AUDIT.md) | Casing Reference Authority — Deep Forensic Repository Audit |
| 2026-09-14 | [docs/audits/2026-09-14_CEMENT_CALCULATION_THIRD_SLICE.md](../../docs/audits/2026-09-14_CEMENT_CALCULATION_THIRD_SLICE.md) | Calculation #3 (Cement Job Volumes) + Cross-Calculation Contract Audit |
| 2026-09-14 | [docs/audits/2026-09-14_WELL_CONTROL_INPUT_BOUNDARY_HARDENING.md](../../docs/audits/2026-09-14_WELL_CONTROL_INPUT_BOUNDARY_HARDENING.md) | Well Control Input-Boundary Hardening + Reproducibility Readiness |
| 2026-09-14 | [docs/audits/2026-09-14_WELL_CONTROL_KILL_SHEET_FOURTH_SLICE.md](../../docs/audits/2026-09-14_WELL_CONTROL_KILL_SHEET_FOURTH_SLICE.md) | Well Control Kill Sheet — Calculation #4 (Composite) Deep Forensic Audit |
| 2026-09-19 | [docs/audits/2026-09-14_WELL_CONTROL_DUAL_PATH_CONSOLIDATION.md](../../docs/audits/2026-09-14_WELL_CONTROL_DUAL_PATH_CONSOLIDATION.md) | Well Control Dual-Path Forensics + ICP/FCP Canonical Consolidation |
| 2026-09-19 | [docs/audits/2026-09-19_COMPLETE_COVERAGE_AUDIT_AND_ANTI_COLLISION_UI.md](../../docs/audits/2026-09-19_COMPLETE_COVERAGE_AUDIT_AND_ANTI_COLLISION_UI.md) | Complete-Coverage Calculation Audit + Anti-Collision UI Functionalization |
| 2026-09-19 | [docs/audits/2026-09-19_MSE_FIFTH_CALCULATION_SLICE.md](../../docs/audits/2026-09-19_MSE_FIFTH_CALCULATION_SLICE.md) | MSE (Teale) — Fifth Persistent Calculation + Five-Calculation Architecture Review |
| 2026-09-19 | [docs/audits/2026-09-19_MUD_VOLUME_SIXTH_CALCULATION_AND_MSE_DECOUPLING.md](../../docs/audits/2026-09-19_MUD_VOLUME_SIXTH_CALCULATION_AND_MSE_DECOUPLING.md) | MSE Save-Gating Decoupling + Mud Volume Sixth Persistent Calculation |
| 2026-09-19 | [docs/audits/2026-09-19_REPOSITORY_WIDE_CAPABILITY_AUDIT.md](../../docs/audits/2026-09-19_REPOSITORY_WIDE_CAPABILITY_AUDIT.md) | DrillMaster — Repository-Wide Capability Audit + Product Completion Pass |
| 2026-09-20 | [docs/audits/2026-09-20_WELLBORE_ANALYTICS_SCOPE_CERTIFICATION.md](../../docs/audits/2026-09-20_WELLBORE_ANALYTICS_SCOPE_CERTIFICATION.md) | Mission 24 — Wellbore Scope Convergence, Analytics Truth & Explicit Aggregate Certificatio |
| 2026-09-22 | [docs/audits/2026-09-22_RELEASE_CANDIDATE_INTEGRITY_CERTIFICATION.md](../../docs/audits/2026-09-22_RELEASE_CANDIDATE_INTEGRITY_CERTIFICATION.md) | DrillMaster — Release Candidate Integrity, Reproducibility, CI & Production Acceptance Bou |
| 2026-09-22 | [docs/audits/2026-09-22_REPORT_SCOPED_OWNERSHIP_INTEGRITY_CERTIFICATION.md](../../docs/audits/2026-09-22_REPORT_SCOPED_OWNERSHIP_INTEGRITY_CERTIFICATION.md) | Mission 26 — Report-Scoped Ownership, Snapshot Integrity & Cross-Scope Contamination Harde |
| 2026-09-22 | [docs/audits/2026-09-22_SCOPE_CONTRACT_COMPLETION_CERTIFICATION.md](../../docs/audits/2026-09-22_SCOPE_CONTRACT_COMPLETION_CERTIFICATION.md) | Mission 25 — Scope Contract Completion, Import→Selection Chain & Whole-Well Certification |
| 2026-09-28 | [M30_DOMAIN_MATRIX.md](../../M30_DOMAIN_MATRIX.md) | M30 domain evidence matrix |
| 2026-09-28 | [M30_RELEASE_CERTIFICATION.md](../../M30_RELEASE_CERTIFICATION.md) | M30 — release decision and 33 audit answers |
| 2026-09-28 | [M30_ROOT_CAUSES.md](../../M30_ROOT_CAUSES.md) | M30 — evidenced root causes and repairs |
| 2026-09-28 | [M30_SEMANTIC_AUDIT.md](../../M30_SEMANTIC_AUDIT.md) | Mission 30 — semantic audit checkpoint (INCOMPLETE) |
| 2026-09-28 | [M33_DOMAIN_MATRIX.md](../../M33_DOMAIN_MATRIX.md) | M33 — domain matrix (69-domain M29 taxonomy) |
| 2026-09-28 | [M33_ENGINE_DEFAULTS.md](../../M33_ENGINE_DEFAULTS.md) | M33 — Engine-default forensics (Part E) |
| 2026-09-28 | [M33_EVIDENCE_INDEX.md](../../M33_EVIDENCE_INDEX.md) | M33 — evidence index |
| 2026-09-28 | [M33_RELEASE_CERTIFICATION.md](../../M33_RELEASE_CERTIFICATION.md) | M33 — release decision and audit answers |
| 2026-09-28 | [M33_ROOT_CAUSES.md](../../M33_ROOT_CAUSES.md) | M33 — root causes |
| 2026-09-28 | [M33_SEMANTIC_AUDIT.md](../../M33_SEMANTIC_AUDIT.md) | M33 — Semantic Adjudication Closure, Engine-Default Forensics, Evidence Regeneration & Ver |
| 2026-09-28 | [M34_AUDIT_ANSWERS.md](../../M34_AUDIT_ANSWERS.md) | M34 — The 60 Required Answers |
| 2026-09-28 | [M34_DOMAIN_MATRIX.md](../../M34_DOMAIN_MATRIX.md) | M34 — 69-Domain Matrix |
| 2026-09-28 | [M34_EVIDENCE_INDEX.md](../../M34_EVIDENCE_INDEX.md) | M34 — Evidence Index |
| 2026-09-28 | [M34_FORENSIC_RECOVERY.md](../../M34_FORENSIC_RECOVERY.md) | M34 — Forensic Recovery & Method |
| 2026-09-28 | [M34_M33_RECOVERY.md](../../M34_M33_RECOVERY.md) | M34 — Mission 33 Recovery Report |
| 2026-09-28 | [M34_RELEASE_CERTIFICATION.md](../../M34_RELEASE_CERTIFICATION.md) | M34 — Release Certification |
| 2026-09-28 | [M34_ROOT_CAUSES.md](../../M34_ROOT_CAUSES.md) | M34 — Root Causes |
| 2026-09-28 | [M34_SEMANTIC_AUDIT.md](../../M34_SEMANTIC_AUDIT.md) | M34 — Semantic Audit |
| 2026-09-28 | [M35_FINAL_REPORT.md](../../M35_FINAL_REPORT.md) | M35 — FINAL REPORT (release-certification recovery) |
| 2026-09-28 | [M35_RELEASE_CERTIFICATION_RECOVERY.md](../../M35_RELEASE_CERTIFICATION_RECOVERY.md) | M35 — RELEASE-CERTIFICATION RECOVERY |
| 2026-09-28 | [docs/audits/2026-09-22_M27_INDEPENDENT_REAUDIT.md](../../docs/audits/2026-09-22_M27_INDEPENDENT_REAUDIT.md) | M27 independent forensic re-audit, repairs and release decision |
| 2026-09-28 | [docs/audits/2026-09-22_M28_FORENSIC_RELEASE_GATE.md](../../docs/audits/2026-09-22_M28_FORENSIC_RELEASE_GATE.md) | Mission 28 — Forensic re-audit, repairs and final source gate |
| 2026-09-28 | [docs/audits/2026-09-23_M29_DOMAIN_MATRIX.md](../../docs/audits/2026-09-23_M29_DOMAIN_MATRIX.md) | Mission 29 — domain/source/test coverage matrix |
| 2026-09-28 | [docs/audits/2026-09-23_M29_RELEASE_CLOSURE.md](../../docs/audits/2026-09-23_M29_RELEASE_CLOSURE.md) | Mission 29 — release closure evidence and incomplete certification audit |
| 2026-09-28 | [docs/audits/m29-evidence/README.md](../../docs/audits/m29-evidence/README.md) | Mission 29 evidence boundaries |
| 2026-09-28 | [docs/audits/m30-evidence/README.md](../../docs/audits/m30-evidence/README.md) | M30 reproducible evidence — incomplete semantic audit |
| 2026-09-28 | [docs/audits/m36-evidence/M36_RECOVERY_AND_P6_REPORT.md](../../docs/audits/m36-evidence/M36_RECOVERY_AND_P6_REPORT.md) | M36 — RECOVERY AND P6 CONTINUATION REPORT |
| 2026-09-28 | [docs/audits/m36-evidence/P6_PROGRESS.md](../../docs/audits/m36-evidence/P6_PROGRESS.md) | M36 / P6 progress — current reconciled status |
| 2026-09-28 | [docs/audits/m36-evidence/p6-batch-002.md](../../docs/audits/m36-evidence/p6-batch-002.md) | P6 p6-batch-002 — class A (safety / authorization / mutation) |
| 2026-09-28 | [docs/audits/m36-evidence/p6-batch-003.md](../../docs/audits/m36-evidence/p6-batch-003.md) | P6 p6-batch-003 — class A (safety / authorization / mutation) - all 45 records are class A |
| 2026-09-28 | [docs/audits/m36-evidence/p6-batch-004.md](../../docs/audits/m36-evidence/p6-batch-004.md) | P6 p6-batch-004 — class mixed HIGH (A safety/authorization/mutation, B data integrity, C e |
| 2026-09-28 | [docs/audits/m36-evidence/p6-batch-005.md](../../docs/audits/m36-evidence/p6-batch-005.md) | P6 p6-batch-005 — class mixed HIGH - C:37, D:8 (kill-sheet canonical inputs 26 records / 1 |
| 2026-09-28 | [docs/audits/m36-evidence/p6-batch-006.md](../../docs/audits/m36-evidence/p6-batch-006.md) | P6 p6-batch-006 — class class D (lower-risk guards/preview conveniences): D:45 |
| 2026-09-28 | [docs/audits/m36-evidence/p6-batch-007.md](../../docs/audits/m36-evidence/p6-batch-007.md) | P6 p6-batch-007 — class class E 37 / class D 8 (optional-resource loaders, narrow parser g |
| 2026-09-28 | [docs/audits/m36-evidence/p6-batch-008.md](../../docs/audits/m36-evidence/p6-batch-008.md) | P6 p6-batch-008 — class class E (import statistics/heuristics, validator comparison guards |
| 2026-09-28 | [docs/audits/m36-evidence/p6-batch-009.md](../../docs/audits/m36-evidence/p6-batch-009.md) | P6 p6-batch-009 — class class E (tab-level truthiness guards, optional plotting preludes,  |
| 2026-09-28 | [docs/audits/m36-evidence/p6-batch-010.md](../../docs/audits/m36-evidence/p6-batch-010.md) | P6 p6-batch-010 — class class E (dialog date parse, release-gate return-code checks, test- |
| 2026-10-06 | [docs/audits/2026-10-06_M40_SAFETY_CRITICAL_ENGINEERING_HARDENING.md](../../docs/audits/2026-10-06_M40_SAFETY_CRITICAL_ENGINEERING_HARDENING.md) | M40 — Safety-Critical Engineering Hardening, Canonical Hydraulics, Numerical Integrity & E |
| 2026-10-07 | [docs/audits/2026-10-07_M41_RHEOLOGY_HYDRAULICS_CERTIFICATION.md](../../docs/audits/2026-10-07_M41_RHEOLOGY_HYDRAULICS_CERTIFICATION.md) | M41 — Rheology & Hydraulics Model Certification (bounded repository evidence) |
| 2026-10-18 | [docs/audits/2026-10-18_M42_13_REL13_RESOLUTION_AND_WINDOWS_HANDOFF.md](../../docs/audits/2026-10-18_M42_13_REL13_RESOLUTION_AND_WINDOWS_HANDOFF.md) | M42.13 — REL-13 same-SHA resolution, Windows lifecycle forensics, exact-tip CI reconciliat |
| 2026-10-18 | [docs/audits/2026-10-18_M42_14_ARTIFACT_BYTE_VERIFICATION_AND_WINDOWS_HANDOFF.md](../../docs/audits/2026-10-18_M42_14_ARTIFACT_BYTE_VERIFICATION_AND_WINDOWS_HANDOFF.md) | M42.14 — Artifact byte verification, exact-tip reconciliation and controlled Windows-test  |
| 2026-10-18 | [docs/audits/2026-10-18_M42_15_RELEASE_EVIDENCE_HARDENING_AND_RUNTIME_MIGRATION.md](../../docs/audits/2026-10-18_M42_15_RELEASE_EVIDENCE_HARDENING_AND_RUNTIME_MIGRATION.md) | M42.15 — Release evidence hardening, Actions runtime migration, latest-candidate verificat |
| 2026-10-19 | [docs/MONEY_MIGRATION.md](../../docs/MONEY_MIGRATION.md) | Money representation: current state and migration design |
| 2026-10-19 | [docs/audits/2026-09-08-ddr/REDACTION_NOTICE.md](../../docs/audits/2026-09-08-ddr/REDACTION_NOTICE.md) | Redaction notice (M43, 2026-10-19) |

Out-of-repository session deliverables mentioned in some reports (for example
`/home/user/M42_9_REPORT.md`) are not part of the repository and are not indexed.
