"""Reconcile the mutation result files of one run (M238): ``python tools/quality/mutation_reconcile.py <sha>``.

Reads ``docs/mission-reports/m201-m230-evidence/mutation_final_<sha>/`` (the 16 result JSONs and the progress
file), recounts every status from the per-mutant records, checks them against the summary fields, and prints a
Markdown table. A mutant whose status is SURVIVED with its ``equivalent`` justification set is counted as
EQUIVALENT (never KILLED). Read-only.
"""
import glob
import json
import os
import re
import sys

BASE = "docs/mission-reports/m201-m230-evidence"


def _count(value):
    return len(value) if isinstance(value, list) else value


def rows_for(sha: str) -> list:
    progress = open(f"{BASE}/mutation_final_{sha}/progress_{sha}.txt", encoding="utf-8").read()
    seconds = dict(re.findall(r"(\S+) exit=0 seconds=(\d+)", progress))
    rows = []
    for path in sorted(glob.glob(f"{BASE}/mutation_final_{sha}/mutation_*.json")):
        name = os.path.basename(path)[len("mutation_"):-5]
        data = json.load(open(path, encoding="utf-8"))
        statuses = [m["status"] for m in data["mutants"]]
        flagged = [m for m in data["mutants"] if m.get("equivalent")]
        flagged_survivors = sum(1 for m in flagged if m["status"] == "SURVIVED")
        killed, invalid = statuses.count("KILLED"), statuses.count("INVALID")
        equivalent = statuses.count("EQUIVALENT") + flagged_survivors
        survived = statuses.count("SURVIVED") - flagged_survivors
        summary = tuple(_count(data[key]) for key in
                        ("killed", "survived_non_equivalent", "declared_equivalent", "invalid"))
        if (killed, survived, equivalent, invalid) != summary:
            raise SystemExit(f"{name}: per-mutant statuses {killed, survived, equivalent, invalid} != summary {summary}")
        survivors = [m["id"] for m in data["mutants"] if m["status"] == "SURVIVED" and not m.get("equivalent")]
        equivalents = [f'{m["id"]} (status {m["status"]}, equivalent flag set)' for m in flagged]
        tool = f"tools/quality/mutation_{name}.py"
        schema = "id lists" if isinstance(data["killed"], list) else "counts"
        rows.append((name, len(statuses), data["complete"], killed, survived, equivalent, invalid, seconds.get(name),
                     tool, os.path.exists(tool), survivors, equivalents, data["baseline"]["summary"], schema))
    return rows


def main(sha: str) -> None:
    rows = rows_for(sha)
    print("| Catalogue | Tool | Mutants | complete | K | S | E | I | Seconds | Filtered (`--only`) | JSON schema "
          "| Baseline | Survivors / equivalents |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    totals = [0] * 5
    seconds_total = 0
    for name, n, complete, k, s, e, i, sec, tool, exists, survivors, equivalents, baseline, schema in rows:
        totals = [totals[0] + n, totals[1] + k, totals[2] + s, totals[3] + e, totals[4] + i]
        seconds_total += int(sec or 0)
        notes = "; ".join([*(f"SURVIVED `{x}`" for x in survivors), *(f"EQUIVALENT `{x}`" for x in equivalents)]) or "—"
        print(f"| {name} | `{tool}`{'' if exists else ' (MISSING)'} | {n} | {complete} | {k} | {s} | {e} | {i} | {sec} "
              f"| no (full catalogue) | {schema} | {baseline.split(' in ')[0]} | {notes} |")
    complete_count = sum(1 for row in rows if row[2] is True)
    print(f"| **total** | {len(rows)} tools | **{totals[0]}** | {complete_count}/{len(rows)} True | **{totals[1]}** "
          f"| **{totals[2]}** | **{totals[3]}** | **{totals[4]}** | {seconds_total} | | | | |")


if __name__ == "__main__":
    main(sys.argv[1])
