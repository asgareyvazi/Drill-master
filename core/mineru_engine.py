"""External MinerU document-intelligence adapter.

MinerU is deliberately treated as an optional, out-of-process engine.  This
module does not import MinerU or PySide6 and never writes to the DrillMaster
database.  It discovers a user-managed MinerU installation, invokes the
official CLI when requested, and converts its generated Markdown/JSON/assets
into a small intermediate document representation.

The adapter is intentionally conservative: values are preserved as extracted
text until a deterministic, unambiguous canonical-schema mapping is available.
Unknown or ambiguous values remain outside the canonical payload and are
reported for review rather than being guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from core.canonical_schema import FIELD_SPECS, lookup_alias
from core.runtime_config import data_dir, read_mineru_settings
from core.value_normalizer import normalize_for_field
from core.import_ir import raw_document_from_mineru

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = frozenset(
    {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".bmp",
        ".tif",
        ".tiff",
        ".docx",
        ".pptx",
        ".xlsx",
    }
)
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"})
CPU_MINERU_BACKEND = "pipeline"
GPU_MINERU_BACKEND = "hybrid-engine"
SUPPORTED_MINERU_METHODS = frozenset({"auto", "txt", "ocr"})


def cuda_available() -> bool:
    """Return CUDA availability without making torch/MinerU a hard dependency."""
    configured = _first_env("DRILLMASTER_MINERU_CUDA_AVAILABLE", "MINERU_CUDA_AVAILABLE")
    if configured is not None:
        return _parse_bool(configured, default=False)
    try:
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except (ImportError, AttributeError, RuntimeError):
        return False


def resolve_mineru_backend(requested: str) -> str:
    """Resolve ``auto``/GPU backends to a backend supported by this machine."""
    requested = (requested or "auto").strip().lower()
    if requested == "auto":
        return GPU_MINERU_BACKEND if cuda_available() else CPU_MINERU_BACKEND
    if requested in {"hybrid-engine", "vlm-engine", "hybrid-http-client", "vlm-http-client"} and not cuda_available():
        logger.info("CUDA unavailable; selecting CPU-compatible MinerU backend pipeline instead of %s", requested)
        return CPU_MINERU_BACKEND
    return requested


def resolve_mineru_method(requested: str) -> str:
    requested = (requested or "auto").strip().lower()
    return requested if requested in SUPPORTED_MINERU_METHODS else "auto"


class MinerUError(RuntimeError):
    """Base class for actionable MinerU errors."""


class MinerUNotInstalledError(MinerUError):
    """No usable MinerU executable or Python environment was found."""


class MinerUExecutableError(MinerUError):
    """The configured executable/Python environment cannot be used."""


class MinerUUnsupportedFormatError(MinerUError):
    """MinerU does not support the requested input suffix."""


class MinerUProcessError(MinerUError):
    """MinerU returned a non-zero exit status."""


class MinerUTimeoutError(MinerUError):
    """MinerU exceeded its configured timeout."""


class MinerUOutputError(MinerUError):
    """MinerU completed but did not produce a readable document output."""


class MinerUNormalizationError(MinerUError):
    """MinerU output could not be safely normalized."""


@dataclass(frozen=True)
class MinerUConfig:
    """Runtime configuration for an external MinerU installation.

    Environment variables use the project convention ``DRILLMASTER_*`` and
    accept the shorter ``MINERU_*`` aliases for deployment scripts.  No
    configuration is written into the repository.
    """

    enabled: bool = False
    executable: Optional[str] = None
    python_executable: Optional[str] = None
    backend: str = "auto"
    method: str = "auto"
    output_dir: Optional[Path] = None
    timeout_seconds: int = 600
    keep_output: bool = False

    @classmethod
    def from_environment(cls) -> "MinerUConfig":
        persisted = read_mineru_settings()
        executable_setting = _configured_value(
            persisted, "executable", "DRILLMASTER_MINERU_EXECUTABLE", "MINERU_EXECUTABLE"
        )
        python_setting = _configured_value(
            persisted, "python", "DRILLMASTER_MINERU_PYTHON", "MINERU_PYTHON"
        )
        executable = discover_mineru_executable(executable_setting)
        python_executable = _resolve_executable(python_setting) if python_setting else None

        explicit_enabled = _configured_value(
            persisted, "enabled", "DRILLMASTER_MINERU_ENABLED", "MINERU_ENABLED"
        )
        if explicit_enabled is None:
            enabled = bool(executable or python_executable)
        else:
            enabled = _parse_bool(explicit_enabled, default=False)

        output_value = _configured_value(
            persisted, "output_dir", "DRILLMASTER_MINERU_OUTPUT_DIR", "MINERU_OUTPUT_DIR"
        )
        output_dir = Path(output_value).expanduser() if output_value else None
        timeout_value = _configured_value(
            persisted, "timeout", "DRILLMASTER_MINERU_TIMEOUT", "MINERU_TIMEOUT"
        )
        try:
            timeout_seconds = max(1, int(timeout_value)) if timeout_value else 600
        except (TypeError, ValueError):
            timeout_seconds = 600

        backend = _configured_value(
            persisted, "backend", "DRILLMASTER_MINERU_BACKEND", "MINERU_BACKEND"
        ) or "auto"
        method = _configured_value(
            persisted, "method", "DRILLMASTER_MINERU_METHOD", "MINERU_METHOD"
        ) or "auto"
        keep_output = _parse_bool(
            _configured_value(persisted, "keep_output", "DRILLMASTER_MINERU_KEEP_OUTPUT", "MINERU_KEEP_OUTPUT"),
            default=False,
        )
        return cls(
            enabled=enabled,
            executable=executable,
            python_executable=python_executable,
            backend=backend,
            method=method,
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
            keep_output=keep_output,
        )


def _first_env(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _configured_value(persisted: Mapping[str, Any], key: str, *env_names: str) -> Any:
    env_value = _first_env(*env_names)
    if env_value is not None:
        return env_value
    value = persisted.get(key)
    return value if value not in (None, "") else None


def _parse_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_executable(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    expanded = Path(value).expanduser()
    if expanded.is_file():
        return str(expanded.resolve())
    found = shutil.which(value)
    return str(Path(found).resolve()) if found else None


def discover_mineru_executable(explicit: Optional[str] = None) -> Optional[str]:
    """Discover MinerU without importing or installing it.

    Priority is explicit configuration, PATH, then a platform-neutral
    development fallback derived from the current user's home directory.  The
    fallback does not contain a developer username and is only accepted when
    the file exists.
    """
    if explicit:
        return _resolve_executable(explicit)

    for name in ("mineru", "mineru.exe"):
        found = shutil.which(name)
        if found:
            return str(Path(found).resolve())

    # Development-only convention for a separately managed Windows venv.
    candidates = (
        Path.home() / "Desktop" / "mineru-env" / "Scripts" / "mineru.exe",
        Path.home() / "Desktop" / "mineru-env" / "bin" / "mineru",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return None


@dataclass(frozen=True)
class Provenance:
    source_file: str
    source_page: Optional[int] = None
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None
    source_column: Optional[int | str] = None
    bounding_box: Optional[tuple[float, ...]] = None
    extraction_method: str = "mineru"
    confidence: Optional[float] = None
    source_table: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "source_page": self.source_page,
            "source_sheet": self.source_sheet,
            "source_row": self.source_row,
            "source_column": self.source_column,
            "bounding_box": list(self.bounding_box) if self.bounding_box else None,
            "extraction_method": self.extraction_method,
            "confidence": self.confidence,
            "source_table": self.source_table,
        }


@dataclass
class DocumentTextBlock:
    text: str
    provenance: Provenance


@dataclass
class DocumentHeading:
    text: str
    level: int
    provenance: Provenance


@dataclass
class DocumentTable:
    headers: list[str]
    rows: list[list[str]]
    provenance: Provenance
    name: str = ""


@dataclass
class DocumentPage:
    number: int
    text: str = ""
    provenance: Optional[Provenance] = None


@dataclass
class MinerUDocument:
    source_file: str
    backend: str
    method: str
    output_dir: Optional[str] = None
    pages: list[DocumentPage] = field(default_factory=list)
    headings: list[DocumentHeading] = field(default_factory=list)
    text_blocks: list[DocumentTextBlock] = field(default_factory=list)
    tables: list[DocumentTable] = field(default_factory=list)
    images: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_files: list[str] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def table_count(self) -> int:
        return len(self.tables)


@dataclass
class MinerUParseResult:
    source_file: str
    success: bool
    document: Optional[MinerUDocument] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    output_dir: Optional[str] = None
    fallback_available: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)
    cleanup_dir: Optional[str] = None

    def cleanup(self) -> None:
        """Remove this result's isolated output after its consumer is done."""
        if not self.cleanup_dir:
            return
        shutil.rmtree(self.cleanup_dir, ignore_errors=True)
        self.cleanup_dir = None


@dataclass
class MinerUHealth:
    available: bool
    enabled: bool
    executable: Optional[str]
    python_executable: Optional[str]
    version: Optional[str] = None
    backend: str = CPU_MINERU_BACKEND
    method: str = "auto"
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "enabled": self.enabled,
            "executable": self.executable,
            "python_executable": self.python_executable,
            "version": self.version,
            "backend": self.backend,
            "method": self.method,
            "error": self.error,
        }


class MinerUAdapter:
    """Safe, UI-independent adapter for the installed MinerU CLI."""

    def __init__(
        self,
        config: Optional[MinerUConfig] = None,
        runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
    ) -> None:
        self.config = config or MinerUConfig.from_environment()
        self._runner = runner or subprocess.run
        self._version_cache: Optional[str] = None

    def _diagnostics(self, *, version: Optional[str] = None) -> dict[str, Any]:
        return {
            "executable": self.config.executable,
            "python": self.config.python_executable,
            "python_executable": self.config.python_executable,
            "version": version or self._version_cache or "unknown",
            "backend": self.resolved_backend(),
            "method": self.resolved_method(),
        }

    def resolved_backend(self) -> str:
        return resolve_mineru_backend(self.config.backend)

    def resolved_method(self) -> str:
        return resolve_mineru_method(self.config.method)

    @staticmethod
    def is_available() -> bool:
        return MinerUAdapter().health_check().available

    def _command_prefix(self) -> list[str]:
        if self.config.executable:
            return [self.config.executable]
        if self.config.python_executable:
            return [self.config.python_executable, "-m", "mineru"]
        return []

    def health_check(self) -> MinerUHealth:
        prefix = self._command_prefix()
        if not self.config.enabled:
            return MinerUHealth(
                available=False,
                enabled=False,
                executable=self.config.executable,
                python_executable=self.config.python_executable,
                backend=self.resolved_backend(),
                method=self.resolved_method(),
                error="MinerU is disabled or not detected",
            )
        if not prefix:
            return MinerUHealth(
                available=False,
                enabled=True,
                executable=None,
                python_executable=self.config.python_executable,
                backend=self.resolved_backend(),
                method=self.resolved_method(),
                error=(
                    "MinerU was not found. Configure MINERU_EXECUTABLE or "
                    "MINERU_PYTHON, or add mineru to PATH."
                ),
            )
        try:
            version = self.get_version()
            return MinerUHealth(
                available=True,
                enabled=True,
                executable=self.config.executable,
                python_executable=self.config.python_executable,
                version=version,
                backend=self.resolved_backend(),
                method=self.resolved_method(),
            )
        except MinerUError as exc:
            return MinerUHealth(
                available=False,
                enabled=True,
                executable=self.config.executable,
                python_executable=self.config.python_executable,
                backend=self.resolved_backend(),
                method=self.resolved_method(),
                error=str(exc),
            )

    def get_version(self) -> str:
        if self._version_cache is not None:
            return self._version_cache
        prefix = self._command_prefix()
        if not prefix:
            raise MinerUNotInstalledError(
                "MinerU was not found. Configure its executable or Python environment."
            )
        try:
            completed = self._run_control(prefix + ["--version"])
        except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
            raise MinerUExecutableError(f"MinerU version probe failed: {exc}") from exc
        output = _combined_output(completed)
        if completed.returncode != 0:
            # Some installations expose --help but not --version.  A help
            # probe still proves the CLI is usable; version may remain unknown.
            try:
                help_result = self._run_control(prefix + ["--help"])
            except (OSError, subprocess.SubprocessError) as exc:
                raise MinerUExecutableError(f"MinerU version probe failed: {exc}") from exc
            help_output = _combined_output(help_result)
            match = _version_from_text(help_output)
            if help_result.returncode == 0 and match:
                self._version_cache = match
                return match
            if help_result.returncode == 0:
                self._version_cache = "unknown"
                return self._version_cache
            raise MinerUExecutableError(
                f"MinerU CLI probe failed with exit code {completed.returncode}: "
                f"{_safe_process_message(output)}"
            )
        self._version_cache = _version_from_text(output) or "unknown"
        return self._version_cache

    def _run_control(self, command: Sequence[str]) -> subprocess.CompletedProcess:
        return self._runner(
            list(command),
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=min(self.config.timeout_seconds, 30),
            check=False,
        )

    def parse_file(self, input_path: str | os.PathLike[str], output_dir: Optional[str | os.PathLike[str]] = None) -> MinerUParseResult:
        """Run MinerU for one file and parse generated Markdown/JSON/assets."""
        source = Path(input_path).expanduser()
        source_display = str(source)
        started = time.monotonic()
        try:
            source = source.resolve(strict=True)
        except FileNotFoundError as exc:
            return self._failure(source_display, "invalid-input", f"Input file does not exist: {source}", started)
        if not source.is_file():
            return self._failure(source_display, "invalid-input", f"Input is not a file: {source}", started)
        if source.suffix.lower() not in SUPPORTED_SUFFIXES:
            return self._failure(
                source_display,
                "unsupported-format",
                f"Unsupported MinerU input format: {source.suffix or '<none>'}",
                started,
            )
        if not self.config.enabled or not self._command_prefix():
            return self._failure(
                source_display,
                "not-installed",
                "MinerU was not found. Configure its executable path or Python environment.",
                started,
                fallback_available=source.suffix.lower() == ".pdf",
            )

        version_error = None
        try:
            version = self.get_version()
        except MinerUError as exc:
            # A usable parser may not expose --version; preserve that fact in
            # diagnostics without pretending a version is known.
            version = "unknown"
            version_error = str(exc)
            logger.warning("MinerU version probe unavailable: %s", exc)
        diagnostics = self._diagnostics(version=version)
        if version_error:
            diagnostics["version_error"] = version_error

        temporary_root: Optional[Path] = None
        try:
            root = Path(output_dir).expanduser().resolve() if output_dir else self.config.output_dir
            if root is None and self.config.keep_output:
                root = data_dir() / "mineru-output"
            if root is None:
                # Do not use TemporaryDirectory here: the result is consumed
                # after parse_file returns (IR mapping, review, and optional
                # asset inspection).  The ParseResult owns explicit cleanup.
                temporary_root = Path(tempfile.mkdtemp(prefix="drillmaster-mineru-"))
                root = temporary_root
            root.mkdir(parents=True, exist_ok=True)
            identity = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:10]
            run_dir = root / f"{_safe_output_stem(source.stem)}-{identity}"
            if run_dir.exists():
                shutil.rmtree(run_dir)
            run_dir.mkdir(parents=True, exist_ok=True)
            command = self._command_prefix() + [
                "-p",
                str(source),
                "-o",
                str(run_dir),
                "-b",
                self.resolved_backend(),
                "-m",
                self.resolved_method(),
            ]
            logger.info(
                "MinerU parse started: file=%s backend=%s method=%s",
                source.name,
                self.resolved_backend(),
                self.resolved_method(),
            )
            try:
                completed = self._runner(
                    command,
                    shell=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.config.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                return self._failure(
                    source_display,
                    "timeout",
                    f"MinerU timed out after {self.config.timeout_seconds} seconds.",
                    started,
                    stdout=_text(getattr(exc, "stdout", "")),
                    stderr=_text(getattr(exc, "stderr", "")),
                    output_dir=str(run_dir),
                    fallback_available=source.suffix.lower() == ".pdf",
                )
            except FileNotFoundError as exc:
                return self._failure(
                    source_display,
                    "executable-not-found",
                    f"MinerU executable could not be started: {exc}",
                    started,
                    output_dir=str(run_dir),
                    fallback_available=source.suffix.lower() == ".pdf",
                )

            stdout = _text(getattr(completed, "stdout", ""))
            stderr = _text(getattr(completed, "stderr", ""))
            if completed.returncode != 0:
                return self._failure(
                    source_display,
                    "process-failed",
                    f"MinerU failed with exit code {completed.returncode}: {_safe_process_message(stderr or stdout)}",
                    started,
                    stdout=stdout,
                    stderr=stderr,
                    output_dir=str(run_dir),
                    fallback_available=source.suffix.lower() == ".pdf",
                )
            try:
                document = parse_mineru_output(
                    run_dir,
                    source_file=str(source),
                    backend=self.resolved_backend(),
                    method=self.resolved_method(),
                )
            except MinerUOutputError as exc:
                return self._failure(
                    source_display,
                    "output-missing",
                    str(exc),
                    started,
                    stdout=stdout,
                    stderr=stderr,
                    output_dir=str(run_dir),
                    fallback_available=source.suffix.lower() == ".pdf",
                )
            document.metadata["diagnostics"] = dict(diagnostics)
            duration = time.monotonic() - started
            logger.info(
                "MinerU parse finished: file=%s duration=%.2fs pages=%d tables=%d",
                source.name,
                duration,
                document.page_count,
                document.table_count,
            )
            return MinerUParseResult(
                source_file=source_display,
                success=True,
                document=document,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                output_dir=str(run_dir),
                diagnostics=diagnostics,
                cleanup_dir=(None if self.config.keep_output else str(temporary_root or run_dir)),
            )
        except OSError as exc:
            return self._failure(source_display, "output-error", f"MinerU output directory error: {exc}", started)

    def parse_batch(self, input_paths: Iterable[str | os.PathLike[str]]) -> list[MinerUParseResult]:
        """Parse files independently; one failure does not abort the batch."""
        results = []
        for path in input_paths:
            results.append(self.parse_file(path))
        return results

    @staticmethod
    def _failure(
        source_file: str,
        error_type: str,
        error: str,
        started: float,
        *,
        stdout: str = "",
        stderr: str = "",
        output_dir: Optional[str] = None,
        fallback_available: bool = False,
    ) -> MinerUParseResult:
        logger.warning("MinerU parse failed: file=%s type=%s error=%s", Path(source_file).name, error_type, error)
        return MinerUParseResult(
            source_file=source_file,
            success=False,
            error=error,
            error_type=error_type,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=time.monotonic() - started,
            output_dir=output_dir,
            fallback_available=fallback_available,
        )


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _combined_output(completed: subprocess.CompletedProcess) -> str:
    return (_text(getattr(completed, "stdout", "")) + "\n" + _text(getattr(completed, "stderr", ""))).strip()


def _safe_process_message(text: str) -> str:
    # Keep error messages useful without echoing potentially sensitive output.
    compact = " ".join(text.split())
    return compact[-500:] if compact else "no diagnostic output"


def _version_from_text(text: str) -> Optional[str]:
    match = re.search(r"(?<!\d)(\d+\.\d+(?:\.\d+)?)(?!\d)", text)
    return match.group(1) if match else None


def _safe_output_stem(stem: str) -> str:
    """Keep the isolated Windows output path short and filesystem-safe."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return (safe or "document")[:80]


def _validate_mineru_asset_references(root: Path, content_files: Sequence[Path]) -> None:
    """Verify every referenced image resolves inside the materialized output."""
    pattern = re.compile(
        r"(?P<ref>(?:[A-Za-z0-9_. -]+[\\\\/])+[A-Za-z0-9_. -]+\.(?:png|jpe?g|webp|gif|bmp|tiff?))",
        re.IGNORECASE,
    )
    for content_file in content_files:
        try:
            text = content_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise MinerUOutputError(f"Cannot read MinerU output {content_file}: {exc}") from exc
        for raw_ref in pattern.findall(text):
            ref = raw_ref.replace("\\\\", "/")
            if ref.startswith(("http://", "https://", "data:")):
                continue
            candidates = []
            ref_path = Path(ref)
            if ref_path.is_absolute():
                candidates.append(ref_path)
            candidates.extend((content_file.parent / ref_path, root / ref_path))
            if not any(candidate.is_file() for candidate in candidates):
                raise MinerUOutputError(
                    f"MinerU output references missing asset '{raw_ref}' "
                    f"from '{content_file.relative_to(root)}'"
                )


def parse_mineru_output(
    output_dir: str | os.PathLike[str],
    *,
    source_file: str,
    backend: str = "hybrid-engine",
    method: str = "auto",
) -> MinerUDocument:
    """Parse a MinerU output directory without assuming a single layout."""
    root = Path(output_dir).expanduser().resolve()
    if not root.is_dir():
        raise MinerUOutputError(f"MinerU output directory is missing: {root}")
    files = [path for path in root.rglob("*") if path.is_file()]
    markdown_files = sorted(path for path in files if path.suffix.lower() in {".md", ".markdown"})
    json_files = sorted(path for path in files if path.suffix.lower() == ".json")
    content_files = markdown_files + json_files
    asset_files = sorted(path for path in files if path.suffix.lower() in IMAGE_SUFFIXES)
    _validate_mineru_asset_references(root, content_files)
    if not markdown_files and not json_files:
        raise MinerUOutputError(
            f"MinerU completed without Markdown or JSON output in {root}. "
            "Check the configured backend and output permissions."
        )

    document = MinerUDocument(
        source_file=source_file,
        backend=backend,
        method=method,
        output_dir=str(root),
        raw_files=[str(path.relative_to(root)) for path in files],
    )
    for path in asset_files:
        document.images.append(
            {
                "path": str(path.resolve()),
                "relative_path": str(path.relative_to(root)),
                "source_file": source_file,
                "provenance": Provenance(source_file, extraction_method="mineru-asset").to_dict(),
            }
        )

    for path in markdown_files:
        _parse_markdown(path.read_text(encoding="utf-8", errors="replace"), document, source_file)
    for path in json_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError) as exc:
            document.metadata.setdefault("warnings", []).append(f"Malformed MinerU JSON {path.name}: {exc}")
            continue
        _parse_json_payload(payload, document, source_file)

    if not document.pages:
        page_number = 1
        document.pages.append(
            DocumentPage(
                number=page_number,
                text="\n".join(block.text for block in document.text_blocks),
                provenance=Provenance(source_file, source_page=page_number),
            )
        )
    document.metadata.update(
        {
            "source_file": source_file,
            "backend": backend,
            "method": method,
            "pages": document.page_count,
            "tables": document.table_count,
            "assets": len(document.images),
            "asset_paths": [image["path"] for image in document.images],
        }
    )
    return document


def parse_pdf_native_fallback(input_path: str | os.PathLike[str]) -> MinerUDocument:
    """Adapt the deterministic PDF-native fallback directly into common IR.

    This path never creates an XLSX and therefore cannot enter an Excel parser.
    It intentionally preserves the fallback engine, page, table, and raw text
    provenance for the same normalizer used by MinerU output.
    """
    from core.import_adapters.pdf_tables import extract_tables

    source = str(Path(input_path).expanduser().resolve())
    result = extract_tables(source)
    if not result.get("tables"):
        raise MinerUOutputError(
            "PDF fallback produced no tables or text: "
            + str(result.get("error") or "unknown PDF fallback error")
        )
    document = MinerUDocument(
        source_file=source,
        backend="pdf-native-fallback",
        method=str(result.get("engine") or "pdf-native"),
        metadata={
            "fallback": True,
            "engine": result.get("engine"),
            "tier": result.get("tier"),
            "metrics": result.get("metrics", []),
        },
    )
    page_numbers: set[int] = set()
    for table_number, payload in enumerate(result.get("tables", []), 1):
        data = payload.get("data", []) if isinstance(payload, Mapping) else []
        report = payload.get("report", {}) if isinstance(payload, Mapping) else {}
        if not isinstance(data, list) or not data:
            continue

        # PyMuPDF fallback returns a wrapper whose records carry their own
        # page and data values.  Camelot/OCR return ordinary row dictionaries.
        nested = [item for item in data if isinstance(item, Mapping) and isinstance(item.get("data"), Mapping)]
        if nested:
            records = [item.get("data", {}) for item in nested]
            page = report.get("page")
            if page is None:
                page = nested[0].get("page")
        else:
            records = [item for item in data if isinstance(item, Mapping)]
            page = payload.get("page") if isinstance(payload, Mapping) else None
            page = page if page is not None else report.get("page")

        if not records:
            continue
        headers: list[str] = []
        for record in records:
            for key in record:
                if key not in headers:
                    headers.append(str(key))
        rows = [[str(record.get(header, "") or "") for header in headers] for record in records]
        try:
            page_number = int(page) if page is not None else None
        except (TypeError, ValueError):
            page_number = None
        if page_number is not None:
            page_numbers.add(page_number)
        document.tables.append(
            DocumentTable(
                headers=headers,
                rows=rows,
                provenance=Provenance(
                    source,
                    source_page=page_number,
                    extraction_method=f"pdf-fallback-{result.get('engine') or 'native'}",
                    source_table=f"pdf-table-{table_number}",
                ),
                name=f"PDF table {table_number}",
            )
        )

    if not document.tables:
        raise MinerUOutputError("PDF fallback returned rows in an unsupported shape")
    for page_number in sorted(page_numbers) or [1]:
        document.pages.append(
            DocumentPage(
                number=page_number,
                provenance=Provenance(source, source_page=page_number, extraction_method="pdf-native-fallback"),
            )
        )
    document.metadata.update({"pages": document.page_count, "tables": document.table_count})
    return document


def _new_provenance(source_file: str, page: Optional[int] = None, *, method: str = "mineru") -> Provenance:
    return Provenance(source_file=source_file, source_page=page, extraction_method=method)


def _parse_markdown(text: str, document: MinerUDocument, source_file: str) -> None:
    lines = text.splitlines()
    current_page: Optional[int] = None
    current_heading = ""
    page_text: dict[int, list[str]] = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        page_match = re.search(r"(?:page|page_num|page-number)\s*[:=]\s*(\d+)", line, re.I)
        if page_match:
            current_page = int(page_match.group(1))
        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading_match:
            current_heading = heading_match.group(2).strip()
            document.headings.append(
                DocumentHeading(
                    text=current_heading,
                    level=len(heading_match.group(1)),
                    provenance=_new_provenance(source_file, current_page),
                )
            )
        if _is_markdown_table_header(lines, i):
            headers = _split_markdown_row(line)
            rows: list[list[str]] = []
            i += 2  # header plus separator
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(_split_markdown_row(lines[i].strip()))
                i += 1
            document.tables.append(
                DocumentTable(
                    headers=headers,
                    rows=rows,
                    provenance=_new_provenance(source_file, current_page, method="mineru-markdown-table"),
                    name=current_heading,
                )
            )
            continue
        if line:
            if not heading_match and not line.startswith("<!--"):
                document.text_blocks.append(
                    DocumentTextBlock(line, _new_provenance(source_file, current_page, method="mineru-markdown"))
                )
                page_key = current_page or 1
                page_text.setdefault(page_key, []).append(line)
        i += 1

    for number, values in sorted(page_text.items()):
        document.pages.append(
            DocumentPage(
                number=number,
                text="\n".join(values),
                provenance=_new_provenance(source_file, number),
            )
        )


def _is_markdown_table_header(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and "|" in lines[index]
        and "|" in lines[index + 1]
        and bool(re.search(r"\|?\s*:?-{3,}:?\s*\|", lines[index + 1]))
    )


def _split_markdown_row(line: str) -> list[str]:
    value = line.strip().strip("|")
    return [part.strip() for part in value.split("|")]


class _HTMLTableParser(HTMLParser):
    """Small stdlib-only parser for MinerU table_body HTML fragments."""

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: Optional[list[str]] = None
        self._cell: Optional[list[str]] = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"th", "td"} and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        lowered = tag.lower()
        if lowered in {"th", "td"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif lowered == "tr" and self._row is not None:
            if any(cell.strip() for cell in self._row):
                self.rows.append(self._row)
            self._row = None


def _parse_html_table(value: str) -> tuple[list[str], list[list[str]]]:
    parser = _HTMLTableParser()
    try:
        parser.feed(value)
        parser.close()
    except (TypeError, ValueError):
        return [], []
    if not parser.rows:
        return [], []
    return parser.rows[0], parser.rows[1:]


def _parse_json_payload(payload: Any, document: MinerUDocument, source_file: str) -> None:
    """Extract common MinerU JSON shapes while preserving unknown values."""
    seen_texts = {block.text for block in document.text_blocks}

    def visit(node: Any, page: Optional[int] = None, sheet: Optional[str] = None) -> None:
        if isinstance(node, Mapping):
            page_value = node.get("page", node.get("page_idx", node.get("page_id", page)))
            try:
                page_value = int(page_value) if page_value is not None else page
            except (TypeError, ValueError):
                page_value = page
            sheet_value = node.get("sheet", node.get("sheet_name", sheet))
            if isinstance(sheet_value, (int, float)):
                sheet_value = str(sheet_value)

            for key in ("text", "content", "markdown", "md"):
                value = node.get(key)
                if isinstance(value, str) and value.strip() and value.strip() not in seen_texts:
                    text = value.strip()
                    document.text_blocks.append(
                        DocumentTextBlock(text, Provenance(source_file, page_value, sheet_value, extraction_method="mineru-json"))
                    )
                    seen_texts.add(text)

            table_body = node.get("table_body")
            if isinstance(table_body, str) and "<table" in table_body.lower():
                html_headers, html_rows = _parse_html_table(table_body)
                if html_headers:
                    document.tables.append(
                        DocumentTable(
                            headers=html_headers,
                            rows=html_rows,
                            provenance=Provenance(
                                source_file,
                                page_value,
                                sheet_value,
                                extraction_method="mineru-json-html-table",
                            ),
                            name=str(node.get("title", node.get("caption", "")) or ""),
                        )
                    )

            headers = node.get("headers", node.get("columns"))
            rows = node.get("rows", node.get("data"))
            if isinstance(headers, list) and isinstance(rows, list):
                normalized_headers = [_cell_text(value) for value in headers]
                normalized_rows = [
                    [_cell_text(value) for value in row]
                    for row in rows
                    if isinstance(row, (list, tuple))
                ]
                if normalized_headers:
                    document.tables.append(
                        DocumentTable(
                            headers=normalized_headers,
                            rows=normalized_rows,
                            provenance=Provenance(
                                source_file,
                                page_value,
                                sheet_value,
                                extraction_method="mineru-json-table",
                            ),
                            name=str(node.get("name", node.get("title", "")) or ""),
                        )
                    )

            for key, value in node.items():
                if key not in {"text", "content", "markdown", "md", "headers", "columns", "rows", "data"}:
                    visit(value, page_value, sheet_value)
        elif isinstance(node, list):
            for item in node:
                visit(item, page, sheet)
        elif isinstance(node, str) and node.strip() and node.strip() not in seen_texts:
            # Only long/free text values are treated as blocks; short JSON
            # labels and IDs are left for their containing structure.
            if len(node.strip()) > 20:
                document.text_blocks.append(
                    DocumentTextBlock(node.strip(), Provenance(source_file, page, sheet, extraction_method="mineru-json"))
                )
                seen_texts.add(node.strip())

    visit(payload)
    page_numbers = sorted(
        {
            block.provenance.source_page
            for block in document.text_blocks
            if block.provenance.source_page is not None
        }
    )
    for number in page_numbers:
        if not any(page.number == number for page in document.pages):
            values = [
                block.text
                for block in document.text_blocks
                if block.provenance.source_page == number
            ]
            document.pages.append(
                DocumentPage(number, "\n".join(values), _new_provenance(source_file, number, method="mineru-json"))
            )


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Mapping):
        for key in ("text", "content", "value"):
            if key in value:
                return _cell_text(value[key])
    return str(value).strip()


@dataclass
class CanonicalValidation:
    valid: bool
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class NormalizedDocument:
    source_file: str
    canonical_data: dict[str, Any]
    provenance: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    validation: CanonicalValidation
    fields_extracted: int
    tables_extracted: int
    pages: int
    needs_review: bool = False
    raw_document: Any = None
    backend: str = ""
    method: str = ""

    def metadata(self) -> dict[str, Any]:
        return {
            "source": "MinerU",
            "backend": self.backend,
            "method": self.method,
            "pages": self.pages,
            "tables": self.tables_extracted,
            "fields_extracted": self.fields_extracted,
            "needs_review": self.needs_review,
            "warnings": self.warnings,
            "validation_errors": self.validation.errors,
            "mineru_provenance": self.provenance,
            "raw_ir": self.raw_document.to_dict(include_cells=True) if self.raw_document is not None else None,
        }


class DocumentNormalizer:
    """Map only unambiguous MinerU items to the existing canonical schema."""

    @staticmethod
    def _update_raw_cell_state(raw_document, table_index: int, row_number: int,
                               column_index: int, normalized_value: Any,
                               field_path: Optional[str], normalization: Any,
                               review: bool = False) -> None:
        """Carry normalization/validation/review state back into the IR."""
        if raw_document is None or table_index >= len(raw_document.tables):
            return
        table = raw_document.tables[table_index]
        if row_number <= 0 or row_number > len(table.rows):
            return
        row = table.rows[row_number - 1]
        if column_index <= 0 or column_index > len(row):
            return
        cell = row[column_index - 1]
        cell.normalized_value = normalized_value
        spec = FIELD_SPECS.get(field_path) if field_path else None
        cell.normalized_unit = spec.unit if spec is not None else None
        cell.validation_state = (
            "valid" if normalization is None or getattr(normalization, "ok", False)
            else "needs_review"
        )
        cell.review_state = "review" if review or cell.validation_state != "valid" else "accepted"
        if review:
            table.review_state = "review"

    @staticmethod
    def _table_source(provenance: Provenance, table: DocumentTable) -> dict[str, Any]:
        source = provenance.to_dict()
        source["source_table"] = table.name or None
        return source

    TABLE_KEY_MAP = {
        "time_log": "time_logs_24h",
        "time_log_morning": "time_logs_morning",
        "survey": "surveys",
        "mud_chemical": "bulk_materials",
        "bha": "bha_components",
        "downhole": "downhole_equipment",
        "drilling_param": "drilling_params_table",
        "scr": "scr_data",
        "bop": "bop_components",
        "formation": "formation_data",
        "solid_control": "solid_control",
        "transport": "boats",
        "lookahead": "lookahead",
        "service": "service_companies",
        "cement": "cement_additives",
        "fuel_water": "fuel_water_data",
        "casing": "casing_data",
        "pob": "pob_data",
        "time_breakdown": "time_breakdown",
    }

    def normalize(self, document: MinerUDocument) -> NormalizedDocument:
        # The external engine's representation is adapted to the same raw IR
        # used by Excel before canonical mapping/typed normalization.
        raw_document = raw_document_from_mineru(document)
        canonical: dict[str, Any] = {}
        provenance: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        fields_extracted = 0

        for table_index, table in enumerate(document.tables):
            raw_table = raw_document.tables[table_index] if table_index < len(raw_document.tables) else None
            headers = [str(cell.value) for cell in raw_table.headers] if raw_table is not None else list(table.headers)
            rows = [[cell.value for cell in row] for row in raw_table.rows] if raw_table is not None else list(table.rows)
            table_fields: list[Optional[str]] = []
            table_context = f"{table.name} {' '.join(headers)}".lower()
            for header in headers:
                field_path = self._resolve_field(header, table_context)
                table_fields.append(field_path)
                if field_path is None and header.strip():
                    warnings.append(
                        {
                            "level": "review",
                            "message": f"No unambiguous canonical field for table column '{header}'.",
                            "source": self._table_source(table.provenance, table),
                        }
                    )
            storage_key = self._storage_key(table_context, table_fields)
            if any(field_path for field_path in table_fields):
                table_records: list[dict[str, Any]] = []
                for row_number, row in enumerate(rows, 1):
                    row_class = self._classify_row(row, headers, table_fields)
                    if row_class != "data":
                        warnings.append(
                            {
                                "level": "review",
                                "message": f"Ignored {row_class} row; it was not mapped as report data.",
                                "value": " | ".join(str(cell) for cell in row if cell not in (None, "")),
                                "source": Provenance(
                                    document.source_file,
                                    table.provenance.source_page,
                                    table.provenance.source_sheet,
                                    row_number,
                                    None,
                                    table.provenance.bounding_box,
                                    table.provenance.extraction_method,
                                    table.provenance.confidence,
                                    source_table=table.name,
                                ).to_dict(),
                            }
                        )
                        continue
                    record: dict[str, Any] = {}
                    for index, field_path in enumerate(table_fields):
                        if field_path is None or index >= len(row):
                            continue
                        value = row[index]
                        if value == "":
                            continue
                        spec = FIELD_SPECS.get(field_path)
                        normalized_value = value
                        normalization = normalize_for_field(value, spec) if spec is not None else None
                        if normalization is not None:
                            normalized_value = normalization.value if normalization.ok else None
                            if normalization.needs_review or (
                                normalization.missing and isinstance(value, str) and value.strip()
                            ):
                                warnings.append(
                                    {
                                        "level": "review",
                                        "field": field_path,
                                        "value": value,
                                        "normalized_value": None,
                                        "expected_type": normalization.expected_type,
                                        "message": (
                                            f"Value {value!r} was preserved for review; it is not a safe "
                                            f"{normalization.expected_type} literal."
                                        ),
                                        "source": Provenance(
                                            document.source_file,
                                            table.provenance.source_page,
                                            table.provenance.source_sheet,
                                            row_number,
                                            index + 1,
                                            table.provenance.bounding_box,
                                            table.provenance.extraction_method,
                                            table.provenance.confidence,
                                            source_table=table.name,
                                        ).to_dict(),
                                    }
                                )
                        self._update_raw_cell_state(
                            raw_document, table_index, row_number, index + 1,
                            normalized_value, field_path, normalization,
                            review=bool(
                                normalization is not None
                                and (normalization.needs_review or normalization.missing)
                            ),
                        )
                        short_key = field_path.rsplit(".", 1)[-1]
                        record[short_key] = normalized_value
                        fields_extracted += 1
                        item_provenance = Provenance(
                            source_file=document.source_file,
                            source_page=table.provenance.source_page,
                            source_sheet=table.provenance.source_sheet,
                            source_row=row_number,
                            source_column=index + 1,
                            bounding_box=table.provenance.bounding_box,
                            extraction_method=table.provenance.extraction_method,
                            confidence=table.provenance.confidence,
                            source_table=table.name,
                        ).to_dict()
                        provenance.append(
                            {
                                "canonical_field": field_path,
                                "original_value": value,
                                "normalized_value": normalized_value,
                                "value": value,  # legacy consumer alias
                                "normalization_state": (
                                    "missing" if normalization is not None and normalization.missing
                                    else "valid" if normalization is None or normalization.ok
                                    else "needs_review"
                                ),
                                **item_provenance,
                            }
                        )
                    if record:
                        record["_source_row"] = row_number
                        record["_source_cells"] = {
                            str(field_path or headers[index]): {
                                "page": table.provenance.source_page,
                                "row": row_number,
                                "column": index + 1,
                            }
                            for index, field_path in enumerate(table_fields)
                            if index < len(headers)
                        }
                        if storage_key == "time_logs_morning" and record.get("time_from") in (None, ""):
                            record["_classification"] = "continuation"
                            record["_review_reason"] = "Continuation text has no independent time anchor"
                        table_records.append(record)

                # Existing DB import code expects scalar report sections as
                # dictionaries. A one-row MinerU table can safely take that
                # shape; multi-row data remains a list collection.
                scalar_sections = {"well_info", "daily_report", "mud_report", "drilling_params"}
                if storage_key in scalar_sections and len(table_records) == 1:
                    existing = canonical.get(storage_key)
                    if existing is None:
                        canonical[storage_key] = table_records[0]
                    elif isinstance(existing, dict):
                        warnings.append(
                            {
                                "level": "review",
                                "message": f"Duplicate canonical section {storage_key}; table values were not selected.",
                                "source": self._table_source(table.provenance, table),
                            }
                        )
                elif table_records:
                    canonical.setdefault(storage_key, []).extend(table_records)

        for block_index, block in enumerate(document.text_blocks):
            raw_text = raw_document.text_blocks[block_index][0] if block_index < len(raw_document.text_blocks) else block.text
            field_path, value = self._resolve_text_block(raw_text)
            if field_path is None:
                warnings.append({
                    "level": "review",
                    "message": f"Unresolved or ambiguous text label in document: {raw_text!r}",
                    "value": raw_text,
                    "source": block.provenance.to_dict(),
                })
                continue
            section, key = field_path.split(".", 1)
            section_data = canonical.setdefault(section, {})
            if key in section_data:
                warnings.append(
                    {
                        "level": "review",
                        "message": f"Duplicate canonical value for {field_path}; later value was not selected.",
                        "source": block.provenance.to_dict(),
                    }
                )
                continue
            spec = FIELD_SPECS.get(field_path)
            normalization = normalize_for_field(value, spec) if spec is not None else None
            normalized_value = value if normalization is None else (normalization.value if normalization.ok else None)
            section_data[key] = normalized_value
            if normalization is not None and (
                normalization.needs_review
                or (normalization.missing and isinstance(value, str) and value.strip())
            ):
                warnings.append(
                    {
                        "level": "review",
                        "field": field_path,
                        "value": value,
                        "normalized_value": None,
                        "expected_type": normalization.expected_type,
                        "message": (
                            f"Value {value!r} was preserved for review; it is not a safe "
                            f"{normalization.expected_type} literal."
                        ),
                        "source": block.provenance.to_dict(),
                    }
                )
            fields_extracted += 1
            provenance.append(
                {
                    "canonical_field": field_path,
                    "original_value": value,
                    "normalized_value": normalized_value,
                    "value": value,
                    "normalization_state": (
                        "missing" if normalization is not None and normalization.missing
                        else "valid" if normalization is None or normalization.ok
                        else "needs_review"
                    ),
                    **block.provenance.to_dict(),
                }
            )

        validation = validate_canonical_payload(canonical)
        warnings.extend(validation.warnings)
        # A normalization review is also a validation warning at the import
        # boundary, even though the typed canonical payload now contains NULL.
        # This keeps UI/error summaries from losing malformed source tokens.
        validation.warnings.extend(
            warning for warning in warnings if warning not in validation.warnings
        )
        return NormalizedDocument(
            source_file=document.source_file,
            canonical_data=canonical,
            provenance=provenance,
            warnings=warnings,
            validation=validation,
            fields_extracted=fields_extracted,
            tables_extracted=document.table_count,
            pages=document.page_count,
            needs_review=bool(warnings or validation.errors),
            raw_document=raw_document,
            backend=document.backend,
            method=document.method,
        )

    @staticmethod
    def _classify_row(row: list[str], headers: list[str], fields: list[Optional[str]]) -> str:
        """Keep headings/units/notes out of typed record conversion.

        MinerU commonly emits a section title such as ``Drilling Data`` as a
        physical table row.  It is metadata, not a drilling parameter.  The
        classifier is intentionally conservative: mixed/textual operational
        rows are retained, while a row that is clearly a repeated header,
        unit row, or title is reviewed and skipped.
        """
        values = [str(value).strip() for value in row if value not in (None, "")]
        if not values:
            return "empty"
        lowered = [value.lower() for value in values]
        header_tokens = {
            " ".join(str(header).strip().lower().split())
            for header in headers if str(header).strip()
        }
        if any(value in header_tokens for value in lowered):
            return "repeated-header"
        if any(re.fullmatch(r"(?:[a-z°²%/]+(?:-[a-z0-9²%/]+)?)", value) for value in lowered):
            numeric_fields = sum(
                1 for field_path in fields
                if field_path and FIELD_SPECS.get(field_path) and FIELD_SPECS[field_path].quantity in {
                    "integer", "number", "length", "density", "pressure", "force", "rpm", "torque",
                    "rate", "flow_rate", "volume", "viscosity", "temperature", "angle", "dls", "area",
                    "stress", "currency",
                }
            )
            if numeric_fields and not any(re.search(r"\d", value) for value in lowered):
                return "unit"
        if len(values) == 1 and re.search(
            r"\b(?:drilling data|mud data|daily report|report data|table|parameters?|notes?|remarks?)\b",
            values[0],
            re.IGNORECASE,
        ):
            return "title"
        return "data"

    @staticmethod
    def _resolve_field(label: str, context: str = "") -> Optional[str]:
        normalized = " ".join(str(label).strip().lower().split())
        context = " ".join(str(context or "").lower().split())
        if not normalized:
            return None
        exact = [path for path in FIELD_SPECS if path.lower() == normalized]
        if len(exact) == 1:
            return exact[0]
        candidates = [
            path
            for path, spec in FIELD_SPECS.items()
            if normalized in {" ".join(alias.lower().split()) for alias in spec.aliases}
        ]
        # ``Hrs`` is intentionally broad in the canonical schema. Add the
        # morning duration candidate only when the surrounding table context
        # says it is a morning time log; absent that context it remains
        # ambiguous and is emitted for review.
        if normalized in {"hrs", "hours"} and "time log morning" in context:
            if "time_log_morning.duration" not in candidates:
                candidates.append("time_log_morning.duration")
        if len(candidates) == 1:
            return candidates[0]
        # Context may safely disambiguate a table whose title explicitly
        # names a canonical section; it never invents a value or unit. Prefer
        # the most specific section phrase ("time log morning" over "time log").
        sections = {path.split(".", 1)[0] for path in candidates}
        section_aliases = {
            "well_info": ("well info", "well information"),
            "daily_report": ("daily report", "daily reporting"),
            "time_log": ("time log", "24h log", "24 hour log"),
            "time_log_morning": ("time log morning", "morning log", "morning time log"),
        }
        contextual = [
            section for section in sections
            if any(
                re.search(rf"\b{re.escape(alias)}\b", context)
                for alias in section_aliases.get(section, (section.replace("_", " "),))
            )
        ]
        for section in sorted(contextual, key=len, reverse=True):
            scoped = [path for path in candidates if path.startswith(section + ".")]
            if len(scoped) == 1:
                return scoped[0]
        # Existing alias lookup is useful for exact, non-colliding aliases.
        mapped = lookup_alias(label)
        return mapped if mapped in candidates and len(candidates) == 1 else None

    def _resolve_text_block(self, text: str) -> tuple[Optional[str], str]:
        match = re.match(r"^\s*([^:：|\t]{2,80})\s*[:：|\t]\s*(.+?)\s*$", text)
        if not match:
            return None, ""
        label, value = match.groups()
        normalized = " ".join(label.lower().split())
        # A qualified label supplies context; a bare ambiguous alias remains
        # unresolved and is emitted as review by normalize().
        if normalized.endswith("report date"):
            field_path = self._resolve_field("report date", normalized)
        elif normalized.endswith("hrs") or normalized.endswith("hours"):
            field_path = self._resolve_field("hrs", normalized)
        else:
            field_path = self._resolve_field(label, normalized)
        return field_path, value.strip()

    def _storage_key(self, context: str, fields: list[Optional[str]]) -> str:
        sections = [field_path.split(".", 1)[0] for field_path in fields if field_path]
        if sections:
            section = sections[0]
            if all(item == section for item in sections):
                return self.TABLE_KEY_MAP.get(section, section)
        # Unknown mixed tables are not flattened into a guessed database
        # collection.  A neutral document table keeps the extracted values in
        # the intermediate/canonical review payload only.
        return "document_tables"


def _safe_canonical_value(field_path: str, value: Any) -> Any:
    """Return a typed value or ``None``; never leak malformed text to SQL.

    The normalizer's caller records the original token and location as a
    review item.  This helper remains for compatibility with integrations that
    imported it directly.
    """
    spec = FIELD_SPECS.get(field_path)
    if spec is None:
        return value
    result = normalize_for_field(value, spec)
    return result.value if result.ok else None


def validate_canonical_payload(canonical: Mapping[str, Any]) -> CanonicalValidation:
    """Validate mapped values against existing FieldSpec bounds/types.

    Missing fields are not errors because a document may be a partial report.
    Present but ambiguous/out-of-range values are errors or review warnings;
    they are never replaced with defaults.
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    numeric_quantities = {
        "integer", "number", "length", "density", "pressure", "force", "rpm",
        "torque", "rate", "flow_rate", "volume", "viscosity", "temperature",
        "angle", "dls", "area", "stress", "currency",
    }
    collection_sections = {
        "surveys": "survey",
        "time_logs_24h": "time_log",
        "time_logs_morning": "time_log_morning",
        "drilling_params_table": "drilling_param",
        "bha_components": "bha",
        "downhole_equipment": "downhole",
        "bulk_materials": "bulk_material",
        "bop_components": "bop",
        "cement_additives": "cement",
        "service_companies": "service",
        "lookahead": "lookahead",
        "fuel_water_data": "fuel_water",
        "casing_data": "casing",
        "pob_data": "pob",
    }

    def validate_value(field_path: str, value: Any) -> None:
        spec = FIELD_SPECS.get(field_path)
        if spec is None or value is None or value == "":
            return
        if spec.quantity in numeric_quantities and not isinstance(value, (int, float)):
            warnings.append({
                "level": "review",
                "field": field_path,
                "value": value,
                "message": "Numeric field was preserved as text because its unit/value was ambiguous.",
            })
            return
        if spec.quantity == "integer" and isinstance(value, float) and not value.is_integer():
            errors.append({"level": "error", "field": field_path, "value": value, "message": "Expected an integer."})
            return
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if spec.min_val is not None and value < spec.min_val:
                errors.append({"level": "error", "field": field_path, "value": value, "message": f"Value is below minimum {spec.min_val}."})
            if spec.max_val is not None and value > spec.max_val:
                errors.append({"level": "error", "field": field_path, "value": value, "message": f"Value exceeds maximum {spec.max_val}."})

    for section, values in canonical.items():
        if isinstance(values, list):
            schema_section = collection_sections.get(section)
            for record in values:
                if not isinstance(record, Mapping) or not schema_section:
                    continue
                for key, value in record.items():
                    validate_value(f"{schema_section}.{key}", value)
            continue
        if not isinstance(values, Mapping):
            warnings.append({"level": "review", "field": section, "message": "Unstructured canonical section retained for review."})
            continue
        for key, value in values.items():
            validate_value(f"{section}.{key}", value)
    return CanonicalValidation(valid=not errors, errors=errors, warnings=warnings)
