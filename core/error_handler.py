# core/error_handler.py 

"""
Error Handler - مدیریت متمرکز خطاها
"""
import logging
import traceback
from functools import wraps
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
            for arg in args:
                if hasattr(arg, 'rollback'):
                    try:
                        arg.rollback()
                    except Exception:
                        pass
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

            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Unexpected Error")
            msg.setText(f"An unexpected error occurred:\n\n{error_msg}")
            msg.setDetailedText(detail)
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec()

        sys.excepthook = handle_exception
        logger.info("Global error handler installed")