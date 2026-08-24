"""Read-only static audit for the release gate.
It reports debt without rewriting production code or failing on legacy debt yet.
"""
import ast
from pathlib import Path


def main():
    wildcard, bare_except, duplicate_methods = [], [], []
    for path in Path(".").rglob("*.py"):
        if any(part in {".git", ".venv", "build", "dist"} for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        names = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                wildcard.append(str(path))
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                bare_except.append(f"{path}:{node.lineno}")
            if isinstance(node, ast.FunctionDef):
                names[node.name] = names.get(node.name, 0) + 1
        duplicate_methods.extend(f"{path}:{name} ({count})" for name, count in names.items() if count > 1)
    print(f"wildcard imports: {len(wildcard)}")
    print(f"bare except handlers: {len(bare_except)}")
    print(f"duplicate method names per file: {len(duplicate_methods)}")
    print("Static audit is informational until legacy cleanup phase.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
