"""Convert CI evidence into bounded, secret-safe workflow diagnostics.

Two modes share one guarantee: a failing step always publishes an actionable,
truncated, credential-redacted ``::error::`` annotation.

``--junit`` converts a pytest JUnit XML report.  A GitHub Actions step publishes
at most ten ``::error::`` annotations, so a suite with more failures than that
silently loses detail; this parser keeps one annotation per failure up to the cap
and always adds a single aggregate annotation plus a Markdown step summary that
lists every failed test identity.

``--annotate`` reports a build-stage failure, where no machine-readable report
exists yet: the exception text plus the tail of the build log(s) named on the
command line, so a packaging failure is identifiable from the check run alone.

Only test identities, exception class names, assertion text, ``file:line``
locations and build-log text are emitted.  Values that look like credentials are
redacted so a failing assertion can never publish a password, token or API key
into the run log, an annotation or the summary artifact.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_ANNOTATIONS = 10
MESSAGE_LIMIT = 300
MAX_AGGREGATE_NAMES = 25
# A single annotation must stay small enough that GitHub never truncates it
# silently; the tail of a build log is the informative part.
ANNOTATION_LIMIT = 3000

# ``tests\test_x.py:332:``, ``C:\a\tests\test_x.py:332:`` and ``tests/test_x.py:332:``
SOURCE_LOCATION = re.compile(r"(?P<path>(?:[A-Za-z]:)?[^\s:;\"'<>|]*\.py):(?P<line>\d+)")
# Raw Python tracebacks (captured subprocess stderr) use the ``File "...", line N`` form.
TRACEBACK_FILE = re.compile(r'File "(?P<path>[^"]+)", line (?P<line>\d+)')
EXCEPTION_NAME = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|Failure|Failed))\b")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)([\"']?[A-Za-z0-9_]*(?:password|passwd|passphrase|secret|token|api[_-]?key|apikey|authorization|credential)[A-Za-z0-9_]*[\"']?\s*[=:]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;)}]+)"
)
NON_TEST_FRAME = re.compile(r"(site-packages|lib[\\/]python3|_pytest[\\/]|encodings[\\/]|pathlib\.py)")


def redact(value: str) -> str:
    """Remove credential-looking values and collapse a blob into one line."""
    text = SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}<redacted>", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MESSAGE_LIMIT:
        text = text[: MESSAGE_LIMIT - 1] + "…"
    return text


def _first_meaningful_line(detail: str) -> str:
    """Return pytest's assertion line (``E   ...``), else the last traceback line."""
    lines = [line.strip() for line in (detail or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("E") and len(line) > 1:
            return line.lstrip("E").strip()
    return lines[-1] if lines else ""


def _exception_name(case, message: str, detail: str) -> str:
    attribute = (case.get("type") or "").strip()
    if attribute:
        return attribute.split(".")[-1]
    for candidate in (message, detail):
        line = (candidate or "").strip()
        if not line:
            continue
        head = line.split(":", 1)[0].strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|Failure|Failed)", head):
            return head
        match = EXCEPTION_NAME.search(line)
        if match:
            return match.group(1)
    return "test failure"


def _locations(*blobs: str) -> list[tuple[str, str]]:
    """Every ``path:line`` in the blobs, in document order, deduplicated."""
    found: list[tuple[int, str, str]] = []
    for blob in blobs:
        for pattern in (SOURCE_LOCATION, TRACEBACK_FILE):
            for match in pattern.finditer(blob or ""):
                found.append((match.start(), match.group("path"), match.group("line")))
    ordered: list[tuple[str, str]] = []
    for _, path, line in sorted(found):
        if (path, line) not in ordered:
            ordered.append((path, line))
    return ordered


def locate(detail: str, message: str) -> tuple[str, str]:
    """Return the most useful ``path:line`` for a failure.

    Pytest lists traceback frames outermost-first, so the first frame that is
    not a library or interpreter frame is the test code that asserted.  The
    full chain is kept for the Markdown summary.
    """
    matches = _locations(detail) or _locations(message)
    if not matches:
        return "source location unavailable", ""
    for path, line in matches:
        if not NON_TEST_FRAME.search(path):
            return path, line
    return matches[0]


def frames(detail: str, limit: int = 4) -> list[str]:
    seen: list[str] = []
    for path, line in _locations(detail):
        entry = f"{path}:{line}"
        if entry not in seen:
            seen.append(entry)
        if len(seen) >= limit:
            break
    return seen


def parse_report(junit_path: Path) -> dict:
    """Read a JUnit XML file; never raise on unexpected content."""
    result = {"collected": 0, "passed": 0, "skipped": 0, "failed": 0, "errors": 0,
              "failures": [], "skipped_tests": [], "parse_error": ""}
    try:
        root = ET.parse(junit_path).getroot()
    except FileNotFoundError:
        result["parse_error"] = f"JUnit report not found: {junit_path}"
        return result
    except ET.ParseError as exc:
        result["parse_error"] = f"JUnit report could not be parsed: {type(exc).__name__}"
        return result
    except OSError as exc:  # pragma: no cover - defensive on locked files
        result["parse_error"] = f"JUnit report could not be read: {type(exc).__name__}"
        return result
    for case in root.iter("testcase"):
        result["collected"] += 1
        identity = f"{case.get('classname', '<unknown class>')}.{case.get('name', '<unknown test>')}"
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        if failure is None and error is None and skipped is not None:
            result["skipped"] += 1
            result["skipped_tests"].append({"test": identity, "reason": redact(skipped.get("message") or "")})
            continue
        if failure is None and error is None:
            result["passed"] += 1
            continue
        node = failure if failure is not None else error
        if failure is not None:
            result["failed"] += 1
        else:
            result["errors"] += 1
        raw_message = node.get("message") or ""
        detail = node.text or ""
        path, line = locate(detail, raw_message)
        result["failures"].append({
            "test": identity,
            "kind": "failure" if failure is not None else "error",
            "exception": _exception_name(case, raw_message, detail),
            "location": path,
            "line": line,
            "message": redact(raw_message) or redact(_first_meaningful_line(detail)) or "(no message recorded)",
            "frames": frames(detail),
        })
    return result


def _escape_data(value: str) -> str:
    return (value or "").replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    return _escape_data(value).replace(",", "%2C").replace(":", "%3A")


def _annotation_file_property(location: str) -> str:
    """GitHub resolves ``file=`` only for repository-relative, forward-slash paths."""
    if not location or location == "source location unavailable":
        return ""
    # Pseudo-filenames such as "<string>" (exec/-c frames captured from a subprocess
    # traceback) name no file in the checkout; GitHub cannot anchor an annotation to
    # them, and a rejected annotation would hide the failure it describes.
    if "<" in location or ">" in location:
        return ""
    if re.match(r"^[A-Za-z]:[\\/]", location) or location.startswith(("/", "\\")):
        return ""
    return location.replace("\\", "/")


def render_annotations(result: dict, limit: int = MAX_ANNOTATIONS) -> list[str]:
    """One annotation per failure up to the cap, plus an uncapped aggregate."""
    failures = result.get("failures", [])
    annotations = []
    for item in failures[:limit]:
        location = item["location"] + (f":{item['line']}" if item.get("line") else "")
        attributes = []
        relative = _annotation_file_property(item["location"])
        if relative:
            attributes.append(f"file={relative}")
            if item.get("line"):
                attributes.append(f"line={item['line']}")
        suffix = f" [{', '.join(item['frames'][1:3])}]" if len(item.get("frames", [])) > 1 else ""
        body = f"{item['test']} | {item['exception']} at {location} | {item['message']}{suffix}"
        prefix = f"::error {' '.join(attributes)}::" if attributes else "::error "
        annotations.append(prefix + _escape_data(body))
    if len(failures) > limit:
        names = "; ".join(item["test"] for item in failures[limit:])
        annotations.append("::error " + _escape_data(
            f"Windows regression failures beyond the {limit}-annotation limit "
            f"({len(failures) - limit} more): {names}"))
    if failures:
        listed = ", ".join(item["test"] for item in failures[:MAX_AGGREGATE_NAMES])
        if len(failures) > MAX_AGGREGATE_NAMES:
            listed += f", … (+{len(failures) - MAX_AGGREGATE_NAMES} more)"
        annotations.append("::error " + _escape_data(
            f"Windows regression suite recorded {result['failed']} failure(s) and {result['errors']} error(s) "
            f"across {result['collected']} test(s). Full list: {listed}"))
    return annotations


def render_summary(result: dict) -> str:
    """Markdown for ``$env:GITHUB_STEP_SUMMARY``; not truncated by annotation limits."""
    lines = [
        "### Windows regression summary",
        "",
        f"- Collected: {result['collected']}  |  Passed: {result['passed']}  |  "
        f"Failed: {result['failed']}  |  Errors: {result['errors']}  |  Skipped: {result['skipped']}",
    ]
    if result.get("parse_error"):
        lines += ["", "> [!WARNING]", f"> {redact(result['parse_error'])}"]
    failures = result.get("failures", [])
    if failures:
        lines += ["", f"#### Failed tests ({len(failures)})", "",
                  "| Test | Kind | Exception | Location | Message |", "| --- | --- | --- | --- | --- |"]
        for item in failures:
            location = item["location"] + (f":{item['line']}" if item.get("line") else "")
            lines.append(f"| `{item['test']}` | {item['kind']} | {item['exception']} | `{location}` | {item['message']} |")
    skipped = result.get("skipped_tests", [])
    if skipped:
        lines += ["", f"#### Skipped tests ({len(skipped)})", ""]
        lines += [f"- `{item['test']}` — {item['reason'] or 'no reason recorded'}" for item in skipped]
    lines.append("")
    return "\n".join(lines)


def build_stage_annotation(title: str, message: str, log_paths: list[Path], tail_lines: int = 25) -> str:
    """Compose one bounded, redacted ``::error::`` annotation for a build stage.

    A packaging failure has no JUnit report, so the exception text and the tail
    of whatever log the stage produced are the only diagnostics.  Missing logs
    are named explicitly: "log not found" distinguishes a stage that died before
    writing one from a stage whose log explains the failure.
    """
    parts = [f"stage failure: {redact(message)}"] if message else ["stage failure: no exception message"]
    for path in log_paths:
        if not path or not path.is_file():
            parts.append(f"{path.name if path else 'log'}: not found")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        tail = [redact(line) for line in lines[-max(1, tail_lines):]]
        parts.append(f"{path.name} ({len(lines)} line{'s' if len(lines) != 1 else ''}, tail): "
                     + (" | ".join(tail) if tail else "empty"))
    body = " ;; ".join(parts)
    if len(body) > ANNOTATION_LIMIT:
        # The marker is part of the budget so the emitted line never exceeds it.
        body = "…" + body[-(ANNOTATION_LIMIT - 1):]
    return f"::error title={_escape_property(title)}::{_escape_data(body)}"


def emit(line: str) -> None:
    """Write to stdout without assuming the console can encode non-ASCII text.

    A Windows runner's console codepage cannot encode every character that can
    appear in a captured test message, and a UnicodeEncodeError while printing a
    diagnostic would hide the real failure.
    """
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        print(line)
        return
    buffer.write((line + "\n").encode("utf-8", errors="backslashreplace"))
    buffer.flush()


def emit_error(line: str) -> None:
    """Same encoding guarantee as :func:`emit`, for the standard-error channel."""
    buffer = getattr(sys.stderr, "buffer", None)
    if buffer is None:
        print(line, file=sys.stderr)
        return
    buffer.write((line + "\n").encode("utf-8", errors="backslashreplace"))
    buffer.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, default=None, help="pytest JUnit XML report")
    parser.add_argument("--limit", type=int, default=MAX_ANNOTATIONS, help="maximum per-failure annotations")
    parser.add_argument("--summary-out", type=Path, default=None, help="write Markdown summary to this file")
    parser.add_argument("--json-out", type=Path, default=None, help="write the parsed report as JSON")
    parser.add_argument("--annotations", action="store_true", help="print workflow commands to stdout")
    parser.add_argument("--annotate", action="store_true", help="report a build-stage failure instead of a JUnit report")
    parser.add_argument("--annotate-title", default="Build stage failure", help="annotation title")
    parser.add_argument("--annotate-message", default="", help="exception or stage text to report")
    parser.add_argument("--annotate-file", type=Path, action="append", default=[],
                        help="log file whose redacted tail is included (repeatable)")
    parser.add_argument("--tail-lines", type=int, default=25, help="log tail size per --annotate-file")
    args = parser.parse_args(argv)

    if args.annotate:
        if args.junit is not None or args.summary_out is not None or args.json_out is not None:
            emit_error("error: --annotate reports a stage failure and takes no JUnit or output-file options")
            return 2
        emit(build_stage_annotation(args.annotate_title, args.annotate_message, list(args.annotate_file),
                                   args.tail_lines))
        return 0

    if args.junit is None:
        emit_error("error: --junit is required unless --annotate is used")
        return 2

    result = parse_report(args.junit)
    if args.annotations:
        for annotation in render_annotations(result, args.limit):
            emit(annotation)
    if args.summary_out is not None:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(render_summary(result), encoding="utf-8")
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if result.get("parse_error"):
        emit(f"error: {result['parse_error']}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
