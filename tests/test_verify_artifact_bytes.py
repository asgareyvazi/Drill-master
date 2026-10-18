"""Contract tests for packaging/verify_artifact_bytes.py, the byte verifier for one specific CI artifact.

Each test builds a synthetic artifact shaped exactly like the Windows release gate's upload
(``DrillMaster-release-<run>/...`` beside the test and transcript files) and computes the candidate's
expected values from it, so a failure is caused by the one property under test and nothing else.  The
adversarial cases keep the *outer* hash valid on purpose: a crafted archive whose digest is pinned
must still be refused for what is inside it.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import stat
import struct
import warnings
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "packaging" / "verify_artifact_bytes.py"
CANDIDATES = ROOT / "docs" / "audits" / "m42-14-evidence" / "artifact-candidates.json"
SHA = "a" * 40
RUN = 4242
INSTALLER = "DrillMaster-1.0.0-Setup.exe"
PORTABLE = "DrillMaster-1.0.0-windows-x64.zip"
REL = f"DrillMaster-release-{RUN}"


def _module():
    spec = importlib.util.spec_from_file_location("drillmaster_verify_artifact_bytes", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def fake_pe(signature_size: int = 0, filler: bytes = b"payload") -> bytes:
    """A minimal PE32+ header whose certificate-table entry (data directory 4) is under test control."""
    lfanew = 0x80
    head = bytearray(0x400)
    head[:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, lfanew)
    head[lfanew:lfanew + 4] = b"PE\0\0"
    optional = lfanew + 24
    struct.pack_into("<H", head, optional, 0x20B)
    struct.pack_into("<II", head, optional + 112 + 4 * 8, 0x300 if signature_size else 0, signature_size)
    return bytes(head) + filler * 50


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(tmp_path: Path, *, mutate=None, extra=(), omit=(), stored_corruption: bool = False,
          installer_signature: int = 0):
    """Write a synthetic artifact; return (archive path, candidate entry)."""
    installer = fake_pe(installer_signature, b"installer")
    exe = fake_pe(0, b"application")
    portable_buffer = io.BytesIO()
    with zipfile.ZipFile(portable_buffer, "w", zipfile.ZIP_DEFLATED) as portable:
        portable.writestr("DrillMaster-1.0.0/DrillMaster.exe", exe)
        portable.writestr("DrillMaster-1.0.0/_internal/base_library.zip", b"lib")
    portable_bytes = portable_buffer.getvalue()
    rows = sorted([{"filename": INSTALLER, "sha256": _sha(installer), "size_bytes": len(installer)},
                   {"filename": PORTABLE, "sha256": _sha(portable_bytes), "size_bytes": len(portable_bytes)}],
                  key=lambda row: row["filename"])
    docs = {
        "release-metadata.json": {
            "schema": "drillmaster-release-artifacts/v2", "git_sha": SHA, "version": "1.0.0",
            "platform": "windows-x64", "python": "3.12.10",
            "build_tools": {"pip": "24", "pyinstaller": "6.11.1", "innosetup_package_version": "6.7.1",
                            "innosetup_compiler_file_version": "6.7.1.0",
                            "innosetup_version_source": "installed-package-metadata",
                            "innosetup_identity_verified": True},
            "reproducible_build": {"status": "NOT_CLAIMED", "reason": "one build"},
            "artifact_scope": "outer release artifacts", "artifacts": rows},
        "acceptance-report.json": {"schema": "drillmaster-windows-acceptance/v2", "identity": {
            "source_sha": SHA, "installer_filename": INSTALLER, "installer_size_bytes": len(installer),
            "installer_sha256": _sha(installer), "portable_zip_filename": PORTABLE,
            "portable_zip_size_bytes": len(portable_bytes), "portable_zip_sha256": _sha(portable_bytes),
            "installed_lifecycle_status": "PASS", "signing_status": "UNSIGNED"}},
        "signing-status.json": {"status": "UNSIGNED", "files": [
            {"filename": INSTALLER, "status": "UNSIGNED", "sha256": _sha(installer)},
            {"filename": "DrillMaster.exe", "status": "UNSIGNED", "sha256": _sha(exe),
             "container_archive_sha256": _sha(portable_bytes)}]},
        "installer-lifecycle.json": {"status": "PASS", "installer_hash_verified": True},
    }
    sums = "".join(f"{row['sha256']}  {row['filename']}\n" for row in rows)
    members = {f"{REL}/{INSTALLER}": installer, f"{REL}/{PORTABLE}": portable_bytes,
               f"{REL}/SHA256SUMS.txt": sums.encode("ascii"),
               f"{REL}/DrillMaster-1.0.0/DrillMaster.exe": exe,
               f"DrillMaster-M42-tests-{RUN}/windows-regressions.xml": b"<testsuites/>",
               f"DrillMaster-build-transcript-{RUN}.txt": b"transcript"}
    for name, payload in docs.items():
        members[f"{REL}/{name}"] = json.dumps(payload).encode("utf-8")
    if mutate:
        mutate(members, docs)
    archive = tmp_path / "artifact.zip"
    method = zipfile.ZIP_STORED if stored_corruption else zipfile.ZIP_DEFLATED
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # duplicate-name cases are deliberate
        with zipfile.ZipFile(archive, "w", method) as bundle:
            for name, payload in members.items():
                if name not in omit:
                    bundle.writestr(name, payload)
            for name, payload, attr in extra:
                info = zipfile.ZipInfo(name)
                if attr is not None:
                    info.external_attr = attr
                bundle.writestr(info, payload)
    if stored_corruption:
        raw = bytearray(archive.read_bytes())
        marker = raw.find(b"transcript")
        raw[marker] ^= 0xFF  # flips one stored byte; the archive's own CRC must now refuse it
        archive.write_bytes(bytes(raw))
    data = archive.read_bytes()
    candidate = {"artifact_id": 99, "artifact_name": f"drillmaster-windows-{SHA}", "run_id": RUN,
                 "source_sha": SHA, "archive_size_bytes": len(data), "archive_sha256": _sha(data),
                 "installer": {"filename": INSTALLER, "size_bytes": len(installer), "sha256": _sha(installer)},
                 "portable_zip": {"filename": PORTABLE, "size_bytes": len(portable_bytes),
                                  "sha256": _sha(portable_bytes)},
                 "signing_status": "UNSIGNED"}
    return archive, candidate


def _status(report, name):
    matches = [item for item in report["checks"] if item["name"] == name]
    assert matches, f"check {name!r} was not run: {[item['name'] for item in report['checks']]}"
    return matches[0]["status"]


ALL_CHECKS = ["archive_size", "archive_sha256", "zip_crc", "member_paths", "member_layout", "required_members",
              "installer_bytes", "installer_pe_signature", "portable_zip_bytes", "portable_exe_pe_signature",
              "sha256sums_binding", "release_metadata_binding", "acceptance_report_binding",
              "signing_record_binding", "lifecycle_record"]


def test_the_valid_candidate_passes_every_check_and_executes_nothing(tmp_path):
    archive, candidate = build(tmp_path)
    report = _module().verify(archive, candidate)
    assert report["status"] == "PASS", report["checks"]
    assert [item["name"] for item in report["checks"]] == ALL_CHECKS
    assert report["executed_anything"] is False
    assert report["observed"]["installer_certificate_table"] == [0, 0]


def test_streaming_works_with_a_tiny_chunk(tmp_path, monkeypatch):
    """The archive is read in chunks; a chunk far smaller than any member must give the same answer."""
    module = _module()
    monkeypatch.setattr(module, "CHUNK", 7)
    archive, candidate = build(tmp_path)
    assert module.verify(archive, candidate)["status"] == "PASS"


def test_the_live_artifact_api_must_agree_with_the_candidate(tmp_path):
    module = _module()
    archive, candidate = build(tmp_path)
    live = {"id": 99, "name": candidate["artifact_name"], "size_in_bytes": candidate["archive_size_bytes"],
            "digest": f"sha256:{candidate['archive_sha256']}", "expired": False,
            "workflow_run": {"id": RUN, "head_sha": SHA}}
    assert _status(module.verify(archive, candidate, live), "live_api_binding") == "PASS"
    for key, value in (("digest", "sha256:" + "0" * 64), ("expired", True), ("workflow_run", {"id": RUN, "head_sha": "b" * 40})):
        report = module.verify(archive, candidate, {**live, key: value})
        assert report["status"] == "FAIL" and _status(report, "live_api_binding") == "FAIL", key


@pytest.mark.parametrize("field, delta", [("archive_size_bytes", 1), ("archive_sha256", None)])
def test_a_wrong_archive_identity_stops_before_anything_inside_is_trusted(tmp_path, field, delta):
    archive, candidate = build(tmp_path)
    candidate[field] = candidate[field] + delta if delta else "0" * 64
    report = _module().verify(archive, candidate)
    assert report["status"] == "FAIL"
    assert {item["name"] for item in report["checks"]} == {"archive_size", "archive_sha256"}, (
        "no inner check may run on an archive of the wrong identity")


def test_a_missing_archive_is_a_failure(tmp_path):
    _, candidate = build(tmp_path)
    report = _module().verify(tmp_path / "absent.zip", candidate)
    assert report["status"] == "FAIL" and _status(report, "archive_present") == "FAIL"


def test_a_corrupted_member_fails_the_crc_even_when_the_outer_hash_is_pinned_to_it(tmp_path):
    archive, candidate = build(tmp_path, stored_corruption=True)
    report = _module().verify(archive, candidate)
    assert _status(report, "archive_sha256") == "PASS" and _status(report, "zip_crc") == "FAIL"
    assert report["status"] == "FAIL"


@pytest.mark.parametrize("name, reason", [
    ("../evil.txt", "traversal"), (f"{REL}/../../evil.txt", "traversal"), ("/abs.txt", "absolute"),
    ("C:/evil.txt", "drive"), (f"{REL}/a\\..\\b.txt", "backslash"), (f"{REL}/ctl\x01.txt", "control")])
def test_unsafe_member_paths_are_refused(tmp_path, name, reason):
    archive, candidate = build(tmp_path, extra=[(name, b"x", None)])
    report = _module().verify(archive, candidate)
    assert report["status"] == "FAIL" and _status(report, "member_paths") == "FAIL"
    assert reason in next(item["detail"] for item in report["checks"] if item["name"] == "member_paths")
    assert "installer_bytes" not in {item["name"] for item in report["checks"]}, "nothing is read past an unsafe listing"


def test_case_fold_duplicates_symlinks_and_foreign_members_are_refused(tmp_path):
    module = _module()
    for extra, check in (
            ([(f"{REL}/sha256sums.TXT", b"x", None)], "member_paths"),
            ([(f"{REL}/link", b"target", (stat.S_IFLNK | 0o777) << 16)], "member_paths"),
            ([(f"{REL}/fifo", b"", (stat.S_IFIFO | 0o644) << 16)], "member_paths"),
            ([("unexpected/readme.txt", b"x", None)], "member_layout")):
        archive, candidate = build(tmp_path, extra=extra)
        report = module.verify(archive, candidate)
        assert report["status"] == "FAIL" and _status(report, check) == "FAIL", extra[0][0]


def test_a_missing_or_ambiguous_mandatory_member_is_refused(tmp_path):
    module = _module()
    archive, candidate = build(tmp_path, omit={f"{REL}/{INSTALLER}"})
    assert _status(module.verify(archive, candidate), "required_members") == "FAIL"
    archive, candidate = build(tmp_path, extra=[(f"{REL}/DrillMaster-1.0.0/{INSTALLER}", b"decoy", None)])
    report = module.verify(archive, candidate)
    assert report["status"] == "FAIL" and _status(report, "required_members") == "FAIL"
    assert "found" in next(item["detail"] for item in report["checks"] if item["name"] == "required_members")


@pytest.mark.parametrize("part, field", [("installer", "sha256"), ("installer", "size_bytes"),
                                         ("portable_zip", "sha256"), ("portable_zip", "size_bytes")])
def test_inner_size_and_hash_must_match_the_independently_sourced_values(tmp_path, part, field):
    archive, candidate = build(tmp_path)
    candidate[part][field] = "0" * 64 if field == "sha256" else candidate[part][field] + 1
    report = _module().verify(archive, candidate)
    name = "installer_bytes" if part == "installer" else "portable_zip_bytes"
    assert report["status"] == "FAIL" and _status(report, name) == "FAIL"


def test_the_checksum_list_must_name_exactly_the_bytes_observed(tmp_path):
    def wrong_sums(members, docs):
        members[f"{REL}/SHA256SUMS.txt"] = f"{'0' * 64}  {PORTABLE}\n{'1' * 64}  {INSTALLER}\n".encode()
    archive, candidate = build(tmp_path, mutate=wrong_sums)
    assert _status(_module().verify(archive, candidate), "sha256sums_binding") == "FAIL"

    def extra_line(members, docs):
        members[f"{REL}/SHA256SUMS.txt"] += f"{'2' * 64}  other.exe\n".encode()
    archive, candidate = build(tmp_path, mutate=extra_line)
    assert _status(_module().verify(archive, candidate), "sha256sums_binding") == "FAIL"


def test_malformed_metadata_and_a_wrong_source_sha_are_refused(tmp_path):
    module = _module()

    def malformed(members, docs):
        members[f"{REL}/release-metadata.json"] = b"{not json"
    archive, candidate = build(tmp_path, mutate=malformed)
    assert _status(module.verify(archive, candidate), "release_metadata_binding") == "FAIL"

    def foreign_sha(members, docs):
        docs["release-metadata.json"]["git_sha"] = "b" * 40
        members[f"{REL}/release-metadata.json"] = json.dumps(docs["release-metadata.json"]).encode()
    archive, candidate = build(tmp_path, mutate=foreign_sha)
    assert _status(module.verify(archive, candidate), "release_metadata_binding") == "FAIL"

    def foreign_acceptance(members, docs):
        docs["acceptance-report.json"]["identity"]["source_sha"] = "b" * 40
        members[f"{REL}/acceptance-report.json"] = json.dumps(docs["acceptance-report.json"]).encode()
    archive, candidate = build(tmp_path, mutate=foreign_acceptance)
    report = module.verify(archive, candidate)
    assert report["status"] == "FAIL" and _status(report, "acceptance_report_binding") == "FAIL"


def test_a_signature_state_contradicting_the_candidate_is_refused(tmp_path):
    module = _module()
    archive, candidate = build(tmp_path, installer_signature=0x1200)
    report = module.verify(archive, candidate)
    assert _status(report, "installer_pe_signature") == "FAIL", "an embedded signature contradicts UNSIGNED"

    def signed_record(members, docs):
        docs["signing-status.json"]["status"] = "SIGNED"
        members[f"{REL}/signing-status.json"] = json.dumps(docs["signing-status.json"]).encode()
    archive, candidate = build(tmp_path, mutate=signed_record)
    assert _status(module.verify(archive, candidate), "signing_record_binding") == "FAIL"


def test_a_failed_lifecycle_record_is_refused(tmp_path):
    def failed(members, docs):
        members[f"{REL}/installer-lifecycle.json"] = json.dumps({"status": "FAIL"}).encode()
    archive, candidate = build(tmp_path, mutate=failed)
    assert _status(_module().verify(archive, candidate), "lifecycle_record") == "FAIL"


def test_non_pe_bytes_have_no_certificate_table():
    module = _module()
    assert module.pe_certificate_table(b"not a pe" * 100) is None
    assert module.pe_certificate_table(fake_pe(0)) == (0, 0)
    assert module.pe_certificate_table(fake_pe(0x40))[1] == 0x40


def test_the_cli_exit_codes(tmp_path, capsys):
    module = _module()
    archive, candidate = build(tmp_path)
    candidates = tmp_path / "candidates.json"
    candidates.write_text(json.dumps({"candidates": [candidate]}), encoding="utf-8")
    out = tmp_path / "report.json"
    assert module.main(["--archive", str(archive), "--candidates", str(candidates), "--artifact-id", "99",
                        "--json-out", str(out)]) == 0
    assert capsys.readouterr().out.startswith(f"PASS artifact=99 sha={SHA}")
    assert json.loads(out.read_text())["status"] == "PASS"
    assert module.main(["--archive", str(archive), "--candidates", str(candidates), "--artifact-id", "7"]) == 2
    candidate["archive_sha256"] = "0" * 64
    candidates.write_text(json.dumps({"candidates": [candidate]}), encoding="utf-8")
    assert module.main(["--archive", str(archive), "--candidates", str(candidates), "--artifact-id", "99"]) == 1


def test_the_verifier_cannot_execute_or_modify_anything():
    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in ("subprocess", "os.system", "startfile", "Popen", "os.exec", "extractall(", "unlink(",
                      "chmod(", ".write_bytes(", "urllib", "requests"):
        assert forbidden not in source, forbidden


def test_the_committed_candidates_are_complete_and_bound_to_their_own_run():
    payload = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    assert payload["schema"] == "drillmaster-artifact-byte-candidates/v1"
    assert "independently sourced" in payload["scope_rule"]
    ids = [entry["artifact_id"] for entry in payload["candidates"]]
    assert len(ids) == len(set(ids)) == 2
    for entry in payload["candidates"]:
        assert entry["artifact_name"] == f"drillmaster-windows-{entry['source_sha']}"
        assert len(entry["source_sha"]) == 40 and int(entry["source_sha"], 16) >= 0
        for digest in (entry["archive_sha256"], entry["installer"]["sha256"], entry["portable_zip"]["sha256"]):
            assert len(digest) == 64 and int(digest, 16) >= 0
        assert entry["signing_status"] == "UNSIGNED", "nothing here may promote a signing state"
        assert entry["run_attempt"] == 1 and entry["source_gate_run_id"] != entry["run_id"]
