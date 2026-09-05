# app.py
"""
DrillMaster - Main Application
"""
import os
import sys
import logging
import logging.handlers
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMessageBox, QDialog, QSplashScreen
)
from PySide6.QtGui import (
    QFont, QPixmap, QPainter, QColor,
    QLinearGradient, QBrush
)

from PySide6.QtCore import Qt, QRect, QTimer, QEventLoop

from core.database import (
    DatabaseManager,
    bootstrap_password_for_role,
    is_production_environment,
)
from core.error_handler import GlobalErrorHandler
from core.runtime_config import (
    database_path,
    ensure_writable_directories,
    log_dir,
)
from core.version import __version__
from dialogs.bootstrap_dialog import BootstrapDialog
from dialogs.login_dialog import LoginDialog
from dialogs.startup_dialog import StartupDialog
from main_window import MainWindow

def _setup_logging() -> None:
    """Configure a rotating user-data log with a safe stderr fallback."""
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handlers = []
    try:
        target_dir = log_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            target_dir / "drillmaster.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except OSError:
        # A read-only profile must not prevent the UI from starting. The
        # warning is visible on stderr, without including configuration values.
        pass

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not root_logger.handlers:
        for handler in handlers:
            root_logger.addHandler(handler)


_setup_logging()
logger = logging.getLogger(__name__)

# ==================== App Constants ====================
class AppConfig:
    """تنظیمات برنامه"""
    APP_NAME = "DrillMaster"
    APP_VERSION = __version__
    ORGANIZATION_NAME = "DrillMaster Inc."
    
    # Timing
    SPLASH_DISPLAY_MS = 800
    BACKUP_INTERVAL_MIN = 30
    RECENT_MENU_DELAY_MS = 1000
    STARTUP_DELAY_MS = 500
    
    # UI
    DEFAULT_FONT = "Segoe UI"
    DEFAULT_FONT_SIZE = 10
    DEFAULT_STYLE = "Fusion"
    
    # Database
    DB_PATH = database_path()
    LOG_PATH = str(log_dir() / "drillmaster.log")


class DrillMasterSplash(QSplashScreen):
    """Splash Screen حرفه‌ای."""

    def __init__(self):
        pixmap = QPixmap(500, 300)
        pixmap.fill(QColor("#1e2a3a"))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # گرادیان پس‌زمینه
        gradient = QLinearGradient(0, 0, 500, 300)
        gradient.setColorAt(0, QColor("#1e2a3a"))
        gradient.setColorAt(1, QColor("#2c3e50"))
        painter.fillRect(0, 0, 500, 300, QBrush(gradient))

        # آیکون
        painter.setFont(QFont("Arial", 48))
        painter.setPen(QColor("#3498db"))
        painter.drawText(
            QRect(0, 40, 500, 80),
            Qt.AlignCenter,
            "DrillMaster"
        )

        # عنوان
        painter.setFont(QFont("Segoe UI", 28, QFont.Bold))
        painter.setPen(QColor("#ecf0f1"))
        painter.drawText(
            QRect(0, 130, 500, 50),
            Qt.AlignCenter,
            "DrillMaster"
        )

        # زیرعنوان
        painter.setFont(QFont("Segoe UI", 12))
        painter.setPen(QColor("#95a5a6"))
        painter.drawText(
            QRect(0, 185, 500, 30),
            Qt.AlignCenter,
            "Drilling Operations Management System"
        )

        # نسخه
        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor("#7f8c8d"))
        painter.drawText(
            QRect(0, 265, 500, 25),
            Qt.AlignCenter,
            f"Version {AppConfig.APP_VERSION}  |  © 2024 DrillMaster Inc."
        )

        painter.end()

        super().__init__(pixmap)
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        )

    def set_status(self, message: str):
        """به‌روزرسانی پیام وضعیت."""
        self.showMessage(
            f"  {message}",
            Qt.AlignBottom | Qt.AlignLeft,
            QColor("#3498db")
        )
        QApplication.processEvents()


class DrillMasterApp(QApplication):
    """Main application class."""

    def __init__(self, argv):
        super().__init__(argv)

        self.setApplicationName(AppConfig.APP_NAME)
        self.setApplicationVersion(AppConfig.APP_VERSION)
        self.setOrganizationName("DrillMaster Inc.")

        self.setFont(QFont("Segoe UI", 10))
        self.setStyle("Fusion")

        self.db_manager = None
        self.user = None
        self.main_window = None
        self.startup_result = None

        # The desktop application defaults to production behavior. Development
        # fixtures remain available only when the operator explicitly selects
        # DRILLMASTER_ENV=development or test.
        if not os.getenv("DRILLMASTER_ENV") and not os.getenv("DRILLMASTER_ENVIRONMENT"):
            os.environ["DRILLMASTER_ENV"] = "production"

        self.initialize()

    @staticmethod
    def _needs_first_run_bootstrap() -> bool:
        """Return whether a new file-backed desktop database needs setup."""
        import sqlite3

        path = database_path()
        if path == ":memory:":
            return False
        database = Path(path).expanduser()
        if not database.exists():
            return True
        try:
            with sqlite3.connect(str(database)) as connection:
                table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
                ).fetchone()
                if table is None:
                    return True
                return connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        except (OSError, sqlite3.DatabaseError):
            # A present but unreadable/corrupt database must go through the
            # normal fatal initialization path, not be overwritten by setup.
            return False

    def _run_first_run_bootstrap(self) -> bool:
        """Collect production credentials before the first schema bootstrap."""
        explicit_environment = (
            os.getenv("DRILLMASTER_ENV") or os.getenv("DRILLMASTER_ENVIRONMENT") or ""
        ).strip().lower()
        if explicit_environment in {"development", "dev", "test", "testing"}:
            return True
        if not self._needs_first_run_bootstrap():
            return True
        try:
            ensure_writable_directories()
            dialog = BootstrapDialog()
            if dialog.exec() != QDialog.Accepted:
                return False
            passwords = dialog.passwords()
            os.environ["DRILLMASTER_ADMIN_PASSWORD"] = passwords["admin"]
            os.environ["DRILLMASTER_USER_PASSWORD"] = passwords["engineer"]
            os.environ["DRILLMASTER_VIEWER_PASSWORD"] = passwords["viewer"]
            logger.info("First-run production bootstrap credentials collected")
            return True
        except Exception:
            logger.exception("First-run bootstrap failed")
            QMessageBox.critical(
                None,
                "First-run setup failed",
                "DrillMaster could not complete secure first-run setup. "
                "No database was initialized.",
            )
            return False

    def initialize(self):
        """Initialize application."""
        splash = DrillMasterSplash()
        splash.show()
        QApplication.processEvents()

        try:
            GlobalErrorHandler.setup(self)

            splash.set_status("Applying styles...")
            self._apply_global_stylesheet()

            splash.set_status("Checking first-run security setup...")
            if not self._run_first_run_bootstrap():
                splash.close()
                self.quit()
                return

            splash.set_status("Initializing database...")
            self.db_manager = DatabaseManager()
            if not self.db_manager.initialize():
                splash.close()
                QMessageBox.critical(
                    None, "Database Error",
                    "Failed to initialize database.\nApplication will exit."
                )
                sys.exit(1)

            splash.set_status("Checking data...")
            # Demo/sample records are never offered automatically in
            # production. A production database starts with only the explicit
            # bootstrap users and is populated by an authenticated operator.
            if self.is_database_empty() and not is_production_environment():
                splash.close()
                self.show_welcome_message()
                splash.show()

            splash.set_status("Ready!")
            QApplication.processEvents()

            # ✅ جایگزین time.sleep با QTimer event loop
            loop = QEventLoop()
            QTimer.singleShot(AppConfig.SPLASH_DISPLAY_MS, loop.quit)
            loop.exec()

            splash.close()

            if not self.show_login():
                sys.exit(0)

            if not self.show_startup():
                sys.exit(0)

            self.create_main_window()
            self.aboutToQuit.connect(self.cleanup)

        except Exception as e:
            splash.close()
            logger.error(f"Initialization error: {str(e)}")
            QMessageBox.critical(
                None, "Initialization Error",
                f"Failed to initialize application:\n\n{str(e)}"
            )
            sys.exit(1)

    def _apply_global_stylesheet(self):
        """اعمال stylesheet کلی برنامه."""
        self.setStyleSheet("""
            QToolTip {
                background-color: #2c3e50;
                color: #ecf0f1;
                border: 1px solid #34495e;
                padding: 5px;
                border-radius: 3px;
                font-size: 11px;
            }
            QScrollBar:vertical {
                background: #f1f3f5;
                width: 10px;
                border-radius: 5px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #adb5bd;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #868e96;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
                background: none;
            }
            QScrollBar:horizontal {
                background: #f1f3f5;
                height: 10px;
                border-radius: 5px;
                margin: 0;
            }
            QScrollBar::handle:horizontal {
                background: #adb5bd;
                border-radius: 5px;
                min-width: 20px;
            }
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0;
                background: none;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:focus {
                outline: none;
                border: 1px solid #3498db;
            }
            QLineEdit, QTextEdit, QPlainTextEdit {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 1px solid #3498db;
            }
            QComboBox {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QComboBox:focus {
                border: 1px solid #3498db;
            }
            QTableWidget {
                gridline-color: #dee2e6;
                selection-background-color: #3498db;
                selection-color: white;
            }
            QHeaderView::section {
                background-color: #2c3e50;
                color: white;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
            QProgressBar {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 4px;
            }
            QStatusBar {
                border-top: 1px solid #dee2e6;
                font-size: 11px;
            }
            QToolBar {
                border-bottom: 1px solid #dee2e6;
                spacing: 3px;
                padding: 2px;
            }
            QSplitter::handle {
                background: #dee2e6;
            }
            QSplitter::handle:horizontal {
                width: 3px;
            }
        """)

    def is_database_empty(self) -> bool:
        """بررسی اینکه آیا دیتابیس خالی است."""
        try:
            session = self.db_manager.create_session()
            from core.database import Company
            count = session.query(Company).count()
            session.close()
            return count == 0
        except Exception as e:
            logger.error(f"Error checking database: {e}")
            return False

    def show_welcome_message(self):
        """نمایش پیام خوش‌آمدگویی."""
        reply = QMessageBox.question(
            None,
            "👋 Welcome to DrillMaster!",
            "Welcome to DrillMaster!\n\n"
            "It looks like this is your first time.\n"
            "Would you like to create sample data to get started?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self.create_sample_data()

    def create_sample_data(self):
        """Create development-only sample data."""
        if is_production_environment():
            logger.warning("Sample data request rejected in production")
            return False
        try:
            from datetime import date
            session = self.db_manager.create_session()
            from core.database import Company, Project, Well

            company = Company(
                name="Demo Drilling Company",
                code="DDC001",
                address="123 Oilfield Ave, Houston, TX",
                contact_person="Demo Manager",
                contact_email="demo@drillmaster.com",
                contact_phone="+1-713-555-0123"
            )
            session.add(company)
            session.flush()

            project = Project(
                company_id=company.id,
                name="Demo Exploration Project",
                code="DEMO_001",
                location="Demo Field, Texas",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 12, 31),
                status="Active",
                manager="Project Manager",
                budget=1000000.00,
                currency="USD"
            )
            session.add(project)
            session.flush()

            well = Well(
                project_id=project.id,
                name="Demo Well #1",
                code="DEMO_WELL_001",
                well_type="Exploration",
                purpose="Oil Production",
                status="Planning",
                field_name="Demo Field",
                location="Texas, USA",
                target_depth=3000.0,
                water_depth=0.0,
                elevation=100.0
            )
            session.add(well)
            session.commit()
            session.close()

            QMessageBox.information(
                None,
                "✅ Sample Data Created",
                "Sample data created successfully!\n\n"
                "You can now explore DrillMaster with this demo project."
            )

        except Exception as e:
            logger.error(f"Error creating sample data: {e}")
            QMessageBox.warning(
                None,
                "Warning",
                f"Could not create sample data:\n{str(e)}"
            )

    def show_login(self) -> bool:
        """نمایش دیالوگ Login."""
        try:
            # Auto-login is a development/test convenience only.
            import os
            if (
                not is_production_environment()
                and os.getenv("DRILLMASTER_AUTO_LOGIN", "").lower()
                in ("1", "true", "yes")
            ):
                auto_password = bootstrap_password_for_role("admin")
                if auto_password:
                    self.user = self.db_manager.authenticate_user("admin", auto_password)
                if self.user:
                    from core.permissions import permissions
                    permissions.set_user(self.user)
                    logger.info("Auto-login as admin (development/test mode)")
                    return True

            login_dialog = LoginDialog(self.db_manager)
            if login_dialog.exec() == QDialog.Accepted:
                self.user = login_dialog.get_user()
            if self.user:
                from core.permissions import permissions
                permissions.set_user(self.user)
                
                # Audit log
                self.db_manager.log_audit(
                    action="login",
                    entity_type="user",
                    entity_id=self.user.get('id'),
                    entity_name=self.user.get('username', ''),
                    details=f"Login successful - role: {self.user.get('role', 'user')}",
                    user_id=self.user.get('id'),
                    username=self.user.get('username', '')
                )
                return self.user is not None
            return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            QMessageBox.critical(None, "Login Error", f"Failed:\n{str(e)}")
            return False

    def show_startup(self) -> bool:
        """نمایش دیالوگ Startup."""
        try:
            startup_dialog = StartupDialog(self.db_manager)
            if startup_dialog.exec() == QDialog.Accepted:
                self.startup_result = startup_dialog.get_result()
                return True
            return False
        except Exception:
            logger.exception("Startup dialog failed")
            self.startup_result = None
            QMessageBox.critical(
                None,
                "Startup Error",
                "The startup dialog could not be opened. The application will exit.",
            )
            return False

    def create_main_window(self):
        """ایجاد و نمایش Main Window."""
        try:
            self.main_window = MainWindow(
                db_manager=self.db_manager,
                user=self.user,
                startup_result=self.startup_result
            )

            # مرکز کردن
            screen = self.primaryScreen()
            if screen:
                screen_geo = screen.availableGeometry()
                window_geo = self.main_window.frameGeometry()
                window_geo.moveCenter(screen_geo.center())
                self.main_window.move(window_geo.topLeft())

            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()

            # Apply permissions
            from core.permissions import permissions
            if permissions.is_viewer():
                self.main_window.apply_viewer_mode()
                
        except Exception as e:
            logger.error(f"Error creating main window: {e}", exc_info=True)
            QMessageBox.critical(
                None, "Error",
                f"Failed to create main window:\n{str(e)}"
            )
            sys.exit(1)

    def cleanup(self):
        """پاکسازی منابع."""
        try:
            if self.main_window:
                if hasattr(self.main_window, 'cleanup'):
                    self.main_window.cleanup()
                self.main_window = None

            if self.db_manager:
                self.db_manager.close()
                self.db_manager = None

            logger.info("Application cleanup complete")

        except Exception as e:
            logger.error(f"Cleanup error: {e}")


def run_package_smoke() -> int:
    """Run a non-GUI smoke check inside a frozen bundle."""
    import importlib
    import tempfile

    from core.runtime_config import ensure_writable_directories

    required_modules = (
        "core.database",
        "core.engineering",
        "core.engineering.registry",
        "core.ddr_pdf_export",
        "core.professional_export",
        "core.excel_intelligence",
        "core.document_import",
        "core.ai_import_mapper",
        "core.optional_capabilities",
        "dialogs.login_dialog",
        "dialogs.startup_dialog",
        "tabs.w11_Export",
        "tabs.w12_Analysis",
        "tabs.w13_Engineering_Calculator",
    )
    try:
        with tempfile.TemporaryDirectory(prefix="drillmaster-package-smoke-") as directory:
            os.environ["DRILLMASTER_ENV"] = "test"
            os.environ["DRILLMASTER_DATA_DIR"] = directory
            os.environ["DRILLMASTER_AI_IMPORT"] = "0"
            ensure_writable_directories()
            for module_name in required_modules:
                importlib.import_module(module_name)
            manager = DatabaseManager()
            if not manager.initialize():
                return 1
            try:
                session = manager.create_session()
                try:
                    from sqlalchemy import text

                    schema_version = session.execute(
                        text("SELECT MAX(version) FROM schema_version")
                    ).scalar()
                    if schema_version != 1:
                        return 1
                finally:
                    session.close()
            finally:
                manager.close()
        return 0
    except Exception:
        logger.exception("Frozen package smoke test failed")
        return 1


def main():
    """Main entry point."""
    if "--package-smoke" in sys.argv:
        return run_package_smoke()
    try:
        app = DrillMasterApp(sys.argv)
        return app.exec()
    except Exception:
        logger.exception("Fatal application error")
        QMessageBox.critical(
            None,
            "Fatal Error",
            "A fatal error occurred. Review the DrillMaster log for details.",
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())