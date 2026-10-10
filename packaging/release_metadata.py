"""Create a traceable, machine-readable Windows release manifest and checksums.

The manifest is an *engineering* record.  It states which toolchain the build
environment could actually verify, never what a caller hoped it was: an
installer entry without a verified Inno Setup package identity is rejected here
rather than published with a placeholder such as ``0.0.0.0`` or ``NOT_BUILT``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "drillmaster-release-artifacts/v2"
SHA256_CHUNK_SIZE = 1024 * 1024
# Inno Setup releases are three (or four) dotted numeric components; looser
# shapes such as "6.7" or "6.7.x" cannot be compared against a pin.
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)?$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
NOT_BUILT = "NOT_BUILT"
# Values a build environment can produce that carry no identity information.
UNVERIFIED_IDENTITIES = frozenset({
    "", "0", "0.0", "0.0.0", "0.0.0.0", "unknown", "unspecified", "unset",
    "none", "null", "n/a", "na", "tbd", "placeholder",
})
ALLOWED_IDENTITY_SOURCES = frozenset({
    # Read back from the package specification the build environment installed.
    "installed-package-metadata",
    # Queried from the package manager's local database.
    "package-manager-query",
    # Supplied by the operator; recorded as attested, never as verified.
    "operator-attested",
    NOT_BUILT,
})
VERIFIED_IDENTITY_SOURCES = ALLOWED_IDENTITY_SOURCES - {"operator-attested", NOT_BUILT}
# --- Signing evidence contract -----------------------------------------------------------
# Four vocabularies are deliberately distinct, because conflating them is how a report
# starts meaning something its evidence does not say:
#   * raw Authenticode states, spelled exactly as Windows' SignatureStatus enum spells them;
#   * normalized per-file states, which is what published evidence records per file;
#   * the aggregate state of one signing run over the examined executables;
#   * report-level states that describe the *absence* of an evidence record, which are not
#     signature findings at all.
SIGNING_SCHEMA = "drillmaster-signing-status/v2"
AUTHENTICODE_RAW_STATUSES = frozenset({"Unknown", "NotSigned", "HashMismatch", "NotTrusted",
                                       "Valid", "UnknownError"})
# Windows' spelling -> the normalized per-file state.  ``UnknownError`` is an unknown, not a
# signature problem; an unrecognised spelling stays unknown too.
AUTHENTICODE_TO_FILE_STATUS = {
    # A verified signature.  ``Ok`` is the spelling other Windows verification tools use for the
    # same verdict, and the two must not disagree about whether a build is signed.
    "valid": "PASS",
    "ok": "PASS",
    # Deliberately unsigned, which is a configuration fact and not a trust failure.
    "notsigned": "UNSIGNED",
    # A signature exists and is broken or untrusted: a distribution-trust finding.
    "hashmismatch": "FAIL",
    "nottrusted": "FAIL",
    "nottrustedfordata": "FAIL",
    "notgenuinelysigned": "FAIL",
    # The query could not reach a verdict.  Never promoted to FAIL and never demoted to UNSIGNED.
    "unknown": "UNKNOWN",
    "unknownerror": "UNKNOWN",
}
SIGNING_NOT_APPLICABLE = "NOT_APPLICABLE"
SIGNING_FILE_VOCABULARY = frozenset({"PASS", "UNSIGNED", "FAIL", "UNKNOWN", SIGNING_NOT_APPLICABLE})
SIGNING_STATUS_VOCABULARY = frozenset({"PASS", "UNSIGNED", "FAIL", "UNKNOWN", "NOT_RUN"})
SIGNING_ABSENCE_VOCABULARY = frozenset({"NOT_VERIFIED"})
SIGNING_FILE_REQUIRED_FIELDS = ("filename", "status", "size_bytes", "sha256",
                               "signature_bearing", "status_message")
SIGNING_FILE_FIELDS = frozenset(SIGNING_FILE_REQUIRED_FIELDS) | {
    "provenance", "raw_status", "raw_status_recognized", "signer", "manifest_digest_match",
    "container_archive", "container_archive_sha256", "container_member",
}
SIGNING_REQUIRED_FIELDS = ("schema", "method", "status", "policy", "files", "examined_count",
                           "archive_count", "signing_configured_in_build", "credentials_available",
                           "release_metadata_sha256", "source_sha")
SIGNING_OPTIONAL_FIELDS = frozenset({"prerequisite", "credential_environment_variables",
                                    "harness", "generated_at_utc", "reason"})
DIAGNOSTIC_FIELD_LIMIT = 600


def normalize_authenticode_status(raw: object) -> tuple[str, bool]:
    """Map a raw SignatureStatus spelling onto the per-file vocabulary.

    Returns ``(status, rule_applied)``.  An absent or unrecognised spelling is ``UNKNOWN``
    with ``rule_applied=False`` and is deliberately *not* a ``FAIL``: "Windows answered with
    something we have no rule for" and "Windows reported a signature problem" are different
    findings, and a capitalization difference must never be what separates them.
    """
    text = "" if raw is None else str(raw).strip()
    # Case-folded lookup: capitalization is how two implementations used to end up with different
    # answers for the same Windows reply, and an unknown answer must not become a FAIL by spelling.
    mapped = AUTHENTICODE_TO_FILE_STATUS.get(text.lower())
    if mapped is None:
        return "UNKNOWN", False
    return mapped, True


def aggregate_signing_status(files: list[dict]) -> str:
    """Fold normalized per-file states into one aggregate, never into a guess.

    ``NOT_APPLICABLE`` rows (container archives) are excluded because "a ZIP is unsigned" is
    not a statement about trust.  Nothing examined, or anything uninterpretable, is UNKNOWN;
    a mix that includes a real signature problem is FAIL.
    """
    examined = [item for item in files if item.get("status") != SIGNING_NOT_APPLICABLE]
    if not examined:
        return "UNKNOWN"
    statuses = {str(item.get("status")) for item in examined}
    if "UNKNOWN" in statuses:
        return "UNKNOWN"
    if statuses == {"UNSIGNED"}:
        return "UNSIGNED"
    if statuses == {"PASS"}:
        return "PASS"
    return "FAIL"


def validate_signing_document(payload: object) -> dict:
    """Enforce the signing-evidence contract, whoever wrote the document.

    The generator calls this before publishing and the acceptance report calls it before
    using any field, so an aggregate that the per-file findings do not support, a status
    outside the vocabulary, a missing reason, a duplicated file, a container treated as an
    executable, a malformed digest or an unbounded diagnostic is refused here once rather
    than reinterpreted differently in two places.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"signing evidence must be a JSON object, got {type(payload).__name__}")
    schema = payload.get("schema")
    if schema != SIGNING_SCHEMA:
        raise ValueError(f"signing evidence must use schema {SIGNING_SCHEMA}; {schema!r} is not "
                         "reinterpreted by a later schema")
    status = payload.get("status")
    status_text = status if isinstance(status, str) else ""
    if status_text not in SIGNING_STATUS_VOCABULARY:
        raise ValueError(f"signing aggregate status is outside the vocabulary: {status!r}")
    # A run that never happened has nothing to bind: no bytes were examined, so there is no
    # manifest digest and no per-file finding.  It must still say why in one bounded reason.
    if status_text == "NOT_RUN":
        absent = [field for field in SIGNING_REQUIRED_FIELDS
                  if field not in payload and field not in ("release_metadata_sha256", "source_sha")]
        if absent:
            raise ValueError(f"signing evidence is missing required field(s): {', '.join(absent)}")
        reason = str(payload.get("reason") or "").strip()
        if not reason:
            raise ValueError("a NOT_RUN signing record must carry a bounded reason")
        if len(reason) > DIAGNOSTIC_FIELD_LIMIT:
            raise ValueError("a NOT_RUN signing reason exceeded the bound")
        for field in ("files", "examined_count", "archive_count"):
            value = payload.get(field)
            if field == "files":
                if value != []:
                    raise ValueError("a NOT_RUN signing record cannot also carry per-file findings")
            elif value:
                raise ValueError(f"a NOT_RUN signing record must report a zero {field}")
        for field in ("signing_configured_in_build", "credentials_available"):
            if not isinstance(payload.get(field), bool):
                raise ValueError(f"signing evidence field {field} must be a boolean")
        return payload
    missing = [field for field in SIGNING_REQUIRED_FIELDS if field not in payload]
    if missing:
        raise ValueError(f"signing evidence is missing required field(s): {', '.join(missing)}")
    unexpected = sorted(set(payload) - set(SIGNING_REQUIRED_FIELDS) - SIGNING_OPTIONAL_FIELDS)
    if unexpected:
        raise ValueError(f"signing evidence carries field(s) outside {SIGNING_SCHEMA}: "
                         + ", ".join(unexpected))
    if not isinstance(payload.get("files"), list):
        raise ValueError("signing evidence 'files' must be a list of per-file records")
    for field in ("signing_configured_in_build", "credentials_available"):
        if not isinstance(payload[field], bool):
            raise ValueError(f"signing evidence field {field} must be a boolean")
    for field in ("examined_count", "archive_count"):
        value = payload[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"signing evidence field {field} must be a non-negative integer")
    if not DIGEST_PATTERN.match(str(payload["release_metadata_sha256"])):
        raise ValueError("signing evidence must record the SHA-256 of the manifest it was derived from")
    if not SHA_PATTERN.match(str(payload["source_sha"])):
        raise ValueError("signing evidence must record the full source SHA it was produced for")
    files = payload["files"]
    if not files:
        raise ValueError("a signing run must record at least one published file")
    seen: set[str] = set()
    examined = 0
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise ValueError(f"signing file record {index} must be a JSON object")
        extra = sorted(set(item) - SIGNING_FILE_FIELDS)
        if extra:
            raise ValueError(f"signing file record {index} carries unknown field(s): {', '.join(extra)}")
        absent = [field for field in SIGNING_FILE_REQUIRED_FIELDS if field not in item]
        if absent:
            raise ValueError(f"signing file record {index} is missing field(s): {', '.join(absent)}")
        name = str(item["filename"])
        if not name or Path(name).name != name:
            raise ValueError(f"signing file record {index} must name a bare file name, got {name!r}")
        key = name.lower()
        if key in seen:
            raise ValueError(f"duplicate signing file record for {name}")
        seen.add(key)
        file_status = item["status"]
        # isinstance first: a structured value must be refused as a contract violation, not crash
        # the caller with an unhashable-type TypeError on a frozenset membership test.
        if not isinstance(file_status, str) or file_status not in SIGNING_FILE_VOCABULARY:
            raise ValueError(f"signing status for {name} is outside the per-file vocabulary: {file_status!r}")
        if not DIGEST_PATTERN.match(str(item["sha256"])):
            raise ValueError(f"signing record for {name} has a malformed SHA-256 digest")
        size = item["size_bytes"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"signing record for {name} has a negative or non-integer size_bytes")
        bearing = item["signature_bearing"]
        if not isinstance(bearing, bool):
            raise ValueError(f"signing record for {name} must classify signature_bearing as a boolean")
        if bearing == (file_status == SIGNING_NOT_APPLICABLE):
            raise ValueError(f"signing record for {name}: signature_bearing={bearing} contradicts "
                             f"status {file_status!r}")
        message = str(item["status_message"] or "")
        if len(message) > DIAGNOSTIC_FIELD_LIMIT:
            raise ValueError(f"signing record for {name} carries an unbounded diagnostic")
        if file_status == "UNKNOWN" and not message.strip():
            raise ValueError(f"signing record for {name} reports UNKNOWN without a reason")
        container, member = item.get("container_archive"), item.get("container_member")
        container_digest = item.get("container_archive_sha256")
        if bool(container) != bool(member) or bool(container) != bool(container_digest):
            raise ValueError(f"signing record for {name} has incomplete container provenance")
        if container:
            if not DIGEST_PATTERN.match(str(container_digest)):
                raise ValueError(f"signing record for {name} has a malformed container digest")
            if not bearing:
                raise ValueError(f"signing record for {name} binds a container but is not signature-bearing")
            if Path(str(member)).name.lower() != name.lower():
                raise ValueError(f"signing record for {name} names archive member {member!r}, which is a "
                                 "different file")
        if file_status != SIGNING_NOT_APPLICABLE:
            examined += 1
    derived = aggregate_signing_status(files)
    if status != derived:
        raise ValueError(f"aggregate signing status {status!r} contradicts the per-file findings, "
                         f"which fold to {derived!r}")
    if payload["examined_count"] != examined:
        raise ValueError(f"examined_count {payload['examined_count']} disagrees with the {examined} "
                         "signature-bearing record(s) present")
    if payload["archive_count"] != len(files) - examined:
        raise ValueError("archive_count disagrees with the number of NOT_APPLICABLE records")
    return payload


def sha256_file(path: Path, *, chunk_size: int = SHA256_CHUNK_SIZE) -> str:
    """Hash a file by streaming fixed-size blocks (never whole-file reads)."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


# Historical internal name kept so existing callers/tests keep resolving.
_sha256 = sha256_file


def validate_tool_version(value: object, *, field: str, artifact_present: bool) -> str:
    """Return a usable tool version, or raise when the value proves nothing.

    ``artifact_present`` ties strictness to evidence: a manifest that publishes an
    artifact built by a tool must name a verified version of that tool.  When the
    tool was never invoked (portable-only builds) the explicit ``NOT_BUILT``
    marker is honest and is preserved as-is.
    """
    text = "" if value is None else str(value).strip()
    if text.upper() == NOT_BUILT:
        if artifact_present:
            raise ValueError(
                f"{field} cannot be {NOT_BUILT} while the artifact it builds is in this manifest"
            )
        return NOT_BUILT
    lowered = text.lower()
    if lowered in UNVERIFIED_IDENTITIES:
        raise ValueError(f"{field}={text!r} is a placeholder, not a verified tool version")
    if not VERSION_PATTERN.match(text):
        raise ValueError(f"{field}={text!r} is not a dotted numeric version such as 6.7.1")
    if all(int(part) == 0 for part in text.split(".")):
        raise ValueError(f"{field}={text!r} is an all-zero version and identifies no release")
    return text


def validate_identity_source(value: object, *, artifact_present: bool) -> str:
    """Record how the version was obtained; refuse an unknown provenance label."""
    text = NOT_BUILT if value is None else str(value).strip()
    if text not in ALLOWED_IDENTITY_SOURCES:
        raise ValueError(
            "innosetup version source must be one of "
            + ", ".join(sorted(ALLOWED_IDENTITY_SOURCES))
            + f"; got {text!r}"
        )
    if artifact_present and text == NOT_BUILT:
        raise ValueError(f"{NOT_BUILT} identity source is invalid while an installer is published")
    return text


def _artifact(path: Path, root: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    try:
        name = resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("Release artifacts must be inside the release directory") from exc
    if not resolved.is_file():
        raise ValueError(f"Release artifact is not a file: {name}")
    return {"filename": name, "sha256": sha256_file(resolved), "size_bytes": resolved.stat().st_size}


REQUIRED_FIELDS = (
    "schema", "git_sha", "version", "platform", "python", "build_tools",
    "reproducible_build", "artifact_scope", "artifacts",
)
ARTIFACT_FIELDS = ("filename", "sha256", "size_bytes")
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def validate_document(payload: object) -> dict:
    """Enforce the published manifest contract, whatever produced the file.

    The release generator calls this before writing and every consumer calls it before
    reading, so a document carrying a stale schema, a foreign field, a duplicated artifact
    entry or a malformed digest is refused instead of being partially reinterpreted.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"release metadata must be a JSON object, got {type(payload).__name__}")
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"release metadata must use schema {SCHEMA}; no other schema is reinterpreted here")
    missing = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing:
        raise ValueError(f"release metadata is missing required field(s): {', '.join(missing)}")
    unexpected = sorted(set(payload) - set(REQUIRED_FIELDS))
    if unexpected:
        raise ValueError(f"release metadata carries field(s) outside {SCHEMA}: {', '.join(unexpected)}")
    tools = payload["build_tools"]
    if not isinstance(tools, dict):
        raise ValueError("release metadata build_tools must be a JSON object")
    required_tools = ("pip", "pyinstaller", "innosetup_package_version", "innosetup_compiler_file_version",
                      "innosetup_version_source", "innosetup_identity_verified")
    absent = [name for name in required_tools if name not in tools]
    if absent:
        raise ValueError(f"release metadata build_tools is missing field(s): {', '.join(absent)}")
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("release metadata artifacts must be a non-empty list")
    seen: set[str] = set()
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            raise ValueError(f"artifact entry {index} must be a JSON object")
        keys = set(item) - set(ARTIFACT_FIELDS)
        if keys:
            raise ValueError(f"artifact entry {index} carries unknown field(s): {', '.join(sorted(keys))}")
        absent_fields = [name for name in ARTIFACT_FIELDS if name not in item]
        if absent_fields:
            raise ValueError(f"artifact entry {index} is missing field(s): {', '.join(absent_fields)}")
        name = Path(str(item["filename"])).name.lower()
        if not name:
            raise ValueError(f"artifact entry {index} has an empty filename")
        if name in seen:
            raise ValueError(f"duplicate artifact entry for {name}; a manifest may record each file once")
        seen.add(name)
        if not DIGEST_PATTERN.match(str(item["sha256"])):
            raise ValueError(f"artifact {name} records a malformed SHA-256 digest")
        size = item["size_bytes"]
        # A zero-length artifact is a legitimate thing to record and to re-hash (the report
        # re-measures every size anyway); a negative, fractional or boolean one is not.
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError(f"artifact {name} records a negative or non-integer size_bytes")
    return payload


def write_manifest(
    release_root: Path,
    *,
    source_sha: str,
    version: str,
    python_version: str,
    pyinstaller_version: str,
    pip_version: str,
    innosetup_package_version: str | None = None,
    innosetup_file_version: str | None = None,
    innosetup_version_source: str | None = None,
    bundle_zip: Path,
    installer: Path | None,
) -> Path:
    """Write ``release-metadata.json`` plus ``SHA256SUMS.txt`` for the release root.

    A published installer requires both a well-formed Inno Setup package version and
    a verified source for that version; a bare version string is not enough, because
    the previous schema could not tell a read-back package identity from an assumption.
    """
    if len(source_sha) != 40 or any(char not in "0123456789abcdef" for char in source_sha):
        raise ValueError("source-sha must be a full lowercase Git commit SHA")
    root = release_root.resolve(strict=True)
    artifacts = [_artifact(bundle_zip, root)]
    if installer is not None:
        artifacts.append(_artifact(installer, root))
    names = [str(item["filename"]) for item in artifacts]
    if len(set(names)) != len(names):
        raise ValueError(f"release artifacts must be recorded once each; got {sorted(names)}")

    installer_present = installer is not None
    recorded_package_version = validate_tool_version(
        innosetup_package_version, field="innosetup_package_version", artifact_present=installer_present
    )
    source = validate_identity_source(innosetup_version_source, artifact_present=installer_present)
    file_version = "" if innosetup_file_version is None else str(innosetup_file_version).strip()
    if installer_present and not file_version:
        file_version = "UNAVAILABLE"

    manifest = {
        "schema": SCHEMA,
        "git_sha": source_sha,
        "version": version,
        "platform": "windows-x64",
        "python": python_version,
        "build_tools": {
            "pip": pip_version,
            "pyinstaller": pyinstaller_version,
            "innosetup_package_version": recorded_package_version,
            "innosetup_compiler_file_version": file_version if installer_present else NOT_BUILT,
            "innosetup_version_source": source,
            # True only when the build environment read the identity back from the
            # installed package; an operator-attested value is recorded but flagged.
            "innosetup_identity_verified": bool(
                installer_present and source in VERIFIED_IDENTITY_SOURCES
            ),
        },
        "reproducible_build": {
            "status": "NOT_CLAIMED",
            "reason": "one build was performed; reproducibility requires two independent builds compared by artifact hash",
        },
        "artifact_scope": "outer release artifacts; inner bundle files inside the portable ZIP are not individually hashed here",
        "artifacts": sorted(artifacts, key=lambda item: str(item["filename"])),
    }
    validate_document(manifest)
    metadata_path = root / "release-metadata.json"
    metadata_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksum_path = root / "SHA256SUMS.txt"
    checksum_path.write_text(
        "".join(f"{item['sha256']}  {item['filename']}\n" for item in manifest["artifacts"]),
        encoding="ascii",
    )
    return metadata_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--pyinstaller-version", required=True)
    parser.add_argument("--pip-version", required=True)
    parser.add_argument("--innosetup-package-version", default=NOT_BUILT,
                        help="version read back from the installed Inno Setup package")
    parser.add_argument("--innosetup-file-version", default="",
                        help="diagnostic: VersionInfo.FileVersion of the located ISCC.exe")
    parser.add_argument("--innosetup-version-source", default=NOT_BUILT,
                        help="how the package version was established: "
                             + ", ".join(sorted(ALLOWED_IDENTITY_SOURCES)))
    parser.add_argument("--bundle-zip", type=Path, required=True)
    parser.add_argument("--installer", type=Path)
    args = parser.parse_args(argv)
    metadata = write_manifest(
        args.release_root,
        source_sha=args.source_sha,
        version=args.version,
        python_version=args.python_version,
        pyinstaller_version=args.pyinstaller_version,
        pip_version=args.pip_version,
        innosetup_package_version=args.innosetup_package_version,
        innosetup_file_version=args.innosetup_file_version,
        innosetup_version_source=args.innosetup_version_source,
        bundle_zip=args.bundle_zip,
        installer=args.installer,
    )
    print(f"Release metadata: {metadata}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
