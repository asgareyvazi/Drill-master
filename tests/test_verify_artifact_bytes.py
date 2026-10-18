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

import re

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
        # Shaped like packaging/windows_release_evidence.run_signing's output (schema v2); the
        # manifest digest is filled in below, once the metadata bytes exist.
        "signing-status.json": {
            "schema": "drillmaster-signing-status/v2", "method": "Windows Get-AuthenticodeSignature",
            "status": "UNSIGNED", "policy": "observe", "examined_count": 2, "archive_count": 1,
            "signing_configured_in_build": False, "credentials_available": False, "source_sha": SHA,
            "release_metadata_sha256": None,
            "files": [
                {"filename": INSTALLER, "status": "UNSIGNED", "raw_status": "NotSigned", "size_bytes": len(installer),
                 "sha256": _sha(installer), "signature_bearing": True, "status_message": "not signed"},
                {"filename": "DrillMaster.exe", "status": "UNSIGNED", "raw_status": "NotSigned", "size_bytes": len(exe),
                 "sha256": _sha(exe), "signature_bearing": True, "status_message": "not signed",
                 "container_archive": PORTABLE, "container_archive_sha256": _sha(portable_bytes),
                 "container_member": "DrillMaster-1.0.0/DrillMaster.exe"},
                {"filename": PORTABLE, "status": "NOT_APPLICABLE", "size_bytes": len(portable_bytes),
                 "sha256": _sha(portable_bytes), "signature_bearing": False, "status_message": "container archive"}]},
        "installer-lifecycle.json": {"status": "PASS", "installer_hash_verified": True, "installer_filename": INSTALLER,
                                     "installer_sha256": _sha(installer),
                                     "steps": [{"name": "verify_installer", "status": "PASS"},
                                               {"name": "silent_uninstall", "status": "PASS"}]},
    }
    sums = "".join(f"{row['sha256']}  {row['filename']}\n" for row in rows)
    members = {f"{REL}/{INSTALLER}": installer, f"{REL}/{PORTABLE}": portable_bytes,
               f"{REL}/SHA256SUMS.txt": sums.encode("ascii"),
               f"{REL}/DrillMaster-1.0.0/DrillMaster.exe": exe,
               f"DrillMaster-M42-tests-{RUN}/windows-regressions.xml": b"<testsuites/>",
               f"DrillMaster-build-transcript-{RUN}.txt": b"transcript"}
    metadata_bytes = json.dumps(docs["release-metadata.json"]).encode("utf-8")
    docs["signing-status.json"]["release_metadata_sha256"] = _sha(metadata_bytes)
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
                 "run_number": 7, "run_attempt": 1, "source_gate_run_id": RUN + 1, "source_sha": SHA, "archive_size_bytes": len(data), "archive_sha256": _sha(data),
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
    # M42.14 recorded two candidates and M42.15 appended a third; each mission appends, and the
    # preservation test below pins the earlier entries' values so an append cannot hide a rewrite.
    assert len(ids) == len(set(ids)) == 3
    assert ids[:2] == [12135787858, 12136310366], "earlier candidates keep their place in the order"
    assert payload["branch"] == "arena/72010272-drill-master"
    for entry in payload["candidates"]:
        assert entry["artifact_name"] == f"drillmaster-windows-{entry['source_sha']}"
        assert len(entry["source_sha"]) == 40 and int(entry["source_sha"], 16) >= 0
        for digest in (entry["archive_sha256"], entry["installer"]["sha256"], entry["portable_zip"]["sha256"]):
            assert len(digest) == 64 and int(digest, 16) >= 0
        assert entry["signing_status"] == "UNSIGNED", "nothing here may promote a signing state"
        assert entry["run_attempt"] == 1 and entry["source_gate_run_id"] != entry["run_id"]


# --- M42.15: run identity, the signing and lifecycle contracts, candidate schema, robustness ----------

BRANCH = "arena/72010272-drill-master"


def _runs(candidate):
    windows = {"id": candidate["run_id"], "run_number": candidate["run_number"], "run_attempt": candidate["run_attempt"],
               "head_sha": SHA, "head_branch": BRANCH, "path": ".github/workflows/windows-release-gate.yml",
               "status": "completed", "conclusion": "success"}
    source = {"id": candidate["source_gate_run_id"], "run_number": 3, "run_attempt": 1, "head_sha": SHA,
              "head_branch": BRANCH, "path": ".github/workflows/ci.yml", "status": "completed", "conclusion": "success"}
    return windows, source


def _rewrite(name, change):
    def mutate(members, docs):
        change(docs[name])
        members[f"{REL}/{name}"] = json.dumps(docs[name]).encode("utf-8")
    return mutate


def test_live_run_records_must_prove_a_completed_successful_run_on_the_same_sha(tmp_path):
    """An uploaded artifact is not evidence that its build passed; the live run records are."""
    module = _module()
    archive, candidate = build(tmp_path)
    windows, source = _runs(candidate)
    report = module.verify(archive, candidate, windows_run=windows, source_run=source, expected_branch=BRANCH)
    assert report["status"] == "PASS", report["checks"]
    assert _status(report, "windows_run_binding") == _status(report, "source_run_binding") == "PASS"
    for which, key, value in (
            ("windows", "conclusion", "failure"), ("windows", "status", "in_progress"),
            ("windows", "conclusion", None), ("windows", "head_sha", "b" * 40), ("windows", "run_attempt", 2),
            ("windows", "run_number", 8), ("windows", "head_branch", "drill-Master"),
            ("windows", "path", ".github/workflows/ci.yml"), ("windows", "id", candidate["run_id"] + 5),
            ("source", "conclusion", "cancelled"), ("source", "head_sha", "b" * 40),
            ("source", "id", candidate["run_id"]), ("source", "path", ".github/workflows/windows-release-gate.yml")):
        runs = {"windows": dict(windows), "source": dict(source)}
        runs[which][key] = value
        report = module.verify(archive, candidate, windows_run=runs["windows"], source_run=runs["source"],
                               expected_branch=BRANCH)
        assert report["status"] == "FAIL" and _status(report, f"{which}_run_binding") == "FAIL", (which, key)


@pytest.mark.parametrize("change, fragment", [
    (lambda doc: doc.update(source_sha="b" * 40), "produced for source"),
    (lambda doc: doc.update(release_metadata_sha256="0" * 64), "not bound to the release metadata"),
    (lambda doc: doc["files"][0].update(status="PASS", raw_status="Valid"), "contradicts the per-file findings"),
    (lambda doc: doc["files"].pop(0) and doc.update(examined_count=1), "does not record the shipped installer"),
    (lambda doc: doc["files"].append(dict(doc["files"][1])), "duplicate signing file record"),
    (lambda doc: doc["files"][1].update(sha256="1" * 64), "hashes a different executable"),
    (lambda doc: doc["files"][1].update(container_archive_sha256="2" * 64), "archive bytes this report did not verify"),
    (lambda doc: [doc["files"][1].pop(key) for key in ("container_archive", "container_archive_sha256",
                                                        "container_member")], "never examines the executable"),
    (lambda doc: doc["files"][0].update(signature_bearing="yes"), "signature_bearing as a boolean"),
    (lambda doc: doc.update(schema="drillmaster-signing-status/v1"), "must use schema"),
    (lambda doc: doc.update(unexpected_field=1), "outside drillmaster-signing-status/v2"),
])
def test_the_signing_record_is_held_to_the_builds_own_contract_and_bound_to_these_bytes(tmp_path, change, fragment):
    archive, candidate = build(tmp_path, mutate=_rewrite("signing-status.json", change))
    report = _module().verify(archive, candidate)
    assert report["status"] == "FAIL" and _status(report, "signing_record_binding") == "FAIL"
    detail = next(item["detail"] for item in report["checks"] if item["name"] == "signing_record_binding")
    assert fragment in detail, detail


def test_an_unsigned_build_cannot_be_promoted_to_signed_by_consistent_looking_records(tmp_path):
    """Records that all say PASS do not make an unsigned PE signed, and a PASS candidate is refused."""
    module = _module()

    def all_pass(doc):
        doc["status"] = "PASS"
        for row in doc["files"][:2]:
            row.update(status="PASS", raw_status="Valid")
    archive, candidate = build(tmp_path, mutate=_rewrite("signing-status.json", all_pass))
    report = module.verify(archive, candidate)
    assert _status(report, "signing_record_binding") == "FAIL", "the record contradicts the UNSIGNED expectation"
    assert _status(report, "installer_pe_signature") == "PASS", "the bytes themselves still carry no signature"
    candidate["signing_status"] = "PASS"
    report = module.verify(archive, candidate)
    assert report["status"] == "FAIL" and _status(report, "candidate_schema") == "FAIL"
    assert "does not evaluate Authenticode trust" in report["checks"][0]["detail"]


def test_a_signature_blob_is_reported_as_present_and_untrusted_not_as_signed(tmp_path):
    archive, candidate = build(tmp_path, installer_signature=0x900)
    report = _module().verify(archive, candidate)
    detail = next(item["detail"] for item in report["checks"] if item["name"] == "installer_pe_signature")
    assert "signature blob is present" in detail and "trust was not evaluated" in detail
    assert report["observed"]["installer_certificate_table"][1] == 0x900


def test_signing_configured_in_build_is_published_not_treated_as_a_contradiction(tmp_path):
    """The contract allows a build configured for signing to stay UNSIGNED when credentials are absent."""
    archive, candidate = build(tmp_path, mutate=_rewrite("signing-status.json",
                                                         lambda doc: doc.update(signing_configured_in_build=True)))
    report = _module().verify(archive, candidate)
    assert report["status"] == "PASS", report["checks"]
    assert report["observed"]["signing"]["signing_configured_in_build"] is True


@pytest.mark.parametrize("change, fragment", [
    (lambda doc: doc.update(installer_sha256="3" * 64), "different SHA-256 than the one shipped"),
    (lambda doc: doc["steps"].append({"name": "install_files_removed", "status": "FAIL"}), "non-passing steps"),
    (lambda doc: doc.update(steps=[]), "lists no steps"),
    (lambda doc: doc.update(installer_hash_verified=False), "without having verified the hash"),
    (lambda doc: doc.update(installer_filename="Other-Setup.exe"), "installer_filename"),
])
def test_the_lifecycle_record_must_have_executed_the_shipped_installer(tmp_path, change, fragment):
    archive, candidate = build(tmp_path, mutate=_rewrite("installer-lifecycle.json", change))
    report = _module().verify(archive, candidate)
    assert report["status"] == "FAIL" and _status(report, "lifecycle_record") == "FAIL"
    assert fragment in next(item["detail"] for item in report["checks"] if item["name"] == "lifecycle_record")


def test_a_duplicated_manifest_row_is_refused(tmp_path):
    archive, candidate = build(tmp_path, mutate=_rewrite(
        "release-metadata.json", lambda doc: doc["artifacts"].append(dict(doc["artifacts"][0]))))
    report = _module().verify(archive, candidate)
    assert _status(report, "release_metadata_binding") == "FAIL"
    assert "duplicate artifact entry" in next(i["detail"] for i in report["checks"] if i["name"] == "release_metadata_binding")


@pytest.mark.parametrize("change", [
    lambda c: c.update(run_attempt=0), lambda c: c.update(run_number="64"), lambda c: c.update(source_sha="abc"),
    lambda c: c.update(artifact_name="drillmaster-windows-other"), lambda c: c.update(archive_sha256="A" * 64),
    lambda c: c["installer"].update(filename="../Setup.exe"), lambda c: c["portable_zip"].update(size_bytes=True),
    lambda c: c.update(source_gate_run_id=c["run_id"]), lambda c: c.pop("source_gate_run_id"),
])
def test_an_invalid_candidate_is_refused_before_any_byte_is_read(tmp_path, change):
    archive, candidate = build(tmp_path)
    change(candidate)
    report = _module().verify(archive, candidate)
    assert report["status"] == "FAIL" and [item["name"] for item in report["checks"]] == ["candidate_schema"]
    assert _module().verify(archive, "not an object")["status"] == "FAIL"


def test_a_truncated_archive_whose_hash_is_pinned_fails_without_crashing(tmp_path):
    archive, candidate = build(tmp_path)
    data = archive.read_bytes()[: len(archive.read_bytes()) * 2 // 3]
    archive.write_bytes(data)
    candidate.update(archive_size_bytes=len(data), archive_sha256=_sha(data))
    report = _module().verify(archive, candidate)
    assert report["status"] == "FAIL"
    assert {item["name"] for item in report["checks"]} & {"zip_structure", "zip_crc"}


def test_verification_leaves_the_archive_untouched_and_no_temporary_files_behind(tmp_path, monkeypatch):
    import tempfile
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    archive, candidate = build(tmp_path)
    before = (archive.read_bytes(), archive.stat().st_mtime_ns)
    assert _module().verify(archive, candidate)["status"] == "PASS"
    assert (archive.read_bytes(), archive.stat().st_mtime_ns) == before
    assert list(scratch.iterdir()) == [], "temporary copies must not outlive the verification"


def test_the_cli_distinguishes_a_crash_and_a_bad_registry_from_a_failed_check(tmp_path, monkeypatch, capsys):
    module = _module()
    archive, candidate = build(tmp_path)
    registry = tmp_path / "candidates.json"
    registry.write_text(json.dumps({"branch": BRANCH, "candidates": [candidate]}), encoding="utf-8")
    windows, source = _runs(candidate)
    (tmp_path / "w.json").write_text(json.dumps(windows))
    (tmp_path / "s.json").write_text(json.dumps(source))
    args = ["--archive", str(archive), "--candidates", str(registry), "--artifact-id", "99"]
    assert module.main(args + ["--windows-run-json", str(tmp_path / "w.json"),
                               "--source-run-json", str(tmp_path / "s.json")]) == 0
    windows["head_branch"] = "elsewhere"
    (tmp_path / "w.json").write_text(json.dumps(windows))
    assert module.main(args + ["--windows-run-json", str(tmp_path / "w.json")]) == 1, "the registry branch is enforced"
    registry.write_text("{not json", encoding="utf-8")
    assert module.main(args) == 2
    registry.write_text(json.dumps({"candidates": [candidate]}), encoding="utf-8")
    monkeypatch.setattr(module, "verify", lambda *a, **k: 1 / 0)
    assert module.main(args) == 3
    assert "verifier crashed" in capsys.readouterr().err


def test_the_historical_candidates_are_preserved_exactly():
    """M42.14's two entries keep their verified values; later missions append, never rewrite."""
    entries = {entry["artifact_id"]: entry for entry in json.loads(CANDIDATES.read_text(encoding="utf-8"))["candidates"]}
    assert entries[12135787858]["archive_sha256"] == "891873eeb1a8a76f57b72b11ecdcf9b316ed2f2d9b40e9445efb7cb001abed6f"
    assert entries[12135787858]["installer"]["sha256"] == "ff14393e50c7a348eb7876a0ef3fffe47de849210b7a3b530e0d52bca6f9f9e1"
    assert entries[12135787858]["portable_zip"]["sha256"] == "0863b887604091998e3b580e84ca906e9aaa644a86aa54012c4f9353726ebd1f"
    assert entries[12136310366]["archive_sha256"] == "8391f63bd5927ba89a30b6eb45b62a6e480eaa01ac5351cce895882a5c4259b2"
    assert entries[12136310366]["installer"]["sha256"] == "1ddabf57bc2e26b3a3ff039466bd05706803292136d5c4bde786854e2933d73b"
    assert entries[12136310366]["portable_zip"]["sha256"] == "50303d397f3b396942312831a86052136d845112ad852be3ec1aa29a2a9dfb74"
    module = _module()
    for entry in entries.values():
        assert module.candidate_problems(entry) == [], entry["artifact_id"]


def test_a_container_row_for_some_other_executable_does_not_stand_in_for_drillmaster_exe(tmp_path):
    def other(doc):
        doc["files"][1].update(filename="Helper.exe", container_member="DrillMaster-1.0.0/Helper.exe")
    archive, candidate = build(tmp_path, mutate=_rewrite("signing-status.json", other))
    report = _module().verify(archive, candidate)
    assert report["status"] == "FAIL" and _status(report, "signing_record_binding") == "FAIL"
    assert "0 DrillMaster.exe rows" in next(i["detail"] for i in report["checks"] if i["name"] == "signing_record_binding")


def test_a_crc_failure_is_terminal_so_damaged_members_are_never_decompressed(tmp_path):
    """Corrupt the installer itself: reading it again would raise, so nothing may run after zip_crc."""
    archive, candidate = build(tmp_path, stored_corruption=True)
    raw = bytearray(archive.read_bytes())
    raw[raw.find(b"installer" * 3) + 4] ^= 0xFF
    archive.write_bytes(bytes(raw))
    candidate.update(archive_size_bytes=len(raw), archive_sha256=_sha(bytes(raw)))
    report = _module().verify(archive, candidate)
    assert report["status"] == "FAIL"
    assert [item["name"] for item in report["checks"]][-1] == "zip_crc"


def test_every_workflow_action_is_pinned_to_a_full_commit_sha_with_its_release_tag():
    """M42.15: floating majors drifted to node20 unnoticed; a pin cannot, and its tag comment says what it is."""
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            if "uses:" not in line:
                continue
            assert re.search(r"uses: [\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$", line), (workflow.name, line)


def test_the_verification_workflow_stays_read_only_and_on_an_explicit_image():
    text = (ROOT / ".github" / "workflows" / "artifact-byte-verification.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: read\n  actions: read\n" in text
    assert "write" not in text.split("jobs:", 1)[0], "no write permission at workflow level"
    assert "ubuntu-latest" not in text, "the production image is chosen explicitly, not left to a label migration"
    assert "persist-credentials: false" in text
    assert "secrets." not in text and "set -x" not in text
    assert "docs/audits/m42-14-evidence/artifact-candidates.json" in text and "--windows-run-json" in text
    assert re.search(r"\b\d{10,12}\b", text) is None, "artifact and run IDs come from the registry, not the workflow"
