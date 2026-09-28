# core/text_utils.py
"""Small, dependency-free text and display formatting helpers."""


def safe_str(value, default=""):
    return default if value is None else str(value)


def clean_text(value, default=""):
    """Trim and collapse whitespace in UI/imported text."""
    if value is None:
        return default
    return " ".join(str(value).split())


def wrap_text(text, width=0):
    return clean_text(text)


def wrap_html(text, width=0):
    return clean_text(text).replace("\n", "<br>") if text else ""


def safe_float(value, default=0.0):
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    try:
        return int(float(value)) if value is not None else default
    except (ValueError, TypeError):
        return default


def truncate(value, length=80, suffix="…"):
    text = safe_str(value)
    if length < 1:
        return ""
    return text if len(text) <= length else text[:max(0, length - len(suffix))] + suffix


def format_date(value, default=""):
    if value is None:
        return default
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = clean_text(value)
    return text[:10] if len(text) >= 10 and text[4] == "-" else (text or default)


def fmt_num(value, digits=1, default=None):
    """Format a number for display; an unknown value is shown as "—".

    ``default`` used to be ``0.0``, which printed a missing (NULL) engineering
    value as an explicit zero in the daily report and other HTML/UI surfaces
    ("Not recorded" in the input widget, "0.0" in the export). Callers that
    really mean "absent movement is zero" must now say so explicitly with
    ``default=0.0``; genuine unknown stays unknown.
    """
    number = safe_float(value, default)
    return "—" if number is None else f"{number:.{digits}f}"


def not_recorded_text(field: str) -> str:
    """Explicit statement for an empty report section.

    A section with no rows means "not recorded for this scope" and must never be
    readable as a zero/safe fact (missing safety record is not zero incidents).
    """
    return f"Not recorded: no {field} data was submitted for this scope."
