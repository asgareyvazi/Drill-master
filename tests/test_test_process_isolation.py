"""Even an explicitly configured test mode must not seed an operator DB."""
import os
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("mode", ["test", "development", "production"])
def test_pytest_paths_are_disposable_with_explicit_mode(monkeypatch, tmp_path, mode):
    hooks = runpy.run_path(str(Path(__file__).with_name("conftest.py")))
    operator_db = tmp_path / "operator.db"
    operator_db.write_bytes(b"untouched")
    monkeypatch.setenv("DRILLMASTER_ENV", mode)
    monkeypatch.setenv("DRILLMASTER_DB_PATH", str(operator_db))
    monkeypatch.setenv("DRILLMASTER_DATA_DIR", str(tmp_path))
    config = SimpleNamespace()
    hooks["pytest_configure"](config)
    try:
        assert os.environ["DRILLMASTER_ENV"] == mode
        assert Path(os.environ["DRILLMASTER_DB_PATH"]) != operator_db
        assert Path(os.environ["DRILLMASTER_DATA_DIR"]) != tmp_path
    finally:
        hooks["pytest_unconfigure"](config)
    assert os.environ["DRILLMASTER_DB_PATH"] == str(operator_db)
    assert operator_db.read_bytes() == b"untouched"
