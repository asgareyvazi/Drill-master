"""Headless release smoke checks for startup and optional capability boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

from core.runtime_config import database_path, describe_paths


ROOT = Path(__file__).resolve().parent.parent


def test_runtime_paths_are_deployment_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(tmp_path / "user-data"))
    monkeypatch.delenv("DRILLMASTER_DB_PATH", raising=False)
    paths = describe_paths()
    assert paths["database"].startswith(str(tmp_path / "user-data"))
    assert paths["log_dir"].startswith(str(tmp_path / "user-data"))
    assert database_path().endswith("drillmaster.db")


def test_production_schema_auth_and_fixture_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("DRILLMASTER_ENV", "production")
    monkeypatch.setenv("DRILLMASTER_DB_PATH", str(tmp_path / "drillmaster.sqlite"))
    monkeypatch.setenv("DRILLMASTER_ADMIN_PASSWORD", "release-admin-password-9a")
    monkeypatch.setenv("DRILLMASTER_USER_PASSWORD", "release-engineer-password-9b")
    monkeypatch.setenv("DRILLMASTER_VIEWER_PASSWORD", "release-viewer-password-9c")

    from core.database import Company, DatabaseManager, User

    manager = DatabaseManager()
    assert manager.initialize() is True
    try:
        session = manager.create_session()
        try:
            assert session.query(User).count() == 3
            assert session.query(Company).count() == 0
            version = session.execute(
                __import__("sqlalchemy").text("SELECT MAX(version) FROM schema_version")
            ).scalar()
            assert version == 1
        finally:
            session.close()
        assert manager.authenticate_user("admin", "release-admin-password-9a")
        assert manager.authenticate_user("admin", "admin123") is None
        backup = tmp_path / "backup" / "verified.db"
        assert manager.backup_to(backup) == str(backup)
        assert manager.backup_to(manager.db_path) is None
    finally:
        manager.close()


def test_reopen_upgrade_preserves_production_hierarchy(tmp_path, monkeypatch):
    monkeypatch.setenv("DRILLMASTER_ENV", "production")
    monkeypatch.setenv("DRILLMASTER_DB_PATH", str(tmp_path / "upgrade.sqlite"))
    monkeypatch.setenv("DRILLMASTER_ADMIN_PASSWORD", "release-admin-password-9a")
    monkeypatch.setenv("DRILLMASTER_USER_PASSWORD", "release-engineer-password-9b")
    monkeypatch.setenv("DRILLMASTER_VIEWER_PASSWORD", "release-viewer-password-9c")

    from core.database import Company, DatabaseManager, Project, Well

    first = DatabaseManager()
    assert first.initialize() is True
    session = first.create_session()
    try:
        company = Company(name="Upgrade Company", code="UPG-C")
        session.add(company)
        session.flush()
        project = Project(company_id=company.id, name="Upgrade Project", code="UPG-P")
        session.add(project)
        session.flush()
        session.add(Well(project_id=project.id, name="Upgrade Well", code="UPG-W"))
        session.commit()
    finally:
        session.close()
        first.close()

    second = DatabaseManager()
    assert second.initialize() is True
    try:
        hierarchy = second.get_hierarchy()
        assert any(company["name"] == "Upgrade Company" for company in hierarchy)
        session = second.create_session()
        try:
            version = session.execute(
                __import__("sqlalchemy").text("SELECT MAX(version) FROM schema_version")
            ).scalar()
            assert version == 1
        finally:
            session.close()
    finally:
        second.close()


def test_engineering_registry_and_export_interfaces_are_importable():
    from core.engineering import CalculatorBridge, EngineeringResult, capability_registry
    from core.ddr_pdf_export import DDRPDFExporter
    from core.professional_export import ProfessionalExcelExport, ProfessionalPDFExport

    assert CalculatorBridge is not None
    assert EngineeringResult is not None
    assert capability_registry is not None
    assert DDRPDFExporter is not None
    assert ProfessionalExcelExport is not None
    assert ProfessionalPDFExport is not None


def test_w12_w13_headless_interfaces_and_optional_ai_status(monkeypatch):
    w12_tree = ast.parse((ROOT / "tabs" / "w12_Analysis.py").read_text(encoding="utf-8"))
    w13_source = (ROOT / "tabs" / "w13_Engineering_Calculator.py").read_text(encoding="utf-8")
    w13_tree = ast.parse(w13_source)
    w12_classes = {node.name for node in w12_tree.body if isinstance(node, ast.ClassDef)}
    w13_classes = {node.name for node in w13_tree.body if isinstance(node, ast.ClassDef)}
    assert "AnalysisWidget" in w12_classes
    assert {"DrillingCalculationEngine", "EngineeringCalculatorTab"} <= w13_classes

    monkeypatch.delenv("DRILLMASTER_AI_IMPORT", raising=False)
    from core.ai_import_mapper import AIImportMapper
    from core.optional_capabilities import detect_optional_capabilities

    mapper = AIImportMapper()
    assert mapper.enabled is False
    assert mapper.available() is False
    assert mapper.last_status == "disabled"
    capabilities = detect_optional_capabilities()
    assert capabilities["ollama"]["status"] == "disabled"
    assert capabilities["qwen"]["status"] == "disabled"
    assert capabilities["mineru"]["network_probed"] is False
