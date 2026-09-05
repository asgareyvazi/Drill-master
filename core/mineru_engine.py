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
from core.runtime_config import read_mineru_settings

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
    backend: str = "hybrid-engine"
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
        ) or "hybrid-engine"
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


@dataclass
class MinerUHealth:
    available: bool
    enabled: bool
    executable: Optional[str]
    python_executable: Optional[str]
    version: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "enabled": self.enabled,
            "executable": self.executable,
            "python_executable": self.python_executable,
            "version": self.version,
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
                error="MinerU is disabled or not detected",
            )
        if not prefix:
            return MinerUHealth(
                available=False,
                enabled=True,
                executable=None,
                python_executable=self.config.python_executable,
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
            )
        except MinerUError as exc:
            return MinerUHealth(
                available=False,
                enabled=True,
                executable=self.config.executable,
                python_executable=self.config.python_executable,
                error=str(exc),
            )

    def get_version(self) -> str:
        prefix = self._command_prefix()
        if not prefix:
            raise MinerUNotInstalledError(
                "MinerU was not found. Configure its executable or Python environment."
            )
        try:
            completed = self._run_control(prefix + ["--version"])
        except FileNotFoundError as exc:
            raise MinerUExecutableError(f"MinerU executable could not be started: {exc}") from exc
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
                return match
            if help_result.returncode == 0:
                return "unknown"
            raise MinerUExecutableError(
                f"MinerU CLI probe failed with exit code {completed.returncode}: "
                f"{_safe_process_message(output)}"
            )
        return _version_from_text(output) or "unknown"

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

        temporary: Optional[tempfile.TemporaryDirectory[str]] = None
        try:
            root = Path(output_dir).expanduser().resolve() if output_dir else self.config.output_dir
            if root is None:
                temporary = tempfile.TemporaryDirectory(prefix="drillmaster-mineru-")
                root = Path(temporary.name)
            root.mkdir(parents=True, exist_ok=True)
            identity = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:10]
            run_dir = root / f"{source.stem}-{identity}"
            if run_dir.exists():
                shutil.rmtree(run_dir)
            run_dir.mkdir(parents=True, exist_ok=True)
            command = self._command_prefix() + [
                "-p",
                str(source),
                "-o",
                str(run_dir),
                "-b",
                self.config.backend,
                "-m",
                self.config.method,
            ]
            logger.info(
                "MinerU parse started: file=%s backend=%s method=%s",
                source.name,
                self.config.backend,
                self.config.method,
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
                    output_dir=str(run_dir) if self.config.keep_output else None,
                    fallback_available=source.suffix.lower() == ".pdf",
                )
            except FileNotFoundError as exc:
                return self._failure(
                    source_display,
                    "executable-not-found",
                    f"MinerU executable could not be started: {exc}",
                    started,
                    output_dir=str(run_dir) if self.config.keep_output else None,
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
                    output_dir=str(run_dir) if self.config.keep_output else None,
                    fallback_available=source.suffix.lower() == ".pdf",
                )
            try:
                document = parse_mineru_output(
                    run_dir,
                    source_file=str(source),
                    backend=self.config.backend,
                    method=self.config.method,
                )
            except MinerUOutputError as exc:
                return self._failure(
                    source_display,
                    "output-missing",
                    str(exc),
                    started,
                    stdout=stdout,
                    stderr=stderr,
                    output_dir=str(run_dir) if self.config.keep_output else None,
                    fallback_available=source.suffix.lower() == ".pdf",
                )
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
                output_dir=str(run_dir) if self.config.keep_output else None,
            )
        except OSError as exc:
            return self._failure(source_display, "output-error", f"MinerU output directory error: {exc}", started)
        finally:
            if temporary is not None and self.config.keep_output:
                # keep_output with an implicit temporary root is intentionally
                # not useful; do not leave an unreferenced temporary tree.
                temporary.cleanup()
            elif temporary is not None:
                temporary.cleanup()

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


def parse_mineru_output(
    output_dir: str | os.PathLike[str],
    *,
    source_file: str,
    backend: str = "hybrid-engine",
    method: str = "auto",
) -> MinerUDocument:
    """Parse a MinerU output directory without assuming a single layout."""
    root = Path(output_dir)
    if not root.is_dir():
        raise MinerUOutputError(f"MinerU output directory is missing: {root}")
    files = [path for path in root.rglob("*") if path.is_file()]
    markdown_files = sorted(path for path in files if path.suffix.lower() in {".md", ".markdown"})
    json_files = sorted(path for path in files if path.suffix.lower() == ".json")
    asset_files = sorted(path for path in files if path.suffix.lower() in IMAGE_SUFFIXES)
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
                "path": str(path.relative_to(root)),
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
        }
    )
    return document


def _new_provenance(source_file: str, page: Optional[int] = None, *, method: str = "mineru") -> Provenance:
    return Provenance(source_file=source_file, source_page=page, extraction_method=method)


def _parse_markdown(text: str, document: MinerUDocument, source_file: str) -> None:
    lines = text.splitlines()
    current_page: Optional[int] = None
    page_text: dict[int, list[str]] = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        page_match = re.search(r"(?:page|page_num|page-number)\s*[:=]\s*(\d+)", line, re.I)
        if page_match:
            current_page = int(page_match.group(1))
        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading_match:
            document.headings.append(
                DocumentHeading(
                    text=heading_match.group(2).strip(),
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

    def metadata(self) -> dict[str, Any]:
        return {
            "source": "MinerU",
            "backend": "",
            "method": "",
            "pages": self.pages,
            "tables": self.tables_extracted,
            "fields_extracted": self.fields_extracted,
            "needs_review": self.needs_review,
            "warnings": self.warnings,
            "validation_errors": self.validation.errors,
            "mineru_provenance": self.provenance,
        }


class DocumentNormalizer:
    """Map only unambiguous MinerU items to the existing canonical schema."""

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
        canonical: dict[str, Any] = {}
        provenance: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        fields_extracted = 0

        for table in document.tables:
            table_fields: list[Optional[str]] = []
            table_context = f"{table.name} {' '.join(table.headers)}".lower()
            for header in table.headers:
                field_path = self._resolve_field(header, table_context)
                table_fields.append(field_path)
                if field_path is None and header.strip():
                    warnings.append(
                        {
                            "level": "review",
                            "message": f"No unambiguous canonical field for table column '{header}'.",
                            "source": table.provenance.to_dict(),
                        }
                    )
            storage_key = self._storage_key(table_context, table_fields)
            if any(field_path for field_path in table_fields):
                table_records: list[dict[str, Any]] = []
                for row_number, row in enumerate(table.rows, 1):
                    record: dict[str, Any] = {}
                    for index, field_path in enumerate(table_fields):
                        if field_path is None or index >= len(row):
                            continue
                        value = row[index]
                        if value == "":
                            continue
                        short_key = field_path.rsplit(".", 1)[-1]
                        record[short_key] = _safe_canonical_value(field_path, value)
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
                        ).to_dict()
                        provenance.append(
                            {
                                "canonical_field": field_path,
                                "value": value,
                                **item_provenance,
                            }
                        )
                    if record:
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
                                "source": table.provenance.to_dict(),
                            }
                        )
                elif table_records:
                    canonical.setdefault(storage_key, []).extend(table_records)

        for block in document.text_blocks:
            field_path, value = self._resolve_text_block(block.text)
            if field_path is None:
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
            section_data[key] = _safe_canonical_value(field_path, value)
            fields_extracted += 1
            provenance.append(
                {
                    "canonical_field": field_path,
                    "value": value,
                    **block.provenance.to_dict(),
                }
            )

        validation = validate_canonical_payload(canonical)
        warnings.extend(validation.warnings)
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
        )

    @staticmethod
    def _resolve_field(label: str, context: str = "") -> Optional[str]:
        normalized = " ".join(str(label).strip().lower().split())
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
        if len(candidates) == 1:
            return candidates[0]
        # Context may safely disambiguate a table whose title explicitly
        # names a canonical section; it never invents a value or unit.
        sections = {path.split(".", 1)[0] for path in candidates}
        for section in sections:
            if re.search(rf"\b{re.escape(section.replace('_', ' '))}\b", context):
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
        return self._resolve_field(label), value.strip()

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
    """Convert only unambiguous numeric literals; never infer units/dates."""
    spec = FIELD_SPECS.get(field_path)
    if spec is None or spec.quantity not in {
        "integer",
        "number",
        "length",
        "density",
        "pressure",
        "force",
        "rpm",
        "torque",
        "rate",
        "flow_rate",
        "volume",
        "viscosity",
        "temperature",
        "angle",
        "dls",
        "area",
        "stress",
        "currency",
    }:
        return value
    text = str(value).strip().replace(",", "")
    if re.fullmatch(r"[-+]?\d+", text):
        return int(text)
    if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", text):
        return float(text)
    return value


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
