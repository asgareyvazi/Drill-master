"""Tests for the external MinerU adapter and document normalizer.

These tests use a subprocess runner double; they do not install, vendor, or
pretend to execute MinerU.  The real integration test is opt-in via
MINERU_INTEGRATION_INPUT.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

from core.mineru_engine import (
    DocumentNormalizer,
    MinerUAdapter,
    MinerUConfig,
    parse_mineru_output,
    validate_canonical_payload,
)


def _completed(code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(["mineru"], code, stdout=stdout, stderr=stderr)


def test_mineru_discovery_prefers_explicit_path(monkeypatch, tmp_path):
    executable = tmp_path / "mineru.exe"
    executable.write_text("external launcher", encoding="utf-8")
    monkeypatch.setattr("core.mineru_engine.shutil.which", lambda _: "/wrong/path/mineru")

    from core.mineru_engine import discover_mineru_executable

    assert discover_mineru_executable(str(executable)) == str(executable.resolve())


def test_mineru_version_and_health_check():
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if command[-1] == "--version":
            return _completed(stdout="MinerU 3.4.5\n")
        return _completed(stdout="usage: mineru")

    adapter = MinerUAdapter(
        MinerUConfig(enabled=True, executable="mineru.exe"),
        runner=runner,
    )
    health = adapter.health_check()

    assert health.available is True
    assert health.version == "3.4.5"
    assert calls[0][-1] == "--version"


def test_mineru_unavailable_is_graceful():
    adapter = MinerUAdapter(MinerUConfig(enabled=False))
    health = adapter.health_check()
    assert health.available is False
    assert health.enabled is False
    assert "disabled" in (health.error or "")


def test_mineru_invocation_uses_safe_cli_and_parses_markdown(tmp_path):
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf fixture")
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        output = Path(command[command.index("-o") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / "report.md").write_text(
            "# Daily Report\n\n"
            "| Mud Weight |\n| --- |\n| 12.5 |\n\n"
            "Report Date: 2026-09-05\n",
            encoding="utf-8",
        )
        return _completed(stdout="parsed")

    adapter = MinerUAdapter(
        MinerUConfig(
            enabled=True,
            executable="mineru.exe",
            backend="hybrid-engine",
            method="auto",
            timeout_seconds=30,
        ),
        runner=runner,
    )
    result = adapter.parse_file(source, tmp_path / "mineru-output")

    assert result.success is True
    assert result.document is not None
    assert result.document.table_count == 1
    command, kwargs = calls[0]
    assert command[:1] == ["mineru.exe"]
    assert command[command.index("-p") + 1] == str(source.resolve())
    assert command[command.index("-b") + 1] == "hybrid-engine"
    assert command[command.index("-m") + 1] == "auto"
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 30

    normalized = DocumentNormalizer().normalize(result.document)
    assert normalized.canonical_data["mud_report"]["mw"] == 12.5
    assert normalized.provenance[0]["source_file"] == str(source.resolve())
    assert normalized.validation.valid is True


def test_mineru_invalid_input_and_unsupported_format(tmp_path):
    adapter = MinerUAdapter(MinerUConfig(enabled=True, executable="mineru"))
    missing = adapter.parse_file(tmp_path / "missing.pdf")
    assert missing.success is False
    assert missing.error_type == "invalid-input"

    source = tmp_path / "report.txt"
    source.write_text("not supported", encoding="utf-8")
    unsupported = adapter.parse_file(source)
    assert unsupported.success is False
    assert unsupported.error_type == "unsupported-format"


def test_mineru_timeout_and_process_failure_are_reported(tmp_path):
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf")

    def timeout_runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], stderr=b"timed out")

    timeout_result = MinerUAdapter(
        MinerUConfig(enabled=True, executable="mineru", timeout_seconds=4),
        runner=timeout_runner,
    ).parse_file(source, tmp_path / "timeout-output")
    assert timeout_result.success is False
    assert timeout_result.error_type == "timeout"
    assert timeout_result.fallback_available is True

    def failure_runner(command, **kwargs):
        return _completed(2, stderr="backend unavailable")

    failure_result = MinerUAdapter(
        MinerUConfig(enabled=True, executable="mineru"),
        runner=failure_runner,
    ).parse_file(source, tmp_path / "failure-output")
    assert failure_result.success is False
    assert failure_result.error_type == "process-failed"
    assert "backend unavailable" in (failure_result.error or "")


def test_mineru_malformed_or_missing_output_is_not_success(tmp_path):
    source = tmp_path / "report.docx"
    source.write_bytes(b"docx")

    def runner(command, **kwargs):
        Path(command[command.index("-o") + 1]).mkdir(parents=True, exist_ok=True)
        return _completed()

    result = MinerUAdapter(
        MinerUConfig(enabled=True, executable="mineru"),
        runner=runner,
    ).parse_file(source, tmp_path / "output")
    assert result.success is False
    assert result.error_type == "output-missing"


def test_table_normalization_preserves_unknown_values_and_provenance(tmp_path):
    output = tmp_path / "out"
    output.mkdir()
    (output / "document.md").write_text(
        "## Survey\n\n"
        "| MD | Inc | Azi | Unknown Value |\n"
        "| --- | --- | --- | --- |\n"
        "| 1000 | 2.5 | 120 | do not map |\n",
        encoding="utf-8",
    )
    document = parse_mineru_output(output, source_file="survey.pdf")
    normalized = DocumentNormalizer().normalize(document)

    assert normalized.canonical_data["surveys"][0]["md"] == 1000
    assert normalized.canonical_data["surveys"][0]["inc"] == 2.5
    assert normalized.canonical_data["surveys"][0]["azi"] == 120
    assert "unknown value" not in normalized.canonical_data["surveys"][0]
    assert any(item["source_page"] is None for item in normalized.provenance)
    assert normalized.needs_review is True


def test_no_fabricated_values_and_invalid_canonical_data_rejected():
    normalized = DocumentNormalizer().normalize(
        parse_mineru_output_from_text("Mud Weight: unclear\nUnknown: 123\n")
    )
    assert normalized.canonical_data == {"mud_report": {"mw": "unclear"}}
    assert normalized.validation.valid is True
    assert normalized.validation.warnings

    invalid = validate_canonical_payload({"mud_report": {"mw": 30.0}})
    assert invalid.valid is False
    assert invalid.errors[0]["field"] == "mud_report.mw"
    invalid_table = validate_canonical_payload({"surveys": [{"md": -1.0}]})
    assert invalid_table.valid is False
    assert invalid_table.errors[0]["field"] == "survey.md"


def parse_mineru_output_from_text(text: str):
    """Build a tiny output fixture without introducing a MinerU implementation."""
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="mineru-test-"))
    (root / "document.md").write_text(text, encoding="utf-8")
    return parse_mineru_output(root, source_file="document.pdf")


def test_mineru_batch_isolates_file_failures(tmp_path):
    good = tmp_path / "good.pdf"
    bad = tmp_path / "bad.pdf"
    good.write_bytes(b"good")
    bad.write_bytes(b"bad")

    def runner(command, **kwargs):
        source = Path(command[command.index("-p") + 1])
        output = Path(command[command.index("-o") + 1])
        if source.name == "bad.pdf":
            return _completed(1, stderr="bad input")
        output.mkdir(parents=True, exist_ok=True)
        (output / "good.md").write_text("Good text", encoding="utf-8")
        return _completed()

    results = MinerUAdapter(
        MinerUConfig(enabled=True, executable="mineru"),
        runner=runner,
    ).parse_batch([good, bad])
    assert [result.success for result in results] == [True, False]
    assert results[1].error_type == "process-failed"
