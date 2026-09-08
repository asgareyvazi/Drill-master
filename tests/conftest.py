"""Explicit, disposable test-process defaults; application defaults stay production.

Configure before collection/session fixtures. Individual production tests override
or remove settings and exercise the real fail-closed policy. Never seed fixtures
in the normal per-user database when pytest is run without an explicit mode.
"""
import os
from pathlib import Path
import tempfile


def pytest_configure(config):
    config._drillmaster_test_mode_added = not any(
        key in os.environ for key in ("DRILLMASTER_ENV", "DRILLMASTER_ENVIRONMENT")
    )
    if config._drillmaster_test_mode_added:
        config._drillmaster_previous_paths = {key: os.environ.get(key) for key in ("DRILLMASTER_DATA_DIR", "DRILLMASTER_DB_PATH")}
        config._drillmaster_test_directory = tempfile.TemporaryDirectory(prefix="drillmaster-tests-", ignore_cleanup_errors=True)
        directory = config._drillmaster_test_directory.name
        os.environ["DRILLMASTER_ENV"] = "test"
        os.environ["DRILLMASTER_DATA_DIR"] = directory
        os.environ["DRILLMASTER_DB_PATH"] = str(Path(directory) / "test-session.db")


def pytest_unconfigure(config):
    if getattr(config, "_drillmaster_test_mode_added", False):
        os.environ.pop("DRILLMASTER_ENV", None)
        for key, value in config._drillmaster_previous_paths.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config._drillmaster_test_directory.cleanup()
