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


def fmt_num(value, digits=1, default=0.0):
    return f"{safe_float(value, default):.{digits}f}"
