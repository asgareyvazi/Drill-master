"""M193: re-audit the 50 repositories of the M52 open-source adoption register against their upstream today.

Read-only. It parses ``docs/engineering/OPEN_SOURCE_ADOPTION_REGISTER.md`` (repository, recorded upstream SHA,
recorded licence, classification), then asks the GitHub REST API for each repository's current state: whether it
still exists, the default-branch head SHA, the licence GitHub detects (SPDX id), whether it is archived, and the
last push. Nothing is downloaded, cloned, installed or executed. ``--offline`` only parses the register.

The output states, per repository, what changed since M52. It never upgrades a classification by itself: a licence
that appeared or changed is reported as ``LICENCE CHANGED - RE-REVIEW`` for a person to decide; a repository that
disappeared is ``GONE``, and its recorded classification stays (nothing was taken from it).

Usage: python tools/quality/oss_reaudit_m193.py [--offline] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
REGISTER = ROOT / "docs" / "engineering" / "OPEN_SOURCE_ADOPTION_REGISTER.md"
CONTRACT = "oss-reaudit-m193-v1"

_HEADING = re.compile(r"^### (\d+)\. (\S+)\s*$")
_SHA = re.compile(r"^\* Upstream SHA: `([0-9a-f]{40})` \(([^,]+), branch `([^`]+)`\)")
_LICENCE = re.compile(r"^\* Licence: ([^;]+);")
_CLASS = re.compile(r"^\* \*\*Classification: ([A-Z ]+)\*\*")

# GitHub's SPDX ids against the register's wording.
_SPDX_EQUIVALENT = {"none detected": {None, "NOASSERTION"}}

UNCHANGED, MOVED, LICENCE_CHANGED, GONE, ARCHIVED, ERROR = (
    "UNCHANGED", "NEW COMMITS", "LICENCE CHANGED - RE-REVIEW", "GONE", "ARCHIVED", "NOT CHECKED")


def parse_register(text: str) -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []
    current: Optional[Dict[str, object]] = None
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            current = {"number": int(heading.group(1)), "repository": heading.group(2), "sha": None,
                       "sha_date": None, "branch": None, "licence": None, "classification": None}
            entries.append(current)
            continue
        if current is None:
            continue
        for pattern, keys in ((_SHA, ("sha", "sha_date", "branch")), (_LICENCE, ("licence",)),
                              (_CLASS, ("classification",))):
            match = pattern.match(line)
            if match and current[keys[0]] is None:
                for key, value in zip(keys, match.groups()):
                    current[key] = value.strip()
    return entries


def _licence_matches(recorded: Optional[str], spdx: Optional[str]) -> bool:
    if recorded is None:
        return False
    if recorded in _SPDX_EQUIVALENT:
        return spdx in _SPDX_EQUIVALENT[recorded]
    return (spdx or "").lower() == recorded.lower()


def assess(entry: Dict[str, object], remote: Optional[Dict[str, object]], error: Optional[str] = None
           ) -> Dict[str, object]:
    """The re-audit verdict of one repository (pure; ``remote`` is the API state or None when it is gone)."""
    out = dict(entry)
    if error:
        out.update(state=ERROR, detail=error)
        return out
    if remote is None:
        out.update(state=GONE, detail="the repository is no longer reachable; nothing was taken from it, the M52 "
                                      "classification stays")
        return out
    out.update(current_sha=remote.get("sha"), current_licence=remote.get("spdx"), archived=remote.get("archived"),
               pushed_at=remote.get("pushed_at"), default_branch=remote.get("default_branch"))
    states = []
    if not _licence_matches(entry.get("licence"), remote.get("spdx")):
        states.append(LICENCE_CHANGED)
    if remote.get("archived"):
        states.append(ARCHIVED)
    if remote.get("sha") and remote.get("sha") != entry.get("sha"):
        states.append(MOVED)
    out["state"] = "; ".join(states) if states else UNCHANGED
    return out


def gh_fetch(repository: str) -> Dict[str, object]:
    """Current state through the authenticated ``gh`` CLI (read-only GET requests)."""
    def get(path: str) -> Optional[dict]:
        run = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=60)
        if run.returncode != 0:
            if "Not Found" in run.stderr or "404" in run.stderr:
                return None
            raise RuntimeError(run.stderr.strip()[:200] or f"gh exited {run.returncode}")
        return json.loads(run.stdout)

    repo = get(f"repos/{repository}")
    if repo is None:
        return {"gone": True}
    branch = repo.get("default_branch")
    head = get(f"repos/{repository}/commits/{branch}") if branch else None
    licence = repo.get("license") or {}
    return {"gone": False, "sha": (head or {}).get("sha"), "spdx": licence.get("spdx_id"),
            "archived": bool(repo.get("archived")), "pushed_at": repo.get("pushed_at"), "default_branch": branch}


def reaudit(entries, fetch: Callable[[str], Dict[str, object]]) -> List[Dict[str, object]]:
    results = []
    for entry in entries:
        try:
            remote = fetch(str(entry["repository"]))
        except Exception as exc:  # silent-ok: the repository is reported NOT CHECKED with the reason
            results.append(assess(entry, None, error=f"{type(exc).__name__}: {exc}"))
            continue
        results.append(assess(entry, None if remote.get("gone") else remote))
    return results


def summary(results) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in results:
        for state in str(row["state"]).split("; "):
            counts[state] = counts.get(state, 0) + 1
    return dict(sorted(counts.items()))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="parse the register only")
    parser.add_argument("--json", help="write the result here")
    args = parser.parse_args(argv)
    entries = parse_register(REGISTER.read_text(encoding="utf-8"))
    if len(entries) != 50 or any(e["sha"] is None or e["classification"] is None for e in entries):
        print(f"register parse incomplete: {len(entries)} entries", file=sys.stderr)
        return 2
    results = entries if args.offline else reaudit(entries, gh_fetch)
    payload = {"contract": CONTRACT, "register": str(REGISTER.relative_to(ROOT)), "entries": len(entries),
               "summary": {} if args.offline else summary(results), "results": results}
    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for row in results:
        print(f"{row['number']:>2} {row['repository']:<60} {row.get('state', 'PARSED')}")
    if not args.offline:
        print(json.dumps(payload["summary"]))
    return 0 if args.offline or not any(r["state"] == ERROR for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
