# core/error_handler.py 

"""
Error Handler - مدیریت متمرکز خطاها
"""
import logging
import traceback
from functools import wraps
from pathlib import Path
from datetime import datetime, timezone
from typing import Callable, Optional, Any

from PySide6.QtWidgets import QMessageBox, QApplication

logger = logging.getLogger(__name__)


class DrillMasterError(Exception):
    """Exception پایه برنامه."""
    def __init__(self, message: str, details: str = "", code: str = ""):
        super().__init__(message)
        self.message = message
        self.details = details
        self.code = code


class DatabaseError(DrillMasterError):
    """خطای دیتابیس."""
    pass


class ValidationError(DrillMasterError):
    """خطای اعتبارسنجی."""
    pass


class DataImportError(DrillMasterError):
    """خطای ایمپورت داده - ✅ نام تغییر کرد از ImportError"""
    pass


def safe_call(
    func: Callable = None,
    *,
    default: Any = None,
    log_error: bool = True,
    show_error: bool = False,
    error_msg: str = "",
):
    """
    Decorator برای فراخوانی امن توابع.
    """
    def decorator(f):
        if not callable(f):
            raise TypeError("safe_call expects a callable")
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                if log_error:
                    logger.error(
                        f"Error in {f.__name__}: {e}\n"
                        f"{traceback.format_exc()}"
                    )
                if show_error:
                    parent = args[0] if args else None
                    msg = error_msg or f"Error in {f.__name__}: {str(e)}"
                    if hasattr(parent, 'show_error'):
                        parent.show_error(msg)
                    else:
                        QMessageBox.warning(None, "Error", msg)
                return default
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator


def handle_db_error(func):
    """
    Decorator مخصوص عملیات دیتابیس.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"DB error in {func.__name__}: {e}")
            candidates = list(args) + list(kwargs.values())
            for arg in candidates:
                session = getattr(arg, "session", arg)
                if hasattr(session, 'rollback'):
                    try:
                        session.rollback()
                    except Exception:
                        logger.debug("Unable to rollback DB session", exc_info=True)
            raise DatabaseError(
                f"Database operation failed: {str(e)}",
                details=traceback.format_exc()
            )
    return wrapper


class GlobalErrorHandler:
    """Handler مرکزی برای exception های مدیریت نشده."""

    @staticmethod
    def setup(app):
        import sys

        def handle_exception(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return

            logger.critical(
                "Unhandled exception",
                exc_info=(exc_type, exc_value, exc_traceback)
            )

            error_msg = str(exc_value)
            detail = "".join(traceback.format_tb(exc_traceback))
            try:
                report_dir = Path.home() / ".drillmaster" / "crash_reports"
                report_dir.mkdir(parents=True, exist_ok=True)
                report = report_dir / f"crash_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.log"
                report.write_text(f"{error_msg}\n\n{detail}", encoding="utf-8")
            except Exception:
                logger.debug("Could not persist crash report", exc_info=True)

            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Unexpected Error")
            msg.setText(f"An unexpected error occurred:\n\n{error_msg}")
            msg.setDetailedText(detail)
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()

        sys.excepthook = handle_exception
        logger.info("Global error handler installed")