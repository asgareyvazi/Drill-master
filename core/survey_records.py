"""Survey domain preparation shared by manual edits and DDR persistence.

Only the established TrajectoryCalculator performs engineering calculations.
Missing angles are reviewable source measurements, never invented zeroes.
"""
from core.value_normalizer import ValueNormalizer
from core.canonical_mapper import review_item
from core.engineering.engines.trajectory import TrajectoryCalculator

DERIVED_FIELDS = ("tvd", "north", "east", "vs", "hd", "dls")


def prepare_surveys(records):
    accepted, issues, seen = [], [], set()
    rejected = 0
    for index, source in enumerate(records, 1):
        location = dict(source.get("_source_location") or {}) if isinstance(source, dict) else {}
        location.setdefault("row", index)
        problems = []
        record = dict(source) if isinstance(source, dict) else {}
        for field in ("md", "inc", "azi"):
            raw = record.get(field)
            if raw is None and record.get(field + "_source") is not None:
                raw = record[field + "_source"]
            result = ValueNormalizer.normalize(raw, "number")
            if not result.ok or (field == "md" and result.missing):
                problems.append((field, f"{field} requires a finite numeric measurement"))
            record[field] = result.value
        if record.get("md") is not None and (record["md"] < 0 or record["md"] in seen):
            problems.append(("md", "Negative or duplicate measured depth"))
        if record.get("inc") is not None and not 0 <= record["inc"] <= 180:
            problems.append(("inc", "Inclination must be between 0 and 180 degrees"))
        if problems:
            rejected += 1
            for field, reason in problems:
                issues.append(review_item(field=f"survey.{field}", entity="survey_points", original_value=source,
                                          location=location, reason=reason, status="INVALID_SOURCE", decision="REJECT").to_dict())
            continue
        seen.add(record["md"])
        missing = [field for field in ("inc", "azi") if record[field] is None]
        if missing:
            issues.append(review_item(field="survey." + "/".join(missing), entity="survey_points", original_value=source,
                                      location=location, reason="Missing directional measurement; station retained with NULL angle; calculation unavailable").to_dict())
        # Derived fields are recalculated, not used as directional inputs.
        for field in DERIVED_FIELDS:
            record[field] = None
        accepted.append(record)
    accepted.sort(key=lambda row: row["md"])
    complete = [row for row in accepted if row["inc"] is not None and row["azi"] is not None]
    if complete:
        calculated = TrajectoryCalculator.calculate(complete)
        for source, derived in zip(complete, calculated):
            for field in DERIVED_FIELDS:
                source[field] = derived[field]
    return accepted, issues, rejected


def plot_series(records):
    """Presentation data uses only real stations with calculated coordinates."""
    import math
    def finite(record):
        try:
            return all(math.isfinite(float(record.get(k))) for k in ("md", "inc", "azi", *DERIVED_FIELDS))
        except (ValueError, TypeError, OverflowError):
            return False
    usable = [r for r in records if isinstance(r, dict) and finite(r)]
    return {key: [r[key] for r in usable] for key in ("md", "north", "east", "tvd", "hd")}
