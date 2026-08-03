# ui/utils.py - نسخه یکپارچه (جایگزین هر دو فایل قبلی)
"""
UI Utilities - توابع کمکی یکپارچه برای رابط کاربری
جایگزین ui/helper.py و ui/utils.py قبلی
"""
from PySide6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QPushButton,
    QMessageBox, QApplication
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont
import logging

logger = logging.getLogger(__name__)


# ==================== Decorator ====================

def make_scrollable(widget_class):
    class ScrollableWidget(QScrollArea):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self.setWidgetResizable(True)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.setFrameShape(QScrollArea.NoFrame)
            
            # ✅ ساده‌ترین روش - بدون object.__setattr__
            self._inner = widget_class(*args, **kwargs)
            self.setWidget(self._inner)

        def __getattr__(self, name):
            # جلوگیری از infinite loop
            if name == '_inner':
                raise AttributeError(name)
            try:
                return getattr(self._inner, name)
            except AttributeError:
                raise AttributeError(
                    f"'{type(self).__name__}' has no attribute '{name}'"
                )

    ScrollableWidget.__name__ = f"Scrollable{widget_class.__name__}"
    ScrollableWidget.__qualname__ = f"Scrollable{widget_class.__qualname__}"
    return ScrollableWidget
            

# ==================== Button Helpers ====================

def create_styled_button(
    text: str,
    color: str = "#0078d4",
    icon=None,
    tooltip: str = "",
    size: str = "normal"
) -> QPushButton:
    """
    ایجاد دکمه با استایل یکپارچه.
    
    Args:
        text: متن دکمه
        color: رنگ پس‌زمینه (hex)
        icon: آیکون (اختیاری)
        tooltip: راهنما (اختیاری)
        size: اندازه - "small", "normal", "large"
    """
    btn = QPushButton(text)

    if icon:
        btn.setIcon(QIcon(icon))

    # محاسبه رنگ hover (تیره‌تر از رنگ اصلی)
    hover_color = _darken_color(color, 20)
    pressed_color = _darken_color(color, 40)

    # padding بر اساس size
    padding_map = {
        "small": "4px 10px",
        "normal": "8px 16px",
        "large": "12px 24px",
    }
    font_size_map = {
        "small": "10px",
        "normal": "11px",
        "large": "13px",
    }
    padding = padding_map.get(size, "8px 16px")
    font_size = font_size_map.get(size, "11px")

    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {color};
            color: white;
            border: 1px solid {color};
            padding: {padding};
            border-radius: 4px;
            font-weight: bold;
            font-size: {font_size};
        }}
        QPushButton:hover {{
            background-color: {hover_color};
            border-color: {hover_color};
        }}
        QPushButton:pressed {{
            background-color: {pressed_color};
            border-color: {pressed_color};
        }}
        QPushButton:disabled {{
            background-color: #6c757d;
            border-color: #6c757d;
            color: #ccc;
        }}
    """)

    if tooltip:
        btn.setToolTip(tooltip)

    return btn


def _darken_color(hex_color: str, amount: int = 20) -> str:
    """رنگ hex را تیره‌تر می‌کند."""
    try:
        hex_color = hex_color.lstrip('#')
        r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        r = max(0, r - amount)
        g = max(0, g - amount)
        b = max(0, b - amount)
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return hex_color


# ==================== Message Helpers ====================

def show_success_message(parent, message: str, title: str = "✅ Success"):
    """نمایش پیام موفقیت."""
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Information)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.setStandardButtons(QMessageBox.Ok)
    msg_box.exec()


def show_error_message(parent, message: str, title: str = "❌ Error"):
    """نمایش پیام خطا."""
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Critical)
    msg_box.setWindowTitle(title)
    msg_box.setText(str(message))
    msg_box.setStandardButtons(QMessageBox.Ok)
    msg_box.exec()


def show_warning_message(parent, message: str, title: str = "⚠️ Warning"):
    """نمایش پیام هشدار."""
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Warning)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.setStandardButtons(QMessageBox.Ok)
    msg_box.exec()


def show_question(
    parent,
    message: str,
    title: str = "❓ Confirm"
) -> bool:
    """نمایش پیام تأیید - True اگر Yes انتخاب شود."""
    reply = QMessageBox.question(
        parent, title, message,
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )
    return reply == QMessageBox.Yes


# ==================== Window Helpers ====================

def center_on_screen(widget):
    """مرتب کردن ویجت در وسط صفحه."""
    try:
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            widget_geo = widget.frameGeometry()
            widget_geo.moveCenter(screen_geo.center())
            widget.move(widget_geo.topLeft())
    except Exception as e:
        logger.debug(f"center_on_screen error: {e}")


def set_widget_style(widget, style_type: str = "card"):
    """
    اعمال استایل‌های رایج به ویجت.
    
    style_type: "card", "panel", "header", "info"
    """
    styles = {
        "card": """
            QWidget {
                background: white;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                padding: 10px;
            }
        """,
        "panel": """
            QWidget {
                background: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 4px;
            }
        """,
        "header": """
            QWidget {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #2c3e50, stop:1 #34495e);
                border-radius: 5px;
                padding: 8px;
            }
        """,
        "info": """
            QWidget {
                background: #e8f4f8;
                border-left: 4px solid #3498db;
                border-radius: 3px;
                padding: 8px;
            }
        """,
    }
    widget.setStyleSheet(styles.get(style_type, ""))