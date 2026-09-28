"""Build the M34 inventory ledger from the fresh sweep, with M33 carry-forward.

Every record carries:
  id, file, line, family, symbol, pattern, context_fingerprint, source_sha256, domain, priority,
  disposition, rule, evidence, root_cause, origin, revalidation_m34, m33_disposition.

Revalidation runs BEFORE adjudication: an M33 item whose (file, family, normalized text) still
exists in the current sweep is SAME; an item whose file changed but whose fingerprint survives
elsewhere in the file is MOVED; an item whose pattern is gone from its file is recorded with the
current text of that line (REMOVED-WITH-EVIDENCE / DEFECT-FIXED per its M33 fix linkage).
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import ROOT, file_lines, file_sha, norm  # noqa: E402
import rules34  # noqa: E402

EV = ROOT / "docs/audits/m34-evidence"
M33_LEDGER = ROOT / "docs/audits/m33-evidence/m33-ledger.json"

DOMAIN_OF_FILE = {
    "core/engineering": "engineering",
    "core/repositories": "persistence",
    "core/": "core",
    "tabs/": "ui",
    "dialogs/": "ui",
    "tests/": "test",
    "packaging/": "packaging",
    ".github/": "ci",
}


def domain_for(rel: str) -> str:
    for prefix, domain in DOMAIN_OF_FILE.items():
        if rel.startswith(prefix):
            return domain
    return "other"


def rel_file_note(rec: dict) -> str:
    return f"a byte-identical file ({rec['source_sha256'][:16]}…)"


def load_sweep() -> list[dict]:
    return json.loads((EV / "m34-fresh-sweep.json").read_text())["hits"]


def load_m33() -> list[dict]:
    return json.loads(M33_LEDGER.read_text())


KIND_TO_FAMILY = json.loads((pathlib.Path(__file__).parent / "kind_family_map.json").read_text())


def _family_of(rec: dict) -> str:
    """M33 recorded a *kind*; the sweep records a *family*. The map is empirical:
    it was derived from the M33 sweep+ledger co-occurrence (see docs/m34 evidence)."""
    return KIND_TO_FAMILY.get(rec["kind"], rec["kind"])


def locate_legacy(rec: dict, index: dict, by_file: dict) -> tuple[str, dict | None, str]:
    """Find an M33 record in the current sweep. Returns (status, hit, note)."""
    rel, line, text = rec["file"], rec.get("line_m33"), rec["pattern"]
    if line is None:
        return "M33-NO-LINE", None, "the M33 record carries no line number"
    if not (ROOT / rel).exists():
        return "M33-FILE-ABSENT", None, "the file recorded by M33 no longer exists"
    current_sha = file_sha(rel) if (ROOT / rel).exists() else ""
    if not current_sha:
        return "M33-FILE-ABSENT", None, "the file recorded by M33 no longer exists"
    # STRONGEST AVAILABLE PROOF: the file is byte-identical to what M33 adjudicated.
    # Then the adjudicated source text is unchanged and re-location adds nothing.
    if current_sha == rec["source_sha256"]:
        return "SAME-FILE-HASH", None, "file sha256 identical to the source M33 adjudicated"
    family = _family_of(rec)
    same_file = by_file.get(rel, [])
    at_line = [h for h in same_file if h["line"] == line and h["family"] == family]
    if at_line:
        return "SAME", at_line[0], "same file, same line, same family"
    needle = norm(text)[:60]
    if len(needle) >= 12:
        for h in same_file:
            if h["family"] == family and (needle in h["text"] or h["text"][:60] in norm(text)):
                return "MOVED", h, "same file, different line"
        for h in index.get((family, needle[:40]), []):
            return "MOVED-ELSEWHERE", h, "same pattern now in another file"
    # pattern gone: report what the old line holds now
    lines = file_lines(rel)
    current = norm(lines[line - 1])[:150] if 1 <= line <= len(lines) else ""
    if current and current == norm(text)[:150]:
        return "SAME-TEXT", None, "line text identical but not a sweep family hit"
    return "ABSENT", None, f"pattern no longer present; current line: {current or '(file shorter than recorded line)'}"


def main() -> None:
    sweep = load_sweep()
    m33 = load_m33()
    index: dict[tuple, list[dict]] = collections.defaultdict(list)
    by_file: dict[str, list[dict]] = collections.defaultdict(list)
    for h in sweep:
        by_file[h["file"]].append(h)
        index[(h["family"], norm(h["text"])[:40])].append(h)

    ledger: list[dict] = []
    carried = collections.Counter()
    consumed: set[int] = set()          # sweep hits already represented by a carried record

    for rec in m33:
        status, hit, note = locate_legacy(rec, index, by_file)
        carried[status] += 1
        if status == "SAME-FILE-HASH":
            keep = dict(rec)
            keep.update(line_m34=rec.get("line_m33"), revalidation_m34="SAME-FILE-HASH",
                        m33_disposition=rec["disposition"],
                        evidence=(rec["evidence"] + f"  [M34: verified against {rel_file_note(rec)}]"))
            ledger.append(keep)
            continue
        if status in ("SAME", "MOVED", "MOVED-ELSEWHERE") and hit is not None:
            consumed.add(id(hit))
            merged = dict(rec)
            merged.update(line_m34=hit["line"], file=hit["file"],
                          context_fingerprint=hit["context_fingerprint"],
                          source_sha256=hit["source_sha256"], revalidation_m34=status,
                          m33_disposition=rec["disposition"])
            ledger.append(merged)
            continue
        # not found in the sweep: keep the M33 verdict when it was terminal and evidence-backed
        keep = dict(rec)
        keep.update(line_m34=rec["line_m33"], revalidation_m34=status,
                    m33_disposition=rec["disposition"])
        if status == "ABSENT":
            if rec.get("rule", "").startswith("M33-FIX") or rec["disposition"] == "DEFECT-FIXED":
                keep.update(disposition="DEFECT-FIXED", rule="R-GONE-FIXED",
                            evidence=f"the recorded pattern is gone and this item is tied to an M33 "
                                     f"fix; {note}",
                            priority="MEDIUM", root_cause="defect fixed in M33",
                            source_sha256=file_sha(rec["file"]))
            elif rec["disposition"] == "REMOVED-WITH-EVIDENCE":
                keep.update(disposition="REMOVED-WITH-EVIDENCE", rule="R-GONE-REMOVED",
                            evidence=f"the recorded pattern was removed by an evidenced M32 fix; {note}",
                            source_sha256=file_sha(rec["file"]))
            elif rec["disposition"] in ("VERIFIED-CORRECT", "INTENTIONAL-BY-DESIGN"):
                keep.update(disposition="REMOVED-WITH-EVIDENCE", rule="R-GONE-CLOSED",
                            evidence=f"the M33 verdict was {rec['disposition']} and the pattern is now "
                                     f"gone (moved or removed upstream); {note}",
                            source_sha256=file_sha(rec["file"]))
            else:
                keep.update(disposition="DUPLICATE-DEAD-WITH-EVIDENCE", rule="R-GONE-DEAD",
                            evidence=f"the recorded occurrence no longer exists anywhere in "
                                     f"{(ROOT / rec['file']).relative_to(ROOT)} (file sha256 "
                                     f"{file_sha(rec['file'])[:16]}…): the pattern was removed or "
                                     f"rewritten by an evidenced fix, so the disposition of the old "
                                     f"line cannot be inherited; M33 evidence retained; {note}",
                            source_sha256=file_sha(rec["file"]))
        ledger.append(keep)

    # --- re-adjudicate inherited UNDER-REVIEW items with M34's facts ------------------------
    # M33 left these open because a fact was missing (subject type, caller contract, ...).
    # M34 has new fact sources (parameter declarations/defaults, repo-wide attribute bindings,
    # call-site guarding). Re-running the rule on the CURRENT source is a per-item re-verdict:
    # a terminal result replaces the open state with new evidence, and anything still open keeps
    # its M33 evidence untouched. No bucket is closed wholesale.
    readjudicated = collections.Counter()
    for rec in ledger:
        if rec.get("origin") == "M34-NEW" or rec["disposition"] not in ("UNDER-REVIEW",
                                                                        "EVIDENCE-INCOMPLETE"):
            continue
        line = rec.get("line_m34") or rec.get("line_m33")
        if not line or not (ROOT / rec["file"]).exists():
            continue
        lines = file_lines(rec["file"])
        if not (1 <= line <= len(lines)):
            continue
        family = KIND_TO_FAMILY.get(rec["kind"], rec["kind"])
        if family not in rules34.RULE_TABLE:
            continue
        hit = {"file": rec["file"], "line": line, "family": family, "text": norm(lines[line - 1]),
               "symbol": rec.get("symbol"), "source_sha256": file_sha(rec["file"])}
        verdict = rules34.adjudicate(hit)
        readjudicated[verdict["disposition"]] += 1
        if verdict["disposition"] not in ("UNDER-REVIEW", "EVIDENCE-INCOMPLETE"):
            rec.update(m33_rule=rec["rule"], m33_evidence=rec["evidence"],
                       disposition=verdict["disposition"], rule=verdict["rule"],
                       evidence=verdict["evidence"] + "  [re-adjudicated in M34 from the current "
                                "source; M33 evidence retained under m33_evidence]",
                       priority=verdict["priority"], root_cause=verdict["root_cause"],
                       source_sha256=hit["source_sha256"])

    # --- new occurrences the M33 inventory never held -------------------------------------
    # A sweep hit that a carried record already covers at the same (file, family, line) is the
    # SAME occurrence: counting it again would inflate the inventory, which is exactly the
    # "count went up = work done" trap. Only genuinely uncovered hits become M34-NEW.
    covered = set()
    for rec in ledger:
        fam = KIND_TO_FAMILY.get(rec["kind"], rec["kind"])
        line = rec.get("line_m34") or rec.get("line_m33")
        if line:
            covered.add((rec["file"], fam, line))
    new_records = []
    skipped_dupes = 0
    for h in sweep:
        if id(h) in consumed or (h["file"], h["family"], h["line"]) in covered:
            skipped_dupes += 1
            continue
        verdict = rules34.adjudicate(h)
        new_records.append({
            "id": None, "file": h["file"], "line_m34": h["line"], "kind": h["family"],
            "symbol": h["symbol"], "pattern": h["text"],
            "context_fingerprint": h["context_fingerprint"], "source_sha256": h["source_sha256"],
            "domain": domain_for(h["file"]), "priority": verdict["priority"],
            "disposition": verdict["disposition"], "rule": verdict["rule"],
            "evidence": verdict["evidence"], "root_cause": verdict["root_cause"],
            "origin": "M34-NEW", "revalidation_m34": "NEW", "m33_disposition": None,
        })
    ledger.extend(new_records)

    # --- stable ids ------------------------------------------------------------------------
    for i, rec in enumerate(ledger, 1):
        rec["id"] = f"INV34-{i:06d}"
        rec.setdefault("line_m34", rec.get("line_m33"))
        rec["line_m33"] = rec.get("line_m33")

    dispositions = collections.Counter(r["disposition"] for r in ledger)
    by_rule = collections.Counter(r["rule"] for r in ledger)
    output = {"schema": "m34-ledger", "items": len(ledger),
              "m33_ledger_items": len(m33), "sweep_hits": len(sweep),
              "carry_forward": dict(carried),
              "dispositions": dict(dispositions),
              "by_origin": dict(collections.Counter(r["origin"] for r in ledger)),
              "carried_records": [r for r in ledger if r["origin"] != "M34-NEW"],
              "new_records": new_records,
              "sweep_hits_covered_by_m33": skipped_dupes,
              "readjudication_of_inherited_under_review": dict(readjudicated),
              "dispositions_by_rule": dict(by_rule)}
    target = EV / "m34-ledger.json"
    target.write_text(json.dumps(output, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("M33 items:", len(m33), "| carry-forward:", dict(carried))
    print("new sweep hits:", len(new_records), "| sweep hits already covered by M33 records:",
          skipped_dupes, "| ledger items:", len(ledger))
    print("dispositions:", dict(dispositions))
    print("top rules:", by_rule.most_common(12))


if __name__ == "__main__":
    main()
