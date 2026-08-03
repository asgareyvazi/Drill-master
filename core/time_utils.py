# core/time_utils.py
"""
Time utilities for handling 24:00 times in daily reports
"""
from datetime import time
from PySide6.QtCore import QTime, Qt, Signal
from PySide6.QtWidgets import QLineEdit, QStyledItemDelegate, QWidget, QHBoxLayout, QLabel
from PySide6.QtGui import QValidator, QIntValidator


class TimeLineEdit(QLineEdit):
    """LineEdit سفارشی برای وارد کردن زمان با پشتیبانی از 24:00"""
    
    timeChanged = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("HH:MM")
        self.setMaxLength(5)
        self.setAlignment(Qt.AlignCenter)
        
        self._hour = 0
        self._minute = 0
        self._is_2400 = False
        
        # تنظیم validator
        self.setValidator(TimeValidator(self))
        
        # اتصالات
        self.textEdited.connect(self._on_text_edited)
        self.editingFinished.connect(self._on_editing_finished)
    
    def _on_text_edited(self, text):
        """بررسی متن وارد شده"""
        if text == "24:00":
            self._is_2400 = True
            self._hour = 24
            self._minute = 0
            self.setText("24:00")
            self.timeChanged.emit()
    
    def _on_editing_finished(self):
        """پس از اتمام ویرایش"""
        text = self.text().strip()

        if text in ("24:00", "24", "2400"):
            self._is_2400 = True
            self._hour = 24
            self._minute = 0
            self.setText("24:00")
            self.timeChanged.emit()
            return

        # تلاش برای parse با فرمت HH:MM
        if ':' in text:
            parts = text.split(':')
            if len(parts) == 2:
                try:
                    hour = int(parts[0])
                    minute = int(parts[1])
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        self._is_2400 = False
                        self._hour = hour
                        self._minute = minute
                        self.setText(f"{hour:02d}:{minute:02d}")
                        self.timeChanged.emit()
                        return
                except ValueError:
                    pass
        elif len(text) >= 2:
            try:
                hour = int(text[:2])
                minute = int(text[2:4]) if len(text) >= 4 else 0
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    self._is_2400 = False
                    self._hour = hour
                    self._minute = minute
                    self.setText(f"{hour:02d}:{minute:02d}")
                    self.timeChanged.emit()
                    return
            except ValueError:
                pass

        # اگر نامعتبر بود، مقدار قبلی را برگردان
        if self._is_2400:
            self.setText("24:00")
        else:
            self.setText(f"{self._hour:02d}:{self._minute:02d}")
    
    def get_time(self):
        """دریافت زمان به صورت (hour, minute, is_2400)"""
        return self._hour, self._minute, self._is_2400
    
    def get_display_string(self):
        """دریافت رشته نمایشی"""
        if self._is_2400:
            return "24:00"
        return f"{self._hour:02d}:{self._minute:02d}"
    
    def get_python_time(self):
        """دریافت به صورت time پایتون"""
        if self._is_2400:
            return time(0, 0)
        return time(self._hour, self._minute)
    
    def set_time(self, hour: int, minute: int = 0, is_2400: bool = False):
        """تنظیم زمان"""
        if is_2400:
            self._is_2400 = True
            self._hour = 24
            self._minute = 0
            self.setText("24:00")
        else:
            self._is_2400 = False
            self._hour = max(0, min(23, hour))
            self._minute = max(0, min(59, minute))
            self.setText(f"{self._hour:02d}:{self._minute:02d}")
        self.timeChanged.emit()
    
    def clear(self):
        """پاک کردن"""
        self._is_2400 = False
        self._hour = 0
        self._minute = 0
        self.setText("")
    
    def calculate_duration_to(self, other) -> float:
        """محاسبه اختلاف تا زمان دیگر (به ساعت)."""
        if not isinstance(other, TimeLineEdit):
            raise TypeError("other must be a TimeLineEdit")
        if self._is_2400:
            self_seconds = 24 * 3600
        else:
            self_seconds = self._hour * 3600 + self._minute * 60
        
        if other._is_2400:
            other_seconds = 24 * 3600
        else:
            other_seconds = other._hour * 3600 + other._minute * 60
        
        diff = other_seconds - self_seconds
        if diff < 0:
            diff += 24 * 3600
        
        return diff / 3600.0


class TimeValidator(QValidator):
    """Validator برای زمان"""
    
    def validate(self, input_str, pos):
        if not input_str:
            return QValidator.Intermediate, input_str, pos
        
        # بررسی 24:00
        if input_str == "24:00":
            return QValidator.Acceptable, input_str, pos
        
        # بررسی فرمت HH:mm
        if ':' in input_str:
            parts = input_str.split(':')
            if len(parts) == 2:
                try:
                    hour = int(parts[0])
                    minute = int(parts[1])
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        return QValidator.Acceptable, input_str, pos
                except ValueError:
                    pass
        
        # بررسی فرمت HHMM
        if len(input_str) >= 2 and input_str.isdigit():
            if len(input_str) <= 4:
                return QValidator.Intermediate, input_str, pos
        
        # Only plausible prefixes are intermediate. Arbitrary text such as
        # ``abc`` must be invalid rather than silently accepted.
        if input_str.isdigit() and len(input_str) <= 4:
            return QValidator.Intermediate, input_str, pos
        if input_str.isdigit() and len(input_str) == 1:
            return QValidator.Intermediate, input_str, pos
        if len(input_str) <= 5 and input_str.count(":") == 1:
            hour, minute = input_str.split(":", 1)
            if hour.isdigit() and len(hour) <= 2 and (not minute or minute.isdigit() and len(minute) <= 2):
                return QValidator.Intermediate, input_str, pos
        return QValidator.Invalid, input_str, pos
    
    def fixup(self, input_str):
        if input_str == "24:00" or input_str == "24":
            return "24:00"
        return input_str


class DrillTime:
    """کلاس ساده برای مدیریت زمان (سازگاری با کدهای قبلی)"""
    
    def __init__(self, hour: int, minute: int = 0):
        self.hour = hour
        self.minute = minute
        self.is_midnight_24 = (hour == 24 and minute == 0)
    
    @classmethod
    def from_line_edit(cls, line_edit: TimeLineEdit):
        hour, minute, is_2400 = line_edit.get_time()
        return cls(hour, minute)
    
    def to_display_string(self):
        if self.is_midnight_24:
            return "24:00"
        return f"{self.hour:02d}:{self.minute:02d}"
    
    def to_python_time(self):
        return time(self.hour if self.hour < 24 else 0, self.minute)
    
    @classmethod
    def from_string(cls, value):
        if isinstance(value, cls):
            return value
        text = str(value).strip()
        if text in {"24", "2400", "24:00"}:
            return cls(24, 0)
        parts = text.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid time: {value!r}")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Invalid time: {value!r}")
        return cls(hour, minute)

    @classmethod
    def from_python_time(cls, value):
        if not isinstance(value, time):
            raise TypeError("value must be datetime.time")
        return cls(value.hour, value.minute)

    def __sub__(self, other):
        """Return the forward elapsed duration from ``other`` to ``self``."""
        if not isinstance(other, DrillTime):
            raise TypeError("other must be DrillTime")
        self_seconds = (24 if self.hour == 24 else self.hour) * 3600 + self.minute * 60
        other_seconds = (24 if other.hour == 24 else other.hour) * 3600 + other.minute * 60
        diff = self_seconds - other_seconds
        if diff < 0:
            diff += 24 * 3600
        return diff / 3600.0