"""Regression: get_hierarchy() must expose the real persisted well updated_at.

The Home tab previously rendered a hard-coded "Today" for every well's
"Last Update" column (fabricated display value). The fix surfaces the real
``Well.updated_at`` through ``get_hierarchy`` so the UI can show an honest
timestamp (or "—" when unavailable). This guards the data contract Qt-free.
"""
from __future__ import annotations

import os

import pytest


def _fresh_manager(tmp_path, monkeypatch):
    monkeypatch.setenv("DRILLMASTER_ENV", "production")
    monkeypatch.setenv("DRILLMASTER_DB_PATH", str(tmp_path / "hier.sqlite"))
    monkeypatch.setenv("DRILLMASTER_ADMIN_PASSWORD", "release-admin-password-9a")
    monkeypatch.setenv("DRILLMASTER_USER_PASSWORD", "release-engineer-password-9b")
    monkeypatch.setenv("DRILLMASTER_VIEWER_PASSWORD", "release-viewer-password-9c")
    from core.database import DatabaseManager

    m = DatabaseManager()
    assert m.initialize() is True
    return m


def test_get_hierarchy_exposes_well_updated_at(tmp_path, monkeypatch):
    from datetime import datetime

    from core.database import Company, Project, Well

    m = _fresh_manager(tmp_path, monkeypatch)
    try:
        session = m.create_session()
        try:
            company = Company(name="Hier Co", code="HC")
            session.add(company)
            session.flush()
            project = Project(company_id=company.id, name="Hier Proj", code="HP")
            session.add(project)
            session.flush()
            session.add(Well(project_id=project.id, name="Hier Well", code="HW"))
            session.commit()
        finally:
            session.close()

        hierarchy = m.get_hierarchy()
        wells = [
            w
            for c in hierarchy
            for p in c["projects"]
            for w in p["wells"]
            if w["name"] == "Hier Well"
        ]
        assert len(wells) == 1, "seeded well must be present in hierarchy"
        well = wells[0]
        # The contract: key present, and it is a real timestamp (not a fabricated string).
        assert "updated_at" in well, "hierarchy must expose updated_at for honest display"
        assert well["updated_at"] is None or isinstance(well["updated_at"], datetime)
    finally:
        m.close()
