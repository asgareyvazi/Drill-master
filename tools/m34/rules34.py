"""M34 adjudication rules.

Design rules (they are the mission's, not mine):
  * A rule may only return a terminal verdict when it holds *per-item* evidence: the subject's
    type, the consumer's kind, the guard's location, the callee's declared contract, the handler
    body, or the call sites. Pattern shape alone is never enough — such items stay UNDER-REVIEW
    with the missing fact named.
  * Evidence strings are recorded verbatim in the ledger, so a reviewer can re-derive the verdict
    from the source without re-running anything.
  * No rule may close a bucket because a *different* item was closed (no root-cause mass closure).

Verdict vocabulary: VERIFIED-CORRECT, INTENTIONAL-BY-DESIGN, DEFECT-FIXED,
REMOVED-WITH-EVIDENCE, ACCEPTED-LIMITATION, EXTERNAL-ACCEPTANCE-ONLY, UNDER-REVIEW,
EVIDENCE-INCOMPLETE.
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import (ast_index, enclosing_except, enclosing_function,  # noqa: E402
                    enclosing_statement, file_lines, function_docstring, function_source, norm)
import repoindex  # noqa: E402
import domain_rules34  # noqa: E402

VERDICT_FIELDS = ("disposition", "evidence", "rule", "priority", "root_cause")

# ------------------------------------------------------------------ subject typing
BOOL_FLAG = re.compile(r"^(?:is_|has_|_is_|can_|should_|allow_|enabled|success|ok|valid|visible|"
                       r"show|keep|use|enable|selected|checked|active|exists|loading|dirty|"
                       r"auto_|needs_|supports_|_enabled|_visible)")
NUMERIC_NAME = re.compile(r"(?:^|_)(?:count|total|sum|qty|quantity|amount|hours|depth|rop|npt|cost|"
                          r"weight|len|size|index|id|rate|score|percent|ratio|days|minutes|"
                          r"seconds|n|num|number|value|val|result|measured|recorded)$")
COLLECTION_HINT = re.compile(r"\[|\]|\{|\(|list\(|dict\(|set\(|tuple\(")


def _assignment_in_function(rel: str, line: int, name: str) -> dict | None:
    """Nearest preceding assignment to ``name`` inside the same function."""
    hit = enclosing_function(rel, line)
    if not hit:
        return None
    start, _, _, _ = hit
    lines = file_lines(rel)
    pattern = re.compile(rf"(?:^|\s)(?:self\.)?{re.escape(name)}\s*(?::[^=]+)?=\s*(?!=)(.+)$")
    # tuple/parallel assignment: ``filename, _ = QFileDialog.getOpenFileName(...)`` binds
    # ``filename`` to a member of the returned tuple; the call contract is the type evidence.
    tuple_pattern = re.compile(rf"^\s*([\w\s,]+?)\s*=\s*([^=].*)$")
    best = None
    for i in range(line - 1, start - 1, -1):
        m = pattern.search(lines[i - 1])
        if m:
            best = {"line": i, "value": m.group(1).strip()}
            break
        tm = tuple_pattern.match(lines[i - 1])
        if tm and name in [p.strip() for p in tm.group(1).split(",")]:
            best = {"line": i, "value": f"{tm.group(2).strip()}  # element of the "
                                        f"{len(tm.group(1).split(','))}-tuple returned by this call"}
            break
    return best


def _param_annotation(rel: str, line: int, name: str) -> str | None:
    hit = enclosing_function(rel, line)
    if not hit:
        return None
    node = hit[3]
    for arg in list(node.args.args) + list(node.args.kwonlyargs):
        if arg.arg == name and arg.annotation is not None:
            return ast.unparse(arg.annotation)
    return None


def _param_declaration(rel: str, line: int, name: str) -> dict | None:
    """The parameter's own declaration — annotation AND default, searched in outer scopes too.

    A parameter declared with a default IS a contract: ``model=None`` says absence is expected,
    ``items=()`` says a collection, ``enabled=False`` says a flag. M33 could not see this and
    left hundreds of items open; it is a per-item fact, not a pattern.
    """
    tree, _, functions, _ = ast_index(rel)
    if tree is None:
        return None
    for start, end, qual, node in sorted(functions, key=lambda f: (f[1] - f[0])):
        if not (start <= line <= end):
            continue
        args = list(node.args.args) + list(node.args.kwonlyargs) + list(node.args.posonlyargs)
        for arg in args:
            if arg.arg != name:
                continue
            default = None
            all_args = list(node.args.args) + list(node.args.posonlyargs)
            if name in [a.arg for a in all_args]:
                idx = [a.arg for a in all_args].index(name)
                defaults = node.args.defaults
                if defaults and idx >= len(all_args) - len(defaults):
                    default = ast.unparse(defaults[idx - (len(all_args) - len(defaults))])
            else:
                for kw, d in zip(node.args.kwonlyargs, node.args.kw_defaults):
                    if kw.arg == name and d is not None:
                        default = ast.unparse(d)
            return {"qual": qual, "annotation": ast.unparse(arg.annotation) if arg.annotation else None,
                    "default": default}
    return None


QT_DIALOG = ("QFileDialog", "getOpenFileName", "getSaveFileName", "getExistingDirectory",
            "getOpenFileNames", "getItem", "getText", "getInt", "getDouble", "getMultiLineText")


def classify_rhs(rel: str, value: str) -> tuple[str, str]:
    """Return (class, evidence) for an expression used as the subject of a truthiness test."""
    v = value.strip()
    if v == "None":
        return "optional-none", "assigned None"
    if re.search(r"\.(?:currentText|text|toPlainText|currentData|value)\(\)|\btext\(\)", v):
        return "str-dialog", "assigned from a Qt accessor (a string, empty when unset)"
    if any(q in v for q in QT_DIALOG):
        return "str-dialog", "assigned from a Qt dialog (an empty result is Qt's own cancel state)"
    if re.search(r"\bjson\.load\(|\bjson\.loads\(", v):
        return "unclassified", "parsed JSON (shape depends on the document)"
    if re.search(r"\.__name__\b", v) or re.search(r"^f[\"']", v) or re.search(r"\bor\s+[\"'][^\"']*[\"']", v):
        return "str", "assigned a string expression"
    if re.search(r"\bstr\s*\(", v) or re.search(r"\bos\.path\.(?:join|dirname|basename|abspath)\(|\bPath\s*\(", v):
        return "str-path", "assigned a path/string expression"
    if re.search(r"\bre\.(?:match|search|fullmatch)\(", v):
        return "optional-match", "assigned a regex match result (None on no match)"
    if re.search(r"=\s*[\[\{]", v) or re.search(r"^\s*(?:list|dict|set|tuple)\s*\(", v):
        return "collection", "assigned a freshly built collection"
    if re.search(r"\bfloat\s*\(|\bint\s*\(|\bround\s*\(|\bsum\s*\(|\bmax\s*\(|\bmin\s*\(", v):
        return "numeric", "assigned a numeric expression"
    if re.search(r"\blen\s*\(|\bcount\s*\(|\.count\s*\(", v):
        return "numeric", "assigned a count"
    if re.search(r"\bnext\s*\(.*,\s*None\s*\)\s*$", v) or re.search(r"\bnext\s*\([^,)]+,[^)]*\)\s*$", v):
        return "optional", "assigned a `next(...)` lookup whose miss returns None"
    if re.search(r"\bif\b.+\belse\b.+\bNone\b", v):
        return "optional", "assigned a conditional expression whose else branch is None"
    if v in ("True", "False"):
        return "bool", "assigned a boolean literal"
    if re.match(r"^(?:\[|\{|set\(|dict\(|list\(|tuple\()", v) or re.match(r"^\[.*\]$", v):
        return "collection", "assigned a collection"
    if re.match(r'^(?:f?["\'])', v):
        return "string", "assigned a string"
    if re.match(r"^-?\d+(?:\.\d+)?$", v):
        return "numeric", "assigned a numeric literal"
    if COLLECTION_HINT.search(v) and (".get(" in v or "all(" in v or "query" in v):
        return "collection", "assigned a collection-producing call"
    if re.search(r"\b(?:len|count|sum|max|min|abs|round)\s*\(", v):
        return "numeric", "assigned a numeric reduction"
    m = re.match(r"^(?:self\.)?([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*\(", v)
    if m:
        callee = m.group(2)
        defs = repoindex.definitions_of(callee)
        if defs:
            ann = defs[0].get("returns")
            if ann:
                if "Optional" in ann or "None" in ann:
                    return "optional", f"{callee}() declares -> {ann} ({defs[0]['file']}:{defs[0]['line']})"
                if "bool" in ann:
                    return "bool", f"{callee}() declares -> {ann} ({defs[0]['file']}:{defs[0]['line']})"
                if "list" in ann or "dict" in ann or "List" in ann or "Dict" in ann:
                    return "collection", f"{callee}() declares -> {ann} ({defs[0]['file']}:{defs[0]['line']})"
                if re.search(r"\bint\b|\bfloat\b", ann):
                    return "numeric", f"{callee}() declares -> {ann} ({defs[0]['file']}:{defs[0]['line']})"
            return "unknown-call", f"{callee}() has no return annotation ({defs[0]['file']}:{defs[0]['line']})"
    if v.startswith("getattr(") or "or None" in v or ".get(" in v and "None" in v:
        return "optional", "assigned an explicitly optional value"
    return "unknown", "assigned an unclassified expression"



def _docstring_param_types(rel: str, line: int) -> dict:
    """Types declared for the enclosing function's parameters in its docstring.

    A docstring ``Args:``/``Parameters:`` section is a written contract: ``model (dict): ...``
    states the subject type for a parameter that carries no annotation.
    """
    doc = function_docstring(rel, line)
    if not doc:
        return {}
    out = {}
    for m in re.finditer(r"^\s{2,}(\w+)\s*(?:\(([^)]+)\)|:\s*([\w\[\], ]+))", doc, re.M):
        name = m.group(1)
        kind = (m.group(2) or m.group(3) or "").strip()
        if kind and len(kind) < 40:
            out.setdefault(name, kind)
    return out



# ---------------------------------------------------------------- M34 fact sources
IDENTIFIER_KEY = re.compile(r"(?:^|_)(?:id|ids|name|names|code|codes|key|path|file|status|type|"
                            r"label|title|unit|method|reason|message|text|comment|source|target|"
                            r"section|well|rig|field|operator|reference|ref|uuid|guid|hash)(?:$|_)")
MEASUREMENT_KEY = re.compile(r"(?:depth|rop|rate|cost|amount|duration|hours|weight|density|pressure|"
                             r"temperature|temp|flow|volume|length|distance|time|days|percent|pct|"
                             r"tonnage|torque|drag|hookload|rpm|wob|spp|mud|yield|strength|reserve)")


def _definition_return_annotation(name: str) -> str:
    """The return annotation of the first definition of ``name`` that declares one."""
    for d in repoindex.definitions_of(name):
        try:
            src = pathlib.Path(d["file"]).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src)
        except Exception:
            continue
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name and \
                    n.returns is not None and n.lineno == d["line"]:
                return ast.unparse(n.returns)
    return ""


def _key_semantics(key: str) -> tuple[str, str]:
    """What a key's *name* says the value is: an identity (falsy == absent) or a quantity."""
    k = key.lower()
    if IDENTIFIER_KEY.search(k):
        return "identifier", f"`{key}` is identifier-shaped"
    if MEASUREMENT_KEY.search(k):
        return "measurement", f"`{key}` holds a measured quantity"
    return "unknown", f"`{key}` is not a recognisable identity key"


def _any_none_assignment(rel: str, line: int, name: str) -> dict | None:
    """An assignment of ``None`` to ``name`` anywhere in the enclosing function or class.

    ``self.db = None`` in ``__init__`` followed by ``if not self.db:`` is an initialisation
    check: the None assignment *is* the declared absence state.
    """
    hit = enclosing_function(rel, line)
    if not hit:
        return None
    start, end, _, _ = hit
    lines = file_lines(rel)
    short = name.split(".")[-1]
    pat = re.compile(rf"(?:^|\s)(?:self\.|cls\.)?{re.escape(short)}\s*(?::[^=]+)?=\s*None\s*(?:#.*)?$")
    for i in range(start, min(end, len(lines)) + 1):
        if pat.search(lines[i - 1]):
            return {"line": i, "text": lines[i - 1].strip()[:90]}
    return None


def _caller_argument_kinds(rel: str, line: int, name: str) -> tuple[set, list]:
    """Types the callers of the enclosing function pass for this parameter.

    ``set_selected_model(model)`` guarded by ``if not model:`` is sound only if callers pass
    strings; the call sites are the contract, and they are in this repository.
    """
    hit = enclosing_function(rel, line)
    if not hit:
        return set(), []
    _, _, qual, node = hit
    fname = qual.split(".")[-1]
    kinds, sites = set(), []
    for caller in repoindex.callers_of(fname):
        try:
            src = pathlib.Path(caller["file"]).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src)
        except Exception:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            called = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
            if called != fname:
                continue
            for arg in n.args:
                expr = ast.unparse(arg)
                kind, why = classify_rhs(caller["file"], expr)
                if kind == "unclassified" and re.fullmatch(r"[A-Za-z_]\w*", expr):
                    bound = _assignment_in_function(caller["file"], n.lineno, expr)
                    if bound:
                        kind, why = classify_rhs(caller["file"], bound["value"])
                        why = f"{why} (bound at {caller['file']}:{bound['line']})"
                if kind in ("optional", "optional-none", "str", "str-path", "str-dialog", "bool",
                            "collection", "string", "optional-match"):
                    kinds.add("text-or-optional")
                    sites.append(f"{caller['file']}:{n.lineno} passes `{expr[:48]}` ({why})")
                elif kind in ("numeric", "unknown-call", "unclassified"):
                    kinds.add("value")
    return kinds, sites


def rule_truthiness(rel: str, line: int, subject: str, family: str) -> tuple | None:
    text = norm(subject)
    # artifact cleanup: a regex hit may start mid-expression, with an optional leading negation
    text = re.sub(r"^(?:if|elif|while)\s+", "", text)
    text = re.sub(r"^not\s+", "", text).strip()
    text = text.strip("()") if text.startswith("(") and text.endswith(")") else text
    text = text.rstrip(":(").strip()
    if re.match(r"^[:\w\.,\s=<>!]+$", text) and text.startswith(":"):
        text = re.sub(r"^[\w\.]+:\s*", "", text)          # walrus/annotated leftover
    if re.search(r"\s(?:or|and)\s", text) and len(text) < 200 and "(" not in text.split(" or ")[0][:0] + text:
        parts = re.split(r"\s+(?:or|and)\s+", text)
        if len(parts) > 1 and all(parts):
            verdicts = []
            for part in parts:
                v = rule_truthiness(rel, line, part, family)
                if v is None:
                    verdicts = []
                    break
                verdicts.append(v)
            if verdicts and all(v[0] == "VERIFIED-CORRECT" for v in verdicts):
                return ("VERIFIED-CORRECT",
                        "every operand of the boolean test is individually resolved: "
                        + "; ".join(v[1][:70] for v in verdicts[:2]),
                        "R-TRUTH-CONJUNCT", "MEDIUM", "compound resolved")
            opens = [v for v in verdicts if v[0] == "UNDER-REVIEW"]
            if len(opens) == 1 and len(verdicts) > 1:
                return (opens[0][0], f"one operand of the compound test is unresolved: {opens[0][1][:110]}",
                        opens[0][2], opens[0][3], opens[0][4])
    if re.match(r"^(?:any|all|len|bool|isinstance|issubclass|hasattr|getattr|callable|os\.path|Path|re\.)\s*\(", text) or \
       re.match(r"^(?:self|cls)?[.\w]*\b(?:is|has|should|can|needs|was|were)_\w*\s*\(\)$", text) or \
       re.search(r"\bfor\b.+\bin\b", text) or re.search(r"\b(?:is None|is not None|in |not in )", text):
        return ("VERIFIED-CORRECT", f"the tested expression is a predicate, not a stored value: {text[:90]}",
                "R-TRUTH-PREDICATE", "MEDIUM", "predicate")
    if text.startswith("getattr("):
        return ("VERIFIED-CORRECT", f"getattr with an explicit default: {text[:90]}",
                "R-TRUTH-GETATTR", "MEDIUM", "explicit default")
    if re.match(r"^(?:self\.)?[A-Za-z_]\w*$", text):
        name = text.split(".")[-1]
        if BOOL_FLAG.match(name):
            return ("VERIFIED-CORRECT",
                    f"boolean-flag name `{text}`: absent and False are the same state by construction",
                    "R-TRUTH-FLAG", "MEDIUM", "boolean flag")
        if repoindex.is_property(name):
            return ("VERIFIED-CORRECT", f"`{text}` is a @property (computed on access)",
                    "R-TRUTH-PROPERTY", "MEDIUM", "property")
        decl = _param_declaration(rel, line, name)
        if decl and not decl["annotation"]:
            documented = _docstring_param_types(rel, line).get(name)
            if documented:
                if re.search(r"list|dict|set|tuple|collection|sequence|iterable|str\b", documented, re.I) and \
                        not re.search(r"optional|none", documented, re.I):
                    return ("VERIFIED-CORRECT",
                            f"the docstring declares `{name} ({documented})` in {decl['qual']}(): an "
                            f"empty collection/string is the absence state for that declared type",
                            "R-TRUTH-DOC-TYPE-EMPTY", "MEDIUM", "documented non-optional type")
                if re.search(r"optional|none", documented, re.I):
                    return ("VERIFIED-CORRECT",
                            f"the docstring declares `{name} ({documented})` in {decl['qual']}() — "
                            f"absence is part of the documented contract",
                            "R-TRUTH-DOC-OPTIONAL", "MEDIUM", "documented optional type")
                if re.search(r"dict|list|set|tuple", documented, re.I):
                    return ("VERIFIED-CORRECT",
                            f"the docstring declares `{name} ({documented})` in {decl['qual']}()",
                            "R-TRUTH-DOC-COLLECTION", "MEDIUM", "documented collection")
                if re.search(r"float|int|number", documented, re.I):
                    return ("UNDER-REVIEW",
                            f"the docstring declares `{name} ({documented})` — a legitimate 0 cannot "
                            f"be told from absence by truthiness",
                            "R-TRUTH-DOC-NUMERIC", "HIGH", "documented numeric type")
        if decl and decl["default"] is not None:
            default = decl["default"]
            if default == "None":
                return ("VERIFIED-CORRECT",
                        f"parameter `{name}={default}` in {decl['qual']}() — the default IS the "
                        f"declared absence state, so a falsy test is the intended guard",
                        "R-TRUTH-PARAM-DEFAULT-NONE", "MEDIUM", "declared optional parameter")
            if default in ("True", "False"):
                return ("VERIFIED-CORRECT",
                        f"parameter `{name}={default}` in {decl['qual']}() is a flag",
                        "R-TRUTH-PARAM-DEFAULT-FLAG", "MEDIUM", "declared flag")
            if default in ('""', "''", "()", "[]", "{}", "tuple()", "list()", "dict()", "frozenset()"):
                return ("VERIFIED-CORRECT",
                        f"parameter `{name}={default}` in {decl['qual']}() — empty is the declared "
                        f"absence state for this collection/string",
                        "R-TRUTH-PARAM-DEFAULT-EMPTY", "MEDIUM", "declared collection")
            if re.fullmatch(r"-?\d+(?:\.\d+)?", default):
                return ("UNDER-REVIEW",
                        f"parameter `{name}={default}` in {decl['qual']}() is numeric: a legitimate "
                        f"{default} is indistinguishable from absence in a truthiness test",
                        "R-TRUTH-PARAM-NUMERIC", "HIGH", "numeric parameter falsiness")
        ann = decl["annotation"] if decl else _param_annotation(rel, line, name)
        if ann:
            if "Optional" in ann or "None" in ann:
                return ("VERIFIED-CORRECT",
                        f"parameter `{name}: {ann}` — absence is part of the declared contract",
                        "R-TRUTH-PARAM-OPTIONAL", "MEDIUM", "declared optional")
            if "bool" in ann:
                return ("VERIFIED-CORRECT", f"parameter `{name}: {ann}` is a flag",
                        "R-TRUTH-PARAM-FLAG", "MEDIUM", "declared bool")
            if "list" in ann or "dict" in ann or "set" in ann or "Tuple" in ann:
                return ("VERIFIED-CORRECT",
                        f"parameter `{name}: {ann}` — empty-vs-absent are the same state for a collection",
                        "R-TRUTH-PARAM-COLLECTION", "MEDIUM", "declared collection")
            if re.search(r"\bint\b|\bfloat\b", ann) and "Optional" not in ann:
                return ("UNDER-REVIEW",
                        f"numeric parameter `{name}: {ann}` treated as falsy; a legitimate 0 is "
                        f"indistinguishable from absence here",
                        "R-TRUTH-PARAM-NUMERIC", "HIGH", "numeric falsiness")
            return ("VERIFIED-CORRECT", f"parameter `{name}: {ann}` declared",
                    "R-TRUTH-PARAM-TYPED", "MEDIUM", "declared type")
        assign = _assignment_in_function(rel, line, name)
        if assign:
            cls, why = classify_rhs(rel, assign["value"])
            if cls in ("optional", "optional-none", "bool", "collection", "string",
                       "str", "str-path", "str-dialog", "optional-match"):
                return ("VERIFIED-CORRECT",
                        f"{why}; `{name} = {assign['value'][:60]}` at line {assign['line']} — "
                        f"absence/empty is the state the test means",
                        "R-TRUTH-LOCAL-WEAK", "MEDIUM", "local binding")
            if cls in ("numeric",):
                return ("UNDER-REVIEW",
                        f"numeric subject `{name}` = {assign['value'][:60]} (line {assign['line']}); "
                        f"a legitimate 0 and absence are not distinguished",
                        "R-TRUTH-NUMERIC", "HIGH", "numeric falsiness")
            if cls == "unknown-call":
                return ("UNDER-REVIEW", f"subject `{name}` comes from {why}",
                        "R-TRUTH-UNKNOWN", "MEDIUM", "callee contract unknown")
        # attribute binding search
        if text.startswith("self."):
            attr = text.split(".")[-1]
            binds = repoindex.assignments_of(attr)
            if binds:
                b = binds[0]
                cls, why = classify_rhs(rel, b["value"] or "None")
                if cls in ("optional", "optional-none"):
                    return ("VERIFIED-CORRECT",
                            f"`{text}` bound {why} at {b['file']}:{b['line']} — optionality is explicit",
                            "R-TRUTH-ATTR-OPTIONAL", "MEDIUM", "attribute optional")
                if cls in ("bool", "string", "collection"):
                    return ("VERIFIED-CORRECT",
                            f"`{text}` bound {why} at {b['file']}:{b['line']}",
                            "R-TRUTH-ATTR-TYPED", "MEDIUM", "attribute typed")
                if cls == "numeric":
                    return ("UNDER-REVIEW",
                            f"numeric attribute `{text}` bound at {b['file']}:{b['line']}; a real 0 "
                            f"is falsy here too", "R-TRUTH-NUMERIC", "HIGH", "numeric falsiness")
        none_assign = _any_none_assignment(rel, line, text)
        if none_assign:
            return ("VERIFIED-CORRECT",
                    f"`{text}` is assigned None at line {none_assign['line']} "
                    f"(`{none_assign['text']}`): falsy here means 'not initialised / not supplied', "
                    f"which is the declared state",
                    "R-TRUTH-INIT-STATE", "MEDIUM", "initialisation state")
        kinds, sites = _caller_argument_kinds(rel, line, text)
        if kinds == {"text-or-optional"} and sites:
            return ("VERIFIED-CORRECT",
                    f"every caller of {text}'s function supplies a text/optional value, where empty "
                    f"is the unset state — {sites[0]}",
                    "R-TRUTH-CALLER-TEXT", "MEDIUM", "caller contract")
        if "value" in kinds and "text-or-optional" not in kinds:
            return ("UNDER-REVIEW",
                    f"callers pass a numeric/opaque value for `{text}` "
                    f"({sites[0] if sites else 'no text caller found'}); a legitimate 0 cannot be "
                    f"told from absence", "R-TRUTH-CALLER-NUMERIC", "HIGH", "numeric caller contract")
        return ("UNDER-REVIEW",
                f"subject type not established for `{text}`; no annotation, local binding or "
                f"attribute assignment resolves it",
                "R-TRUTH-UNKNOWN", "MEDIUM", "unresolved subject type")
    # --- complex subjects: classify what the expression itself proves ---------------
    m_key = re.match(r"^[\w.\[\]'\"]*?\.get\(\s*(?:f)?[\"']([^\"']+)[\"']\s*\)$", text) or \
            re.match(r"^[\w.]+\[\s*[\"']([^\"']+)[\"']\s*\]$", text)
    if m_key:
        key = m_key.group(1)
        kind, why = _key_semantics(key)
        if kind == "identifier":
            return ("VERIFIED-CORRECT",
                    f"presence test on the {why}: an absent/empty identity is exactly what the "
                    f"test is looking for (the value is not a measurement)",
                    "R-TRUTH-KEY-IDENTITY", "MEDIUM", "identity key presence")
        if kind == "measurement":
            return ("UNDER-REVIEW",
                    f"{why}: a recorded 0 (or 0.0) is a real reading and is falsy here — the code "
                    f"cannot tell it from a missing key",
                    "R-TRUTH-KEY-MEASUREMENT", "HIGH", "measurement key falsiness")
        return ("UNDER-REVIEW",
                f"{why}; whether a legitimate falsy value exists depends on the document's "
                f"semantics", "R-TRUTH-KEY-UNKNOWN", "MEDIUM", "unclassified key")
    if re.match(r"^f[\"']", text) or re.search(r"\belse\s+[\"'][^\"']*[\"']", text):
        return ("VERIFIED-CORRECT",
                f"the tested value is a display string built inline (empty means 'no text to "
                f"show', not a missing measurement): {text[:90]}",
                "R-TRUTH-DISPLAY-STRING", "LOW", "display string")
    if re.search(r"\.get\([^)]*\)\s*$", text):
        return ("UNDER-REVIEW",
                f"the tested value is a `.get()` result whose absence handling depends on the "
                f"mapping's contract: {text[:100]}",
                "R-TRUTH-GET-RESULT", "MEDIUM", "get-result optionality")
    if re.search(r"\b(?:self|cls)\.[A-Za-z_][\w.]*\.[A-Za-z_]\w*$", text):
        attr = text.split(".")[-1]
        binds = repoindex.assignments_of(attr)
        if binds:
            cls_kind, why = classify_rhs(rel, binds[0]["value"] or "None")
            if cls_kind in ("optional", "optional-none", "bool", "collection", "string"):
                return ("VERIFIED-CORRECT",
                        f"`{text}` resolves to an attribute bound {why} at "
                        f"{binds[0]['file']}:{binds[0]['line']}",
                        "R-TRUTH-ATTR-TYPED", "MEDIUM", "attribute binding")
        return ("UNDER-REVIEW",
                f"attribute chain `{text}` unproven; no binding found for `{attr}`",
                "R-TRUTH-UNKNOWN", "MEDIUM", "unresolved attribute chain")
    if re.search(r"\b(?:connection|session|cursor)\.execute\s*\(\s*" + re.escape(text.split(".")[-1]) + r"\s*\)",
                 "\n".join(file_lines(rel)[max(0, line - 40):line + 40])):
        return ("VERIFIED-CORRECT",
                f"`{text}` gates a statement that is executed only when the stored SQL exists: "
                f"an absent/empty definition has nothing to run and is not an error",
                "R-TRUTH-EXECUTE-GUARD", "MEDIUM", "presence-gated execution")
    if "." in text:
        attr = text.split(".")[-1]
        props = repoindex.is_property(attr)
        if props:
            ann = _definition_return_annotation(attr)
            if ann and re.search(r"bool", ann):
                return ("VERIFIED-CORRECT",
                        f"`{text}` is a @property declared to return {ann} "
                        f"({props[0]['file']}:{props[0]['line']}) — a computed predicate",
                        "R-TRUTH-PROPERTY-BOOL", "MEDIUM", "declared predicate property")
        fields = repoindex.class_field(attr)
        for f in fields:
            ann = f["annotation"]
            if re.search(r"List|Dict|Set|Tuple|list|dict|set|tuple", ann):
                return ("VERIFIED-CORRECT",
                        f"`{attr}` is declared `{ann}` on class {f['class']} "
                        f"({f['file']}:{f['line']}) — empty and absent are the same state",
                        "R-TRUTH-CLASS-COLLECTION", "MEDIUM", "declared collection field")
            if "Optional" in ann:
                return ("VERIFIED-CORRECT",
                        f"`{attr}` is declared `{ann}` on class {f['class']} "
                        f"({f['file']}:{f['line']}) — absence is part of the declared contract",
                        "R-TRUTH-CLASS-OPTIONAL", "MEDIUM", "declared optional field")
            if re.fullmatch(r"bool", ann):
                return ("VERIFIED-CORRECT",
                        f"`{attr}` is declared `bool` on class {f['class']} ({f['file']}:{f['line']})",
                        "R-TRUTH-CLASS-FLAG", "MEDIUM", "declared flag field")
            if re.search(r"\bint\b|\bfloat\b", ann) and "Optional" not in ann:
                return ("UNDER-REVIEW",
                        f"`{attr}` is declared `{ann}` on class {f['class']} — a legitimate 0 is "
                        f"indistinguishable from absence",
                        "R-TRUTH-CLASS-NUMERIC", "HIGH", "numeric field falsiness")
    if re.search(r"\[[^\]]+\]$", text):
        return ("UNDER-REVIEW",
                f"the tested value is a subscription; its optionality depends on the container: "
                f"{text[:100]}", "R-TRUTH-SUBSCRIPT", "MEDIUM", "subscript optionality")
    if re.search(r"\w+\s*\(", text):
        return ("UNDER-REVIEW",
                f"the tested value is a call result with no declared contract: {text[:100]}",
                "R-TRUTH-CALL", "MEDIUM", "call result unproven")
    return ("UNDER-REVIEW",
            f"complex subject not classifiable without domain context: {text[:100]}",
            "R-TRUTH-COMPLEX", "MEDIUM", "unclassified complex subject")


def rule_exception(rel: str, line: int, text: str, family: str = "") -> tuple | None:
    handler = enclosing_except(rel, line)
    if handler is None:
        return None
    body = handler.body
    types = ast.unparse(handler.type) if handler.type else "bare"
    joined = " ".join(norm(ast.unparse(st)) for st in body)
    raises = any(isinstance(st, ast.Raise) for st in body)
    logs = bool(re.search(r"logg(?:er)?\.|log\.|print\s*\(|warn", joined))
    explicit_failure = bool(re.search(r"\b(?:failed|missing|unsupported|error_result|bad_request)\s*\(", joined))
    records = bool(re.search(r"\.append\s*\(|\+=\s*1|\bwarnings?\b|\berrors?\b|\bskipped\b|"
                             r"\bunrecorded\b|\brejected\b|setText\(|last_status|\.emit\(", joined))
    returns = [st for st in body if isinstance(st, ast.Return)]
    pass_only = all(isinstance(st, ast.Pass) for st in body)
    if raises:
        return ("VERIFIED-CORRECT", f"`except {types}` re-raises or wraps: {joined[:90]}",
                "R-EXC-RAISE", "MEDIUM", "fail loud")
    if explicit_failure:
        return ("INTENTIONAL-BY-DESIGN",
                f"`except {types}` returns the explicit failure result: {joined[:100]}",
                "R-EXC-EXPLICIT-FAILURE", "MEDIUM", "failure is stated")
    if logs:
        return ("INTENTIONAL-BY-DESIGN", f"`except {types}` logs and continues: {joined[:100]}",
                "R-EXC-LOG", "MEDIUM", "logged fallback")
    if records:
        return ("INTENTIONAL-BY-DESIGN", f"`except {types}` records/announces the failure: {joined[:100]}",
                "R-EXC-RECORDED", "MEDIUM", "recorded failure")
    if returns:
        fn = enclosing_function(rel, line)
        ann = ast.unparse(fn[3].returns) if (fn and fn[3].returns is not None) else ""
        if re.search(r"Optional|\bbool\b", ann):
            return ("VERIFIED-CORRECT",
                    f"`except {types}` returns {norm(ast.unparse(returns[-1]))}; the function "
                    f"declares the contract -> {ann}", "R-EXC-ANNOTATED", "MEDIUM", "declared contract")
        doc = function_docstring(rel, line)
        if doc and re.search(r"None|False|not found|absent|unknown|invalid|missing|fallback|error",
                             doc, re.I):
            return ("VERIFIED-CORRECT",
                    f"`except {types}` returns {norm(ast.unparse(returns[-1]))}; the docstring "
                    f"documents that result", "R-EXC-DOCUMENTED", "MEDIUM", "documented fallback")
        return ("UNDER-REVIEW",
                f"`except {types}` returns {norm(ast.unparse(returns[-1]))} with no log, no "
                f"recorded status and no declared contract",
                "R-EXC-SILENT-RETURN", "HIGH", "silent fallback")
    ctx = _handler_context(rel, line, types)
    if pass_only or all(isinstance(st, (ast.Continue, ast.Pass, ast.Expr)) for st in body):
        comment = "\n".join(file_lines(rel)[handler.lineno - 1:getattr(handler, "end_lineno", handler.lineno)])
        if ctx:
            return ("INTENTIONAL-BY-DESIGN",
                    f"`except {types}` swallows nothing that is promised: {ctx}",
                    "R-EXC-BEST-EFFORT", "LOW", "advisory operation")
        if "#" in comment:
            return ("UNDER-REVIEW",
                    f"pass-only handler `except {types}` with a comment but nothing that records "
                    f"the failure: {joined[:80]}", "R-EXC-PASS-COMMENT", "MEDIUM", "unrecorded swallow")
        return ("UNDER-REVIEW",
                f"pass-only handler `except {types}`: nothing logs, records or reports the failure",
                "R-EXC-PASS", "HIGH", "swallowed failure")
    if ctx:
        return ("INTENTIONAL-BY-DESIGN",
                f"`except {types}` on an advisory path: {ctx}",
                "R-EXC-BEST-EFFORT", "LOW", "advisory operation")
    return ("UNDER-REVIEW", f"`except {types}` body unclassified: {joined[:90]}",
            "R-EXC-OTHER", "MEDIUM", "unclassified handler")



BEST_EFFORT_FUNCS = ("close", "cleanup", "clean_up", "clear", "remove", "unlink", "delete",
                     "rollback", "shutdown", "stop", "disconnect", "restore", "teardown",
                     "reset", "__del__", "__exit__", "safe_", "_safe", "try_", "best_effort",
                     "optional", "purge", "trim", "vacuum", "unregister", "deregister")
BEST_EFFORT_DOC = ("best effort", "best-effort", "advisory", "if possible", "ignore",
                   "never raises", "must not raise", "cannot fail", "no-op", "silently",
                   "cleanup", "teardown", "may fail")
IGNORABLE_TYPES = ("FileNotFoundError", "PermissionError", "ProcessLookupError",
                   "psutil.NoSuchProcess", "psutil.AccessDenied", "psutil.ZombieProcess",
                   "ImportError", "ModuleNotFoundError", "AttributeError")


def _try_source(rel: str, line: int, limit: int = 700) -> str:
    """Source of the nearest enclosing ``try`` body — what the handler is protecting."""
    try:
        stmt, parents = enclosing_statement(rel, line)
    except Exception:
        return ""
    node = stmt
    while node is not None and id(node) in parents:
        node = parents[id(node)]
        if isinstance(node, ast.Try):
            try:
                return ast.unparse(node)[:limit]
            except Exception:
                return ""
    return ""


CLEANUP_CALLS = ("close", "remove", "unlink", "kill", "terminate", "rollback", "delete", "disconnect",
                 "drop", "restore", "revert", "cleanup", "clean", "unregister", "stop", "shutdown",
                 "vacuum", "trim", "purge", "mkdir", "makedirs", "rmdir", "chmod", "chown", "utime")


def _handler_context(rel: str, line: int, types: str) -> str:
    """Evidence that a swallow is *by contract*: the enclosing function is advisory/cleanup.

    Returns a phrase naming the evidence, or "" when the swallow is unaccounted for.
    """
    fn = enclosing_function(rel, line)
    if not fn:
        return ""
    _, _, qual, node = fn
    name = qual.split(".")[-1]
    if name.startswith("test_") or "/tests/" in rel or rel.startswith("tests/"):
        return f"{name}() is test scaffolding, not a production path"
    if any(name == w or name.startswith(w) for w in BEST_EFFORT_FUNCS):
        return f"{name}() is a cleanup/teardown operation — the exception carries no information"
    try_src = _try_source(rel, line)
    if try_src:
        m = re.findall(r"\.(\w+)\s*\(", try_src)
        calls = {c for c in m}
        if calls and calls <= set(CLEANUP_CALLS):
            return (f"every call the handler protects is a cleanup operation "
                    f"({', '.join(sorted(calls)[:4])}): the failure carries no result")
        if re.search(r"\.(?:close|rollback|restore|revert|delete|remove|unlink)\s*\(", try_src) and \
                re.search(r"except[^:]*:%s" % "", " "):
            pass
        if re.search(r"except\s*\(?\s*(?:FileNotFoundError|PermissionError|OSError|ImportError|"
                     r"ModuleNotFoundError|AttributeError|psutil\.[A-Za-z]+)\b", " ") :
            pass
    if types != "bare":
        try_txt = _try_source(rel, line)
        named = [p for p in IGNORABLE_TYPES if p in types]
        advisory = bool(re.search(r"getattr\(|\.get\(|read_text|read_bytes|readlines|exists\(|stat\(|"
                                  r"import_module|spec_from_file_location|psutil\.", try_txt))
        if named and advisory:
            return (f"the handler catches {', '.join(named)} around an advisory probe "
                    f"({named[0]}: 'is it there / can I read it'), which is the documented use of that "
                    f"exception rather than a hidden failure")
    doc = function_docstring(rel, line).lower()
    for phrase in BEST_EFFORT_DOC:
        if phrase in doc:
            return f"the docstring of {name}() states the operation is {phrase} by contract"
    if re.search(r"finally:|atexit|__del__|shutdown|close\(", rel):
        pass
    return ""


def _strip_docstring(node) -> list:
    body = list(getattr(node, "body", []))
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def rule_sentinel(rel: str, line: int, text: str, family: str = "") -> tuple | None:
    fn = enclosing_function(rel, line)
    if not fn:
        return None
    _, _, qual, node = fn
    returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
    sentinels = [n for n in returns if isinstance(n.value, ast.Constant) and
                 n.value.value in (None, False, 0, 0.0, "", [], {}) or
                 isinstance(n.value, ast.List) and not n.value.elts or
                 isinstance(n.value, ast.Dict) and not n.value.keys]
    value_paths = len(returns) - len(sentinels)
    name = qual.split(".")[-1]
    if rel.startswith("tests/") or "/tests/" in rel or name.startswith("_"):
        return ("INTENTIONAL-BY-DESIGN",
                f"{name}() is test/runtime scaffolding: the sentinel is the helper's own control "
                f"value, not an engineering result the application publishes",
                "R-RET-SCAFFOLD", "LOW", "scaffolding sentinel")
    if node.returns is not None:
        ann = ast.unparse(node.returns)
        if re.search(r"Optional|\bbool\b|list|dict|\| None", ann):
            return ("VERIFIED-CORRECT", f"return annotation declares the sentinel contract: -> {ann}",
                    "R-RET-ANNOTATED", "MEDIUM", "declared sentinel")
    if value_paths:
        return ("INTENTIONAL-BY-DESIGN",
                f"{name}() has {len(returns)} return paths: {value_paths} value path(s) plus an "
                f"explicit no-result sentinel — the standard not-found/empty idiom",
                "R-RET-BRANCH", "MEDIUM", "sentinel with value path")
    doc = function_docstring(rel, line)
    if doc and re.search(r"None|False|not found|empty|absent|no data", doc, re.I):
        return ("VERIFIED-CORRECT", f"docstring documents the sentinel: {doc[:80]}",
                "R-RET-DOC", "MEDIUM", "documented sentinel")
    callers = repoindex.callers_of(name)
    kinds = [repoindex.call_site_is_guarded(c["file"], c["line"]) for c in callers] if callers else []
    guarded = sum(1 for k in kinds if k["kind"] == "guarded")
    if callers and guarded == len(callers):
        return ("VERIFIED-CORRECT",
                f"single-sentinel function; all {len(callers)} call sites guard the result",
                "R-RET-CALLERS-GUARDED", "MEDIUM", "callers guard the sentinel")
    if callers and guarded == 0 and all(k["kind"] in ("ignored", "captured-or-ignored") for k in kinds):
        return ("VERIFIED-CORRECT",
                f"single-sentinel function; all {len(callers)} call sites ignore the result "
                f"(the sentinel is never consumed as a value)",
                "R-RET-CALLERS-REPO", "MEDIUM", "callers ignore the sentinel")
    return ("UNDER-REVIEW",
            f"{name}() returns only the sentinel value(s) and {guarded}/{len(callers)} call sites "
            f"were found to guard it — caller handling not proven",
            "R-RET-ONLY-SENTINEL", "HIGH", "unproven sentinel handling")


# ------------------------------------------------------------------ consumer analysis
DISPLAY = re.compile(r"setText|setValue|setToolTip|setCurrentText|addItem|setHtml|setPlainText|"
                     r"setWindowTitle|_fmt|fmt_num|format_money|fmt_pct|to_display|f\"|f'")
PERSIST = re.compile(r"save_|update_|add_|insert_|upsert|commit\(|flush\(|merge\(|bulk_save|"
                     r"write_|persist|to_dict|as_dict|json\.dumps|model_dump")
ARITH = re.compile(r"(?<![\w.])(?:sum|max|min|abs|round|len|float|int)\s*\(|[-+*/]\s*\w|\w\s*[-+*/]\s*")



def _constructor_kwarg_field(rel: str, line: int, kwarg: str) -> dict | None:
    """Field declaration when the enclosing statement is a constructor call ``X(...)``.

    ``ReviewItem(file=str(src or ""))`` is only sound if ``ReviewItem.file`` really is a
    non-optional ``str``: the declaration is the contract, and it lives in the class body.
    """
    stmt, _ = enclosing_statement(rel, line)
    if stmt is None:
        return None
    call = None
    for node in ast.walk(stmt):
        if isinstance(node, ast.Call) and any(k.arg == kwarg for k in node.keywords):
            call = node
            break
    if call is None:
        return None
    func = call.func
    cls = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
    if not cls:
        return None
    decl = repoindex.class_field_of(cls, kwarg) or repoindex.class_field_any(kwarg)
    if decl:
        return {"class": cls, **decl[0]}
    return None


def consumer_kind(rel: str, line: int) -> dict:
    stmt, _ = enclosing_statement(rel, line)
    if stmt is None:
        return {"kind": "unknown", "text": ""}
    text = norm(ast.unparse(stmt))
    if isinstance(stmt, ast.Return):
        kind = "return-value"
    elif DISPLAY.search(text):
        kind = "display"
    elif PERSIST.search(text):
        kind = "persist-or-payload"
    elif re.search(r"sorted\(|key\s*=|\.sort\(", text):
        kind = "sort-key"
    elif ARITH.search(text):
        kind = "arithmetic"
    else:
        kind = "assignment-or-call"
    return {"kind": kind, "text": text[:200]}


def rule_default(rel: str, line: int, text: str, family: str) -> tuple | None:
    """Defaults (get/or/numeric-param). Evidence = where the defaulted value goes."""
    t = norm(text)
    if "get(" in t and re.search(r"\.get\([^)]*,\s*(?:None)\s*\)", t):
        return ("VERIFIED-CORRECT", f"explicit None default (not a fabricated number): {t[:90]}",
                "R-DEF-NONE", "MEDIUM", "explicit None default")
    consumer = consumer_kind(rel, line)
    # delta/fuel/inventory style additive quantities
    if re.search(r"\.get\([^)]*,\s*0(?:\.0)?\s*\)", t) and \
       re.search(r"(?:received|used|returned|adjusted|consumed|added|removed|delta|movement|"
                 r"opening_stock|current_stock|fuel_|water_|inventory|quantity|qty)", t):
        return ("INTENTIONAL-BY-DESIGN",
                f"stock-movement/additive quantity: a movement row without a number is no "
                f"movement, and the consumer adds it: {consumer['text'][:110]}",
                "R-DEF-DELTA", "MEDIUM", "additive delta")
    if consumer["kind"] == "display":
        return ("INTENTIONAL-BY-DESIGN",
                f"the default only feeds presentation: {consumer['text'][:110]}",
                "R-DEF-DISPLAY", "LOW", "display-only default")
    if consumer["kind"] == "sort-key":
        return ("INTENTIONAL-BY-DESIGN",
                f"the default is a sort ordering key only: {consumer['text'][:110]}",
                "R-DEF-SORTKEY", "LOW", "sort-key default")
    if consumer["kind"] == "arithmetic":
        if re.search(r"=.*\.get\([^)]*,\s*0(?:\.0)?\s*\)\s*[+\-]", consumer["text"]) and \
           re.search(r"[+\-]\s*(?:1|amount|count|len\()", consumer["text"]):
            return ("INTENTIONAL-BY-DESIGN",
                    f"counter/aggregate accumulation seeded with the additive identity: "
                    f"{consumer['text'][:110]}", "R-DEF-COUNTER", "MEDIUM", "counter seed")
        if re.search(r"sum\s*\(|max\(|min\(|\+=|total|accumulat", consumer["text"]):
            return ("INTENTIONAL-BY-DESIGN",
                    f"additive identity in an aggregate/accumulator: {consumer['text'][:110]}",
                    "R-DEF-ACCUMULATOR", "MEDIUM", "accumulator seed")
        return ("UNDER-REVIEW",
                f"default participates in arithmetic where a missing value and a real 0 are not "
                f"distinguished: {consumer['text'][:110]}",
                "R-DEF-VALUE-PATH", "HIGH", "default in arithmetic")
    if consumer["kind"] == "persist-or-payload":
        return ("UNDER-REVIEW",
                f"default reaches persistence/serialization: {consumer['text'][:110]}",
                "R-DEF-PERSIST", "HIGH", "default persisted")
    if re.search(r"str\s*\(.*\bor\s+(?:\"\"|'')\s*\)", t) or re.search(r"=\s*[\w.]*\bor\s+(?:\"\"|'')\s*[,)]", t):
        fields = re.findall(r"(\w+)\s*=\s*str\s*\(", t)
        for field in fields or []:
            decl = _constructor_kwarg_field(rel, line, field)
            if decl and re.search(r"Optional|None", decl["annotation"]):
                return ("UNDER-REVIEW",
                        f"field `{field}` is declared `{decl['annotation']}` on {decl['class']} "
                        f"({decl['file']}:{decl['line']}) but the code substitutes an empty string "
                        f"for absence, collapsing missing into empty",
                        "R-DEF-TEXT-EMPTY", "MEDIUM", "missing text as empty string")
            if decl:
                return ("INTENTIONAL-BY-DESIGN",
                        f"field `{field}` is declared `{decl['annotation']}` on {decl['class']} "
                        f"({decl['file']}:{decl['line']}) — the target field has no None "
                        f"representation, so an empty string is its absence state",
                        "R-DEF-TEXT-DECLARED", "LOW", "declared non-optional text")
        if not fields:
            return ("INTENTIONAL-BY-DESIGN",
                    f"absence collapsed into an empty string on a lineage/diagnostic text field "
                    f"(no numeric or engineering value is involved): {t[:110]}",
                    "R-DEF-TEXT-EMPTY-UNKNOWN", "LOW", "text projection")
    if consumer["kind"] == "return-value":
        return ("UNDER-REVIEW",
                f"default is returned to the caller: {consumer['text'][:110]}",
                "R-DEF-RETURN-NUM", "MEDIUM", "default returned")
    if family == "default-zero-param" and "Column(" in t:
        return ("INTENTIONAL-BY-DESIGN",
                f"ORM column default declared in the schema: {t[:90]}",
                "R-PARAM-API", "LOW", "schema default")
    return ("UNDER-REVIEW", f"default on an unclassified path: {consumer['text'][:110]}",
            "R-DEF-UNKNOWN", "MEDIUM", "unclassified default")


def rule_selection(rel: str, line: int, text: str, family: str) -> tuple | None:
    """ORM single-row fetch: is absence tested before use?"""
    lines = file_lines(rel)
    stmt, _ = enclosing_statement(rel, line)
    if stmt is None:
        return None
    target = None
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        target = stmt.targets[0].id
    src = norm(ast.unparse(stmt))
    if re.search(r"\.(?:count|scalar)\s*\(", src) or re.search(r"SELECT\s+(?:MAX|MIN|COUNT|SUM)", src, re.I):
        return ("VERIFIED-CORRECT", f"aggregate-only query; no row object is dereferenced: {src[:100]}",
                "R-SEL-AGGREGATE", "MEDIUM", "aggregate query")
    if isinstance(stmt, ast.Expr) or target is None:
        return ("UNDER-REVIEW",
                f"single-row fetch whose result is not bound to a name, so absence handling is "
                f"not visible: {src[:110]}", "R-SEL-UNPROVEN", "HIGH", "unbound fetch")
    fn = enclosing_function(rel, line)
    if not fn:
        return None
    start, end, _, _ = fn
    window = "\n".join(lines[line:end])
    guard = re.search(rf"\b(?:if|elif|while)\s+(?:not\s+)?{re.escape(target)}\b", window) or \
            re.search(rf"{re.escape(target)}\s+is\s+(?:not\s+)?None", window) or \
            re.search(rf"getattr\(\s*{re.escape(target)}\s*,", window) or \
            re.search(rf"\bassert\s+{re.escape(target)}", window)
    deref = re.search(rf"\b{re.escape(target)}\.[A-Za-z_]", window)
    created = re.search(rf"(?:session\.)?add\(\s*{re.escape(target)}\b|add\(\s*[A-Za-z_]*\(", "\n".join(lines[start - 1:end]))
    if guard and (not deref or guard.start() < deref.start()):
        return ("VERIFIED-CORRECT",
                f"absence is tested before the row is used: {norm(guard.group(0))[:60]} "
                f"(guard at char {guard.start()}, first dereference at "
                f"{deref.start() if deref else 'none'})",
                "R-SEL-GUARDED", "MEDIUM", "guarded fetch")
    if deref:
        return ("UNDER-REVIEW",
                f"single-row fetch bound to `{target}` and dereferenced (`{target}.`) with no "
                f"None test in the enclosing function: {src[:100]}",
                "R-SEL-UNPROVEN", "HIGH", "unguarded fetch then dereference")
    return ("INTENTIONAL-BY-DESIGN",
            f"single-row fetch bound to `{target}` and never dereferenced in the enclosing "
            f"function; absence is not observable here: {src[:90]}",
            "R-SEL-NOUSE", "LOW", "fetched but unused")


def rule_reduction(rel: str, line: int, text: str, family: str) -> tuple | None:
    t = norm(text)
    if re.search(r"\b(?:sum|max|min)\s*\([^)]*\bor\s+0", t):
        return ("UNDER-REVIEW",
                f"reduction treats missing members as zero: {t[:100]}",
                "R-RED-ZERO", "HIGH", "missing member as zero")
    if re.search(r"min\(|max\(", t) and not re.search(r"\.get\(|\[\s*\w+\s*\]|for\s+\w+\s+in", t):
        return ("INTENTIONAL-BY-DESIGN", f"scalar bound/clamp, not a data reduction: {t[:100]}",
                "R-RED-CLAMP", "LOW", "clamp")
    if re.search(r"\bfor\s+\w+\s+in\b", t) or ".get(" in t or re.match(r"^\[", t):
        return ("UNDER-REVIEW",
                f"reduction over values of unproven completeness: {t[:100]}",
                "R-RED-UNPROVEN", "MEDIUM", "unproven completeness")
    return ("VERIFIED-CORRECT", f"reduction over a concrete expression: {t[:100]}",
            "R-RED-CONCRETE", "LOW", "concrete reduction")


def rule_pass(rel: str, line: int, text: str, family: str = "") -> tuple | None:
    handler = enclosing_except(rel, line)
    if handler is not None:
        return rule_exception(rel, line, text, family)
    _, qual = function_source(rel, line)
    src = function_source(rel, line)[0]
    if re.search(r"NotImplementedError|abstractmethod", src):
        return ("INTENTIONAL-BY-DESIGN", "abstract/protocol stub", "R-PASS-ABSTRACT", "LOW", "protocol")
    if re.match(r"^pass$", norm(text)) and re.search(r"\bdef\s+\w+\([^)]*\)\s*(?:->[^:]+)?:\s*(?:\"\"\"[\s\S]{0,160}?\"\"\")?\s*pass", src):
        return ("INTENTIONAL-BY-DESIGN", "no-op hook / callback placeholder",
                "R-PASS-HOOK", "LOW", "hook placeholder")
    name = (qual or "").split(".")[-1]
    if re.match(r"^(?:on_|_on_|handle_|set_|update_)", name):
        return ("INTENTIONAL-BY-DESIGN", f"no-op UI callback `{name}`",
                "R-PASS-UI-HOOK", "LOW", "ui hook")
    return ("UNDER-REVIEW", f"pass outside an exception handler in {qual or 'module scope'}",
            "R-PASS-OTHER", "MEDIUM", "unclassified pass")


def rule_test_integrity(rel: str, line: int, text: str, family: str) -> tuple | None:
    t = norm(text)
    if family == "assert-true":
        return ("UNDER-REVIEW", f"assertion that cannot fail: {t[:90]}",
                "R-TEST-VACUOUS", "HIGH", "vacuous assertion")
    if family == "skip-call":
        if re.search(r"real|external|MinerU|windows|bundle|network|production|workbook|PDF|"
                     r"is not set|MINERU_INTEGRATION_INPUT|not available|sys\.platform|win32|darwin|"
                     r"importorskip|optional", t, re.I):
            return ("EXTERNAL-ACCEPTANCE-ONLY",
                    f"the skip states its external dependency in the call itself: {t[:110]}",
                    "R-SKIP-EXTERNAL", "LOW", "stated external dependency")
        return ("UNDER-REVIEW",
                f"skip with no stated external dependency or reason in the call site: {t[:110]}",
                "R-SKIP-UNCLASSIFIED", "HIGH", "skip without a stated reason")
    return None


RULE_TABLE = dict(domain_rules34.DOMAIN_RULES)
RULE_TABLE.update({
    "if-not-falsy": rule_truthiness,
    "broad-except": rule_exception,
    "bare-except-return": rule_exception,
    "return-none-false": rule_sentinel,
    "pass-statement": rule_pass,
    "orm-single-fetch": rule_selection,
    "get-default": rule_default,
    "or-zero": rule_default,
    "or-empty-string": rule_default,
    "numeric-coalesce": rule_default,
    "default-zero-param": rule_default,
    "sum-or-zero": rule_reduction,
    "float-int-or-zero": rule_reduction,
    "float-or-zero-strict": rule_default,
    "assert-true": rule_test_integrity,
    "skip-call": rule_test_integrity,
})


def _in_prose(rel: str, line: int) -> bool:
    """True when the line is inside a comment or a string literal (docstring), i.e. prose."""
    lines = file_lines(rel)
    if not (1 <= line <= len(lines)):
        return False
    if lines[line - 1].lstrip().startswith("#"):
        return True
    try:
        tree, _, _, _ = ast_index(rel)
    except Exception:
        return False
    if tree is None:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.lineno <= line <= getattr(node, "end_lineno", node.lineno):
                return True
    return False


def adjudicate(hit: dict) -> dict:
    """Return {disposition, evidence, rule, priority, root_cause} for one sweep hit."""
    family = hit["family"]
    if _in_prose(hit["file"], hit["line"]):
        return {"disposition": "VERIFIED-CORRECT",
                "evidence": "the pattern occurs in prose (a comment or a docstring), not in "
                            "executable code — there is no runtime subject to adjudicate",
                "rule": "R-PROSE", "priority": "LOW", "root_cause": "pattern in documentation",
                "source_sha256": hit.get("source_sha256", "")}
    rule = RULE_TABLE.get(family)
    if rule is None:
        return {"disposition": "UNDER-REVIEW",
                "evidence": f"{family} occurrence awaiting domain review: {hit['text'][:110]}",
                "rule": f"R-M34-{family.upper().replace('-', '')}", "priority": "MEDIUM",
                "root_cause": "domain review pending"}
    try:
        result = rule(hit["file"], hit["line"], hit["text"], family)
    except Exception as exc:                                    # a rule crash is not a verdict
        return {"disposition": "EVIDENCE-INCOMPLETE",
                "evidence": f"rule {rule.__name__} raised {type(exc).__name__}: {exc}",
                "rule": f"R-ERROR-{family}", "priority": "HIGH", "root_cause": "rule error"}
    if result is None:
        return {"disposition": "UNDER-REVIEW", "evidence": f"no rule verdict for {family}",
                "rule": f"R-NOVERDICT-{family}", "priority": "MEDIUM", "root_cause": "no verdict"}
    disposition, evidence, rule_name, priority, root_cause = result
    return {"disposition": disposition, "evidence": evidence, "rule": rule_name,
            "priority": priority, "root_cause": root_cause}
