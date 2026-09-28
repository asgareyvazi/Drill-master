import ast
import collections
import hashlib
import json
import subprocess
from pathlib import Path

root = Path.cwd()
out = root / "docs/audits/m29-evidence"
out.mkdir(parents=True, exist_ok=True)
paths = sorted(
    p
    for folder in ("core", "dialogs", "tabs", "ui")
    for p in (root / folder).rglob("*.py")
    if "__pycache__" not in p.parts
)
paths += [root / n for n in ("app.py", "main_window.py", "run.py", "verify_release.py")]


class Scan(ast.NodeVisitor):
    def __init__(self, path, source):
        self.path = path
        self.source = source
        self.stack = []
        self.rows = []
        self.lines = [line.encode("utf-8") for line in source.splitlines()]

    def segment(self, node):
        first, last = node.lineno - 1, node.end_lineno - 1
        if first == last:
            return self.lines[first][node.col_offset : node.end_col_offset].decode()
        return b"\n".join(
            [self.lines[first][node.col_offset :]]
            + self.lines[first + 1 : last]
            + [self.lines[last][: node.end_col_offset]]
        ).decode()

    def record(self, node, kind):
        self.rows.append(
            dict(
                id=f"{self.path}:{node.lineno}:{kind}",
                file=self.path,
                line=node.lineno,
                context=".".join(self.stack),
                kind=kind,
                expression=self.segment(node),
                classification=None,
                audit_status="NOT-REVIEWED",
            )
        )

    def visit_ClassDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        for default in node.args.defaults + list(node.args.kw_defaults):
            if isinstance(default, ast.Constant) and type(default.value) in (int, float):
                self.record(default, "numeric-parameter-default")
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_BoolOp(self, node):
        if isinstance(node.op, ast.Or) and any(
            isinstance(v, ast.Constant) and type(v.value) in (int, float) and v.value == 0 for v in node.values
        ):
            self.record(node, "or-zero")
        self.generic_visit(node)

    def visit_Call(self, node):
        name = (
            node.func.attr
            if isinstance(node.func, ast.Attribute)
            else node.func.id
            if isinstance(node.func, ast.Name)
            else ""
        )
        if (
            name == "get"
            and len(node.args) > 1
            and isinstance(node.args[1], ast.Constant)
            and type(node.args[1].value) in (int, float)
        ):
            self.record(node, "numeric-get-default")
        if name in ("first", "one", "one_or_none"):
            self.record(node, "selection")
        if name in ("sum", "max", "min", "mean", "avg", "std", "median"):
            self.record(node, "reduction")
        for keyword in node.keywords:
            if (
                keyword.arg == "default"
                and isinstance(keyword.value, ast.Constant)
                and type(keyword.value.value) in (int, float)
            ):
                self.record(node, "numeric-default")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        broad = node.type is None or any(
            isinstance(n, ast.Name) and n.id in ("Exception", "BaseException") for n in ast.walk(node.type)
        )
        self.record(node, "broad-exception" if broad else "typed-exception")
        self.generic_visit(node)


rows = []
manifest = []
for path in paths:
    source = path.read_text()
    rel = str(path.relative_to(root))
    manifest.append(
        dict(file=rel, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), lines=len(source.splitlines()))
    )
    visitor = Scan(rel, source)
    visitor.visit(ast.parse(source))
    rows.extend(visitor.rows)
# Apply individual expression reviews only while BOTH source and expression hashes match.
adjudications = json.loads((out / "site-adjudications.json").read_text())
source_hashes = {m["file"]: m["sha256"] for m in manifest}
for row in rows:
    for review in adjudications:
        if (
            review["file"] == row["file"]
            and review["context"] == row["context"]
            and review["kind"] == row["kind"]
            and review["source_sha256"] == source_hashes[row["file"]]
            and review["expression_sha256"] == hashlib.sha256(row["expression"].encode()).hexdigest()
        ):
            row.update(
                classification=review["classification"],
                audit_status="REVIEWED",
                reason=review["reason"],
                evidence=review["evidence"],
                exception_outcome=review["exception_outcome"],
            )
            break
(out / "risky-site-inventory.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
extra = (
    list((root / "tests").rglob("*.py"))
    + list((root / "config").rglob("*.json"))
    + list((root / "templates").glob("*.json"))
    + list((root / "packaging").glob("*"))
    + list((root / ".github/workflows").glob("*"))
)
extra += [
    root / n
    for n in (
        "pyproject.toml",
        "requirements.txt",
        "requirements-lock.txt",
        "requirements-build.txt",
        "tools/qt_headless_env.sh",
        ".github/ruff-debt-ceiling.txt",
    )
]
for name in subprocess.check_output(["git", "ls-files", "-z"], text=True).split("\0"):
    if name and not name.startswith("docs/") and not name.endswith(".md"):
        extra.append(root / name)
known = {m["file"] for m in manifest}
for path in sorted(extra):
    if path.is_file() and "__pycache__" not in path.parts and str(path.relative_to(root)) not in known:
        manifest.append(dict(file=str(path.relative_to(root)), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        known.add(str(path.relative_to(root)))
(out / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
summary = dict(
    files=len(paths),
    sites=len(rows),
    kinds=dict(collections.Counter(r["kind"] for r in rows)),
    review_status=dict(collections.Counter(r["audit_status"] for r in rows)),
    warning="Inventory completeness is not semantic adjudication. NOT-REVIEWED sites remain a repository verification blocker, not verified SAFE.",
)
(out / "inventory-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
refs = []
for line in subprocess.check_output(
    ["git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads", "refs/remotes"], text=True
).splitlines():
    name, sha = line.split()
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", name, "HEAD"]).returncode == 0
    active = name == "arena/01a0c945-drill-master" or name == "origin/arena/01a085e0-drill-master"
    refs.append(
        dict(
            ref=name,
            sha=sha,
            ancestor_of_session_head=ancestor,
            classification="ACTIVE" if active else "MERGED-SAFE-TO-DELETE" if ancestor else "UNMERGED-REVIEW-REQUIRED",
            unique_counts=subprocess.check_output(
                ["git", "rev-list", "--left-right", "--count", "HEAD..." + name], text=True
            ).strip(),
            action="RETAINED; no branch deleted",
        )
    )
(out / "branch-inventory.json").write_text(json.dumps(refs, indent=2) + "\n")
