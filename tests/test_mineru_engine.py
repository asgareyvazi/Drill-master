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
    parse_pdf_native_fallback,
    resolve_mineru_backend,
    validate_canonical_payload,
    MinerUOutputError,
)


def _completed(code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(["mineru"], code, stdout=stdout, stderr=stderr)


def test_mineru_discovery_prefers_explicit_path(monkeypatch, tmp_path):
    executable = tmp_path / "mineru.exe"
    executable.write_text("external launcher", encoding="utf-8")
    monkeypatch.setattr("core.mineru_engine.shutil.which", lambda _: "/wrong/path/mineru")

    from core.mineru_engine import discover_mineru_executable

    assert discover_mineru_executable(str(executable)) == str(executable.resolve())


def test_cpu_backend_is_selected_without_cuda(monkeypatch):
    monkeypatch.setenv("DRILLMASTER_MINERU_CUDA_AVAILABLE", "0")
    assert resolve_mineru_backend("auto") == "pipeline"
    assert resolve_mineru_backend("hybrid-engine") == "pipeline"


def test_gpu_backend_can_be_selected_when_cuda_is_available(monkeypatch):
    monkeypatch.setenv("DRILLMASTER_MINERU_CUDA_AVAILABLE", "1")
    assert resolve_mineru_backend("auto") == "hybrid-engine"
    assert resolve_mineru_backend("hybrid-engine") == "hybrid-engine"


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


def test_mineru_persisted_configuration_is_supported(monkeypatch, tmp_path):
    executable = tmp_path / "mineru.exe"
    executable.write_text("external launcher", encoding="utf-8")
    monkeypatch.setattr(
        "core.mineru_engine.read_mineru_settings",
        lambda: {
            "enabled": True,
            "executable": str(executable),
            "backend": "pipeline",
            "method": "ocr",
            "timeout": 42,
            "output_dir": str(tmp_path / "mineru-output"),
            "keep_output": True,
        },
    )
    config = MinerUConfig.from_environment()
    assert config.enabled is True
    assert config.executable == str(executable.resolve())
    assert config.backend == "pipeline"
    assert config.method == "ocr"
    assert config.timeout_seconds == 42
    assert config.output_dir == (tmp_path / "mineru-output")
    assert config.keep_output is True


def test_mineru_invocation_uses_safe_cli_and_parses_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("DRILLMASTER_MINERU_CUDA_AVAILABLE", "1")
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf fixture")
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        if command[-1] == "--version":
            return _completed(stdout="MinerU 3.4.5")
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
    assert result.diagnostics == {
        "executable": "mineru.exe",
        "python": None,
        "python_executable": None,
        "version": "3.4.5",
        "backend": "hybrid-engine",
        "method": "auto",
    }
    command, kwargs = next((command, kwargs) for command, kwargs in calls if "-p" in command)
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


def test_mineru_materializes_assets_and_keeps_result_alive_until_cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv("DRILLMASTER_MINERU_CUDA_AVAILABLE", "0")
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf")
    output_root = tmp_path / "mineru-output"

    def runner(command, **kwargs):
        if command[-1] == "--version":
            return _completed(stdout="MinerU 3.4.5")
        output = Path(command[command.index("-o") + 1])
        asset = output / "auto" / "images" / "asset.jpg"
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(b"jpg")
        (output / "auto" / "page.md").write_text(
            "# Daily Report\n\n![asset](images/asset.jpg)\n",
            encoding="utf-8",
        )
        return _completed(stdout="parsed")

    result = MinerUAdapter(
        MinerUConfig(enabled=True, executable="mineru", backend="auto"),
        runner=runner,
    ).parse_file(source, output_root)

    assert result.success is True
    assert result.document is not None
    assert result.document.output_dir
    assert Path(result.document.output_dir).is_dir()
    assert result.document.metadata["assets"] == 1
    assert Path(result.document.images[0]["path"]).is_file()
    assert result.document.backend == "pipeline"
    result.cleanup()
    assert not Path(result.document.output_dir).exists()


def test_missing_referenced_mineru_asset_is_reported(tmp_path):
    output = tmp_path / "out"
    output.mkdir()
    (output / "page.md").write_text("![missing](auto/images/not-created.jpg)", encoding="utf-8")
    import pytest

    with pytest.raises(MinerUOutputError, match="missing asset"):
        parse_mineru_output(output, source_file="report.pdf")


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
        if command[-1] == "--version":
            return _completed(stdout="MinerU 3.4.5")
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
    assert normalized.canonical_data == {"mud_report": {"mw": None}}
    assert normalized.validation.valid is True
    assert normalized.validation.warnings
    assert any(item.get("value") == "unclear" for item in normalized.warnings)

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


def test_pdf_native_fallback_adapts_rows_to_common_ir(monkeypatch, tmp_path):
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf")
    monkeypatch.setattr(
        "core.import_adapters.pdf_tables.extract_tables",
        lambda _source: {
            "engine": "pymupdf",
            "tier": 2,
            "metrics": [{"engine": "pymupdf", "rows": 2}],
            "tables": [{
                "data": [
                    {"Report Date": "2026-09-05", "Mud Weight": "12.5"},
                    {"Report Date": "2026-09-06", "Mud Weight": "12.6"},
                ],
                "report": {"page": 3},
            }],
        },
    )
    document = parse_pdf_native_fallback(source)
    assert document.backend == "pdf-native-fallback"
    assert document.method == "pymupdf"
    assert document.page_count == 1
    assert document.table_count == 1
    assert document.tables[0].provenance.source_page == 3
    assert document.tables[0].rows[0][0] == "2026-09-05"


def test_pdf_native_fallback_reports_empty_output(monkeypatch, tmp_path):
    source = tmp_path / "report.pdf"
    source.write_bytes(b"pdf")
    monkeypatch.setattr(
        "core.import_adapters.pdf_tables.extract_tables",
        lambda _source: {"tables": [], "error": "all PDF tiers failed"},
    )
    import pytest
    from core.mineru_engine import MinerUOutputError

    with pytest.raises(MinerUOutputError, match="all PDF tiers failed"):
        parse_pdf_native_fallback(source)


def test_mineru_batch_isolates_file_failures(tmp_path):
    good = tmp_path / "good.pdf"
    bad = tmp_path / "bad.pdf"
    good.write_bytes(b"good")
    bad.write_bytes(b"bad")

    def runner(command, **kwargs):
        if command[-1] == "--version":
            return _completed(stdout="MinerU 3.4.5")
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
