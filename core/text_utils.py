# core/text_utils.py
"""
Text Utilities - ابزار مرکزی مدیریت متن
"""
import textwrap
from typing import Optional

DEFAULT_LINE_WIDTH = 0  # بدون محدودیت


def wrap_text(text, width=0):
    """فقط پاکسازی - بدون wrap اجباری"""
    if not text:
        return ""
    return str(text).strip()


def wrap_html(text, width=0):
    """تبدیل newline به br برای HTML"""
    if not text:
        return ""
    return str(text).strip().replace("\n", "<br>")


def safe_str(value, default: str = "") -> str:
    """تبدیل امن به رشته"""
    if value is None:
        return default
    return str(value)


def safe_float(value, default: float = 0.0) -> float:
    """تبدیل امن به عدد"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def fmt_num(value, digits: int = 1, default: float = 0.0) -> str:
    """فرمت عددی امن"""
    v = safe_float(value, default)
    return f"{v:.{digits}f}"