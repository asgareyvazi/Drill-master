"""Verify the transferred bytes of one specific Windows CI artifact, without running anything in it.

The Windows release gate publishes its evidence as a GitHub Actions artifact: a ZIP holding the
installer, the portable ZIP, the release metadata, the checksum list and the acceptance, lifecycle
and signing records.  This module answers one question about one such download: *are these the
bytes that were built and gated?*  It is pinned to an entry in a candidates file whose expected values
were read from sources that do not depend on the bytes being checked - GitHub's artifact API for the
archive and the build job's manifest notice for the files inside it - so a matching hash can never
be manufactured from metadata carried inside the same archive.

What it checks, all streamed so a ~320 MB archive is never held in memory:

* the archive's size and SHA-256 against the candidate and, when supplied, the live artifact API;
* the ZIP's own CRCs, every member path (absolute, drive-qualified, traversal, control characters,
  case-fold duplicates, symlinks and other special entries) and the top-level layout of that run;
* each mandatory member exactly once, at the path that run's upload produces;
* the installer and portable ZIP sizes and SHA-256s against the candidate, ``SHA256SUMS.txt``,
  ``release-metadata.json``, ``acceptance-report.json`` and ``signing-status.json``;
* the source SHA recorded in the metadata and the acceptance report;
* whether the installer and the portable bundle's ``DrillMaster.exe`` carry an Authenticode
  certificate table at all - a read of the PE header, not a trust decision.

Nothing in the archive is executed, written back or modified; members are read in place, and the one
nested ZIP is copied to a private temporary file that is deleted afterwards.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import struct
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

# The repository's convention for sibling modules: `packaging/` is not a package (and its name is taken by
# the PyPI `packaging` distribution), so the directory itself goes on the path.
_PACKAGING_DIR = Path(__file__).resolve().parent
if str(_PACKAGING_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGING_DIR))
from release_metadata import validate_document  # noqa: E402

REPORT_SCHEMA = "drillmaster-artifact-byte-verification/v1"
CHUNK = 1024 * 1024
PE_HEADER_BYTES = 64 * 1024
MAX_LISTED = 20
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SUMS_LINE = re.compile(r"^([0-9a-f]{64})  ([^\r\n/\\]+)$")
# Unix file-type bits carried in the high half of a ZIP entry's external attributes.  Entries written
# on Windows carry none (0); a regular file or directory is allowed, anything else is not.
ALLOWED_UNIX_TYPES = {0, stat.S_IFREG, stat.S_IFDIR}


def _hash_stream(stream, sink=None) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = stream.read(CHUNK)
        if not chunk:
            return size, digest.hexdigest()
        size += len(chunk)
        digest.update(chunk)
        if sink is not None:
            sink.write(chunk)


def hash_file(path: Path) -> tuple[int, str]:
    with path.open("rb") as handle:
        return _hash_stream(handle)


def unsafe_member_reason(name: str) -> str | None:
    """Why a member name could escape or confuse an extraction directory, or None when it cannot."""
    if not name:
        return "empty name"
    if any(ord(char) < 32 for char in name):
        return "control character in name"
    if "\\" in name:
        return "backslash separator"
    if name.startswith("/"):
        return "absolute path"
    if re.match(r"^[A-Za-z]:", name) or ":" in name:
        return "drive or stream qualifier"
    if ".." in PurePosixPath(name).parts:
        return "parent-directory traversal"
    return None


def pe_certificate_table(head: bytes) -> tuple[int, int] | None:
    """Return the (offset, size) of a PE image's certificate table, or None if ``head`` is not a PE.

    Data directory 4 is where an embedded Authenticode signature lives.  A size of zero means the
    file carries no signature at all; a non-zero size means one is present, which says nothing yet
    about whether it is trusted.
    """
    if len(head) < 0x40 or head[:2] != b"MZ":
        return None
    (lfanew,) = struct.unpack_from("<I", head, 0x3C)
    if lfanew + 24 + 2 > len(head) or head[lfanew:lfanew + 4] != b"PE\0\0":
        return None
    optional = lfanew + 24
    (magic,) = struct.unpack_from("<H", head, optional)
    directories = optional + {0x10B: 96, 0x20B: 112}.get(magic, -optional - 1)
    if directories < 0:
        return None
    entry = directories + 4 * 8
    if entry + 8 > len(head):
        return None
    return struct.unpack_from("<II", head, entry)


class _Checks:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, name: str, ok: bool, detail: str) -> bool:
        self.items.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail[:600]})
        return ok

    @property
    def passed(self) -> bool:
        return bool(self.items) and all(item["status"] == "PASS" for item in self.items)


def _listed(names: list[str]) -> str:
    shown = ", ".join(names[:MAX_LISTED])
    return shown + (f" (+{len(names) - MAX_LISTED} more)" if len(names) > MAX_LISTED else "")


def _read_json_member(bundle: zipfile.ZipFile, name: str) -> dict:
    payload = json.loads(bundle.read(name).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{name} is not a JSON object")
    return payload


def verify(archive: Path, candidate: dict, live_api: dict | None = None) -> dict:
    """Verify ``archive`` against one candidate entry; return a bounded, publishable report."""
    checks = _Checks()
    run_id = str(candidate["run_id"])
    source_sha = str(candidate["source_sha"])
    release_root = f"DrillMaster-release-{run_id}"
    expected_installer = candidate["installer"]
    expected_portable = candidate["portable_zip"]
    observed: dict = {}
    report = {"schema": REPORT_SCHEMA, "artifact_id": candidate["artifact_id"],
              "artifact_name": candidate["artifact_name"], "run_id": candidate["run_id"],
              "source_sha": source_sha, "executed_anything": False, "checks": checks.items,
              "observed": observed}

    def finish() -> dict:
        report["status"] = "PASS" if checks.passed else "FAIL"
        return report

    if live_api is not None:
        run = live_api.get("workflow_run") or {}
        mismatches = [label for label, live, expected in (
            ("id", live_api.get("id"), candidate["artifact_id"]),
            ("name", live_api.get("name"), candidate["artifact_name"]),
            ("size_in_bytes", live_api.get("size_in_bytes"), candidate["archive_size_bytes"]),
            ("digest", live_api.get("digest"), f"sha256:{candidate['archive_sha256']}"),
            ("workflow_run.id", run.get("id"), candidate["run_id"]),
            ("workflow_run.head_sha", run.get("head_sha"), source_sha),
            ("expired", live_api.get("expired"), False)) if live != expected]
        checks.add("live_api_binding", not mismatches,
                   "the artifact API agrees with the candidate on id, name, size, digest, run and SHA"
                   if not mismatches else f"the artifact API disagrees on: {', '.join(mismatches)}")

    if not archive.is_file():
        checks.add("archive_present", False, f"no file at {archive}")
        return finish()
    size, digest = hash_file(archive)
    observed.update({"archive_size_bytes": size, "archive_sha256": digest})
    size_ok = checks.add("archive_size", size == candidate["archive_size_bytes"],
                         f"{size} bytes; expected {candidate['archive_size_bytes']}")
    hash_ok = checks.add("archive_sha256", digest == candidate["archive_sha256"],
                         f"{digest}; expected {candidate['archive_sha256']}")
    if not (size_ok and hash_ok):
        # Nothing inside an archive of the wrong identity is evidence of anything.
        return finish()

    try:
        bundle = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError) as exc:
        checks.add("zip_structure", False, f"{type(exc).__name__}: {exc}")
        return finish()
    with bundle:
        infos = bundle.infolist()
        observed["member_count"] = len(infos)
        try:
            bad_crc = bundle.testzip()
        except (zipfile.BadZipFile, OSError, EOFError, NotImplementedError) as exc:
            bad_crc = f"{type(exc).__name__}: {exc}"
        checks.add("zip_crc", bad_crc is None,
                   f"CRC-32 verified for all {len(infos)} members" if bad_crc is None
                   else f"first member failing its CRC or read: {bad_crc}")

        unsafe, special, seen, duplicates, foreign = [], [], {}, [], []
        allowed_top = {release_root, f"DrillMaster-M42-tests-{run_id}",
                       f"DrillMaster-build-transcript-{run_id}.txt"}
        for info in infos:
            reason = unsafe_member_reason(info.filename)
            if reason:
                unsafe.append(f"{info.filename!r}: {reason}")
                continue
            unix_type = stat.S_IFMT(info.external_attr >> 16)
            if unix_type not in ALLOWED_UNIX_TYPES:
                special.append(f"{info.filename} (mode {oct(info.external_attr >> 16)})")
            key = info.filename.rstrip("/").casefold()
            if key in seen:
                duplicates.append(f"{seen[key]} / {info.filename}")
            else:
                seen[key] = info.filename
            if PurePosixPath(info.filename).parts[0] not in allowed_top:
                foreign.append(info.filename)
        checks.add("member_paths", not (unsafe or special or duplicates),
                   "no absolute, drive-qualified, traversing, duplicate or special member"
                   if not (unsafe or special or duplicates) else
                   f"unsafe: {_listed(unsafe)}; special: {_listed(special)}; case-fold duplicates: "
                   f"{_listed(duplicates)}")
        checks.add("member_layout", not foreign,
                   f"every member sits under the layout of run {run_id}" if not foreign
                   else f"members outside the run's layout: {_listed(foreign)}")
        if unsafe or special or duplicates or foreign:
            return finish()

        required = {key: f"{release_root}/{name}" for key, name in (
            ("installer", expected_installer["filename"]), ("portable_zip", expected_portable["filename"]),
            ("metadata", "release-metadata.json"), ("sums", "SHA256SUMS.txt"),
            ("acceptance", "acceptance-report.json"), ("signing", "signing-status.json"),
            ("lifecycle", "installer-lifecycle.json"))}
        by_leaf: dict[str, list[str]] = {}
        for info in infos:
            if not info.is_dir():
                by_leaf.setdefault(PurePosixPath(info.filename).name.casefold(), []).append(info.filename)
        problems = []
        for path in required.values():
            hits = by_leaf.get(PurePosixPath(path).name.casefold(), [])
            if hits != [path]:
                problems.append(f"{PurePosixPath(path).name}: found {hits or 'nothing'}, expected exactly {path}")
        if not checks.add("required_members", not problems,
                          "each mandatory member present exactly once at its expected path" if not problems
                          else "; ".join(problems)):
            return finish()

        with tempfile.TemporaryDirectory(prefix="drillmaster-verify-") as scratch:
            with bundle.open(required["installer"]) as member:
                head = member.read(PE_HEADER_BYTES)
                digest_obj = hashlib.sha256(head)
                size_total = len(head)
                while True:
                    chunk = member.read(CHUNK)
                    if not chunk:
                        break
                    size_total += len(chunk)
                    digest_obj.update(chunk)
            installer_size, installer_sha = size_total, digest_obj.hexdigest()
            observed["installer"] = {"size_bytes": installer_size, "sha256": installer_sha}
            checks.add("installer_bytes", (installer_size, installer_sha) ==
                       (expected_installer["size_bytes"], expected_installer["sha256"]),
                       f"{installer_size} bytes, {installer_sha}; expected {expected_installer['size_bytes']} "
                       f"bytes, {expected_installer['sha256']}")
            table = pe_certificate_table(head)
            observed["installer_certificate_table"] = list(table) if table else None
            checks.add("installer_pe_signature",
                       table is not None and (table[1] == 0) == (candidate["signing_status"] == "UNSIGNED"),
                       "not a readable PE image" if table is None else
                       f"certificate table size {table[1]}: "
                       + ("no embedded Authenticode signature" if table[1] == 0 else "a signature blob is present")
                       + f"; candidate records {candidate['signing_status']}")

            nested = Path(scratch) / "portable.zip"
            with bundle.open(required["portable_zip"]) as member, nested.open("wb") as sink:
                portable_size, portable_sha = _hash_stream(member, sink)
            observed["portable_zip"] = {"size_bytes": portable_size, "sha256": portable_sha}
            checks.add("portable_zip_bytes", (portable_size, portable_sha) ==
                       (expected_portable["size_bytes"], expected_portable["sha256"]),
                       f"{portable_size} bytes, {portable_sha}; expected {expected_portable['size_bytes']} "
                       f"bytes, {expected_portable['sha256']}")
            exe_record: dict = {}
            try:
                with zipfile.ZipFile(nested) as portable:
                    exes = [info for info in portable.infolist()
                            if PurePosixPath(info.filename.replace("\\", "/")).name.casefold() == "drillmaster.exe"]
                    if len(exes) != 1:
                        checks.add("portable_exe_pe_signature", False,
                                   f"{len(exes)} DrillMaster.exe members in the portable ZIP; expected exactly 1")
                    else:
                        with portable.open(exes[0]) as member:
                            exe_head = member.read(PE_HEADER_BYTES)
                            exe_digest = hashlib.sha256(exe_head)
                            exe_size = len(exe_head)
                            for chunk in iter(lambda: member.read(CHUNK), b""):
                                exe_size += len(chunk)
                                exe_digest.update(chunk)
                        exe_record = {"member": exes[0].filename, "size_bytes": exe_size,
                                      "sha256": exe_digest.hexdigest()}
                        exe_table = pe_certificate_table(exe_head)
                        exe_record["certificate_table"] = list(exe_table) if exe_table else None
                        checks.add("portable_exe_pe_signature",
                                   exe_table is not None and
                                   (exe_table[1] == 0) == (candidate["signing_status"] == "UNSIGNED"),
                                   "not a readable PE image" if exe_table is None else
                                   f"{exes[0].filename}: certificate table size {exe_table[1]}; candidate records "
                                   f"{candidate['signing_status']}")
            except (zipfile.BadZipFile, OSError) as exc:
                checks.add("portable_exe_pe_signature", False, f"portable ZIP unreadable: {type(exc).__name__}: {exc}")
            observed["portable_exe"] = exe_record

        actual = {expected_installer["filename"]: (installer_size, installer_sha),
                  expected_portable["filename"]: (portable_size, portable_sha)}

        try:
            lines = [line for line in bundle.read(required["sums"]).decode("ascii").splitlines() if line.strip()]
            parsed = [SUMS_LINE.match(line) for line in lines]
            malformed = [line for line, match in zip(lines, parsed) if not match]
            sums = {match.group(2): match.group(1) for match in parsed if match}
            ok = not malformed and len(sums) == len(parsed) == len(actual) and all(
                sums.get(name) == values[1] for name, values in actual.items())
            checks.add("sha256sums_binding", ok,
                       "SHA256SUMS.txt lists exactly the installer and portable ZIP with the hashes observed"
                       if ok else f"SHA256SUMS.txt disagrees: entries={sums}; malformed={malformed[:3]}")
        except (UnicodeDecodeError, KeyError) as exc:
            checks.add("sha256sums_binding", False, f"SHA256SUMS.txt unreadable: {exc}")

        try:
            metadata = validate_document(_read_json_member(bundle, required["metadata"]))
            rows = {str(row["filename"]): (row["size_bytes"], row["sha256"]) for row in metadata["artifacts"]}
            ok = metadata["git_sha"] == source_sha and rows == actual
            checks.add("release_metadata_binding", ok,
                       f"git_sha {metadata['git_sha']}; artifacts match the bytes observed" if ok else
                       f"git_sha {metadata['git_sha']} (expected {source_sha}); recorded {rows}; observed {actual}")
        except (ValueError, KeyError, UnicodeDecodeError) as exc:
            checks.add("release_metadata_binding", False, f"release-metadata.json refused: {exc}")

        try:
            identity = _read_json_member(bundle, required["acceptance"])["identity"]
            expected_identity = {
                "source_sha": source_sha,
                "installer_filename": expected_installer["filename"], "installer_size_bytes": installer_size,
                "installer_sha256": installer_sha,
                "portable_zip_filename": expected_portable["filename"], "portable_zip_size_bytes": portable_size,
                "portable_zip_sha256": portable_sha,
                "installed_lifecycle_status": "PASS", "signing_status": candidate["signing_status"]}
            wrong = {key: identity.get(key) for key, value in expected_identity.items() if identity.get(key) != value}
            checks.add("acceptance_report_binding", not wrong,
                       "acceptance-report.json identity agrees on source SHA, both files, lifecycle and signing"
                       if not wrong else f"acceptance-report.json disagrees: {wrong}")
        except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
            checks.add("acceptance_report_binding", False, f"acceptance-report.json refused: {exc}")

        try:
            signing = _read_json_member(bundle, required["signing"])
            files = {str(item.get("filename")): item for item in signing.get("files", []) if isinstance(item, dict)}
            installer_row = files.get(expected_installer["filename"], {})
            exe_row = files.get("DrillMaster.exe", {})
            wrong = []
            if signing.get("status") != candidate["signing_status"]:
                wrong.append(f"status {signing.get('status')}")
            if installer_row.get("sha256") != installer_sha:
                wrong.append("installer sha256")
            if exe_record and exe_row.get("sha256") != exe_record.get("sha256"):
                wrong.append("DrillMaster.exe sha256")
            if exe_row.get("container_archive_sha256") not in (None, portable_sha):
                wrong.append("DrillMaster.exe container_archive_sha256")
            checks.add("signing_record_binding", not wrong,
                       f"signing-status.json reads {signing.get('status')} and names the bytes observed"
                       if not wrong else f"signing-status.json disagrees: {', '.join(wrong)}")
        except (ValueError, KeyError, UnicodeDecodeError) as exc:
            checks.add("signing_record_binding", False, f"signing-status.json refused: {exc}")

        try:
            lifecycle = _read_json_member(bundle, required["lifecycle"])
            ok = lifecycle.get("status") == "PASS" and lifecycle.get("installer_hash_verified") is True
            checks.add("lifecycle_record", ok,
                       "installer-lifecycle.json: status PASS with the installer hash verified before execution"
                       if ok else f"installer-lifecycle.json: status {lifecycle.get('status')}, "
                                  f"installer_hash_verified {lifecycle.get('installer_hash_verified')}")
        except (ValueError, UnicodeDecodeError) as exc:
            checks.add("lifecycle_record", False, f"installer-lifecycle.json refused: {exc}")
    return finish()


def summary_line(report: dict) -> str:
    failed = [item["name"] for item in report["checks"] if item["status"] != "PASS"]
    observed = report.get("observed", {})
    return (f"{report['status']} artifact={report['artifact_id']} sha={report['source_sha']} "
            f"archive={observed.get('archive_size_bytes')}B sha256={observed.get('archive_sha256')} "
            f"installer={observed.get('installer', {}).get('sha256')} "
            f"portableZip={observed.get('portable_zip', {}).get('sha256')} "
            f"checks={len(report['checks']) - len(failed)}/{len(report['checks'])}"
            + (f" failed={','.join(failed)}" if failed else ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--live-api-json", type=Path, help="GET /actions/artifacts/<id> response, read live")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)
    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))["candidates"]
    matching = [entry for entry in candidates if entry["artifact_id"] == args.artifact_id]
    if len(matching) != 1:
        print(f"ERROR: {len(matching)} candidate entries for artifact {args.artifact_id}", file=sys.stderr)
        return 2
    live = json.loads(args.live_api_json.read_text(encoding="utf-8")) if args.live_api_json else None
    report = verify(args.archive, matching[0], live)
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(summary_line(report))
    for item in report["checks"]:
        print(f"  {item['status']} {item['name']}: {item['detail']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
