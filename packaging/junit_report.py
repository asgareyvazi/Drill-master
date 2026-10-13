"""Convert CI evidence into bounded, secret-safe workflow diagnostics.

Two modes share one guarantee: a failing step always publishes an actionable,
truncated, credential-redacted ``::error::`` annotation.  "Always" is what
``--pytest-exit`` and ``--pytest-log`` exist to keep: pytest writes its JUnit
report only when it reaches the end of a run, so a run that is interrupted,
aborted by the shell, or refused at startup leaves nothing for the per-failure
annotations to describe, and the step would fail in silence.  Given the exit
code, those two inputs turn that case into an annotation that names the exit
code, says whether the report was absent, unparsable or empty of cases, and
quotes the tail of the captured log.

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

# The limit above is what GitHub *stores*, and the store cuts from the front: measured on the Windows run this
# diagnostic was written for, a message emitted at exactly that size arrived as an ellipsis plus its last 2999
# characters.  Anything that must survive -- a headline, or a crash excerpt whose first lines are the point --
# is therefore kept inside the safe limit, with room left for the workflow-command framing.
ANNOTATION_SAFE_LIMIT = 2400

# ``tests\test_x.py:332:``, ``C:\a\tests\test_x.py:332:`` and ``tests/test_x.py:332:``
SOURCE_LOCATION = re.compile(r"(?P<path>(?:[A-Za-z]:)?[^\s:;\"'<>|]*\.py):(?P<line>\d+)")
# Raw Python tracebacks (captured subprocess stderr) use the ``File "...", line N`` form.
TRACEBACK_FILE = re.compile(r'File "(?P<path>[^"]+)", line (?P<line>\d+)')
EXCEPTION_NAME = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|Failure|Failed))\b")
SECRET_ASSIGNMENT = re.compile(
    r"(?i)([\"']?[A-Za-z0-9_]*(?:password|passwd|passphrase|secret|token|api[_-]?key|apikey|authorization|credential)[A-Za-z0-9_]*[\"']?\s*[=:]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;)}]+)"
)
NON_TEST_FRAME = re.compile(r"(site-packages|lib[\\/]python3|_pytest[\\/]|encodings[\\/]|pathlib\.py)")
# Written unbuffered to stderr by tests/conftest.py at every test start when the Windows gate arms it;
# the two spellings are one protocol, pinned on both sides by tests.
TEST_START_BREADCRUMB = "DRILLMASTER-TEST-START "


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


def render_summary(result: dict, diagnosis: str = "", crash: str = "") -> str:
    """Markdown for ``$env:GITHUB_STEP_SUMMARY``; not truncated by annotation limits."""
    lines = [
        "### Windows regression summary",
        "",
        f"- Collected: {result['collected']}  |  Passed: {result['passed']}  |  "
        f"Failed: {result['failed']}  |  Errors: {result['errors']}  |  Skipped: {result['skipped']}",
    ]
    if result.get("parse_error"):
        lines += ["", "> [!WARNING]", f"> {redact(result['parse_error'])}"]
    if diagnosis:
        lines += ["", "> [!IMPORTANT]", f"> {redact(diagnosis)}"]
    if crash:
        # The annotation carries an excerpt because GitHub truncates long annotations silently; the summary
        # has no such limit, so the reader gets the dump itself, fenced, in the order the interpreter wrote it.
        lines += ["", "#### Captured crash dump", "", "```", crash, "```", ""]
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


def _log_parts(log_paths: list[Path], tail_lines: int) -> list[str]:
    """Describe each log file, or its absence, with a bounded redacted tail.

    Missing logs are named explicitly: "not found" distinguishes a stage that died before writing one from
    a stage whose log explains the failure.
    """
    parts: list[str] = []
    for path in log_paths:
        if not path or not path.is_file():
            parts.append(f"{path.name if path else 'log'}: not found")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        tail = [redact(line) for line in lines[-max(1, tail_lines):]]
        parts.append(f"{path.name} ({len(lines)} line{'s' if len(lines) != 1 else ''}, tail): "
                     + (" | ".join(tail) if tail else "empty"))
    return parts


def _bounded(body: str) -> str:
    """Keep one annotation inside the limit, preserving its end.

    The marker is part of the budget so the emitted line never exceeds it, and the *tail* is the informative
    part of a log, so truncation eats from the front.  The safe limit rather than the store limit is used:
    a message sized to the stored maximum was observed to arrive with its first characters replaced by an
    ellipsis, which is exactly how a headline disappears.
    """
    if len(body) > ANNOTATION_SAFE_LIMIT:
        return "…" + body[-(ANNOTATION_SAFE_LIMIT - 1):]
    return body


def build_stage_annotation(title: str, message: str, log_paths: list[Path], tail_lines: int = 25) -> str:
    """Compose one bounded, redacted ``::error::`` annotation for a build stage.

    A packaging failure has no JUnit report, so the exception text and the tail
    of whatever log the stage produced are the only diagnostics.
    """
    parts = [f"stage failure: {redact(message)}"] if message else ["stage failure: no exception message"]
    parts.extend(_log_parts(log_paths, tail_lines))
    return f"::error title={_escape_property(title)}::{_escape_data(_bounded(' ;; '.join(parts)))}"


def crash_excerpt(path: Path, limit_lines: int = 20, line_width: int = 200, *, separator: str = " | ",
                  bounded: bool = True, end_lines: int = 4) -> str:
    """Quote a fatal-crash dump from a captured log, anchored on the line that says the run died.

    The *tail* of such a log is the harness's outermost frames, which say only that pytest was inside a test.
    The part that names the crashing code is the marker line and the frames right after it, so an excerpt
    taken from the end -- which is what a log tail is -- would reproduce the useless half of the dump.  A
    hard interpreter death also means no JUnit report was written, so this is the only channel that can carry
    the test's own file and line out of the run.

    Returns the empty string when the log holds no crash marker, leaving the ordinary tail quote to speak.
    """
    markers = ("Fatal Python error", "Windows fatal exception", "Current thread")
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"{path.name}: the captured log could not be read ({type(exc).__name__})"
    start = next((index for index, line in enumerate(lines) if any(marker in line for marker in markers)), None)
    if start is None:
        return ""
    header = f"crash dump from {path.name}, marker at line {start + 1} of {len(lines)}: "
    # A death in pytest's report pipeline leaves a stack of pytest plumbing that names no test at either
    # end (three consecutive Windows runs: our redaction path, traceback formatting, JUnit recording).
    # The test identity then exists only in the crash-surviving breadcrumb the suite writes unbuffered at
    # every test start (tests/conftest.py, armed by the Windows step): the last one written is the test
    # whose protocol was active when the interpreter died.  It rides in the header, so the budget loop
    # below measures it like everything else that must survive.
    crumb = ""
    for line in reversed(lines):
        # Not startswith: pytest's progress marks share the line the next breadcrumb lands on
        # ("...DRILLMASTER-TEST-START ..."), which a line-anchored search steps over -- an end-to-end
        # crash simulation named the first test of the run instead of the crashing one that way.
        at = line.rfind(TEST_START_BREADCRUMB)
        if at >= 0:
            crumb = line[at + len(TEST_START_BREADCRUMB):].strip()
            break
    if crumb:
        header += f"last test started (per the crash-surviving breadcrumb): {redact(crumb)[:200]}; "
    # On the second run this channel was used, the tally answered its question -- 37 frames, 28 distinct, only
    # pluggy's plumbing repeated, so this is not recursion -- and the frames then went somewhere else entirely
    # (ast.parse, reached from pytest's own traceback formatting).  A non-recursive stack puts the interesting
    # part at the bottom, where the test being reported on lives, and a window that only ever keeps the top
    # would keep the plumbing.  So the bounded form keeps both ends: the marker and the frames under it, then the
    # last `end_lines` frames of the dump, with the elision counted between them.  When the budget bites it is
    # the *top* that shrinks -- the elided frames are reproducible from the log, the frame that names the
    # failing test is not.
    budget = ANNOTATION_SAFE_LIMIT - 8
    over_notice = (f"{separator}…(the excerpt stopped at the annotation limit; {len(lines) - start} dump lines "
                    "were available)")
    block = lines[start:]
    tally = f"{separator}{_frame_tally(block)}"
    if bounded and len(block) > limit_lines:
        keep_head = max(limit_lines - end_lines, 1)
        head = [redact(line)[:line_width] for line in block[:keep_head]]
        tail = [redact(line)[:line_width] for line in block[len(block) - end_lines:]]

        def compose(head_count: int, tail_count: int, notice: str) -> str:
            # One builder for one string: an earlier revision measured a `compose`-shaped draft and then
            # reassembled the result by hand, which meant the two could drift apart -- and did, as a mutation
            # that silently un-counted the elision proved by surviving every test.
            pieces = head[:head_count]
            elided = len(block) - head_count - tail_count
            if elided > 0:
                pieces = pieces + [f"...{elided} frame line(s) elided; the end of the stack follows..."]
            if tail_count:
                pieces = pieces + tail[len(tail) - tail_count:]
            return header + separator.join(pieces) + tally + notice

        head_count, tail_count = len(head), len(tail)
        trimmed = False
        while len(_escape_data(compose(head_count, tail_count, over_notice))) > budget:
            # Shrink the middle, not the identity of the event: head frames beyond the marker pair go first, then
            # the front of the tail, and only then the rest of the head.  Each step decreases a counter, so this
            # terminates.
            trimmed = True
            if head_count > 2:
                head_count -= 1
            elif tail_count > 1:
                tail_count -= 1
            elif head_count > 0:
                head_count -= 1
            else:
                break
        notice = over_notice if trimmed else (
            f"{separator}…(the dump continues for {len(block) - limit_lines} more lines)"
            if len(block) > limit_lines else "")
        return compose(head_count, tail_count, notice)
    pieces = [redact(line)[:line_width] for line in block[:limit_lines]]
    cut_notice = (f"{separator}…(the dump continues for {len(block) - len(pieces)} more lines)"
                  if len(block) > len(pieces) else "")
    ends_notice = (f"{separator}(the dump ends {len(block)} lines after the marker)"
                   if len(block) > len(pieces) else "")
    return header + separator.join(pieces) + tally + (cut_notice if bounded else ends_notice)


def describe_abort(result: dict, pytest_exit: int | None, pytest_log: Path | None,
                   tail_lines: int = 25) -> str:
    """Explain a nonzero pytest exit that the JUnit report does not account for.

    A step that fails while publishing nothing is indistinguishable from a step that failed for a reason its
    own tooling suppressed.  pytest writes its JUnit report at the *end* of a run, so a process that is
    interrupted, aborted by the shell, or refused at startup leaves no report -- or an empty one -- and the
    annotations then carry no test identity at all.  That silence used to be the last thing a reader saw.
    With the run's exit code and the captured log supplied, the reader instead gets the exit code, whether the
    report was absent, unparsable or merely empty of cases, and the redacted tail of what pytest printed.
    Failures that *are* in the report are left to the per-failure annotations; this says nothing they cover.
    """
    if pytest_exit is None or int(pytest_exit) == 0:
        return ""
    if not result.get("parse_error") and (result.get("failed") or result.get("errors")):
        return ""
    exit_code = int(pytest_exit)
    pieces = [f"pytest exited {exit_code} and its JUnit report names no failing test"]
    if result.get("parse_error"):
        pieces.append(redact(result["parse_error"]))
    else:
        pieces.append(f"the report holds {result.get('collected', 0)} case(s), "
                      f"{result.get('failed', 0)} failure(s) and {result.get('errors', 0)} error(s), which is "
                      "what an interrupted, aborted or refused run leaves behind")
    if pytest_log is not None:
        pieces.extend(_log_parts([pytest_log], tail_lines))
        if crash_excerpt(pytest_log):
            pieces.append("the captured log holds a fatal crash marker; the interpreter died inside a test, "
                          "and its frames are quoted in a separate annotation")
    pieces.append("the run is not a pass, and it is not a mystery: the exit code above is the verdict")
    return _bounded(" ;; ".join(pieces))



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
    parser.add_argument("--pytest-exit", type=int, default=None,
                        help="pytest's own exit code; used to explain a run that left no usable JUnit report")
    parser.add_argument("--pytest-log", type=Path, default=None,
                        help="captured pytest output, quoted as a bounded redacted tail when --pytest-exit "
                             "is nonzero and the JUnit report names no failing test")
    args = parser.parse_args(argv)

    if (args.pytest_exit is not None or args.pytest_log is not None) and args.annotate:
        emit_error("error: --pytest-exit/--pytest-log describe a test run and cannot accompany --annotate")
        return 2

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
    diagnosis = describe_abort(result, args.pytest_exit, args.pytest_log, args.tail_lines)
    if args.annotations:
        for annotation in render_annotations(result, args.limit):
            emit(annotation)
        if diagnosis:
            emit(f"::error title={_escape_property('Windows regression suite: no failing test to name')}::"
                 + _escape_data(diagnosis))
        crash = crash_excerpt(args.pytest_log) if (args.pytest_log is not None and args.pytest_exit
                                                    and int(args.pytest_exit) != 0) else ""
        if crash:
            emit(f"::error title={_escape_property('Windows regression suite: fatal crash dump')}::"
                 + _escape_data(crash))
    crash_note = (crash_excerpt(args.pytest_log, limit_lines=60, line_width=400, separator="\n",
                                bounded=False)
                  if (args.pytest_log is not None and args.pytest_exit and int(args.pytest_exit) != 0) else "")
    if args.summary_out is not None:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(render_summary(result, diagnosis, crash_note), encoding="utf-8")
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if result.get("parse_error"):
        emit(f"error: {result['parse_error']}")
        return 2
    return 0


def _frame_tally(lines: list[str]) -> str:
    """Summarise how often each stack frame appears, so a 15-line window can still say "recursion".

    The first production use of this excerpt showed why a window is not enough: the frames it kept were four
    alternating ``_redact_tree`` levels and a fault on a line that cannot fault by itself, while the 24 lines
    the annotation budget cut were the ones that would have said whether the stack was deep (our recursion) or
    merely long (memory damage presenting at whichever call came next).  Neither answer fits in 15 lines, but
    both fit in one counted sentence.
    """
    counts: dict[str, int] = {}
    total = 0
    for line in lines:
        frame = re.match(r'File "([^"]+)", line (\d+) in ([\w.<>]+)', line.strip())
        if not frame:
            continue
        total += 1
        # Split on both separators by hand: a Windows path must collapse to its file name on the
        # Linux side of this too, or the key repeats the whole runner directory and spends the budget.
        name = re.split(r"[\\/]", frame.group(1))[-1]
        key = f"{name}:{frame.group(2)} in {frame.group(3)}"
        counts[key] = counts.get(key, 0) + 1
    if not total:
        return "no parseable stack frames"
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    repeated = [f"'{name}' x{count}" for name, count in ordered if count > 1][:3]
    shape = f"{total} frame(s), {len(counts)} distinct"
    if repeated:
        return (f"{shape}; repeats: {'; '.join(repeated)}"
                + (" (recursion suspected: one frame recurs many times)" if ordered[0][1] >= 8 else ""))
    return f"{shape}, no frame repeated -- a straight-line stack, not recursion"


if __name__ == "__main__":
    raise SystemExit(main())
