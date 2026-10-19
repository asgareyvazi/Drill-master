"""Privacy regression check for the tracked repository population.

Run from the repository root::

    python tools/privacy/privacy_check.py            # scan `git ls-files`
    python tools/privacy/privacy_check.py PATH ...   # scan explicit files

Rules live in ``tools/privacy/policy.json`` (documented in
``docs/privacy/PRIVACY_CHECK.md``).  The check:

* rejects file names that follow a real operational naming convention
  (``prohibited_filename_patterns``), wherever they appear;
* requires every binary data file (spreadsheet, PDF, database, image, ...)
  to be on an explicit allowlist pinned by path **and** SHA-256, so an
  approved synthetic fixture cannot silently be replaced by a real file;
* scans text files -- and the XML members of Office archives -- for
  configurable patterns (user-profile paths, private keys, access tokens,
  e-mail addresses outside approved domains);
* matches word tokens against a denylist stored only as salted SHA-256
  digests, so the policy itself never contains the protected values.

Findings name the rule, the file and the line -- never the matched text,
so the output is safe for public CI logs.  Exit status: 0 clean, 1 findings,
2 configuration error.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = Path(__file__).with_name("policy.json")
HASH_PREFIX = b"drillmaster-privacy-v1\x00"
TOKEN_RE = re.compile(r"[0-9][0-9,]*[0-9]|[^\W\d_][\w.\-']*", re.UNICODE)
OFFICE_SUFFIXES = {".xlsx", ".xlsm", ".docx", ".pptx"}
MAX_TEXT_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int = 0
    detail: str = ""

    def render(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{where}: {self.rule}{(' (' + self.detail + ')') if self.detail else ''}"


def normalize_token(token: str) -> str:
    token = unicodedata.normalize("NFKC", token).casefold().strip(".-'")
    if token[:1].isdigit():
        token = token.replace(",", "")
    return token


def token_digest(token: str) -> str:
    return hashlib.sha256(HASH_PREFIX + normalize_token(token).encode("utf-8")).hexdigest()


def _token_variants(token: str):
    yield token
    parts = [p for p in re.split(r"[.\-']", token) if p]
    if len(parts) > 1:
        yield from parts


def load_policy(path: Path = POLICY) -> dict:
    policy = json.loads(path.read_text(encoding="utf-8"))
    for key in ("prohibited_filename_patterns", "data_file_suffixes", "allowlisted_data_files",
                "text_patterns", "allowed_email_domains", "denylist_sha256"):
        if key not in policy:
            raise ValueError(f"policy is missing {key!r}")
    for rule in policy["text_patterns"]:
        re.compile(rule["regex"])
    for digest in policy["denylist_sha256"]:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("denylist entries must be lowercase SHA-256 hex digests")
    return policy


class Scanner:
    def __init__(self, policy: dict):
        self.policy = policy
        self.name_rules = [re.compile(p) for p in policy["prohibited_filename_patterns"]]
        self.text_rules = [(r["id"], re.compile(r["regex"])) for r in policy["text_patterns"]]
        # the local part may not start right after an escape such as ``\n`` (JSON-encoded diffs)
        self.email_re = re.compile(r"(?<![\\\w.%+-])[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
        self.allowed_domains = {d.lower() for d in policy["allowed_email_domains"]}
        self.denylist = set(policy["denylist_sha256"])
        self.data_suffixes = {s.lower() for s in policy["data_file_suffixes"]}
        self.allowlist = {entry["path"]: entry["sha256"] for entry in policy["allowlisted_data_files"]}
        self.text_exempt = set(policy.get("text_scan_exempt_paths", []))

    # -- text ---------------------------------------------------------------
    def scan_text(self, text: str, path: str, member: str = "") -> list[Finding]:
        findings = []
        label = f"{path}!{member}" if member else path
        for number, line in enumerate(text.splitlines(), 1):
            for rule_id, regex in self.text_rules:
                if regex.search(line):
                    findings.append(Finding(rule_id, label, number))
            for match in self.email_re.finditer(line):
                domain = match.group(1).lower()
                if not any(domain == d or domain.endswith("." + d) for d in self.allowed_domains):
                    findings.append(Finding("email-outside-allowed-domains", label, number))
            if self.denylist:
                for raw in TOKEN_RE.findall(line):
                    if any(token_digest(v) in self.denylist for v in _token_variants(raw)):
                        findings.append(Finding("denylisted-identity-token", label, number))
                        break
        return findings

    def scan_office_archive(self, data: bytes, path: str) -> list[Finding]:
        findings = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    if info.filename.lower().endswith((".xml", ".vml", ".rels")) and info.file_size <= MAX_TEXT_BYTES:
                        text = zf.read(info).decode("utf-8", errors="replace")
                        # one logical line per XML text node keeps line numbers meaningful
                        text = re.sub(r">\s*<", ">\n<", text)
                        findings.extend(self.scan_text(text, path, info.filename))
        except zipfile.BadZipFile:
            findings.append(Finding("unreadable-office-archive", path))
        return findings

    # -- files --------------------------------------------------------------
    def scan_file(self, root: Path, rel: str) -> list[Finding]:
        findings = []
        name = rel.rsplit("/", 1)[-1]
        for regex in self.name_rules:
            if regex.search(name):
                findings.append(Finding("prohibited-filename", rel))
        path = root / rel
        if not path.is_file():
            return findings
        suffix = path.suffix.lower()
        data = path.read_bytes()
        if suffix in self.data_suffixes:
            expected = self.allowlist.get(rel)
            if expected is None:
                findings.append(Finding("data-file-not-allowlisted", rel))
            elif hashlib.sha256(data).hexdigest() != expected:
                findings.append(Finding("allowlisted-data-file-changed", rel, detail="sha256 differs from policy"))
            if suffix in OFFICE_SUFFIXES:
                findings.extend(self.scan_office_archive(data, rel))
            return findings
        if rel in self.text_exempt or len(data) > MAX_TEXT_BYTES or b"\x00" in data[:8192]:
            return findings
        findings.extend(self.scan_text(data.decode("utf-8", errors="replace"), rel))
        return findings


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Privacy regression check (see module docstring).")
    parser.add_argument("paths", nargs="*", help="repository-relative paths (default: all tracked files)")
    parser.add_argument("--policy", type=Path, default=POLICY)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--digest", metavar="TOKEN", help="print the denylist digest of TOKEN and exit "
                        "(run locally; never paste protected values into CI)")
    args = parser.parse_args(argv)
    if args.digest is not None:
        print(token_digest(args.digest))
        return 0
    try:
        scanner = Scanner(load_policy(args.policy))
    except (OSError, ValueError, KeyError, re.error) as exc:
        print(f"privacy check: configuration error: {exc}", file=sys.stderr)
        return 2
    files = args.paths or tracked_files(args.root)
    findings = [f for rel in files for f in scanner.scan_file(args.root, rel)]
    for finding in findings:
        print(finding.render())
    print(f"privacy check: {len(files)} file(s) scanned, {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
