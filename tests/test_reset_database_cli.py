"""reset_database.py: arguments never reach the destructive prompt (M43 closure).

Before, `python reset_database.py --help` printed the configured database
path and went straight to "Type RESET to continue". Runs the script in a
subprocess against a disposable data directory; stdin is closed, so reaching
the prompt shows up as an EOFError.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run(args, tmp_path, typed=None):
    env = dict(os.environ)
    env.update(DRILLMASTER_ENV="test", DRILLMASTER_DATA_DIR=str(tmp_path / "data"),
               DRILLMASTER_DB_PATH=str(tmp_path / "data" / "x.db"),
               DRILLMASTER_LOG_DIR=str(tmp_path / "logs"))
    env.pop("DRILLMASTER_ENVIRONMENT", None)
    stdin = {"input": typed} if typed is not None else {"stdin": subprocess.DEVNULL}
    return subprocess.run([sys.executable, str(ROOT / "reset_database.py"), *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=60, **stdin)


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_prints_usage_and_never_prompts(tmp_path, flag):
    result = _run([flag], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "usage: python reset_database.py" in result.stdout
    assert "Type RESET" not in result.stdout and "Configured database" not in result.stdout
    assert not (tmp_path / "data").exists()


def test_unknown_arguments_are_refused_before_configuration(tmp_path):
    result = _run(["--force", "x"], tmp_path)
    assert result.returncode == 2
    assert "takes no arguments" in result.stdout and "nothing was changed" in result.stdout
    assert "Type RESET" not in result.stdout
    assert not (tmp_path / "data").exists()


def test_without_typed_confirmation_nothing_is_reset(tmp_path):
    result = _run([], tmp_path, typed="no\n")
    assert result.returncode == 0
    assert "Type RESET" in result.stdout and "Reset cancelled." in result.stdout
    assert not (tmp_path / "data" / "x.db").exists()
