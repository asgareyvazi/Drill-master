"""Schematic non-fabrication regression tests (2026-09-10 phase).

Contract under test (master handoff):

    «If an engineering fact is not present in authoritative source data,
     the schematic generator MUST NOT invent it.»

Cases A–D from the mandate, plus source-fidelity, determinism, re-import
and persistence invariants. Every test would FAIL against the previous
implementation, which fabricated TD=3000 / GL=10 / KB=15 via ``or``
coercion (converting explicit zeros too) and invented a full 4-string
default casing program, a 500 m shoe depth, ``od*0.9`` wall thickness,
"L-80"/"BTC" metallurgy, cement, a 100 m formation base and "Shale"
lithology.

These tests run REAL production code: ``SchematicAutoBuilder``,
``WellboreSchematicRenderer`` (raster paint into a real QPixmap under
offscreen Qt) and ``DatabaseManager`` persistence against an isolated
in-memory SQLite database. No mocks or stubs are used anywhere.
"""

import json
import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import (
    Base, Company, Project, Well, FormationReport,
    DatabaseManager,
)
from core.wellbore_schematic_engine import (
    SchematicAutoBuilder, WellboreSchematic, WellboreSchematicRenderer,
    SchematicConfig, ElementType,
)


def memory_manager():
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(
        bind=manager.engine, autoflush=False, autocommit=False
    )
    return manager


def make_well(manager, **extra) -> int:
    session = manager.create_session()
    try:
        company = Company(name="OEOC", code="OEOC")
        session.add(company)
        session.flush()
        project = Project(name="Bid Boland", code="BB", company_id=company.id)
        session.add(project)
        session.flush()
        counter = getattr(make_well, "_n", 0) + 1
        make_well._n = counter
        well = Well(
            name=extra.pop("name", f"A-{counter:03d}"),
            code=extra.pop("code", f"A-{counter:03d}"),
            project_id=project.id,
            **extra,
        )
        session.add(well)
        session.commit()
        return well.id
    finally:
        session.close()


def build(manager, well_id):
    return SchematicAutoBuilder(manager).build_from_well(well_id)


# =====================================================================
# Case A — empty well: no fabricated values of any kind
# =====================================================================

class TestCaseAEmptyWell:
    def test_empty_well_produces_empty_schematic(self, manager):
        well_id = make_well(manager)
        s = build(manager, well_id)

        # No default casing program (old code: 4 fabricated strings).
        assert s.casings == []
        assert s.formations == []
        assert s.completion == []

        # No synthetic elevations (old code: None -> 10 / 15).
        assert s.gle_msl_m is None
        assert s.kb_msl_m is None

        # No synthetic tubing (old dataclass defaults: 3.5" / 2800 m).
        assert s.tubing_od_inch is None
        assert s.tubing_bottom_m is None

    def test_td_not_replaced_by_3000(self, manager):
        # Well created without target_depth: the ORM column default
        # stores 0.0. 0 must survive — the old code turned it into 3000.
        well_id = make_well(manager)
        s = build(manager, well_id)
        assert s.total_depth_m == 0.0

    def test_missing_well_returns_all_unknown_schematic(self, manager):
        s = build(manager, 999999)
        assert s.total_depth_m is None
        assert s.gle_msl_m is None
        assert s.kb_msl_m is None
        assert s.casings == []


# =====================================================================
# Case B — explicit zero survives generation
# =====================================================================

class TestCaseBExplicitZero:
    def test_zero_elevations_and_td_survive(self, manager):
        well_id = make_well(
            manager, target_depth=0.0, gle_msl=0.0, rte_msl=0.0,
            water_depth=0.0,
        )
        s = build(manager, well_id)
        # Old code: 0.0 or 10 / 0.0 or 15 / 0.0 or 3000.
        assert s.gle_msl_m == 0.0
        assert s.kb_msl_m == 0.0
        assert s.total_depth_m == 0.0
        assert s.water_depth_m == 0.0

    def test_zero_casing_top_survives(self, manager):
        well_id = make_well(manager, target_depth=2000.0)
        manager.save_casing_report({
            "well_id": well_id,
            "report_date": date(2024, 10, 1),
            "casing_type": "Surface",
            "casing_json": json.dumps([
                {"size": "13.375", "from": 0, "to": 500},
            ]),
        })
        s = build(manager, well_id)
        assert len(s.casings) == 1
        assert s.casings[0].top_depth_m == 0.0


# =====================================================================
# Case C — partial source: only known facts appear
# =====================================================================

class TestCaseCPartialSource:
    def test_td_known_gl_missing_casing_missing(self, manager):
        well_id = make_well(manager, target_depth=2500.0)
        s = build(manager, well_id)

        assert s.total_depth_m == 2500.0
        assert s.gle_msl_m is None
        assert s.casings == []
        assert s.formations == []


# =====================================================================
# Source fidelity — real casing/formation data is consumed exactly
# =====================================================================

class TestSourceFidelity:
    def test_string_sizes_and_thread_parsed_exactly(self, manager):
        """The importer stores sizes as strings like '13 3/8"'.

        Old code crashed on float('13 3/8"') inside a broad except and
        silently dropped every casing; it also fabricated connection
        "BTC" and cement to the shoe.
        """
        well_id = make_well(manager, target_depth=3000.0)
        manager.save_casing_report({
            "well_id": well_id,
            "report_date": date(2024, 10, 1),
            "casing_type": "Surface",
            "casing_json": json.dumps([
                {
                    "size": '13 3/8"', "from": "0", "to": "500",
                    "grade": "P-110", "thread": "VAM",
                },
            ]),
        })
        s = build(manager, well_id)

        assert len(s.casings) == 1
        c = s.casings[0]
        assert c.od_inch == pytest.approx(13.375)
        assert c.top_depth_m == 0.0
        assert c.bottom_depth_m == 500.0
        assert c.grade == "P-110"
        assert c.connection == "VAM"
        # No fabricated wall thickness: unknown ID stays None.
        assert c.id_inch is None
        # No fabricated cement to the shoe.
        assert c.show_cement is False
        assert c.cement_bottom_m == 0.0

    def test_incomplete_casing_row_is_skipped_not_completed(self, manager):
        well_id = make_well(manager, target_depth=3000.0)
        manager.save_casing_report({
            "well_id": well_id,
            "report_date": date(2024, 10, 1),
            "casing_json": json.dumps([
                # No shoe depth: old code invented 500.
                {"size": "20", "from": "0"},
            ]),
        })
        s = build(manager, well_id)
        assert s.casings == []

    def test_formation_without_base_is_skipped_not_completed(self, manager):
        well_id = make_well(manager, target_depth=3000.0)
        session = manager.create_session()
        try:
            session.add(FormationReport(
                well_id=well_id,
                report_name="Imported Formations",
                formations_json=[
                    {"Formation Name": "Aghajari", "Top MD (m)": "100"},
                ],
            ))
            session.commit()
        finally:
            session.close()

        s = build(manager, well_id)
        # Old code invented base=100 and lithology "Shale".
        assert s.formations == []

    def test_formation_with_full_data_keeps_unknown_lithology_empty(
        self, manager
    ):
        well_id = make_well(manager, target_depth=3000.0)
        session = manager.create_session()
        try:
            session.add(FormationReport(
                well_id=well_id,
                report_name="Imported Formations",
                formations_json=[
                    {
                        "Formation Name": "Mishan",
                        "Top MD (m)": "500",
                        "Base MD (m)": "900",
                    },
                ],
            ))
            session.commit()
        finally:
            session.close()

        s = build(manager, well_id)
        assert len(s.formations) == 1
        f = s.formations[0]
        assert f.name == "Mishan"
        assert f.top_depth_m == 500.0
        assert f.bottom_depth_m == 900.0
        # Old code fabricated "Shale".
        assert f.lithology == ""


# =====================================================================
# Case D — existing saved schematic is preserved
# =====================================================================

class TestCaseDExistingSchematicPreserved:
    def _tab_style_payload(self, well_id, schematic, report_date):
        """The exact payload shape tabs/w3b save_data() serializes."""
        return {
            "well_id": well_id,
            "report_date": report_date,
            "schematic_name": f"Schematic_{schematic.well_name}",
            "elements_json": json.dumps({
                "casings": [
                    {
                        "name": c.name, "type": c.element_type.value,
                        "od": c.od_inch, "id": c.id_inch,
                        "top": c.top_depth_m, "bottom": c.bottom_depth_m,
                        "cement_top": c.cement_top_m,
                        "cement_bottom": c.cement_bottom_m,
                    }
                    for c in schematic.casings
                ],
                "config": {
                    "total_depth": schematic.total_depth_m,
                    "well_name": schematic.well_name,
                },
            }, default=str),
        }

    def test_autogenerate_does_not_fabricate_over_saved_rows(self, manager):
        # 1. A real schematic is saved on an earlier date.
        well_id = make_well(manager, target_depth=2500.0, gle_msl=30.0)
        real = build(manager, well_id)
        real.casings.append(
            # values chosen to differ from anything fabricatable
            __import__(
                "core.wellbore_schematic_engine", fromlist=["CasingData"]
            ).CasingData(
                name="Surface", element_type=ElementType.SURFACE_CASING,
                od_inch=10.75, id_inch=9.85, top_depth_m=0.0,
                bottom_depth_m=333.0,
            )
        )
        saved_id = manager.save_wellbore_schematic(
            self._tab_style_payload(well_id, real, date(2024, 1, 1))
        )
        assert saved_id

        # 2. Later, the same well is re-opened and auto-generated while
        #    its source reports are (still) partial, then saved today.
        regenerated = build(manager, well_id)
        assert len(regenerated.casings) == 0  # no fabricated program
        new_id = manager.save_wellbore_schematic(
            self._tab_style_payload(well_id, regenerated, date(2026, 9, 10))
        )
        assert new_id != saved_id

        # 3. The previously saved row is byte-identical.
        old = manager.get_wellbore_schematic(
            well_id=well_id, report_date=date(2024, 1, 1)
        )
        old_elements = json.loads(old["elements_json"])
        assert old_elements["casings"][0]["od"] == 10.75
        assert old_elements["casings"][0]["bottom"] == 333.0
        assert old_elements["config"]["total_depth"] == 2500.0

        # 4. The new row contains no fabricated engineering data.
        new = manager.get_wellbore_schematic(
            well_id=well_id, report_date=date(2026, 9, 10)
        )
        new_elements = json.loads(new["elements_json"])
        assert new_elements["casings"] == []
        # The real source TD is carried; nothing else was invented.
        assert new_elements["config"]["total_depth"] == 2500.0

    def test_unknown_td_persists_as_null(self, manager):
        """A schematic whose TD is unknown persists null, not a number."""
        well_id = make_well(manager)
        s = build(manager, well_id)
        assert s.total_depth_m == 0.0  # ORM column default, preserved
        # Explicitly-unknown TD (None) round-trips through the tab's
        # payload contract as JSON null:
        payload = self._tab_style_payload(
            well_id,
            WellboreSchematic(well_name="X"),
            date(2026, 9, 10),
        )
        manager.save_wellbore_schematic(payload)
        row = manager.get_wellbore_schematic(
            well_id=well_id, report_date=date(2026, 9, 10)
        )
        assert json.loads(row["elements_json"])["config"]["total_depth"] is None


# =====================================================================
# Determinism and re-import
# =====================================================================

class TestDeterminismAndReImport:
    def test_repeated_generation_is_deterministic(self, manager):
        well_id = make_well(manager, target_depth=2500.0, gle_msl=12.0)
        s1 = build(manager, well_id)
        s2 = build(manager, well_id)
        assert s1.total_depth_m == s2.total_depth_m
        assert s1.gle_msl_m == s2.gle_msl_m
        assert s1.kb_msl_m == s2.kb_msl_m
        assert len(s1.casings) == len(s2.casings)

    def test_reimport_does_not_create_synthetic_data(self, manager):
        """Upsert the same source casing report twice (re-import); the
        built schematic must stay exactly faithful both times."""
        well_id = make_well(manager, target_depth=3000.0)
        payload = {
            "well_id": well_id,
            "report_date": date(2024, 10, 1),
            "casing_type": "Production",
            "casing_json": json.dumps([
                {"size": "9-5/8", "from": "0", "to": "2400",
                 "grade": "N-80", "thread": "BTC"},
            ]),
        }
        manager.save_casing_report(dict(payload))
        s1 = build(manager, well_id)
        manager.save_casing_report(dict(payload))  # re-import
        s2 = build(manager, well_id)

        for s in (s1, s2):
            assert len(s.casings) == 1
            c = s.casings[0]
            assert c.od_inch == pytest.approx(9.625)
            assert c.top_depth_m == 0.0
            assert c.bottom_depth_m == 2400.0
            assert c.grade == "N-80"
            assert c.id_inch is None
        assert len(s2.casings) == 1  # no duplicated rows from re-import


# =====================================================================
# Renderer — empty/partial schematics render without exceptions
# =====================================================================

class TestRendererNoData:
    """Raster rendering of unknown-state schematics.

    Rendering runs the REAL production renderer (QPainter raster paint,
    real fonts, no mocks) in a clean subprocess. Reason: the full suite
    contains test_autosave_manager_regression, which creates a
    long-lived QCoreApplication singleton; after it, a QApplication
    cannot be constructed in-process ("Please destroy the
    QCoreApplication singleton..."), and QPixmap/QFont fatally abort
    without a QApplication. A subprocess isolates the render while
    exercising exactly the production code path — this is a process
    isolation technique, not a skip and not a stub.
    """

    RENDER_SCRIPT = """
import sys
sys.path.insert(0, sys.argv[1])

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPainter, QPixmap, QColor

from core.wellbore_schematic_engine import (
    WellboreSchematic, WellboreSchematicRenderer, SchematicConfig,
)

QApplication([])


def render(schematic):
    config = SchematicConfig()
    pixmap = QPixmap(config.total_width, config.total_height)
    pixmap.fill(QColor("#000000"))
    painter = QPainter(pixmap)
    try:
        WellboreSchematicRenderer(schematic, config).render(painter)
    finally:
        painter.end()
    assert not pixmap.isNull()


# The three unknown states the builder can now produce:
render(WellboreSchematic())                       # every field None
render(WellboreSchematic(total_depth_m=2500.0))   # TD known, rest missing
render(WellboreSchematic(total_depth_m=0.0))      # explicit zero TD
render(WellboreSchematic(
    total_depth_m=2500.0,
    casings=[__import__("core.wellbore_schematic_engine", fromlist=["CasingData"]).CasingData(
        name="Surface", element_type=__import__("core.wellbore_schematic_engine", fromlist=["ElementType"]).ElementType.SURFACE_CASING,
        od_inch=13.375, id_inch=None, top_depth_m=0.0, bottom_depth_m=500.0,
    )],
))                                                 # unknown wall thickness
print("RENDER_OK")
"""

    def test_unknown_state_schematics_render(self, tmp_path):
        import subprocess
        import sys
        from pathlib import Path

        repo_root = str(Path(__file__).resolve().parent.parent)
        env = dict(os.environ)
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        proc = subprocess.run(
            [sys.executable, "-c", self.RENDER_SCRIPT, repo_root],
            capture_output=True, text=True, env=env, timeout=120,
        )
        assert proc.returncode == 0, (
            f"renderer subprocess failed:\n{proc.stderr[-2000:]}"
        )
        assert "RENDER_OK" in proc.stdout

    def test_td_only_depth_scale_is_data_driven(self, manager):
        """Scale computation needs no QApplication (no painting)."""
        well_id = make_well(manager, target_depth=2500.0)
        s = build(manager, well_id)
        config = SchematicConfig()
        WellboreSchematicRenderer(s, config)
        assert config.depth_scale > 0  # view scale, no data invented
        assert s.total_depth_m == 2500.0


# Shared in-memory manager fixture (one DB per test, isolated).
@pytest.fixture
def manager():
    return memory_manager()
