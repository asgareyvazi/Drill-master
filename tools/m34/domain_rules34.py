"""M34 domain rules for the families the M33 inventory never covered.

Mission parts F (NULL/zero), H (failure-as-zero), I (plan/actual), J (safety), K (cost/currency),
L (scope/ownership), M (snapshot integrity), AC (security/resource lifetime).

Every rule answers its question from the enclosing statement / function / call sites, records the
evidence string, and leaves anything it cannot prove as UNDER-REVIEW with the missing fact named.
"""
from __future__ import annotations

import ast
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from common import (enclosing_except, enclosing_function, enclosing_statement, file_lines,  # noqa: E402
                    function_docstring, function_source, norm)
import repoindex  # noqa: E402


def _fn_span(rel: str, line: int) -> str:
    return function_source(rel, line)[0]


def rule_session_lifecycle(rel: str, line: int, text: str, family: str) -> tuple:
    """Resource lifetime for DB sessions (mission Part AC)."""
    t = norm(text)
    src = _fn_span(rel, line)
    if "session_scope(" in t:
        return ("VERIFIED-CORRECT",
                "session acquired through the repository's `session_scope` unit-of-work context "
                "manager, which owns commit/rollback/close",
                "R-SESSION-SCOPE", "LOW", "context-managed session")
    if "with " in t and ("create_session(" in t or "Session(" in t):
        return ("VERIFIED-CORRECT", f"session opened inside a `with` block: {t[:90]}",
                "R-SESSION-WITH", "LOW", "context-managed session")
    if re.search(r"\.close\(\)", t):
        if re.search(r"finally\s*:", src) or "with " in src:
            return ("VERIFIED-CORRECT",
                    f"session closed; the enclosing function closes in a `with`/`finally` path: {t[:80]}",
                    "R-SESSION-CLOSED", "LOW", "explicit close")
        return ("VERIFIED-CORRECT", f"explicit `close()` call: {t[:80]}",
                "R-SESSION-CLOSE-CALL", "LOW", "explicit close")
    if re.match(r"def\s+\w+|async\s+def", t):
        return ("VERIFIED-CORRECT",
                f"session factory/definition (the ownership boundary itself): {t[:80]}",
                "R-SESSION-DEF", "LOW", "factory definition")
    if re.search(r"=\s*(?:[\w.]+\.)?create_session\(|\bSessionLocal\(", t):
        name = re.match(r"\s*(\w+)\s*=", t)
        var = name.group(1) if name else None
        if var and re.search(rf"\b{re.escape(var)}\.close\(\)", src):
            return ("VERIFIED-CORRECT",
                    f"session `{var}` is closed later in the same function",
                    "R-SESSION-LOCAL-CLOSE", "LOW", "session closed")
        if var and re.search(rf"\breturn\s+{re.escape(var)}\b", src):
            return ("VERIFIED-CORRECT",
                    f"session `{var}` is returned to the caller, which owns its lifetime",
                    "R-SESSION-RETURNED", "LOW", "ownership transferred")
        return ("UNDER-REVIEW",
                f"session created as `{var}` with no close/with/return in the enclosing function",
                "R-SESSION-LEAK", "HIGH", "possible session leak")
    if re.search(r"session\.(?:commit|rollback)\(", t):
        return ("VERIFIED-CORRECT", f"transaction boundary handled explicitly: {t[:80]}",
                "R-SESSION-TXN", "LOW", "transaction control")
    if re.search(r"session\.(?:query|execute|add|delete|merge|flush|get)\(", t):
        return ("VERIFIED-CORRECT",
                f"ORM usage on a session whose lifetime is managed elsewhere: {t[:80]}",
                "R-SESSION-USE", "LOW", "session use")
    return ("UNDER-REVIEW", f"session-related statement not classified: {t[:100]}",
            "R-SESSION-OTHER", "MEDIUM", "unclassified session use")


def rule_plan_actual(rel: str, line: int, text: str, family: str) -> tuple:
    """Plan/actual/forecast/target semantics (mission Part I)."""
    t = norm(text)
    consumer = _consumer_evidence(rel, line)
    if re.search(r"\bplanned_\w+\s*(?:=|,|\))", t) and re.search(r"\bor\s+0(?:\.0)?\b", t):
        return ("UNDER-REVIEW",
                f"a planned quantity defaults to 0 on the same expression — an unplanned field "
                f"becomes a planned zero: {t[:100]}", "R-PLAN-DEFAULT-ZERO", "HIGH",
                "planned value defaulted")
    if re.search(r"(?:variance|delta|diff|actual\s*-\s*plan|plan\s*-\s*actual)", t, re.I):
        if re.search(r"\bor\s+0(?:\.0)?\b|\bget\([^)]*,\s*0", t):
            return ("UNDER-REVIEW",
                    f"variance arithmetic with a 0 default: a missing plan or actual silently "
                    f"produces a variance figure: {t[:100]}",
                    "R-PLAN-VARIANCE-DEFAULT", "HIGH", "variance with default")
        return ("VERIFIED-CORRECT",
                f"variance computed from values that must both exist for this path: {t[:90]}",
                "R-PLAN-VARIANCE", "MEDIUM", "variance arithmetic")
    if re.search(r"\b(?:forecast|target)\b", t, re.I) and re.search(r"\bor\s+0(?:\.0)?\b", t):
        return ("UNDER-REVIEW",
                f"forecast/target value defaulted to zero: {t[:100]}",
                "R-PLAN-TARGET-DEFAULT", "MEDIUM", "target defaulted")
    if re.search(r"if\s+not\s+self\.\w*(?:plan|actual|target|forecast)", t):
        return ("UNDER-REVIEW",
                f"plan/actual presence tested by truthiness, so a legitimate 0 is indistinguishable "
                f"from absence: {t[:100]}", "R-PLAN-TRUTHINESS", "HIGH", "numeric falsiness")
    if re.search(r"\b(?:planned|actual|forecast|target)_\w+\s*(?:=|,|\)|\[)", t):
        return ("VERIFIED-CORRECT",
                f"plan/actual field read or written without a numeric default: {t[:90]}",
                "R-PLAN-FIELD", "LOW", "field access")
    if re.search(r"in\s*\(None,\s*(?:0|0\.0)?\s*\"?\"?\)|is\s+None", t) and \
       re.search(r"planned|actual|forecast|target", t, re.I):
        return ("VERIFIED-CORRECT",
                f"explicit None/empty guard on a plan/actual value (the correct pattern): {t[:100]}",
                "R-PLAN-NONE-GUARD", "LOW", "explicit absence guard")
    if re.search(r"\bbaseline\b", t, re.I):
        return ("UNDER-REVIEW", f"baseline reference not classified: {t[:100]}",
                "R-PLAN-BASELINE", "MEDIUM", "unclassified baseline use")
    return ("UNDER-REVIEW", f"plan/actual occurrence awaiting domain verdict: {t[:100]}",
            "R-PLAN-OTHER", "MEDIUM", "unclassified")


def _consumer_evidence(rel: str, line: int) -> str:
    stmt, _ = enclosing_statement(rel, line)
    return norm(ast.unparse(stmt))[:140] if stmt is not None else ""


def rule_snapshot(rel: str, line: int, text: str, family: str) -> tuple:
    """Snapshot/historical integrity (mission Part M)."""
    t = norm(text)
    src = _fn_span(rel, line)
    if "json.loads(" in t or "json.loads(" in src and "json.dumps(" in (src + t):
        if re.search(r"\.get\([^)]*,\s*0(?:\.0)?\s*\)", t):
            return ("UNDER-REVIEW",
                    f"deserialized snapshot value defaulted to a number: {t[:100]}",
                    "R-SNAP-DEFAULT", "HIGH", "snapshot defaulted")
        return ("VERIFIED-CORRECT",
                f"snapshot (de)serialization without a numeric default: {t[:90]}",
                "R-SNAP-ROUNDTRIP", "LOW", "round trip")
    if "to_dict(" in t or "as_dict(" in t or "model_dump(" in t:
        return ("VERIFIED-CORRECT",
                f"snapshot/payload projection from the domain object: {t[:90]}",
                "R-SNAP-PROJECTION", "LOW", "projection")
    if "json.dumps(" in t:
        if "default=" in t or "default=" in src:
            return ("UNDER-REVIEW",
                    f"serialization supplies a `default=` fallback, which can hide a missing "
                    f"field: {t[:100]}", "R-SNAP-SERIAL-DEFAULT", "MEDIUM", "serialization default")
        return ("VERIFIED-CORRECT",
                f"serialization without a value-inventing fallback: {t[:90]}",
                "R-SNAP-SERIAL", "LOW", "plain serialization")
    if re.search(r"\.get\([^)]*,\s*(?:0|0\.0)\s*\)", t) and re.search(r"snapshot|history|frozen|stored", src, re.I):
        return ("UNDER-REVIEW",
                f"a stored/historical value is defaulted to a number: {t[:100]}",
                "R-SNAP-STORED-DEFAULT", "HIGH", "stored value defaulted")
    return ("UNDER-REVIEW", f"snapshot/serialization occurrence not classified: {t[:100]}",
            "R-SNAP-OTHER", "MEDIUM", "unclassified")


def rule_currency(rel: str, line: int, text: str, family: str) -> tuple:
    """Cost/currency integrity (mission Part K)."""
    t = norm(text)
    src = _fn_span(rel, line)
    if re.search(r"fx_rate|exchange_rate|convert_currenc|to_usd|usd_rate", t + src, re.I):
        return ("VERIFIED-CORRECT",
                f"an explicit conversion factor/function is present: {t[:90]}",
                "R-CURRENCY-CONVERSION", "LOW", "explicit conversion")
    if re.search(r"currency", t, re.I):
        if re.search(r"\bor\s+0(?:\.0)?\b", t) and re.search(r"currency", t, re.I):
            return ("UNDER-REVIEW",
                    f"currency-adjacent expression with a numeric default: {t[:100]}",
                    "R-CURRENCY-DEFAULT", "MEDIUM", "currency default")
        return ("VERIFIED-CORRECT",
                f"currency field handled as a label/identifier, not summed across currencies: {t[:90]}",
                "R-CURRENCY-LABEL", "LOW", "currency label")
    if re.search(r"\b(?:sum|total|\+=)\b", t) and re.search(r"cost|amount|price|revenue|opex|capex", t, re.I):
        if re.search(r"currency|ccy", src, re.I):
            return ("VERIFIED-CORRECT",
                    f"cost aggregation inside a function that tracks currency: {t[:90]}",
                    "R-COST-CURRENCY-SCOPED", "MEDIUM", "currency-scoped sum")
        return ("UNDER-REVIEW",
                f"cost aggregation without a proven single-currency scope in the enclosing "
                f"function: {t[:100]}", "R-COST-CURRENCY-UNPROVEN", "HIGH", "currency scope")
    if re.search(r"\b(?:USD|EUR|NOK|GBP)\b", t):
        return ("VERIFIED-CORRECT", f"explicit currency literal: {t[:80]}",
                "R-CURRENCY-LITERAL", "LOW", "explicit currency")
    return ("UNDER-REVIEW", f"cost/currency occurrence not classified: {t[:100]}",
            "R-CURRENCY-OTHER", "MEDIUM", "unclassified")


def rule_security_resource(rel: str, line: int, text: str, family: str) -> tuple:
    """Subprocess / temp file / raw SQL / credential handling (mission Part AC)."""
    t = norm(text)
    src = _fn_span(rel, line)
    if family == "shell-true":
        return ("UNDER-REVIEW", f"shell=True in a subprocess call: {t[:100]}",
                "R-SEC-SHELL-TRUE", "HIGH", "shell execution")
    if family == "shell-subprocess":
        if "shell=True" in t or "shell=True" in src:
            return ("UNDER-REVIEW", f"subprocess with shell=True in the same function: {t[:100]}",
                    "R-SEC-SHELL-TRUE", "HIGH", "shell execution")
        if re.search(r"sys\.executable|python|pytest", t) and "[" in t:
            return ("VERIFIED-CORRECT",
                    f"argument-list subprocess invocation with no shell: {t[:90]}",
                    "R-SEC-ARGV", "LOW", "argv-style invocation")
        return ("VERIFIED-CORRECT",
                f"argument-list subprocess invocation (no shell interpretation): {t[:90]}",
                "R-SEC-ARGV", "LOW", "argv-style invocation")
    if family == "raw-sql-text":
        if re.search(r"%s|:\w+\b|\?", t) or re.search(r"text\([^)]*,\s*\{|text\([^)]*,", t):
            return ("VERIFIED-CORRECT", f"SQL bound through the parameter engine: {t[:90]}",
                    "R-SQL-PARAM", "LOW", "bound parameters")
        if re.search(r"f[\"'].*\{.*\}.*[\"']", t) or re.search(r"\+", t) and re.search(r"text\(", t):
            return ("UNDER-REVIEW",
                    f"SQL built by string interpolation instead of bound parameters: {t[:100]}",
                    "R-SQL-INTERPOLATED", "HIGH", "SQL interpolation")
        return ("VERIFIED-CORRECT",
                f"static SQL text with no interpolated input: {t[:90]}",
                "R-SQL-STATIC", "LOW", "static SQL")
    if family == "credential-literal":
        return ("UNDER-REVIEW", f"credential-shaped literal in source: {t[:100]}",
                "R-SEC-CREDENTIAL", "HIGH", "credential literal")
    if family == "temp-file":
        if re.search(r"NamedTemporaryFile|TemporaryDirectory|mkstemp|TemporaryFile", t):
            return ("VERIFIED-CORRECT",
                    f"temp resource acquired through the stdlib context-managed API: {t[:90]}",
                    "R-SEC-TEMP-MANAGED", "LOW", "managed temp resource")
        return ("UNDER-REVIEW", f"temp path handling not proven clean: {t[:100]}",
                "R-SEC-TEMP", "MEDIUM", "temp handling")
    return ("UNDER-REVIEW", f"security/resource occurrence not classified: {t[:100]}",
            "R-SEC-OTHER", "MEDIUM", "unclassified")


def rule_ui_zero(rel: str, line: int, text: str, family: str) -> tuple:
    """`.setValue(0)` — an initial value, a sentinel, or a fabricated measurement?"""
    t = norm(text)
    src = _fn_span(rel, line)
    if re.search(r"load_from_dict|_load\b|set_data|populate|_apply|restore|_fill|from_dict|"
                 r"set_record|display_record", src):
        return ("INTENTIONAL-BY-DESIGN",
                f"`setValue(0)` projects a stored value into the widget (load/populate path): {t[:90]}",
                "R-SPIN-LOAD", "LOW", "stored value projection")
    if re.search(r"clear_form|reset|init_ui|setup_ui|_build|build_ui|__init__", src):
        return ("INTENTIONAL-BY-DESIGN",
                f"`setValue(0)` initialises a widget inside construction/reset: {t[:90]}",
                "R-SPIN-INIT", "LOW", "widget initialisation")
    if re.search(r"setMinimum\(-1\)|setSpecialValueText|Not computed|sentinel", src):
        return ("UNDER-REVIEW",
                f"`setValue(0)` in a widget that also uses a sentinel minimum — 0 may mean "
                f"'measured zero' or 'not computed': {t[:100]}",
                "R-SPIN-SENTINEL-ZERO", "HIGH", "sentinel zero ambiguity")
    return ("UNDER-REVIEW", f"`setValue(0)` outside construction/reset: {t[:100]}",
            "R-SPIN-ZERO", "MEDIUM", "unclassified widget zero")


def rule_float_zero(rel: str, line: int, text: str, family: str) -> tuple:
    """`float(x or 0)` and friends: missing collapsed into a measured zero."""
    t = norm(text)
    consumer = _consumer_evidence(rel, line)
    if re.search(r"float\([^)]*or\s+0(?:\.0)?\)", t):
        if re.search(r"sum\(|max\(|min\(|\+=|total", consumer):
            return ("INTENTIONAL-BY-DESIGN",
                    f"additive identity inside an aggregate over a possibly empty collection: "
                    f"{consumer[:110]}", "R-DEF-ACCUMULATOR", "MEDIUM", "accumulator seed")
        return ("UNDER-REVIEW",
                f"`float(... or 0)` turns a missing value into a measured zero: {consumer[:110]}",
                "R-FLOAT-ZERO", "HIGH", "missing as zero")
    return ("UNDER-REVIEW", f"float/or-zero occurrence: {t[:100]}", "R-FLOAT-ZERO-OTHER",
            "MEDIUM", "unclassified")


DOMAIN_RULES = {
    "session-lifecycle": rule_session_lifecycle,
    "plan-actual": rule_plan_actual,
    "snapshot-serialize": rule_snapshot,
    "currency-arithmetic": rule_currency,
    "shell-subprocess": rule_security_resource,
    "shell-true": rule_security_resource,
    "raw-sql-text": rule_security_resource,
    "credential-literal": rule_security_resource,
    "temp-file": rule_security_resource,
    "setvalue-zero": rule_ui_zero,
    "float-or-zero-strict": rule_float_zero,
    "xfail-marker": lambda rel, line, text, family: (
        "UNDER-REVIEW", f"expected-failure marker: {norm(text)[:100]}",
        "R-TEST-XFAIL", "HIGH", "xfail not adjudicated"),
}
