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
    config._drillmaster_previous_paths = {key: os.environ.get(key) for key in (
        "DRILLMASTER_DATA_DIR", "DRILLMASTER_DB_PATH", "DRILLMASTER_LOG_DIR",
        "DRILLMASTER_BACKUP_DIR", "DRILLMASTER_AI_SETTINGS_PATH",
        "DRILLMASTER_MAPPING_MEMORY_PATH", "DRILLMASTER_STANDARDS_PATH",
        "DRILLMASTER_MINERU_SETTINGS_PATH",
    )}
    config._drillmaster_test_directory = tempfile.TemporaryDirectory(
        prefix="drillmaster-tests-", ignore_cleanup_errors=True)
    directory = config._drillmaster_test_directory.name
    # A supplied ENV=test is not proof that a supplied database is disposable.
    # Preserve explicit mode, but isolate paths in every pytest invocation.
    for key in config._drillmaster_previous_paths:
        os.environ.pop(key, None)
    if config._drillmaster_test_mode_added:
        os.environ["DRILLMASTER_ENV"] = "test"
    os.environ["DRILLMASTER_DATA_DIR"] = directory
    os.environ["DRILLMASTER_DB_PATH"] = str(Path(directory) / "test-session.db")



import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_session_principal():
    """Restore the process-wide signed-in principal after every test (M46).

    ``core.permissions.permissions`` is a module singleton.  Tests that sign a
    user in (``permissions.set_user``) without restoring it leaked that user
    into every later test: with an in-memory database the leaked user id then
    fails the mandatory audit's foreign key, imports roll back, and the later
    test fails (or passes for the wrong reason) depending on file order -
    e.g. ``test_p0_permissions`` before ``test_document_library``.  Each test
    still sets the principal it needs; nothing here grants a permission.
    """
    from core.permissions import permissions
    previous = permissions._user
    try:
        yield
    finally:
        permissions._user = previous


_CRASH_BREADCRUMB_ENV = "DRILLMASTER_CRASH_BREADCRUMB"
_CRASH_BREADCRUMB_PREFIX = "DRILLMASTER-TEST-START "


def pytest_runtest_logstart(nodeid, location):
    """Write the active test's identity where a hard interpreter death cannot lose it.

    A fatal crash during pytest's report pipeline (formatting or recording a result) leaves no JUnit
    report and a faulthandler stack of pytest's own plumbing, which names no test at either end -- three
    consecutive Windows release runs died in three different innocent places that way.  The identity has
    to be recorded *before* that phase, on the unbuffered error descriptor (the same channel faulthandler
    itself uses), or buffered output dies with the process.  Opt-in via the environment so every other
    run is byte-for-byte unchanged; ``packaging/junit_report.py`` quotes the last breadcrumb into the
    crash annotation.  A breadcrumb must never fail a test, so a dead descriptor is swallowed.
    """
    if os.environ.get(_CRASH_BREADCRUMB_ENV) != "1":
        return
    try:
        os.write(2, f"{_CRASH_BREADCRUMB_PREFIX}{nodeid}\n".encode("utf-8", errors="backslashreplace"))
    except OSError:
        return


def pytest_unconfigure(config):
    if getattr(config, "_drillmaster_test_mode_added", False):
        os.environ.pop("DRILLMASTER_ENV", None)
    for key, value in config._drillmaster_previous_paths.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    config._drillmaster_test_directory.cleanup()
