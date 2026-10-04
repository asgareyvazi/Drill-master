"""Guard the single current release-status source and dated-report boundaries."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LIVING_PRODUCT_DOCS = (
    "AI_MAPPING.md",
    "ARCHITECTURE.md",
    "DATABASE_ARCHITECTURE.md",
    "DEPLOYMENT.md",
    "ENGINEERING_ARCHITECTURE.md",
    "ENGINEERING_CAPABILITY_STATUS.md",
    "ENGINEERING_REFERENCE_MATRIX.md",
    "IMPORT_PIPELINE.md",
    "README.md",
    "TESTING.md",
    "docs/ENGINEERING_ARCHITECTURE.md",
    "docs/WINDOWS_ACCEPTANCE.md",
)


def test_living_product_docs_defer_release_verdict_to_canonical_status():
    stale_banner = "Current evidence — 2026-09-27: [Mission 33 semantic audit]"
    for relative in LIVING_PRODUCT_DOCS:
        opening = (ROOT / relative).read_text(encoding="utf-8")[:1600]
        assert "PRODUCTION_READINESS.md" in opening, relative
        assert stale_banner not in opening, relative
        assert "8934" not in opening and "NOT RELEASE-CERTIFIABLE" not in opening, relative


def test_canonical_status_separates_repository_gate_from_external_acceptance():
    status = (ROOT / "PRODUCTION_READINESS.md").read_text(encoding="utf-8")
    assert "Current release status" in status
    assert "PROVENANCE_EXTERNAL_SOURCE_UNAVAILABLE" in status
    assert "Real DDR PDF" in status and "NOT RUN" in status
    assert "production-database" in status and "operator/business acceptance" in status
    assert "any later candidate" in status


def test_older_release_snapshots_are_explicitly_historical():
    for relative in (
        "ENGINEERING_AUDIT.md",
        "ENGINEERING_REFERENCE_MATRIX.md",
        "RELEASE_NOTES.md",
        "M35_FINAL_REPORT.md",
        "M35_RELEASE_CERTIFICATION_RECOVERY.md",
        "M34_RELEASE_CERTIFICATION.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")[:1600]
        assert "Historical" in text or "HISTORICAL" in text, relative
        assert "PRODUCTION_READINESS.md" in text, relative
