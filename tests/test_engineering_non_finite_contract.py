"""Non-finite inputs never become silent engineering numbers (M43 Phase 6).

Every public numeric entry point of core/engineering/engines is called at a
finite base point, then with one argument replaced by NaN or +inf. The call
must raise, or return a result that carries a failure/warning flag. A finite
value returned for a NaN/inf input is a silent substitution; non-finite output
is propagation. Both fail, except for the reasoned allowlist below.
"""
import inspect
import importlib
import math

import pytest

MODULES = ("anti_collision", "bit_performance", "casing", "cement", "fishing", "mse",
           "mud_volume", "torque_drag", "well_control")

ALLOWED = {
    # Legacy float wrappers documented as "0 on invalid input"; only tests call them.
    # The W13 UI uses the structured calc_*_result path, which fails visibly.
    "fishing:calculate_free_point": "legacy float API, 0 on invalid input",
    "fishing:calculate_string_stretch": "legacy float API, 0 on invalid input",
    "fishing:calculate_backoff_depth": "legacy float API, 0 on invalid input",
    # Internal API 5C3 helper; its only caller (collapse_combined) validates both
    # inputs with require_number/optional_number before calling it.
    "casing:CasingEngine.fyax": "inputs validated by its only caller",
}


def _finite(value):
    if isinstance(value, bool) or value is None:
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite(v) for v in value)
    if hasattr(value, "__dict__"):
        return _finite(vars(value))
    return True


def _flagged(value):
    """True only when the result itself reports a problem (not merely has the fields)."""
    if hasattr(value, "success") and hasattr(value, "validation_status"):  # EngineeringResult
        return (value.success is False or value.validation_status != "ok"
                or bool(value.warnings) or bool(value.error))
    if isinstance(value, dict):
        if value.get("success") is False or value.get("valid") is False or value.get("ok") is False:
            return True
        if any(value.get(key) for key in ("error", "errors", "warning", "warnings")):
            return True
        status = str(value.get("status", value.get("validation_status", ""))).lower()
        return status in {"error", "invalid", "warning", "failed", "missing_input", "unsupported"}
    return False


def _entry_points():
    for name in MODULES:
        module = importlib.import_module(f"core.engineering.engines.{name}")
        for attr, obj in vars(module).items():
            if inspect.isclass(obj) and obj.__module__ == module.__name__:
                for method, raw in vars(obj).items():
                    if not method.startswith("_") and isinstance(raw, (staticmethod, classmethod)):
                        yield f"{name}:{attr}.{method}", getattr(obj, method)
            elif inspect.isfunction(obj) and obj.__module__ == module.__name__ and not attr.startswith("_"):
                yield f"{name}:{attr}", obj


def _numeric_cases():
    cases = []
    for label, func in _entry_points():
        required = [p for p in inspect.signature(func).parameters.values()
                    if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY) and p.default is inspect.Parameter.empty]
        if not required or any(p.annotation not in (float, int, "float", "int", inspect.Parameter.empty)
                               for p in required):
            continue
        base = {p.name: 10.0 for p in required}
        try:
            if not _finite(func(**base)):
                continue
        except Exception:
            continue  # 10.0 everywhere is not a valid point for this calculation
        cases.append((label, func, base))
    return cases


CASES = _numeric_cases()


def test_probe_reaches_a_meaningful_population():
    assert len(CASES) >= 30, [label for label, _f, _b in CASES]


@pytest.mark.parametrize("label,func,base", CASES, ids=[c[0] for c in CASES])
def test_non_finite_input_is_rejected_or_flagged(label, func, base):
    if label in ALLOWED:
        return  # reasoned exception, see ALLOWED
    silent = []
    for name in base:
        for bad in (float("nan"), float("inf")):
            args = dict(base, **{name: bad})
            try:
                result = func(**args)
            except Exception:
                continue
            if not _finite(result) or not _flagged(result):
                silent.append(f"{name}={bad}")
    assert silent == [], f"{label} accepted non-finite input silently: {silent}"


def test_allowlist_entries_still_exist():
    labels = {label for label, _f in _entry_points()}
    assert set(ALLOWED) <= labels, set(ALLOWED) - labels
