# ui/helper.py - فقط redirect به utils.py
"""
⚠️ این فایل deprecated است.
لطفاً از ui.utils استفاده کنید.
"""
from ui.utils import (
    make_scrollable,
    create_styled_button,
    show_success_message,
    show_error_message,
    show_warning_message,
    center_on_screen,
)

__all__ = [
    'make_scrollable',
    'create_styled_button',
    'show_success_message',
    'show_error_message',
    'show_warning_message',
    'center_on_screen',
]