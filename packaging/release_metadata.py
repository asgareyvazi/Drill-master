"""Create a traceable, machine-readable Windows release manifest and checksums."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact(path: Path, root: Path) -> dict[str, str]:
    resolved = path.resolve(strict=True)
    try:
        name = resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("Release artifacts must be inside the release directory") from exc
    if not resolved.is_file():
        raise ValueError(f"Release artifact is not a file: {name}")
    return {"filename": name, "sha256": _sha256(resolved)}


def write_manifest(
    release_root: Path,
    *,
    source_sha: str,
    version: str,
    python_version: str,
    pyinstaller_version: str,
    pip_version: str,
    innosetup_version: str,
    bundle_zip: Path,
    installer: Path | None,
) -> Path:
    if len(source_sha) != 40 or any(char not in "0123456789abcdef" for char in source_sha):
        raise ValueError("source-sha must be a full lowercase Git commit SHA")
    root = release_root.resolve(strict=True)
    artifacts = [_artifact(bundle_zip, root)]
    if installer is not None:
        artifacts.append(_artifact(installer, root))
    manifest = {
        "schema": "drillmaster-release-artifacts/v1",
        "git_sha": source_sha,
        "version": version,
        "platform": "windows-x64",
        "python": python_version,
        "build_tools": {
            "pip": pip_version,
            "pyinstaller": pyinstaller_version,
            "inno_setup": innosetup_version,
        },
        "artifacts": sorted(artifacts, key=lambda item: item["filename"]),
    }
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
    parser.add_argument("--innosetup-version", default="NOT_BUILT")
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
        innosetup_version=args.innosetup_version,
        bundle_zip=args.bundle_zip,
        installer=args.installer,
    )
    print(f"Release metadata: {metadata}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
