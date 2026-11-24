"""M407: the sharded runner reports pytest's own counts and never trusts a zero exit code alone."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "quality"))

import run_suite_sharded as runner  # noqa: E402

SAMPLE = textwrap.dedent('''
    import pytest

    def test_pass():
        assert True

    def test_fail():
        assert 1 == 2, "deliberate"

    @pytest.mark.skip(reason="deliberate skip")
    def test_skip():
        pass

    @pytest.mark.xfail(reason="deliberate xfail", strict=False)
    def test_xfail():
        assert False

    @pytest.mark.xfail(reason="deliberate xpass", strict=False)
    def test_xpass():
        assert True
''')


def _run(tmp_path, body, name="test_sample_m407.py"):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    out_json = tmp_path / "result.json"
    out_txt = tmp_path / "result.txt"
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "quality" / "run_suite_sharded.py"), "--shards", "1",
                           "--files", str(path), "--json", str(out_json), "--out", str(out_txt)],
                          cwd=ROOT, capture_output=True, text=True, timeout=300)
    return proc, json.loads(out_json.read_text(encoding="utf-8")), out_txt.read_text(encoding="utf-8")


def test_every_outcome_is_counted_exactly(tmp_path):
    proc, data, text = _run(tmp_path, SAMPLE)
    shard = data["shards"][0]
    assert shard["collected"] == 5
    assert shard["counts"] == {"passed": 1, "failed": 1, "skipped": 1, "xfailed": 1, "xpassed": 1}
    assert shard["ok"] is False and proc.returncode == 1
    assert any("deliberate" in t for t in shard["failures"].values())
    assert "TOTAL collected 5; passed 1, failed 1, error 0, skipped 1, xfailed 1, xpassed 1" in text
    assert "SKIPPED" in text and "XFAILED" in text and "XPASSED" in text
    for key in ("sha", "python_executable", "python_version", "lock_sha256", "command"):
        assert data["meta"][key]


def test_collection_error_is_not_ok(tmp_path):
    proc, data, _ = _run(tmp_path, "import nonexistent_module_m407\n\ndef test_x():\n    pass\n")
    shard = data["shards"][0]
    assert shard["collection_errors"] and shard["ok"] is False and proc.returncode == 1


def test_zero_exit_with_a_failed_test_is_not_ok():
    fake = {"exit_code": 0, "pytest_exitstatus": 0, "collected": 3, "not_run": [], "collection_errors": [],
            "counts": {"passed": 2, "failed": 1}}
    assert runner.shard_ok(fake) is False
    assert runner.shard_ok({**fake, "counts": {"passed": 3}}) is True
    assert runner.shard_ok({**fake, "counts": {"passed": 3}, "collected": 0}) is False
    assert runner.shard_ok({**fake, "counts": {"passed": 2}, "not_run": ["t::x"]}) is False
    assert runner.shard_ok({**fake, "counts": {"passed": 3}, "pytest_exitstatus": None}) is False


def test_m409_durations_are_recorded_and_profiled(tmp_path):
    import suite_profile_m409 as profile

    _proc, data, _ = _run(tmp_path, SAMPLE)
    durations = data["shards"][0]["durations"]
    assert len(durations) == 5 and all(sec >= 0.0 for sec in durations.values())
    loaded, tests = profile.load(str(tmp_path / "result.json"))
    assert tests == durations
    files = profile.per_file(tests)
    assert len(files) == 1 and abs(sum(files.values()) - sum(durations.values())) < 1e-9
    bins = profile.lpt({"a": 5.0, "b": 4.0, "c": 3.0, "d": 3.0}, 2)
    assert sorted(b[0] for b in bins) == [7.0, 8.0]
    text = profile.report(loaded, tests, 3)
    assert "## Top 3 files" in text and "Nothing in this report changes CI" in text
