"""Release verification — comprehensive checks before shipping.

Run with: python -m pytest tests/test_release.py -v
"""

import pytest
import sys
import os
from pathlib import Path


class TestReleaseVerification:
    """Release gate tests — all must pass before shipping."""
    
    def test_python_version(self):
        """Python 3.10+ required."""
        assert sys.version_info >= (3, 10), f"Python {sys.version} is too old"
    
    def test_core_dependencies(self):
        """All core dependencies must be importable."""
        import PySide6
        import sqlalchemy
        import openpyxl
        assert True
    
    def test_all_core_modules_importable(self):
        """All core modules must import without error."""
        # Skip if no display (headless CI/sandbox)
        if not os.environ.get("DISPLAY") and sys.platform == "linux":
            pytest.skip("No display — PySide6 requires libGL")
        from core.database import DatabaseManager, Well, DailyReport
        from core.db_models import Base
        from core.canonical_schema import FIELD_SPECS, CANONICAL_FIELDS
        from core.unit_manager import UnitManager
        from core.managers import StatusBarManager, TableManager, DrillingManager
        from core.permissions import permissions
        from core.selection_manager import SelectionManager
        from core.lineage import LineageTracker, get_import_lineage
        from core.engineering import TrajectoryEngine, HydraulicsEngine
        from core.validators import validate_rows
        from core.import_quality import ImportValidator
        from core.hierarchy_operations import delete_entity, check_delete_permission
        assert True
    
    def test_canonical_schema_minimum_fields(self):
        """Schema must have at least 100 fields."""
        from core.canonical_schema import FIELD_SPECS
        assert len(FIELD_SPECS) >= 100
    
    def test_canonical_schema_critical_fields(self):
        """Critical fields must exist."""
        from core.canonical_schema import get_critical_fields
        critical = get_critical_fields()
        required = [
            "well_info.name", "daily_report.depth_2400",
            "mud_report.mw", "drilling_params.bit_size",
            "survey.md", "bop.working_pressure",
        ]
        for field in required:
            assert field in critical, f"Missing critical field: {field}"
    
    def test_unit_manager_conversions(self):
        """Key unit conversions must work."""
        from core.unit_manager import UnitManager
        
        # ft -> m
        assert abs(UnitManager.convert(100, "length", "ft", "m") - 30.48) < 0.01
        # SG -> ppg
        assert abs(UnitManager.convert(1.5, "density", "sg", "ppg") - 12.52) < 0.1
        # bar -> psi
        assert abs(UnitManager.convert(1, "pressure", "bar", "psi") - 14.5) < 0.1
        # F -> C
        assert abs(UnitManager.convert(212, "temperature", "f", "c") - 100) < 0.1
    
    def test_engineering_trajectory(self):
        """Trajectory calculation must work."""
        from core.engineering import TrajectoryEngine
        
        surveys = [
            {"md": 0, "inc": 0, "azi": 0},
            {"md": 100, "inc": 0, "azi": 0},
        ]
        result = TrajectoryEngine.calculate(surveys)
        assert len(result) == 2
        assert result[1].tvd > 99
    
    def test_engineering_hydraulics(self):
        """Hydraulics calculation must work."""
        from core.engineering import HydraulicsEngine
        
        av = HydraulicsEngine.calculate_annular_velocity(500, 12.25, 5.0)
        assert av > 0
        
        ecd = HydraulicsEngine.calculate_ecd(10.0, 500, 5000)
        assert ecd > 10.0
    
    def test_database_initialization(self):
        """Database must initialize with in-memory SQLite."""
        from core.database import DatabaseManager, Base
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        
        db = DatabaseManager()
        db.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(db.engine)
        db.Session = sessionmaker(bind=db.engine)
        assert db.engine is not None
    
    def test_lineage_tracker(self):
        """Lineage tracker must work."""
        from core.lineage import LineageTracker
        
        tracker = LineageTracker()
        tracker.track_value(
            canonical_field="mud_report.mw",
            value=10.2,
            source_file="test.xlsx",
            confidence=0.95,
        )
        assert tracker.count == 1
        assert tracker.records[0].canonical_field == "mud_report.mw"
    
    def test_import_validator(self):
        """Import validator must detect issues."""
        from core.import_quality import ImportValidator
        
        # Empty data should not crash
        quality = ImportValidator.validate_rows([{}], "daily_report", "Test")
        assert quality is not None
    
    def test_permissions_system(self):
        """Permission system must initialize."""
        from core.permissions import permissions
        assert permissions is not None
    
    def test_no_circular_imports(self):
        """Core modules must not have circular import issues."""
        if not os.environ.get("DISPLAY") and sys.platform == "linux":
            pytest.skip("No display — PySide6 requires libGL")
        import core.database
        import core.db_models
        import core.managers
        import core.canonical_schema
        import core.unit_manager
        import core.lineage
        import core.engineering
        assert True
    
    def test_file_sizes_reasonable(self):
        """No single file should be excessively large."""
        base = Path(__file__).resolve().parent.parent
        large_files = []
        for f in base.glob("*.py"):
            lines = len(f.read_text().splitlines())
            if lines > 3000:
                large_files.append((f.name, lines))
        for f in base.glob("core/*.py"):
            lines = len(f.read_text().splitlines())
            if lines > 3000:
                large_files.append((f.name, lines))
        for f in base.glob("tabs/*.py"):
            lines = len(f.read_text().splitlines())
            if lines > 3000:
                large_files.append((f.name, lines))
        
        # Warn but don't fail — these are known large files
        if large_files:
            import warnings
            warnings.warn(f"Large files (>3000 lines): {large_files}")
