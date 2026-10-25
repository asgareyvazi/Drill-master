"""Cross-version database compatibility check (M46), SYNTHETIC data only.

Proves, with two real code trees and one throw-away SQLite file, that the
M45 ``document_links`` migration is additive and reversible in practice:

1. ``old``  - the old tree (default ``0822a28``, the M44 report tip) creates a
   database with a synthetic well, two daily reports and three documents
   imported through its real reviewed-import path.
2. ``fail`` - the current tree opens a *copy* of that database with a failure
   injected at the last migration step (after the new table and indexes were
   created in the migration transaction).  The open must fail and the copy
   must be byte-for-byte unchanged in schema and rows.
3. ``new``  - the current tree opens the database: table, indexes and
   constraints exist (read back from ``sqlite_master``), schema version is
   still 6, documents/pages are unchanged; three links are created through
   ``DocumentLinkService``; foreign-key and integrity checks pass; a second
   and third open change nothing (idempotent).
4. ``old2`` - the old tree opens the upgraded database, lists and searches the
   documents, then deletes a report, a document and the well through ITS OWN
   audited delete paths (which know nothing about links).  SQLite's foreign
   keys must remove the dependent links: zero orphans, documents kept unless
   deleted.

The old tree is extracted with ``git archive`` into a temporary directory
(no worktree, no change to ``.git``).  Every phase runs in a separate Python
process with its own ``PYTHONPATH`` and a temporary working directory.

Usage::

    python tools/quality/schema_compat_check.py [--old-ref 0822a28] [--json OUT]

Exit status 0 only if every check passed.  Output contains counts, names of
schema objects and pass/fail flags - no document text.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

COMMON = r'''
import hashlib, json, sqlite3, sys
from datetime import date
from pathlib import Path
DB = Path(sys.argv[1]); WORK = Path(sys.argv[2])
def raw(sql, *args):
    con = sqlite3.connect(str(DB))
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()
def snapshot():
    con = sqlite3.connect(str(DB))
    try:
        schema = sorted(r for r in con.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
        digest = hashlib.sha256()
        for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                    "AND name NOT LIKE 'sqlite_%' AND name <> 'schema_version' ORDER BY name"):
            q = '"' + table.replace('"', '""') + '"'
            for row in con.execute(f"SELECT * FROM {q} ORDER BY rowid"):
                digest.update(repr((table, row)).encode())
        return {"schema": hashlib.sha256(repr(schema).encode()).hexdigest(), "rows": digest.hexdigest()}
    finally:
        con.close()
def open_db():
    from tests.synthetic_operations import make_file_database
    return make_file_database(DB)
out = {}
'''

OLD = COMMON + r'''
from core.database import Company, DailyReport, Project, Section, Well
from core.document_library import DocumentLibrary, extract_document
db = open_db()
s = db.create_session()
company = Company(name="SYNTHETIC COMPAT CO", code="SYN-CC"); s.add(company); s.flush()
project = Project(name="SYNTHETIC COMPAT PROJECT", code="SYN-CP", company_id=company.id); s.add(project); s.flush()
well = Well(name="SYN-COMPAT-01", code="SYN-C1", project_id=project.id); s.add(well); s.flush()
section = Section(well_id=well.id, name="SYN 8 1/2 in"); s.add(section); s.flush()
r1 = DailyReport(well_id=well.id, section_id=section.id, report_date=date(2026, 2, 1), report_number=1)
r2 = DailyReport(well_id=well.id, section_id=section.id, report_date=date(2026, 2, 2), report_number=2)
s.add_all([r1, r2]); s.commit()
ids = {"well": well.id, "report_1": r1.id, "report_2": r2.id}
s.close()
lib = DocumentLibrary(db)
docs = {}
for name, text in (("syn_compat_a.txt", "SYNTHETIC compat page alpha SYN-COMPAT-01 depth 1200"),
                   ("syn_compat_b.txt", "SYNTHETIC compat page bravo"),
                   ("syn_compat_c.txt", "SYNTHETIC compat page charlie")):
    path = WORK / name
    path.write_text(text, encoding="utf-8")
    outcome = lib.import_reviewed(extract_document(path))
    docs[name] = outcome.document_id
ids["documents"] = docs
out["ids"] = ids
out["has_link_table"] = bool(raw("SELECT 1 FROM sqlite_master WHERE name='document_links'"))
out["schema_version"] = raw("SELECT version FROM schema_version")[0][0]
out["documents"] = raw("SELECT count(*) FROM documents")[0][0]
out["pages"] = raw("SELECT count(*) FROM document_pages")[0][0]
out["page_text_sha"] = hashlib.sha256(repr(raw("SELECT id, text FROM document_pages ORDER BY id")).encode()).hexdigest()
out["search_hits"] = len(lib.search("compat").get("hits", []))
db.engine.dispose()
print(json.dumps(out))
'''

FAIL = COMMON + r'''
from core.database import DatabaseManager
before = snapshot()
def boom(self, connection):
    created = connection.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE '%document_links%'").fetchone()[0]
    out["objects_created_before_failure"] = created
    raise RuntimeError("injected migration failure")
DatabaseManager._verify_stored_ownership = boom
db = DatabaseManager(bootstrap_passwords={"admin": "Synthetic-Admin-1!", "engineer": "Synthetic-Eng-1!",
                                          "viewer": "Synthetic-View-1!"})
db.db_path = str(DB)
out["initialize_returned"] = db.initialize()
out["diagnostic_stage"] = (db.last_diagnostic or {}).get("stage")
try:
    db.engine.dispose()
except Exception:
    pass
after = snapshot()
out["schema_unchanged"] = before["schema"] == after["schema"]
out["rows_unchanged"] = before["rows"] == after["rows"]
out["has_link_table"] = bool(raw("SELECT 1 FROM sqlite_master WHERE name='document_links'"))
print(json.dumps(out))
'''

NEW = COMMON + r'''
ids = json.loads(sys.argv[3])
db = open_db()
names = {r[0] for r in raw("SELECT name FROM sqlite_master")}
out["objects"] = sorted(n for n in names if "document_links" in n)
out["link_table_sql"] = raw("SELECT sql FROM sqlite_master WHERE name='document_links'")[0][0]
out["fk"] = sorted([r[2], r[3], r[4], r[6]] for r in raw("PRAGMA foreign_key_list(document_links)"))
out["schema_version"] = raw("SELECT version FROM schema_version")[0][0]
out["documents"] = raw("SELECT count(*) FROM documents")[0][0]
out["pages"] = raw("SELECT count(*) FROM document_pages")[0][0]
out["page_text_sha"] = hashlib.sha256(repr(raw("SELECT id, text FROM document_pages ORDER BY id")).encode()).hexdigest()
from core.document_links import DocumentLinkService
svc = DocumentLinkService(db)
d = ids["documents"]
svc.create_link(d["syn_compat_a.txt"], ids["well"])
svc.create_link(d["syn_compat_a.txt"], ids["well"], ids["report_1"], page_no=1)
svc.create_link(d["syn_compat_b.txt"], ids["well"], ids["report_2"])
out["links"] = raw("SELECT count(*) FROM document_links")[0][0]
out["link_audits"] = raw("SELECT count(*) FROM audit_logs WHERE action='document_link'")[0][0]
out["fk_check"] = raw("PRAGMA foreign_key_check")
out["integrity"] = raw("PRAGMA integrity_check")[0][0]
db.engine.dispose()
first = snapshot()
for _ in range(2):
    again = open_db(); again.engine.dispose()
second = snapshot()
out["reopen_schema_unchanged"] = first["schema"] == second["schema"]
out["reopen_rows_unchanged"] = first["rows"] == second["rows"]
print(json.dumps(out))
'''

OLD2 = COMMON + r'''
ids = json.loads(sys.argv[3])
db = open_db()
from core.document_library import DocumentLibrary
lib = DocumentLibrary(db)
out["documents_listed"] = len(lib.list_documents())
out["search_hits"] = len(lib.search("compat").get("hits", []))
from core.authorization import system_scope
links = lambda: raw("SELECT count(*) FROM document_links")[0][0]
out["links_start"] = links()
with system_scope():
    db.delete_daily_report(ids["report_1"])
out["links_after_report_delete"] = links()
d = ids["documents"]
with system_scope():
    lib.delete_document(d["syn_compat_b.txt"])
out["links_after_document_delete"] = links()
with system_scope():
    db.delete_well(ids["well"])
out["links_after_well_delete"] = links()
out["documents_left"] = raw("SELECT count(*) FROM documents")[0][0]
out["fk_check"] = raw("PRAGMA foreign_key_check")
out["integrity"] = raw("PRAGMA integrity_check")[0][0]
db.engine.dispose()
print(json.dumps(out))
'''


def run_phase(name, code, tree, db, work, *extra):
    script = work / f"phase_{name}.py"
    script.write_text(code, encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(tree), QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    cwd = work / f"cwd_{name}"
    cwd.mkdir(exist_ok=True)
    # PYTHONPATH makes core/ and tests/ of that tree importable; the working
    # directory is a scratch directory so no log or setting lands in a tree.
    proc = subprocess.run([sys.executable, str(script), str(db), str(work), *extra], cwd=str(cwd), env=env,
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"phase {name} failed (rc {proc.returncode}):\n{tail}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def extract_tree(ref, dest):
    data = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", ref], check=True,
                          capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        if hasattr(tarfile, "data_filter"):           # Python >= 3.11.4 / 3.12
            tar.extractall(dest, filter="data")
        else:                                         # archive of this repository's own commit
            tar.extractall(dest)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--old-ref", default="0822a28")
    parser.add_argument("--json", help="write the result document here")
    args = parser.parse_args(argv)
    work = Path(tempfile.mkdtemp(prefix="dm_compat_"))
    try:
        old_tree = work / "old_tree"
        old_tree.mkdir()
        extract_tree(args.old_ref, old_tree)
        db = work / "compat.db"
        result = {"old_ref": subprocess.run(["git", "-C", str(REPO), "rev-parse", args.old_ref], check=True,
                                            capture_output=True, text=True).stdout.strip(),
                  "new_ref": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], check=True,
                                            capture_output=True, text=True).stdout.strip()}
        result["old"] = old = run_phase("old", OLD, old_tree, db, work)
        failing = work / "compat_fail.db"
        shutil.copyfile(db, failing)
        result["fail"] = run_phase("fail", FAIL, REPO, failing, work)
        ids = json.dumps(old["ids"])
        result["new"] = new = run_phase("new", NEW, REPO, db, work, ids)
        result["old2"] = old2 = run_phase("old2", OLD2, old_tree, db, work, ids)
        fail = result["fail"]
        checks = {
            "old build has no link table": old["has_link_table"] is False,
            "old build writes schema 6": old["schema_version"] == 6,
            "failed migration is reported": fail["initialize_returned"] is False,
            "failure happened after the link objects were created": fail.get("objects_created_before_failure", 0) >= 1,
            "failed migration leaves schema unchanged": fail["schema_unchanged"],
            "failed migration leaves rows unchanged": fail["rows_unchanged"],
            "failed migration leaves no link table": fail["has_link_table"] is False,
            "upgrade creates table and indexes": set(new["objects"]) >= {
                "document_links", "uq_document_links_well_level", "ix_document_links_well_id",
                "ix_document_links_report_id"},
            "upgrade keeps schema 6": new["schema_version"] == 6,
            "upgrade keeps documents": (new["documents"], new["pages"]) == (old["documents"], old["pages"]),
            "upgrade keeps stored page text": new["page_text_sha"] == old["page_text_sha"],
            "unique target constraint present": "uq_document_links_target" in new["link_table_sql"],
            "three cascading foreign keys": sorted(f[0] for f in new["fk"]) == ["daily_reports", "documents", "wells"]
                and all(f[3] == "CASCADE" for f in new["fk"]),
            "links created and audited": (new["links"], new["link_audits"]) == (3, 3),
            "no FK violations after linking": new["fk_check"] == [],
            "integrity ok after linking": new["integrity"] == "ok",
            "re-open is idempotent (schema)": new["reopen_schema_unchanged"],
            "re-open is idempotent (rows)": new["reopen_rows_unchanged"],
            "old build lists all documents": old2["documents_listed"] == old["documents"],
            "old build still searches": old2["search_hits"] >= 1,
            "old report delete removes its link": (old2["links_start"], old2["links_after_report_delete"]) == (3, 2),
            "old document delete removes its link": old2["links_after_document_delete"] == 1,
            "old well delete removes the rest": old2["links_after_well_delete"] == 0,
            "documents survive well delete": old2["documents_left"] == old["documents"] - 1,
            "no orphans after old deletes": old2["fk_check"] == [],
            "integrity ok after old deletes": old2["integrity"] == "ok",
        }
        result["checks"] = checks
        result["passed"] = all(checks.values())
        text = json.dumps(result, indent=2, default=str)
        if args.json:
            Path(args.json).write_text(text, encoding="utf-8")
        for name, ok in checks.items():
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
        print(f"{sum(checks.values())}/{len(checks)} checks passed (old {result['old_ref'][:7]}, "
              f"new {result['new_ref'][:7]})")
        return 0 if result["passed"] else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
