# main_window.py - نسخه کامل اصلاح شده
"""
Main Window - با managerها و SelectionManager
"""
import os
import logging
from datetime import datetime, date

from PySide6.QtWidgets import *
from PySide6.QtCore import (
    Qt, QTimer, QSettings, QSize, QDateTime, QTime,
    QDate, QPoint, QRect, Signal, Slot, QThread,
    QEventLoop,
)

from shiboken6 import isValid

from PySide6.QtGui import *
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

from core.database import (
    DatabaseManager, Well, Company, Project,
    DailyReport, Section
)
from core.managers import StatusBarManager, AutoSaveManager, ShortcutManager
from core.selection_manager import SelectionManager
from core.functions import CentralFunctions

from tabs.home_tab import HomeTab
from tabs.w1_well_info import WellInfoTab
from tabs.w2_Daily_Report import DailyReportWidget
from tabs.w3_drilling_report import DrillingReportWidget
from tabs.w3b_wellbore_schematic_tab import WellboreSchematicTab
from tabs.w3c_section_data import SectionDataWidget
from tabs.w4_Downhole_Widget import DownholeWidget
from tabs.w5_Equipment_Widget import EquipmentWidget
from tabs.w6_Trajectory_Widget import TrajectoryWidget
from tabs.w7_logistics_Widget import LogisticsWidget
from tabs.w8_Safety_Widget import SafetyWidget
from tabs.w9_Services_Widget import ServicesWidget
from tabs.w10_Planning_Widget import PlanningWidget
from tabs.w11_Export import ExportWidget
from tabs.w12_Analysis import AnalysisWidget
from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
from tabs.w14_Procedure_Widget import ProcedureWidget
from tabs.w15_Reference_Tables import ReferenceTablesWidget
from tabs.w16_Cost_Management import CostManagementWidget

from dialogs.excel_import_dialog import ExcelImportDialog

from dialogs.hierarchy_dialogs import (
    NewCompanyDialog, NewProjectDialog, NewWellDialog,
    NewSectionDialog, NewDailyReportDialog
)
from dialogs.startup_dialog import StartupDialog
from dialogs.calculator_dialog import DrillingCalculatorDialog

logger = logging.getLogger(__name__)



class HierarchyWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            if not self._cancelled:
                data = self.db_manager.get_full_hierarchy()
                if not self._cancelled:
                    self.finished.emit(data)
        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))
                
# ==================== Loading Dialog ====================

class LoadingDialog(QDialog):
    """دیالوگ Loading برای عملیات سنگین."""

    def __init__(self, message: str = "Loading...", parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setFixedSize(300, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)

        self.message_label = QLabel(message)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet(
            "font-size: 13px; color: #2c3e50;"
        )
        layout.addWidget(self.message_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumHeight(8)
        layout.addWidget(self.progress)

        self.setStyleSheet("""
            QDialog {
                background: white;
                border: 1px solid #dee2e6;
                border-radius: 8px;
            }
        """)

    def set_message(self, message: str):
        self.message_label.setText(message)
        QApplication.processEvents()


# ==================== Main Window ====================

class MainWindow(QMainWindow):
    """Main window of DrillMaster."""

    well_selected = Signal(int, dict)
    well_cleared = Signal()
    report_selected = Signal(int, str)

    def __init__(self, db_manager, user, startup_result=None):
        super().__init__()

        self.db_manager = db_manager
        self.user = user
        self.startup_result = startup_result

        # Managers
        self.sel_manager = SelectionManager()
        self.status_manager = StatusBarManager()
        self.status_manager.register_main_window(self)
        self.auto_save_manager = AutoSaveManager()
        self.shortcut_manager = ShortcutManager(self)

        # State
        self.current_well = None
        self.current_report = None
        self.current_report_id = None
        self.settings = QSettings("Nikan", "DrillMaster")

        self.backup_timer = QTimer()
        self.backup_timer.timeout.connect(self._auto_backup)
        self.backup_timer.start(30 * 60 * 1000)  # 30 min

        self._loading_dialog = None


        self._hierarchy_worker = None

        self.init_ui()
        self.setup_connections()
        self.setup_managers()

        if startup_result:
            QTimer.singleShot(
                500, lambda: self.apply_startup_result(startup_result)
            )

        QTimer.singleShot(1000, self.update_recent_menu)
    # ==================== UI Init ====================
    def init_ui(self):
        self.setWindowTitle(f"DrillMaster - {self.user['username']}")
        self.resize(1400, 800)
        self.setMinimumSize(1000, 600)
        self.center_window()

        # ==================== ترتیب مهم است! ====================

        # ✅ مرحله ۱: ساخت Menubar
        self.create_menubar()

        # ✅ مرحله ۲: ساخت Toolbar
        self.create_toolbar()

        # ✅ مرحله ۳: ساخت tree_widget (قبل از dock!)
        self._create_tree_widget()

        # ✅ مرحله ۴: ساخت Tab Widget
        self.create_tab_widget()
        self.setCentralWidget(self.tab_widget)

        # ✅ مرحله ۵: ساخت Dock (بعد از tree_widget!)
        self.create_hierarchy_dock()

        # ✅ مرحله ۶: Status Bar
        self.create_status_bar()

        QTimer.singleShot(100, self.ensure_menubar_visible)

    def _create_tree_widget(self):
        """
        ✅ ساخت tree_widget به صورت جداگانه.
        باید قبل از create_hierarchy_dock فراخوانی شود.
        """
        self.tree_widget = QTreeWidget()
        self.tree_widget.setColumnCount(2)
        self.tree_widget.setHeaderLabels(["Name", "Type"])
        self.tree_widget.setAnimated(True)
        self.tree_widget.setIndentation(18)
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(
            self.show_tree_context_menu
        )
        self.tree_widget.itemClicked.connect(self.on_tree_item_clicked)
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background: white;
                font-size: 11px;
            }
            QTreeWidget::item {
                padding: 3px 2px;
                border-bottom: 1px solid #f1f3f5;
            }
            QTreeWidget::item:selected {
                background: #3498db;
                color: white;
            }
            QTreeWidget::item:hover:!selected {
                background: #ebf5fb;
            }
            QHeaderView::section {
                background: #ecf0f1;
                color: #2c3e50;
                padding: 5px;
                border: none;
                border-bottom: 1px solid #bdc3c7;
                font-weight: bold;
                font-size: 10px;
            }
        """)

    def create_hierarchy_dock(self):
        """
        ✅ ساخت Hierarchy DockWidget.
        tree_widget باید از قبل ساخته شده باشد.
        """
        self.hierarchy_dock = QDockWidget("🏢 Project Hierarchy", self)
        self.hierarchy_dock.setObjectName("HierarchyDock")
        self.hierarchy_dock.setFeatures(
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetFloatable |
            QDockWidget.DockWidgetClosable
        )
        self.hierarchy_dock.setMinimumWidth(220)
        self.hierarchy_dock.setMaximumWidth(450)
        self.hierarchy_dock.setStyleSheet("""
            QDockWidget {
                font-weight: bold;
                font-size: 12px;
            }
            QDockWidget::title {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #2c3e50, stop:1 #34495e);
                color: white;
                padding: 8px;
                font-size: 12px;
            }
            QDockWidget::close-button,
            QDockWidget::float-button {
                background: transparent;
                border: none;
                padding: 2px;
            }
            QDockWidget::close-button:hover,
            QDockWidget::float-button:hover {
                background: rgba(255,255,255,0.3);
                border-radius: 3px;
            }
        """)

        # ===== محتوای Dock =====
        dock_content = QWidget()
        dock_layout = QVBoxLayout(dock_content)
        dock_layout.setContentsMargins(4, 4, 4, 4)
        dock_layout.setSpacing(4)

        # --- Search Bar ---
        search_layout = QHBoxLayout()
        search_layout.setSpacing(3)

        self.tree_search = QLineEdit()
        self.tree_search.setPlaceholderText("🔍 Search...")
        self.tree_search.setClearButtonEnabled(True)
        self.tree_search.setStyleSheet("""
            QLineEdit {
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 11px;
            }
            QLineEdit:focus { border: 1px solid #3498db; }
        """)
        self.tree_search.textChanged.connect(self._filter_hierarchy)
        search_layout.addWidget(self.tree_search)

        # دکمه‌های کوچک کنار search
        for icon, tip, slot in [
            ("▲", "Collapse All", self.tree_widget.collapseAll),
            ("▼", "Expand All",
             lambda: self.tree_widget.expandToDepth(3)),
            ("🔄", "Refresh", self.populate_hierarchy),
        ]:
            btn = QToolButton()
            btn.setText(icon)
            btn.setToolTip(tip)
            btn.setFixedSize(28, 28)
            btn.setStyleSheet("""
                QToolButton {
                    border: 1px solid #bdc3c7;
                    border-radius: 4px;
                    font-size: 11px;
                    background: #f8f9fa;
                }
                QToolButton:hover {
                    background: #3498db;
                    color: white;
                    border-color: #2980b9;
                }
            """)
            btn.clicked.connect(slot)
            search_layout.addWidget(btn)

        dock_layout.addLayout(search_layout)

        # --- Tree Widget (که قبلاً ساخته شده) ---
        dock_layout.addWidget(self.tree_widget, 1)

        # --- Quick Action Buttons ---
        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(3)

        quick_btns = [
            ("🏢", "New Company", self.new_company_dialog),
            ("📁", "New Project", self.new_project_dialog),
            ("🛢️", "New Well", self.new_well_dialog),
            ("📅", "New Report", self.new_daily_report_from_toolbar),
        ]

        for icon, tip, slot in quick_btns:
            btn = QToolButton()
            btn.setText(icon)
            btn.setToolTip(tip)
            btn.setFixedSize(32, 28)
            btn.setStyleSheet("""
                QToolButton {
                    border: 1px solid #bdc3c7;
                    border-radius: 3px;
                    font-size: 13px;
                    background: #f8f9fa;
                }
                QToolButton:hover {
                    background: #3498db;
                    color: white;
                    border-color: #2980b9;
                }
            """)
            btn.clicked.connect(slot)
            quick_layout.addWidget(btn)

        quick_layout.addStretch()
        dock_layout.addLayout(quick_layout)

        # تنظیم محتوا و جایگذاری
        self.hierarchy_dock.setWidget(dock_content)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.hierarchy_dock)

        # ذخیره و بازیابی وضعیت Dock
        self._restore_dock_state()

        # پر کردن درخت
        self.populate_hierarchy()

    def _restore_dock_state(self):
        """بازیابی وضعیت Dock از Settings."""
        try:
            geometry = self.settings.value("dock/hierarchy_geometry")
            if geometry:
                self.hierarchy_dock.restoreGeometry(geometry)
            visible = self.settings.value(
                "dock/hierarchy_visible", True, type=bool
            )
            self.hierarchy_dock.setVisible(visible)
        except Exception:
            pass

    def _save_dock_state(self):
        """ذخیره وضعیت Dock در Settings."""
        try:
            self.settings.setValue(
                "dock/hierarchy_geometry",
                self.hierarchy_dock.saveGeometry()
            )
            self.settings.setValue(
                "dock/hierarchy_visible",
                self.hierarchy_dock.isVisible()
            )
        except Exception:
            pass

    # ==================== Toggle ====================

    def _toggle_hierarchy(self, checked: bool):
        """نمایش/مخفی کردن Hierarchy."""
        if hasattr(self, 'hierarchy_dock'):
            self.hierarchy_dock.setVisible(checked)
            # sync کردن با toolbar action
            if hasattr(self, 'toggle_hierarchy_action'):
                self.toggle_hierarchy_action.setChecked(checked)

    # ==================== Search/Filter ====================

    def _filter_hierarchy(self, text: str):
        """فیلتر زنده درخت."""
        root = self.tree_widget.invisibleRootItem()
        if not text:
            self._show_all_items(root)
            return
        self._filter_items(root, text.lower())

    def _filter_items(
        self,
        item,
        text: str,
        max_depth: int = 10,
        current_depth: int = 0
    ) -> bool:
        """
        فیلتر بازگشتی - با محدودیت عمق
        جلوگیری از stack overflow برای درخت‌های عمیق
        """
        # ✅ جلوگیری از recursion بیش از حد
        if current_depth >= max_depth:
            return False
        
        # چک خود آیتم
        self_match = any(
            text in item.text(col).lower()
            for col in range(item.columnCount())
            if item.text(col)
        )

        # چک فرزندان با عمق محدود
        child_match = any(
            self._filter_items(
                item.child(i),
                text,
                max_depth,
                current_depth + 1
            )
            for i in range(item.childCount())
        )

        show = self_match or child_match
        item.setHidden(not show)

        if show and child_match:
            item.setExpanded(True)

        return show

    def _show_all_items(self, item):
        """نمایش همه آیتم‌ها."""
        item.setHidden(False)
        item.setExpanded(False)
        for i in range(item.childCount()):
            self._show_all_items(item.child(i))
        self.tree_widget.expandToDepth(2)

    # ==================== اضافه کردن به closeEvent ====================

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, "Exit",
            "Are you sure you want to exit?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._save_dock_state()
            
            self._stop_hierarchy_worker()
            
            if hasattr(self, 'backup_timer') and self.backup_timer.isActive():
                self.backup_timer.stop()
            if hasattr(self, 'time_timer') and self.time_timer.isActive():
                self.time_timer.stop()

            self.cleanup()
            event.accept()
        else:
            event.ignore()
        
    # ==================== Toolbar - اضافه کردن Toggle Button ====================

    def create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setObjectName("MainToolbar")
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        def add_action(text, tooltip, slot, shortcut=None):
            act = QAction(text, self)
            act.setToolTip(tooltip)
            act.triggered.connect(slot)
            if shortcut:
                act.setShortcut(shortcut)
            toolbar.addAction(act)
            return act

        add_action("🏠 Home", "Return to startup", self.return_to_startup)
        toolbar.addSeparator()
        add_action("🏢 Company", "New Company", self.new_company_dialog)
        add_action("📁 Project", "New Project", self.new_project_dialog)
        add_action("🛢️ Well", "New Well (Ctrl+N)",
                   self.new_well_dialog, "Ctrl+N")
        toolbar.addSeparator()
        add_action("📂 Open", "Open Well (Ctrl+O)",
                   self.open_well_dialog, "Ctrl+O")
        toolbar.addSeparator()
        add_action("📋 Plan", "Well Plan", self.open_well_plan)
        toolbar.addSeparator()
        add_action("💾 Save", "Save (Ctrl+S)",
                   self.save_current_tab, "Ctrl+S")
        add_action("💾 All", "Save All (Ctrl+Shift+S)",
                   self.save_all_tabs, "Ctrl+Shift+S")
        toolbar.addSeparator()
        add_action("📅 Report", "New Daily Report (Ctrl+R)",
                   self.new_daily_report_from_toolbar, "Ctrl+R")
        add_action("📋 Copy", "Copy Previous",
                   self.copy_previous_from_toolbar)
        toolbar.addSeparator()
        add_action("📊 Import", "Import from Excel (Ctrl+I)",
                   self.open_excel_import, "Ctrl+I")
        add_action("📤 Export", "Export (Ctrl+E)",
                   self.open_export, "Ctrl+E")
        add_action("🖨️ Print", "Print (Ctrl+P)",
                   self.print_report, "Ctrl+P")
        toolbar.addSeparator()
        add_action("🔄 Refresh", "Refresh (F5)",
                   self.refresh_all_tabs, "F5")
        toolbar.addSeparator()

        # ✅ NEW: Toggle Hierarchy
        self.toggle_hierarchy_action = QAction("📂 Panel", self)
        self.toggle_hierarchy_action.setCheckable(True)
        self.toggle_hierarchy_action.setChecked(True)
        self.toggle_hierarchy_action.setToolTip(
            "Show/Hide Hierarchy (Ctrl+H)"
        )
        self.toggle_hierarchy_action.setShortcut("Ctrl+H")
        self.toggle_hierarchy_action.toggled.connect(self._toggle_hierarchy)
        toolbar.addAction(self.toggle_hierarchy_action)

        toolbar.addSeparator()
        add_action("⚙️ Settings", "Settings (Ctrl+,)",
                   self.show_settings, "Ctrl+,")
        add_action("❓ Help", "Help (F1)", self.show_help, "F1")
        toolbar.addSeparator()

        self.auto_save_action = QAction("💾 Auto-save: ON", self)
        self.auto_save_action.setCheckable(True)
        self.auto_save_action.setChecked(True)
        self.auto_save_action.toggled.connect(self.toggle_auto_save)
        toolbar.addAction(self.auto_save_action)
        toolbar.addSeparator()

        # Global Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search...")
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet(
            "border: 1px solid #bdc3c7; border-radius: 4px; "
            "padding: 4px 8px; font-size: 11px;"
        )
        self.search_input.returnPressed.connect(self._global_search)
        toolbar.addWidget(self.search_input)
        toolbar.addSeparator()
        
        # User label
        user_widget = QWidget()
        ul = QHBoxLayout(user_widget)
        ul.setContentsMargins(5, 0, 5, 0)
        ul.addWidget(QLabel("👤"))
        user_lbl = QLabel(
            f"{self.user['username']} ({self.user['role']})"
        )
        user_lbl.setStyleSheet("font-weight: bold; color: #2c3e50;")
        ul.addWidget(user_lbl)
        toolbar.addWidget(user_widget)

    # ==================== Menubar - View Menu ====================

    def create_menubar(self):
        menubar = self.menuBar()
        menubar.setVisible(True)

        # File
        file_menu = menubar.addMenu("📁 File")
        self.recent_menu = file_menu.addMenu("📂 Recent Wells")

        for text, shortcut, slot in [
            ("🛢️ New Well", "Ctrl+N", self.new_well_dialog),
            ("📂 Open Well", "Ctrl+O", self.open_well_dialog),
        ]:
            act = QAction(text, self)
            act.setShortcut(shortcut)
            act.triggered.connect(slot)
            file_menu.addAction(act)

        file_menu.addSeparator()

        for text, shortcut, slot in [
            ("💾 Save", "Ctrl+S", self.save_current_tab),
            ("💾 Save All", "Ctrl+Shift+S", self.save_all_tabs),
        ]:
            act = QAction(text, self)
            act.setShortcut(shortcut)
            act.triggered.connect(slot)
            file_menu.addAction(act)

        file_menu.addSeparator()
        exit_act = QAction("🚪 Exit", self)
        exit_act.setShortcut("Ctrl+Q")
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # Edit
        edit_menu = menubar.addMenu("✏️ Edit")
        for text, shortcut, slot in [
            ("↩️ Undo", "Ctrl+Z", self.undo_action),
            ("↪️ Redo", "Ctrl+Y", self.redo_action),
            ("✂️ Cut", "Ctrl+X", self.cut_action),
            ("📋 Copy", "Ctrl+C", self.copy_action),
            ("📌 Paste", "Ctrl+V", self.paste_action),
        ]:
            act = QAction(text, self)
            act.setShortcut(shortcut)
            act.triggered.connect(slot)
            edit_menu.addAction(act)

        # View - ✅ با Toggle Hierarchy
        view_menu = menubar.addMenu("👁️ View")

        self.hierarchy_menu_action = QAction("📂 Hierarchy Panel", self)
        self.hierarchy_menu_action.setCheckable(True)
        self.hierarchy_menu_action.setChecked(True)
        self.hierarchy_menu_action.setShortcut("Ctrl+H")
        self.hierarchy_menu_action.toggled.connect(self._toggle_hierarchy)
        view_menu.addAction(self.hierarchy_menu_action)

        view_menu.addSeparator()
        refresh_act = QAction("🔄 Refresh", self)
        refresh_act.setShortcut("F5")
        refresh_act.triggered.connect(self.refresh_all_tabs)
        view_menu.addAction(refresh_act)

        # Planning
        planning_menu = menubar.addMenu("📋 Planning")
        plan_act = QAction("📋 Well Plan", self)
        plan_act.triggered.connect(self.open_well_plan)
        planning_menu.addAction(plan_act)

        # Tools
        tools_menu = menubar.addMenu("🔧 Tools")
        for text, slot in [
            ("🧮 Calculator", self.open_calculator),
            ("📊 Import from Excel", self.open_excel_import),
            ("⚙️ Settings", self.show_settings),
        ]:
            act = QAction(text, self)
            act.triggered.connect(slot)
            tools_menu.addAction(act)

        # Help
        help_menu = menubar.addMenu("❓ Help")
        for text, shortcut, slot in [
            ("📚 Help", "F1", self.show_help),
            ("ℹ️ About", "", self.show_about),
        ]:
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(shortcut)
            act.triggered.connect(slot)
            help_menu.addAction(act)


    def center_window(self):
        try:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                frame = self.frameGeometry()
                frame.moveCenter(geo.center())
                self.move(frame.topLeft())
        except Exception:
            pass

    def ensure_menubar_visible(self):
        try:
            menubar = self.menuBar()
            if menubar:
                menubar.setVisible(True)
                menubar.update()
        except Exception as e:
            logger.error(f"Menubar error: {e}")

    def _global_search(self):
        query = self.search_input.text().strip()
        if not query or len(query) < 2:
            return

        results = self.db_manager.search_all(
            query,
            well_id=self.sel_manager.current_well_id
        )

        if not results:
            self.status_manager.show_message(
                "MainWindow", f"No results for '{query}'", 3000
            )
            return

        # نمایش نتایج
        dialog = QDialog(self)
        dialog.setWindowTitle(f"🔍 Search: {query}")
        dialog.setMinimumSize(500, 400)
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel(f"Found {len(results)} results for '{query}':"))

        result_list = QListWidget()
        result_list.setStyleSheet(
            "QListWidget::item { padding: 8px; border-bottom: 1px solid #eee; }"
            "QListWidget::item:selected { background: #3498db; color: white; }"
        )

        for r in results:
            item = QListWidgetItem(
                f"{r['icon']} {r['title']}\n   {r['subtitle']}"
            )
            item.setData(Qt.UserRole, r)
            result_list.addItem(item)

        layout.addWidget(result_list)

        def on_double_click(item):
            data = item.data(Qt.UserRole)
            if data["type"] == "well":
                self.load_well_with_full_context(data["id"])
            elif data["type"] == "report":
                self.sel_manager.select_report(data["id"], data)
                self.tab_widget.setCurrentIndex(4)
            dialog.accept()

        result_list.itemDoubleClicked.connect(on_double_click)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.reject)
        layout.addWidget(close_btn)

        dialog.exec()
        
    # ==================== Ribbon Bar (اختیاری) ====================

    def create_ribbon_bar(self):
        """
        ✅ ایجاد Ribbon Bar.
        اگر qtribbon نصب باشد از آن استفاده می‌کنیم.
        وگرنه از QTabWidget سفارشی.
        """
        try:
            # تلاش برای استفاده از qtribbon
            from qtribbon import RibbonBar as QtRibbon
            self._create_qtribbon()
            logger.info("Using qtribbon library")
        except ImportError:
            # Fallback: QTabWidget سفارشی
            self._create_custom_ribbon()
            logger.info("Using custom ribbon (qtribbon not installed)")

    def _create_qtribbon(self):
        """ساخت Ribbon با کتابخانه qtribbon."""
        try:
            from qtribbon import RibbonBar

            ribbon = RibbonBar(self)
            self.setMenuWidget(ribbon)

            # Home tab
            home = ribbon.addTab("Home")

            file_panel = home.addPanel("File")
            file_panel.addLargeButton(
                "New Well", "🛢️",
                slot=self.new_well_dialog
            )
            file_panel.addLargeButton(
                "Open Well", "📂",
                slot=self.open_well_dialog
            )
            file_panel.addSmallButton(
                "Company", slot=self.new_company_dialog
            )
            file_panel.addSmallButton(
                "Project", slot=self.new_project_dialog
            )

            save_panel = home.addPanel("Save")
            save_panel.addLargeButton(
                "Save", "💾", slot=self.save_current_tab
            )
            save_panel.addSmallButton(
                "Save All", slot=self.save_all_tabs
            )
            save_panel.addSmallButton(
                "Refresh", slot=self.refresh_all_tabs
            )

            # Insert tab
            insert = ribbon.addTab("Insert")
            report_panel = insert.addPanel("Reports")
            report_panel.addLargeButton(
                "Daily Report", "📅",
                slot=self.new_daily_report_from_toolbar
            )
            report_panel.addLargeButton(
                "Well Plan", "📋",
                slot=self.open_well_plan
            )

            # Tools tab
            tools = ribbon.addTab("Tools")
            calc_panel = tools.addPanel("Calculators")
            calc_panel.addLargeButton(
                "Calculator", "🧮",
                slot=self.open_calculator
            )

            import_panel = tools.addPanel("Import/Export")
            import_panel.addLargeButton(
                "Import Excel", "📊",
                slot=self.open_excel_import
            )
            import_panel.addLargeButton(
                "Export", "📤",
                slot=self.open_export
            )

        except Exception as e:
            logger.error(f"qtribbon error: {e}")
            self._create_custom_ribbon()

    def _create_custom_ribbon(self):
        """Fallback: ساخت Ribbon سفارشی."""
        try:
            from ui.ribbon import RibbonBar

            self.ribbon_bar = RibbonBar(self)

            # Quick Access
            self.ribbon_bar.add_quick_button(
                "💾", "Save", self.save_current_tab
            )
            self.ribbon_bar.add_quick_button(
                "↩️", "Undo", self.undo_action
            )
            self.ribbon_bar.add_quick_button(
                "🖨️", "Print", self.print_report
            )

            # Home tab
            home = self.ribbon_bar.add_tab("🏠 Home")

            from ui.ribbon import RibbonGroup, RibbonButton, RibbonSmallButton

            file_group = RibbonGroup("File")
            btn = RibbonButton("🛢️", "New\nWell")
            btn.clicked.connect(self.new_well_dialog)
            file_group.add_button(btn)

            btn2 = RibbonButton("📂", "Open\nWell")
            btn2.clicked.connect(self.open_well_dialog)
            file_group.add_button(btn2)

            sb1 = RibbonSmallButton("🏢", "Company")
            sb1.clicked.connect(self.new_company_dialog)
            sb2 = RibbonSmallButton("📁", "Project")
            sb2.clicked.connect(self.new_project_dialog)
            sb3 = RibbonSmallButton("🏠", "Startup")
            sb3.clicked.connect(self.return_to_startup)
            file_group.add_small_buttons([sb1, sb2, sb3])

            home.add_group(file_group)

            save_group = RibbonGroup("Save")
            btn3 = RibbonButton("💾", "Save")
            btn3.clicked.connect(self.save_current_tab)
            save_group.add_button(btn3)

            sb4 = RibbonSmallButton("💾", "Save All")
            sb4.clicked.connect(self.save_all_tabs)
            sb5 = RibbonSmallButton("🔄", "Refresh")
            sb5.clicked.connect(self.refresh_all_tabs)
            sb6 = RibbonSmallButton("⚙️", "Settings")
            sb6.clicked.connect(self.show_settings)
            save_group.add_small_buttons([sb4, sb5, sb6])

            home.add_group(save_group)

            ie_group = RibbonGroup("Import / Export")
            btn4 = RibbonButton("📊", "Import\nExcel")
            btn4.clicked.connect(self.open_excel_import)
            ie_group.add_button(btn4)
            btn5 = RibbonButton("📤", "Export")
            btn5.clicked.connect(self.open_export)
            ie_group.add_button(btn5)

            home.add_group(ie_group)
            home.finalize()

            ribbon_toolbar = QToolBar("Ribbon")
            ribbon_toolbar.setObjectName("RibbonToolbar")
            ribbon_toolbar.setMovable(False)
            ribbon_toolbar.addWidget(self.ribbon_bar)
            self.addToolBar(Qt.TopToolBarArea, ribbon_toolbar)

        except ImportError:
            logger.warning("Custom ribbon not available")
        except Exception as e:
            logger.error(f"Custom ribbon error: {e}")
          
    # ==================== Tabs ====================

    def create_tab_widget(self):
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setTabsClosable(False)
        self.tab_widget.setMovable(True)
        self.create_tabs()
        self.splitter = QSplitter()
        self.splitter.addWidget(self.tab_widget)

    def create_tabs(self):
        # Tab 0: Home (software)
        self.home_tab = HomeTab(self.db_manager, self)
        self.tab_widget.addTab(self.home_tab, "🏠 Home")
        self.home_tab.set_parent_tab_widget(self.tab_widget)
        self.home_tab.parent_window = self

        # Tab 1: Well Info (well)
        self.well_info_tab = WellInfoTab(self.db_manager, self)
        self.tab_widget.addTab(self.well_info_tab, "🛢️ Well Info")

        # Tab 2: Wellbore Schematic (well)
        self.wellbore_schematic_tab = WellboreSchematicTab(
            self.db_manager, self
        )
        self.tab_widget.addTab(
            self.wellbore_schematic_tab, "📊 Wellbore Schematic"
        )

        # Tab 3: Section Data (section) - NEW
        from tabs.w3c_section_data import SectionDataWidget
        self.section_data_tab = SectionDataWidget(
            self.db_manager, self
        )
        self.tab_widget.addTab(
            self.section_data_tab, "📐 Section Data"
        )

        # Tab 4: Daily Report (report)
        self.daily_report_tab = DailyReportWidget(
            self.db_manager, self
        )
        self.tab_widget.addTab(
            self.daily_report_tab, "📅 Daily Report"
        )

        # Tab 5: Drilling Report (report - only params+mud)
        self.drilling_report_tab = DrillingReportWidget(
            self.db_manager, self
        )
        self.tab_widget.addTab(
            self.drilling_report_tab, "🧭 Drilling Report"
        )

        # Tab 6: Downhole (report)
        self.downhole_tab = DownholeWidget(self.db_manager, self)
        self.tab_widget.addTab(self.downhole_tab, "📡 Downhole")

        # Tab 7: Equipment (report)
        self.equipment_widget = EquipmentWidget(
            self.db_manager, self
        )
        self.tab_widget.addTab(
            self.equipment_widget, "🏗️ Equipment"
        )

        # Tab 8: Trajectory (report)
        self.trajectory_widget = TrajectoryWidget(
            self.db_manager, self
        )
        self.tab_widget.addTab(
            self.trajectory_widget, "📈 Trajectory"
        )

        # Tab 9: Logistics (report)
        self.logistics_widget = LogisticsWidget(
            self.db_manager, self
        )
        self.tab_widget.addTab(
            self.logistics_widget, "📦 Logistics"
        )

        # Tab 10: Safety (report)
        self.safety_widget = SafetyWidget(self.db_manager, self)
        self.tab_widget.addTab(self.safety_widget, "🛡️ Safety")

        # Tab 11: Services (report)
        self.services_widget = ServicesWidget(
            self.db_manager, self
        )
        self.tab_widget.addTab(
            self.services_widget, "🔌 Services"
        )

        # Tab 12: Planning (well)
        self.planning_widget = PlanningWidget(
            self.db_manager, self
        )
        self.tab_widget.addTab(
            self.planning_widget, "📋 Planning"
        )

        # Tab 13: Export (well)
        self.export_widget = ExportWidget(self.db_manager, self)
        self.tab_widget.addTab(self.export_widget, "📤 Export")

        # Tab 14: Cost (well)
        self.cost_widget = CostManagementWidget(
            self.db_manager, self
        )
        self.tab_widget.addTab(self.cost_widget, "💰 Cost")

        # Tab 15: Analysis (well)
        self.analysis_widget = AnalysisWidget(
            self.db_manager, self
        )
        self.tab_widget.addTab(
            self.analysis_widget, "📊 Analysis"
        )

        # Tab 16: Procedures (well)
        self.procedure_widget = ProcedureWidget(
            self.db_manager, self
        )
        self.tab_widget.addTab(
            self.procedure_widget, "📋 Procedures"
        )

        # Tab 17: Eng Calculator (software)
        self.engineering_calc_tab = EngineeringCalculatorTab(
            self.db_manager, self
        )
        self.tab_widget.addTab(
            self.engineering_calc_tab, "⚙️ Eng. Calc"
        )

        # Tab 18: Reference (software)
        self.reference_tab = ReferenceTablesWidget(
            self.db_manager, self
        )
        self.tab_widget.addTab(self.reference_tab, "📚 Reference")

        # SelectionManager connections
        self.sel_manager.well_changed.connect(
            lambda wid, wd: (
                self.export_widget.set_current_well(wid, wd)
                if hasattr(self, 'export_widget') else None
            )
        )
        self.sel_manager.report_changed.connect(
            lambda rid, ri: (
                self.daily_report_tab.load_report_by_id(rid)
                if rid and hasattr(self, 'daily_report_tab')
                else None
            )
        )
    # ==================== Setup ====================

    def setup_managers(self):
        self.shortcut_manager.setup_default_shortcuts()
        self.setup_custom_shortcuts()

        # فقط تب‌های editable
        tabs_with_save = [
            self.well_info_tab,
            self.daily_report_tab,
            self.drilling_report_tab,
            self.downhole_tab,
            self.equipment_widget,
            self.trajectory_widget,
            self.logistics_widget,
            self.safety_widget,
            self.services_widget,
            self.section_data_tab,
        ]
        for tab in tabs_with_save:
            if hasattr(tab, 'save_data'):
                self.auto_save_manager.enable_for_widget(
                    tab.__class__.__name__, tab, interval_minutes=5
                )

    def setup_custom_shortcuts(self):
        shortcuts = [
            ("Ctrl+Shift+C", self.new_company_dialog, "New Company"),
            ("Ctrl+Shift+P", self.new_project_dialog, "New Project"),
            ("Ctrl+Shift+W", self.new_well_dialog, "New Well"),
            ("Ctrl+O", self.open_well_dialog, "Open Well"),
            ("Ctrl+Q", self.close, "Exit"),
            ("Ctrl+,", self.show_settings, "Settings"),
            ("Ctrl+F", lambda: self.search_input.setFocus(), "Search"),
            ("Ctrl+D", lambda: self.tab_widget.setCurrentIndex(4), "Daily Report"),
            ("Ctrl+1", lambda: self.tab_widget.setCurrentIndex(0), "Home"),
            ("Ctrl+2", lambda: self.tab_widget.setCurrentIndex(1), "Well Info"),
            ("Ctrl+T", self._toggle_theme, "Toggle Theme"),
        ]
        for key, slot, desc in shortcuts:
            self.shortcut_manager.add_shortcut_with_feedback(key, slot, desc)

    def _toggle_theme(self):
        settings = QSettings("Nikan", "DrillMaster")
        current = settings.value("ui/theme", "Light")
        new_theme = "Dark" if current == "Light" else "Light"
        settings.setValue("ui/theme", new_theme)
        self._apply_settings()
        self.status_manager.show_success(
            "MainWindow", f"Theme: {new_theme}"
        )
        
    def setup_connections(self):
        self.tab_widget.currentChanged.connect(self.on_tab_changed)


    def populate_hierarchy(self):
        """بارگذاری async hierarchy"""
        from core.cache_manager import cache

        cache_key = "main_window_hierarchy"
        cached = cache.get(cache_key)
        if cached is not None:
            self._build_tree_from_data(cached)
            return

        self.show_loading("Loading hierarchy...")

        # توقف worker قبلی
        self._stop_hierarchy_worker()

        self._hierarchy_worker = HierarchyWorker(self.db_manager)
        self._hierarchy_worker.finished.connect(self._on_hierarchy_loaded)
        self._hierarchy_worker.error.connect(self._on_hierarchy_error)
        self._hierarchy_worker.start()

    def _stop_hierarchy_worker(self):
        worker = getattr(self, '_hierarchy_worker', None)
        if worker is None:
            return

        try:
            worker.cancel()
            if worker.isRunning():
                worker.quit()
                if not worker.wait(3000):
                    worker.terminate()
                    worker.wait(1000)
        except RuntimeError:
            pass
        except Exception as e:
            logger.debug(f"Worker stop warning: {e}")
        finally:
            self._hierarchy_worker = None
            
    def _on_hierarchy_loaded(self, hierarchy):
        from core.cache_manager import cache
        cache.set("main_window_hierarchy", hierarchy, ttl=30.0)
        self._build_tree_from_data(hierarchy)
        self.hide_loading()
        # ✅ پاک کردن reference بعد از اتمام
        self._hierarchy_worker = None

    def _on_hierarchy_error(self, error_msg):
        logger.error(f"Hierarchy load error: {error_msg}")
        self.hide_loading()
        # ✅ پاک کردن reference بعد از خطا
        self._hierarchy_worker = None
        
    def _build_tree_from_data(self, hierarchy):
        """ساخت درخت با مالکیت صحیح"""
        self.tree_widget.clear()
        
        for company_data in hierarchy:
            company_item = QTreeWidgetItem(self.tree_widget)
            company_item.setText(0, f"🏢 {company_data['name']}")
            company_item.setText(1, "Company")
            company_item.setData(0, Qt.UserRole, {
                "type": "company", "id": company_data["id"]
            })
            
            for project_data in company_data.get("projects", []):
                project_item = QTreeWidgetItem(company_item)
                project_item.setText(0, f"📁 {project_data['name']}")
                project_item.setText(1, "Project")
                project_item.setData(0, Qt.UserRole, {
                    "type": "project", "id": project_data["id"]
                })
                
                for well_data in project_data.get("wells", []):
                    well_item = QTreeWidgetItem(project_item)
                    well_item.setText(0, f"🛢️ {well_data['name']}")
                    well_item.setText(1, "Well")
                    well_item.setData(0, Qt.UserRole, {
                        "type": "well", "id": well_data["id"]
                    })
                    
                    # === Well-level items ===
                    schematic_item = QTreeWidgetItem(well_item)
                    schematic_item.setText(0, "  📊 Wellbore Schematic")
                    schematic_item.setText(1, "Well Tab")
                    schematic_item.setData(0, Qt.UserRole, {
                        "type": "well_tab",
                        "well_id": well_data["id"],
                        "tab_title": "📊 Wellbore Schematic",
                    })
                    
                    proc_item = QTreeWidgetItem(well_item)
                    proc_item.setText(0, "  📋 Procedures")
                    proc_item.setText(1, "Well Tab")
                    proc_item.setData(0, Qt.UserRole, {
                        "type": "well_tab",
                        "well_id": well_data["id"],
                        "tab_title": "📋 Procedures",
                    })
                    
                    # === Sections ===
                    for section in well_data.get("sections", []):
                        section_item = QTreeWidgetItem(well_item)
                        section_item.setText(
                            0, f"  📐 {section['name']}"
                        )
                        section_item.setText(1, "Section")
                        section_item.setData(0, Qt.UserRole, {
                            "type": "section",
                            "id": section["id"],
                            "well_id": well_data["id"],
                        })
                        
                        # Section-level sub-items
                        section_tabs = [
                            ("🏗️ Cement Report", "📐 Section Data"),
                            ("📏 Casing Tally", "📐 Section Data"),
                            ("🔩 Casing Report", "📐 Section Data"),
                            ("🏢 Service Companies", "📐 Section Data"),
                        ]
                        for label, tab_title in section_tabs:
                            sub = QTreeWidgetItem(section_item)
                            sub.setText(0, f"    {label}")
                            sub.setText(1, "Section Tab")
                            sub.setData(0, Qt.UserRole, {
                                "type": "section_tab",
                                "section_id": section["id"],
                                "well_id": well_data["id"],
                                "tab_title": tab_title,
                            })
                        
                        # === Reports in this section ===
                        for report in section.get("reports", []):
                            date_str = str(
                                report.get('report_date', '')
                            )
                            rnum = report.get('report_number', '?')
                            report_item = QTreeWidgetItem(section_item)
                            report_item.setText(
                                0, f"    📅 #{rnum} - {date_str}"
                            )
                            report_item.setText(1, "Daily Report")
                            report_item.setData(0, Qt.UserRole, {
                                "type": "daily_report",
                                "id": report["id"],
                                "report_id": report["id"],
                                "section_id": section["id"],
                                "well_id": well_data["id"],
                            })
                            
                            # Report-level sub-items
                            self._add_report_subitems(
                                report_item, report["id"]
                            )
        
        self.tree_widget.expandToDepth(2)
            
    def _invalidate_hierarchy_cache(self):
        from core.cache_manager import cache
        cache.delete("main_window_hierarchy")


    def _add_report_subitems(self, parent_item, report_id):
        """زیرآیتم‌ها فقط report-level"""
        tabs = [
            ("├─ 📅 Daily Report",      "📅 Daily Report"),
            ("├─ ⚙️ Drilling Params",   "🧭 Drilling Report"),
            ("├─ 📡 Downhole",          "📡 Downhole"),
            ("├─ 🏗️ Equipment",         "🏗️ Equipment"),
            ("├─ 📈 Trajectory",        "📈 Trajectory"),
            ("├─ 📦 Logistics",         "📦 Logistics"),
            ("├─ 🛡️ Safety",            "🛡️ Safety"),
            ("└─ 🔌 Services",          "🔌 Services"),
        ]
        for label, tab_title in tabs:
            sub_item = QTreeWidgetItem(parent_item)
            sub_item.setText(0, f"      {label}")
            sub_item.setText(1, "Report Tab")
            sub_item.setData(0, Qt.UserRole, {
                "type": "report_subtab",
                "report_id": report_id,
                "tab_title": tab_title,
            })
            
    def show_tree_context_menu(self, position):
        item = self.tree_widget.itemAt(position)
        if not item:
            return

        menu = QMenu()
        data = item.data(0, Qt.UserRole)

        if data:
            item_type = data.get("type")
            item_id = data.get("id")

            if item_type == "company":
                act = QAction("📁 Add Project", self)
                act.triggered.connect(
                    lambda: self.new_project_dialog_for_company(item_id)
                )
                menu.addAction(act)

                # ✅ Delete Company
                del_act = QAction("🗑️ Delete Company", self)
                del_act.triggered.connect(
                    lambda: self._delete_company(item_id)
                )
                menu.addAction(del_act)

            elif item_type == "project":
                act = QAction("🛢️ Add Well", self)
                act.triggered.connect(
                    lambda: self.new_well_dialog(item_id)
                )
                menu.addAction(act)

                # ✅ Delete Project
                del_act = QAction("🗑️ Delete Project", self)
                del_act.triggered.connect(
                    lambda: self._delete_project(item_id)
                )
                menu.addAction(del_act)

            elif item_type == "well":
                act = QAction("📊 Add Section", self)
                act.triggered.connect(
                    lambda: self.new_section_dialog_for_well(item_id)
                )
                menu.addAction(act)

                # ✅ Delete Well
                del_act = QAction("🗑️ Delete Well", self)
                del_act.triggered.connect(
                    lambda: self._delete_well(item_id)
                )
                menu.addAction(del_act)

            elif item_type == "section":
                act = QAction("📅 Add Daily Report", self)
                act.triggered.connect(
                    lambda: self.new_daily_report_dialog_for_section(item_id)
                )
                menu.addAction(act)

                act2 = QAction("📐 Open Section Data", self)
                act2.triggered.connect(
                    lambda: self._open_section_data(
                        item_id, data.get("well_id")
                    )
                )
                menu.addAction(act2)

                # ✅ Delete Section
                del_act = QAction("🗑️ Delete Section", self)
                del_act.triggered.connect(
                    lambda: self._delete_section(
                        item_id, data.get("well_id")
                    )
                )
                menu.addAction(del_act)

            elif item_type == "daily_report":
                act = QAction("🗑️ Delete Report", self)
                act.triggered.connect(
                    lambda: self.delete_daily_report(item_id)
                )
                menu.addAction(act)

        menu.addSeparator()
        refresh_act = QAction("🔄 Refresh", self)
        refresh_act.triggered.connect(self.populate_hierarchy)
        menu.addAction(refresh_act)

        menu.exec(self.tree_widget.viewport().mapToGlobal(position))
        
    def _delete_company(self, company_id: int):
        """حذف شرکت"""
        reply = QMessageBox.question(
            self, "Delete Company",
            "Delete this company and ALL its projects and wells?\n"
            "This cannot be undone!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        session = self.db_manager.create_session()
        try:
            from core.database import Company
            company = session.query(Company).filter(
                Company.id == company_id
            ).first()
            if company:
                session.delete(company)
                session.commit()
                self.status_manager.show_success(
                    "MainWindow", "Company deleted"
                )
                self._invalidate_hierarchy_cache()
                self.populate_hierarchy()
        except Exception as e:
            session.rollback()
            logger.error(f"Delete company error: {e}")
            self.status_manager.show_error(
                "MainWindow", f"Delete failed: {str(e)}"
            )
        finally:
            session.close()

    def _delete_project(self, project_id: int):
        """حذف پروژه"""
        reply = QMessageBox.question(
            self, "Delete Project",
            "Delete this project and ALL its wells?\n"
            "This cannot be undone!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        session = self.db_manager.create_session()
        try:
            from core.database import Project
            project = session.query(Project).filter(
                Project.id == project_id
            ).first()
            if project:
                session.delete(project)
                session.commit()
                self.status_manager.show_success(
                    "MainWindow", "Project deleted"
                )
                self._invalidate_hierarchy_cache()
                self.populate_hierarchy()
        except Exception as e:
            session.rollback()
            logger.error(f"Delete project error: {e}")
            self.status_manager.show_error(
                "MainWindow", f"Delete failed: {str(e)}"
            )
        finally:
            session.close()

    def _delete_well(self, well_id: int):
        """حذف چاه"""
        reply = QMessageBox.question(
            self, "Delete Well",
            "Delete this well and ALL its reports and data?\n"
            "This cannot be undone!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            if self.db_manager.delete_well(well_id):
                # اگر چاه حذف شده همان چاه جاری بود
                if (self.current_well and
                    isinstance(self.current_well, dict) and
                    self.current_well.get('id') == well_id):
                    self.clear_current_well()
                    self.sel_manager.clear()

                self.status_manager.show_success(
                    "MainWindow", "Well deleted"
                )
                self._invalidate_hierarchy_cache()
                self.populate_hierarchy()
            else:
                self.status_manager.show_error(
                    "MainWindow", "Failed to delete well"
                )
        except Exception as e:
            logger.error(f"Delete well error: {e}")
            self.status_manager.show_error(
                "MainWindow", f"Delete failed: {str(e)}"
            )

    def _delete_section(self, section_id: int, well_id: int = None):
        """حذف سکشن"""
        reply = QMessageBox.question(
            self, "Delete Section",
            "Delete this section and ALL its daily reports?\n"
            "This cannot be undone!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        session = self.db_manager.create_session()
        try:
            from core.database import Section
            section = session.query(Section).filter(
                Section.id == section_id
            ).first()
            if section:
                session.delete(section)
                session.commit()
                self.status_manager.show_success(
                    "MainWindow", "Section deleted"
                )
                self._invalidate_hierarchy_cache()
                self.populate_hierarchy()
        except Exception as e:
            session.rollback()
            logger.error(f"Delete section error: {e}")
            self.status_manager.show_error(
                "MainWindow", f"Delete failed: {str(e)}"
            )
        finally:
            session.close()
        
    def on_tree_item_clicked(self, item, column):
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        item_type = data.get("type")

        if item_type == "well":
            well_id = data.get("id")
            if well_id:
                well_data = self.db_manager.get_well_by_id(well_id) or {}
                self.sel_manager.select_well(well_id, well_data)
                self.tab_widget.setCurrentIndex(1)

        elif item_type == "section":
            section_id = data.get("id")
            well_id = data.get("well_id")
            if well_id:
                well_data = self.db_manager.get_well_by_id(well_id) or {}
                self.sel_manager.select_well(well_id, well_data)
            if section_id:
                sections = self.db_manager.get_sections_by_well(
                    well_id
                ) if well_id else []
                section_data = next(
                    (s for s in sections if s['id'] == section_id), {}
                )
                self.sel_manager.select_section(section_id, section_data)
                self.tab_widget.setCurrentIndex(2)

        elif item_type == "daily_report":
            report_id = data.get("report_id") or data.get("id")
            well_id = data.get("well_id")
            section_id = data.get("section_id")

            if well_id:
                well_data = self.db_manager.get_well_by_id(well_id) or {}
                self.sel_manager.select_well(well_id, well_data)

            if section_id:
                sections = self.db_manager.get_sections_by_well(
                    well_id
                ) if well_id else []
                section_data = next(
                    (s for s in sections if s['id'] == section_id), {}
                )
                self.sel_manager.select_section(section_id, section_data)

            if report_id:
                self.sel_manager.select_report(report_id, data)
                self.tab_widget.setCurrentIndex(2)

        elif item_type == "well_tab":
            well_id = data.get("well_id")
            tab_title = data.get("tab_title", "")
            if well_id:
                well_data = self.db_manager.get_well_by_id(well_id) or {}
                self.sel_manager.select_well(well_id, well_data)
            if tab_title:
                for i in range(self.tab_widget.count()):
                    if tab_title in self.tab_widget.tabText(i):
                        self.tab_widget.setCurrentIndex(i)
                        break

        elif item_type == "section_tab":
            well_id = data.get("well_id")
            section_id = data.get("section_id")
            tab_title = data.get("tab_title", "")
            if well_id:
                well_data = self.db_manager.get_well_by_id(well_id) or {}
                self.sel_manager.select_well(well_id, well_data)
            if section_id:
                sections = self.db_manager.get_sections_by_well(well_id) if well_id else []
                section_data = next((s for s in sections if s['id'] == section_id), {})
                self.sel_manager.select_section(section_id, section_data)
            if tab_title:
                for i in range(self.tab_widget.count()):
                    if tab_title in self.tab_widget.tabText(i):
                        self.tab_widget.setCurrentIndex(i)
                        break
                        
        elif item_type == "report_subtab":
            report_id = data.get("report_id")
            tab_title = data.get("tab_title", "")
            
            if report_id and tab_title:
                # ✅ پیدا کردن index واقعی از روی title
                tab_index = None
                for i in range(self.tab_widget.count()):
                    if tab_title in self.tab_widget.tabText(i):
                        tab_index = i
                        break
                
                if tab_index is not None:
                    self.tab_widget.setCurrentIndex(tab_index)
                    self.sel_manager.select_report(report_id, {"id": report_id})
                else:
                    logger.warning(f"Tab '{tab_title}' not found")
                
        else:
            item.setExpanded(not item.isExpanded())

    def _open_section_data(self, section_id, well_id):
        """باز کردن تب Section Data برای سکشن مشخص"""
        if well_id:
            well_data = self.db_manager.get_well_by_id(well_id) or {}
            self.sel_manager.select_well(well_id, well_data)
        if section_id:
            sections = self.db_manager.get_sections_by_well(well_id) if well_id else []
            section_data = next((s for s in sections if s['id'] == section_id), {})
            self.sel_manager.select_section(section_id, section_data)
        # سوئیچ به تب Section Data
        for i in range(self.tab_widget.count()):
            if "Section Data" in self.tab_widget.tabText(i):
                self.tab_widget.setCurrentIndex(i)
                break
                
    # ==================== Status Bar ====================

    def create_status_bar(self):
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        self.status_label = QLabel("✅ Ready")
        self.status_label.setMinimumWidth(200)
        status_bar.addWidget(self.status_label, 1)

        # Middle
        middle = QWidget()
        ml = QHBoxLayout(middle)
        ml.setContentsMargins(10, 0, 10, 0)
        ml.setSpacing(15)

        self.auto_save_label = QLabel("💾 Auto-save: ON")
        ml.addWidget(self.auto_save_label)

        ml.addWidget(QLabel("│"))

        self.user_label = QLabel(f"👤 {self.user['username']}")
        ml.addWidget(self.user_label)

        ml.addWidget(QLabel("│"))

        self.time_label = QLabel()
        self.update_time()
        ml.addWidget(self.time_label)
        ml.addStretch()

        status_bar.addPermanentWidget(middle)

        # Well label
        self.current_well_label = QLabel("🛢️ No well selected")
        self.current_well_label.setMinimumWidth(200)
        self.current_well_label.setAlignment(Qt.AlignRight)
        self.current_well_label.setStyleSheet(
            "padding: 0 10px; background: #f0f0f0; "
            "border-radius: 3px; border: 1px solid #ddd;"
        )
        status_bar.addPermanentWidget(self.current_well_label)

        self.time_timer = QTimer()
        self.time_timer.timeout.connect(self.update_time)
        self.time_timer.start(60000)

    def update_time(self):
        t = QDateTime.currentDateTime().toString("hh:mm AP")
        self.time_label.setText(f"🕒 {t}")

    # ==================== Loading ====================

    def show_loading(self, message: str = "Loading..."):
        if self._loading_dialog is None:
            self._loading_dialog = LoadingDialog(message, self)
        else:
            self._loading_dialog.set_message(message)

        if self._loading_dialog.parent():
            geo = self.geometry()
            dlg_geo = self._loading_dialog.frameGeometry()
            dlg_geo.moveCenter(geo.center())
            self._loading_dialog.move(dlg_geo.topLeft())

        self._loading_dialog.show()
        QApplication.processEvents()

    def hide_loading(self):
        if self._loading_dialog:
            self._loading_dialog.hide()

    # ==================== Tab Events ====================

    def on_tab_changed(self, index):
        tab_name = self.tab_widget.tabText(index)
        self.status_label.setText(f"📑 {tab_name}")
        self.status_manager.show_message(
            "MainWindow", f"Switched to {tab_name}", 1000
        )

    # ==================== Dialog Methods ====================

    def new_company_dialog(self):
        try:
            dialog = NewCompanyDialog(self.db_manager, self)
            if dialog.exec():
                self.status_manager.show_success(
                    "MainWindow", "Company created!"
                )
                self.populate_hierarchy()
                if hasattr(self, 'home_tab'):
                    self.home_tab.refresh()
        except Exception as e:
            logger.error(f"New company error: {e}")
            self.status_manager.show_error("MainWindow", str(e))

    def new_project_dialog(self):
        try:
            dialog = NewProjectDialog(self.db_manager, self)
            if dialog.exec():
                self.status_manager.show_success(
                    "MainWindow", "Project created!"
                )
                self.populate_hierarchy()
        except Exception as e:
            logger.error(f"New project error: {e}")
            self.status_manager.show_error("MainWindow", str(e))

    def new_project_dialog_for_company(self, company_id):
        try:
            dialog = NewProjectDialog(self.db_manager, self)
            for i in range(dialog.company_combo.count()):
                if dialog.company_combo.itemData(i) == company_id:
                    dialog.company_combo.setCurrentIndex(i)
                    break
            if dialog.exec():
                self.populate_hierarchy()
        except Exception as e:
            logger.error(f"New project for company error: {e}")

    def new_well_dialog(self, project_id=None):
        try:
            dialog = NewWellDialog(self.db_manager, self, project_id)
            if dialog.exec():
                self.status_manager.show_success(
                    "MainWindow", "Well created!"
                )
                self._invalidate_hierarchy_cache() 
                self.populate_hierarchy()
                if hasattr(dialog, 'created_id') and dialog.created_id:
                    QTimer.singleShot(
                        300,
                        lambda: self.load_well_with_full_context(
                            dialog.created_id
                        )
                    )
        except Exception as e:
            logger.error(f"New well error: {e}")
            self.status_manager.show_error("MainWindow", str(e))

    def new_section_dialog_for_well(self, well_id):
        try:
            dialog = NewSectionDialog(self.db_manager, self, well_id)
            if dialog.exec():
                self.populate_hierarchy()
        except Exception as e:
            logger.error(f"New section error: {e}")

    def new_daily_report_dialog_for_section(self, section_id):
        try:
            dialog = NewDailyReportDialog(self.db_manager, self, section_id)
            if dialog.exec():
                self.populate_hierarchy()
        except Exception as e:
            logger.error(f"New daily report error: {e}")

    def delete_daily_report(self, report_id: int):
        reply = QMessageBox.question(
            self, "Confirm Delete",
            "Delete this daily report? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                session = self.db_manager.create_session()
                report = session.query(DailyReport).filter(
                    DailyReport.id == report_id
                ).first()
                if report:
                    session.delete(report)
                    session.commit()
                    self.status_manager.show_success(
                        "MainWindow", "Report deleted"
                    )
                    self.populate_hierarchy()
                session.close()
            except Exception as e:
                logger.error(f"Delete report error: {e}")
                self.status_manager.show_error("MainWindow", str(e))

    def open_well_dialog(self):
        if hasattr(self, 'well_info_tab'):
            self.well_info_tab.load_well_dialog()

    # ==================== ✅ ALL MISSING METHODS ====================

    def open_export(self):
        """سوئیچ به تب Export."""
        for i in range(self.tab_widget.count()):
            if "Export" in self.tab_widget.tabText(i):
                self.tab_widget.setCurrentIndex(i)
                self.status_manager.show_message(
                    "MainWindow", "Switched to Export tab", 2000
                )
                return
        self.status_manager.show_error("MainWindow", "Export tab not found")

    def open_excel_import(self):
        if not self.current_well:
            QMessageBox.warning(
                self, "No Well", "Please select a well first."
            )
            return

        well_id = (
            self.current_well['id']
            if isinstance(self.current_well, dict)
            else self.current_well.id
        )

        try:
            dialog = ExcelImportDialog(self.db_manager, well_id, self)
            dialog.import_completed.connect(self._on_import_completed)
            dialog.exec()

        except ImportError as e:
            QMessageBox.warning(
                self, "Missing Package",
                f"Install required:\npip install openpyxl\n\n{e}"
            )
        except Exception as e:
            logger.error(f"Import dialog error: {e}")
            self.status_manager.show_error("MainWindow", str(e))


    def _on_import_completed(self, results: list):
        """After Import - targeted refresh with IDs"""
        if not results:
            return

        total = sum(r.get('imported', 0) for r in results)
        failed = sum(r.get('failed', 0) for r in results)

        # Find last valid IDs
        report_id = None
        section_id = None
        for r in results:
            if r.get('report_id'):
                report_id = r['report_id']
            if r.get('section_id'):
                section_id = r['section_id']

        well_id = None
        if self.current_well:
            well_id = (
                self.current_well['id']
                if isinstance(self.current_well, dict)
                else self.current_well.id
            )

        message = f"Import done! ✅ {total} imported, ❌ {failed} failed"
        self._show_import_summary(results)
        if failed:
            self.status_manager.show_warning("MainWindow", message)
        else:
            self.status_manager.show_success("MainWindow", message)
        try:
            self.db_manager.log_audit(
                action="import", entity_type="excel", entity_name="multi-tab import",
                details=message, user_id=(self.user or {}).get("id"),
                username=(self.user or {}).get("username", ""),
            )
        except Exception:
            logger.debug("Import audit log failed", exc_info=True)

        # Targeted refresh if we have IDs
        if report_id and section_id and well_id:
            self._targeted_refresh(well_id, section_id, report_id)
        else:
            self.refresh_all_tabs()

        self._invalidate_hierarchy_cache()
        self.populate_hierarchy()


    def _show_import_summary(self, results):
        """Show an actionable import report instead of a misleading toast."""
        lines = []
        for result in results or []:
            report = result.get("import_report") or {}
            if report:
                lines.append(
                    f"Rows: {report.get('total', 0)} | "
                    f"Errors: {report.get('errors', 0)} | "
                    f"Warnings: {report.get('warnings', 0)}"
                )
                for issue in report.get("issues", [])[:20]:
                    lines.append(
                        f"[{issue.get('level', 'error').upper()}] "
                        f"{issue.get('sheet', '')} row {issue.get('row', '')}: "
                        f"{issue.get('message', '')}"
                    )
            lines.extend(result.get("details", [])[-10:])
        if not lines:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Import Quality Report")
        box.setIcon(QMessageBox.Warning if any("ERROR" in line or "FAILED" in line.upper() for line in lines) else QMessageBox.Information)
        box.setText("Import completed with a detailed quality report.")
        box.setDetailedText("\\n".join(lines))
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()

    def _targeted_refresh(
        self, well_id: int, section_id: int, report_id: int
    ):
        """Precise refresh after import with specific IDs - hybrid mode"""
        try:
            # 1. Load data
            well_data = self.db_manager.get_well_by_id(well_id) or {}
            sections = self.db_manager.get_sections_by_well(well_id)
            section_data = next(
                (s for s in sections if s['id'] == section_id), {}
            )
            report_data = (
                self.db_manager.get_daily_report_by_id(report_id) or {}
            )

            # 2. Update main state
            self.current_well = well_data
            self.current_report_id = report_id

            if well_data.get('name'):
                self.current_well_label.setText(
                    f"🛢️ Well: {well_data['name']}"
                )

            # 3. SelectionManager - force full context
            if hasattr(self.sel_manager, "select_full_context"):
                self.sel_manager.select_full_context(
                    well_id,
                    section_id,
                    report_id,
                    well_data,
                    section_data,
                    report_data,
                )
            else:
                self.sel_manager.select_well(well_id, well_data)
                self.sel_manager.select_section(section_id, section_data)
                self.sel_manager.select_report(report_id, report_data)

            # 4. Manual refresh for legacy / non-reactive tabs
            tab_refreshers = [
                (
                    'well_info_tab',
                    lambda: self.well_info_tab.load_well_by_id(well_id),
                ),
                (
                    'daily_report_tab',
                    lambda: self._refresh_daily_report_tab(
                        well_id, section_id, report_id
                    ),
                ),
                (
                    'drilling_report_tab',
                    lambda: self._refresh_drilling_tab(
                        well_id, report_id
                    ),
                ),
                (
                    'section_data_tab',
                    lambda: (
                        self.section_data_tab.on_well_changed(
                            well_id, well_data
                        ),
                        self.section_data_tab.on_section_changed(
                            section_id, section_data
                        ),
                    ),
                ),
                (
                    'downhole_tab',
                    lambda: self._refresh_simple_tab(
                        self.downhole_tab,
                        well_id,
                        report_id,
                        'load_all_data_from_db',
                    ),
                ),
                (
                    'equipment_widget',
                    lambda: self._refresh_simple_tab(
                        self.equipment_widget,
                        well_id,
                        report_id,
                        'load_all_data',
                    ),
                ),
                (
                    'trajectory_widget',
                    lambda: self._refresh_simple_tab(
                        self.trajectory_widget,
                        well_id,
                        report_id,
                        'update_tabs',
                    ),
                ),
                (
                    'logistics_widget',
                    lambda: self._refresh_simple_tab(
                        self.logistics_widget,
                        well_id,
                        report_id,
                        'update_tabs_well',
                    ),
                ),
                (
                    'safety_widget',
                    lambda: self._refresh_simple_tab(
                        self.safety_widget,
                        well_id,
                        report_id,
                        'load_data',
                    ),
                ),
                (
                    'services_widget',
                    lambda: self._refresh_services_tab(
                        well_id, report_id
                    ),
                ),
                (
                    'planning_widget',
                    lambda: self._refresh_planning_tab(
                        well_id, section_id, report_id,
                        well_data, section_data, report_data,
                    ),
                ),
                (
                    'analysis_widget',
                    lambda: self.analysis_widget.on_well_changed(
                        well_id, well_data
                    ),
                ),
                (
                    'export_widget',
                    lambda: self.export_widget.set_current_well(
                        well_id, well_data
                    ),
                ),
                (
                    'wellbore_schematic_tab',
                    lambda: setattr(
                        self.wellbore_schematic_tab,
                        'current_well_id',
                        well_id,
                    ),
                ),
            ]

            for tab_name, refresher in tab_refreshers:
                if hasattr(self, tab_name):
                    try:
                        refresher()
                    except Exception as e:
                        logger.error(f"{tab_name} refresh error: {e}")

            # 5. Optional delayed actions
            if hasattr(self, 'wellbore_schematic_tab'):
                try:
                    QTimer.singleShot(
                        300,
                        self.wellbore_schematic_tab.auto_generate
                    )
                except Exception as e:
                    logger.error(f"Schematic auto-generate error: {e}")

            # 6. Go to Daily Report tab
            QTimer.singleShot(200, self._switch_to_daily_report_tab)

        except Exception as e:
            logger.error(
                f"Targeted refresh error: {e}",
                exc_info=True
            )
            self.refresh_all_tabs()

    def _refresh_daily_report_tab(
        self, well_id: int, section_id: int, report_id: int
    ):
        tab = self.daily_report_tab
        tab.current_well_id = well_id
        tab.current_section_id = section_id
        tab.current_report_id = report_id
        if hasattr(tab, 'current_daily_report_id'):
            tab.current_daily_report_id = report_id
        tab.load_report_by_id(report_id)


    def _refresh_drilling_tab(self, well_id: int, report_id: int):
        tab = self.drilling_report_tab
        if hasattr(tab, 'set_current_well'):
            tab.set_current_well(well_id)
        if hasattr(tab, 'set_current_report'):
            tab.set_current_report(report_id)


    def _refresh_simple_tab(
        self, tab, well_id: int, report_id: int, load_method: str
    ):
        if hasattr(tab, 'current_well'):
            tab.current_well = well_id
        if hasattr(tab, 'current_well_id'):
            tab.current_well_id = well_id
        if hasattr(tab, 'current_report_id'):
            tab.current_report_id = report_id
        if hasattr(tab, load_method):
            getattr(tab, load_method)()


    def _refresh_services_tab(self, well_id: int, report_id: int):
        tab = self.services_widget
        if hasattr(tab, 'current_well_id'):
            tab.current_well_id = well_id
        if hasattr(tab, 'current_report_id'):
            tab.current_report_id = report_id
        if hasattr(tab, 'material_handling_tab'):
            if hasattr(tab.material_handling_tab, 'set_current_well'):
                tab.material_handling_tab.set_current_well(well_id)
            if hasattr(tab.material_handling_tab, 'set_current_report'):
                tab.material_handling_tab.set_current_report(report_id)


    def _refresh_planning_tab(
        self,
        well_id: int,
        section_id: int,
        report_id: int,
        well_data: dict,
        section_data: dict,
        report_data: dict,
    ):
        tab = self.planning_widget
        if hasattr(tab, 'on_well_changed'):
            tab.on_well_changed(well_id, well_data)
        if hasattr(tab, 'on_section_changed'):
            tab.on_section_changed(section_id, section_data)
        if hasattr(tab, 'on_report_changed'):
            tab.on_report_changed(report_id, report_data)


    def _switch_to_daily_report_tab(self):
        """Switch to Daily Report tab after import"""
        for i in range(self.tab_widget.count()):
            if "Daily Report" in self.tab_widget.tabText(i):
                self.tab_widget.setCurrentIndex(i)
                break

    def open_well_plan(self):
        """باز کردن Well Plan Dialog."""
        if not self.current_well:
            QMessageBox.warning(self, "No Well", "Please select a well first.")
            return

        well_id = (
            self.current_well['id']
            if isinstance(self.current_well, dict)
            else self.current_well.id
        )

        try:
            from dialogs.planning_dialog import WellPlanDialog
            dialog = WellPlanDialog(self.db_manager, well_id, self)
            if dialog.exec():
                self.status_manager.show_success(
                    "MainWindow", "Well plan saved!"
                )
                if hasattr(self, 'planning_widget'):
                    if hasattr(self.planning_widget, 'load_plans_list'):
                        self.planning_widget.load_plans_list()
        except Exception as e:
            logger.error(f"Well plan error: {e}")
            for i in range(self.tab_widget.count()):
                if "Planning" in self.tab_widget.tabText(i):
                    self.tab_widget.setCurrentIndex(i)
                    self.status_manager.show_success("MainWindow", "Switched to Planning tab")
                    return
            QMessageBox.information(
                self, "Planning", "Please use the 'Planning' tab to manage well plans."
            )

    def open_calculator(self):
        """باز کردن Drilling Calculator."""
        try:
            dialog = DrillingCalculatorDialog(self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Calculator error: {e}")

    def return_to_startup(self):
        """بازگشت به صفحه Startup."""
        reply = QMessageBox.question(
            self, "Return to Startup",
            "Return to startup screen?\nCurrent work will be auto-saved.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.save_current_tab()
            self.hide()
            try:
                dialog = StartupDialog(self.db_manager, self)
                if dialog.exec():
                    result = dialog.get_result()
                    self.apply_startup_result(result)
                self.show()
                self.raise_()
                self.activateWindow()
            except Exception as e:
                logger.error(f"Return to startup error: {e}")
                self.show()

    def new_daily_report_from_toolbar(self):
        """ایجاد گزارش روزانه جدید."""
        if hasattr(self, 'daily_report_tab') and self.current_well:
            self.daily_report_tab.create_daily_report_for_current_section()
        else:
            self.status_manager.show_error("MainWindow", "No well selected")

    def copy_previous_from_toolbar(self):
        """کپی از گزارش قبلی."""
        if hasattr(self, 'daily_report_tab') and self.current_report_id:
            self.daily_report_tab.copy_previous_day()
        else:
            self.status_manager.show_error("MainWindow", "No report selected")

    def show_settings(self):
        """نمایش دیالوگ Settings."""
        try:
            from dialogs.settings_dialog import SettingsDialog
            dialog = SettingsDialog(self)
            if dialog.exec():
                self.status_manager.show_success(
                    "MainWindow", "Settings saved!"
                )
                self._apply_settings()
        except Exception as e:
            logger.error(f"Settings error: {e}")

    def _apply_settings(self):
        settings = QSettings("Nikan", "DrillMaster")
        theme = settings.value("ui/theme", "Light")

        if theme == "Dark":
            QApplication.instance().setStyleSheet("""
                QMainWindow { background: #1e1e2e; }
                QWidget { background: #1e1e2e; color: #ecf0f1; }
                QTabWidget::pane { background: #2c3e50; border: 1px solid #34495e; }
                QTabBar::tab { background: #34495e; color: #ecf0f1; padding: 8px 16px; }
                QTabBar::tab:selected { background: #3498db; color: white; }
                QGroupBox { border: 1px solid #34495e; border-radius: 4px; margin-top: 10px; padding-top: 10px; color: #ecf0f1; }
                QGroupBox::title { color: #3498db; }
                QLineEdit, QTextEdit, QPlainTextEdit { background: #2c3e50; color: #ecf0f1; border: 1px solid #34495e; border-radius: 4px; padding: 4px; }
                QLineEdit:focus, QTextEdit:focus { border: 1px solid #3498db; }
                QComboBox { background: #2c3e50; color: #ecf0f1; border: 1px solid #34495e; border-radius: 4px; padding: 4px; }
                QSpinBox, QDoubleSpinBox { background: #2c3e50; color: #ecf0f1; border: 1px solid #34495e; border-radius: 4px; }
                QDateEdit, QTimeEdit { background: #2c3e50; color: #ecf0f1; border: 1px solid #34495e; }
                QPushButton { background: #34495e; color: #ecf0f1; border: 1px solid #34495e; border-radius: 4px; padding: 6px 12px; }
                QPushButton:hover { background: #3c5570; }
                QPushButton:pressed { background: #2c3e50; }
                QTableWidget { background: #1e1e2e; alternate-background-color: #2c3e50; gridline-color: #34495e; color: #ecf0f1; }
                QTableWidget::item:selected { background: #3498db; color: white; }
                QHeaderView::section { background: #2c3e50; color: #ecf0f1; padding: 5px; border: none; font-weight: bold; }
                QTreeWidget { background: #1e1e2e; color: #ecf0f1; border: 1px solid #34495e; }
                QTreeWidget::item:selected { background: #3498db; color: white; }
                QScrollBar:vertical { background: #2c3e50; width: 10px; }
                QScrollBar::handle:vertical { background: #34495e; border-radius: 5px; }
                QScrollBar:horizontal { background: #2c3e50; height: 10px; }
                QScrollBar::handle:horizontal { background: #34495e; border-radius: 5px; }
                QStatusBar { background: #2c3e50; color: #ecf0f1; border-top: 1px solid #34495e; }
                QToolBar { background: #2c3e50; border-bottom: 1px solid #34495e; }
                QDockWidget { color: #ecf0f1; }
                QDockWidget::title { background: #2c3e50; color: #ecf0f1; padding: 6px; }
                QMenu { background: #2c3e50; color: #ecf0f1; border: 1px solid #34495e; }
                QMenu::item:selected { background: #3498db; }
                QMenuBar { background: #2c3e50; color: #ecf0f1; }
                QMenuBar::item:selected { background: #3498db; }
                QProgressBar { border: 1px solid #34495e; border-radius: 4px; text-align: center; color: #ecf0f1; }
                QProgressBar::chunk { background: #3498db; border-radius: 4px; }
                QCheckBox { color: #ecf0f1; }
                QRadioButton { color: #ecf0f1; }
                QLabel { color: #ecf0f1; }
                QListWidget { background: #1e1e2e; color: #ecf0f1; border: 1px solid #34495e; }
                QListWidget::item:selected { background: #3498db; }
            """)
        else:
            QApplication.instance().setStyleSheet("")

        autosave = settings.value("autosave/enabled", True, type=bool)
        if hasattr(self, 'auto_save_manager'):
            self.auto_save_manager.set_enabled(autosave)
            status = "ON" if autosave else "OFF"
            if hasattr(self, 'auto_save_action'):
                self.auto_save_action.setChecked(autosave)
                self.auto_save_action.setText(f"💾 Auto-save: {status}")
            if hasattr(self, 'auto_save_label'):
                self.auto_save_label.setText(f"💾 Auto-save: {status}")
                
    def show_help(self):
        """نمایش Help."""
        help_text = """
        <h2>DrillMaster - User Guide</h2>
        <h3>Getting Started</h3>
        <ol>
        <li>Create a company, project, then a well</li>
        <li>Select a well from the tree on the left</li>
        <li>Create sections and daily reports</li>
        <li>Fill in drilling data in each tab</li>
        </ol>
        <h3>Keyboard Shortcuts</h3>
        <table border="1" cellpadding="5">
        <tr><th>Shortcut</th><th>Action</th></tr>
        <tr><td>Ctrl+N</td><td>New Well</td></tr>
        <tr><td>Ctrl+O</td><td>Open Well</td></tr>
        <tr><td>Ctrl+S</td><td>Save</td></tr>
        <tr><td>Ctrl+Shift+S</td><td>Save All</td></tr>
        <tr><td>Ctrl+R</td><td>New Daily Report</td></tr>
        <tr><td>Ctrl+I</td><td>Import from Excel</td></tr>
        <tr><td>Ctrl+E</td><td>Export</td></tr>
        <tr><td>F5</td><td>Refresh</td></tr>
        <tr><td>F1</td><td>Help</td></tr>
        <tr><td>Ctrl+Q</td><td>Exit</td></tr>
        </table>
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("DrillMaster Help")
        dialog.setMinimumSize(500, 400)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setHtml(help_text)
        layout.addWidget(browser)
        btn = QDialogButtonBox(QDialogButtonBox.Close)
        btn.rejected.connect(dialog.reject)
        layout.addWidget(btn)
        dialog.exec()

    def show_about(self):
        QMessageBox.about(
            self, "About DrillMaster",
            "<h2>DrillMaster v1.0.0</h2>"
            "<p>Drilling Operations Management System</p>"
            "<p>© 2024 DrillMaster Inc.</p>"
        )

    def print_report(self):
        """چاپ گزارش."""
        current_tab = self.tab_widget.currentWidget()
        if hasattr(current_tab, 'print_report'):
            current_tab.print_report()
            return

        try:
            printer = QPrinter(QPrinter.HighResolution)
            dialog = QPrintDialog(printer, self)
            if dialog.exec() == QPrintDialog.Accepted:
                tab_name = self.tab_widget.tabText(
                    self.tab_widget.currentIndex()
                )
                html = f"""
                <html><body>
                <h1>DrillMaster - {tab_name}</h1>
                <p>Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                <p>User: {self.user.get('username', '')}</p>
                </body></html>
                """
                from PySide6.QtGui import QTextDocument
                doc = QTextDocument()
                doc.setHtml(html)
                doc.print_(printer)
                self.status_manager.show_success(
                    "MainWindow", "Sent to printer"
                )
        except Exception as e:
            logger.error(f"Print error: {e}")

    # ==================== Save/Load ====================

    def save_current_tab(self):
        current_tab = self.tab_widget.currentWidget()
        if hasattr(current_tab, 'save_data'):
            try:
                if current_tab.save_data():
                    tab_name = self.tab_widget.tabText(
                        self.tab_widget.currentIndex()
                    )
                    self.status_manager.show_success(
                        "MainWindow", f"Saved: {tab_name}"
                    )
                    self._invalidate_hierarchy_cache()
                else:
                    self.status_manager.show_error(
                        "MainWindow", "Save failed"
                    )
            except Exception as e:
                self.status_manager.show_error("MainWindow", str(e))
        else:
            self.status_manager.show_message(
                "MainWindow", "Nothing to save", 2000
            )
    def save_all_tabs(self):
        saved = 0
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if hasattr(tab, 'save_data'):
                try:
                    if tab.save_data():
                        saved += 1
                except Exception as e:
                    logger.error(
                        f"Error saving {self.tab_widget.tabText(i)}: {e}"
                    )
        self.status_manager.show_success(
            "MainWindow", f"Saved {saved} tabs"
        )
        return saved

    def auto_save(self):
        current_tab = self.tab_widget.currentWidget()
        if hasattr(current_tab, 'save_data'):
            try:
                current_tab.save_data()
            except Exception as e:
                logger.error(f"Auto-save error: {e}")

    def refresh_all_tabs(self):
        self.show_loading("Refreshing...")
        try:
            self.populate_hierarchy()
            for i in range(self.tab_widget.count()):
                tab = self.tab_widget.widget(i)
                if hasattr(tab, 'refresh'):
                    try:
                        tab.refresh()
                    except Exception as e:
                        logger.error(
                            f"Refresh error in {self.tab_widget.tabText(i)}: {e}"
                        )
            self.status_manager.show_success("MainWindow", "Refreshed")
        finally:
            self.hide_loading()

    def toggle_auto_save(self, enabled):
        self.auto_save_manager.set_enabled(enabled)
        status = "ON" if enabled else "OFF"
        self.auto_save_action.setText(f"💾 Auto-save: {status}")
        self.auto_save_label.setText(f"💾 Auto-save: {status}")

    # ==================== Well Loading ====================

    def load_well_with_full_context(self, well_id: int):
        """لود چاه با آخرین سکشن و گزارش."""
        try:
            well_data = self.db_manager.get_well_by_id(well_id)
            if not well_data:
                return

            sections = self.db_manager.get_sections_by_well(well_id)
            last_section = None
            if sections:
                last_section = sorted(
                    sections,
                    key=lambda x: x.get('depth_to', 0),
                    reverse=True
                )[0]

            last_report = None
            if last_section:
                reports = self.db_manager.get_daily_reports_by_section(
                    last_section['id']
                )
                if reports:
                    last_report = reports[0]

            self.current_well = well_data
            self.current_well_label.setText(
                f"🛢️ Well: {well_data['name']}"
            )

            self.sel_manager.select_well(well_id, well_data)

            if last_section:
                self.sel_manager.select_section(
                    last_section['id'], last_section
                )

            if last_report:
                self.sel_manager.select_report(
                    last_report['id'], last_report
                )
                self.current_report_id = last_report['id']

            self.select_item_in_tree("well", well_id)

            if hasattr(self, 'well_info_tab'):
                self.well_info_tab.load_well_by_id(well_id)

            if last_report and hasattr(self, 'daily_report_tab'):
                self.daily_report_tab.load_report_by_id(last_report['id'])

            tab_index = 2 if last_report else 1
            self.tab_widget.setCurrentIndex(tab_index)

            msg = f"Well '{well_data['name']}' loaded"
            if last_report:
                msg += f" with Report #{last_report.get('report_number')}"
            self.status_manager.show_success("MainWindow", msg)

        except Exception as e:
            logger.error(f"Load well error: {e}")
            self.status_manager.show_error("MainWindow", str(e))

    def apply_startup_result(self, result):
        """اعمال نتیجه Startup Dialog."""
        if not result:
            return
        try:
            action = result.get("action")
            if action == "load_well":
                well_id = result.get("well_id")
                if well_id:
                    QTimer.singleShot(
                        300,
                        lambda: self.load_well_with_full_context(well_id)
                    )
            elif action == "load_project":
                project_id = result.get("project_id")
                if project_id:
                    QTimer.singleShot(
                        300,
                        lambda: self.load_project_with_context(project_id)
                    )
        except Exception as e:
            logger.error(f"Startup result error: {e}")

    def load_project_with_context(self, project_id: int):
        """لود پروژه."""
        try:
            session = self.db_manager.create_session()
            from core.database import Project, Well
            project = session.query(Project).filter(
                Project.id == project_id
            ).first()
            if project:
                well = session.query(Well).filter(
                    Well.project_id == project_id
                ).first()
                if well:
                    session.close()
                    self.load_well_with_full_context(well.id)
                    return
            session.close()
        except Exception as e:
            logger.error(f"Load project error: {e}")

    def select_item_in_tree(self, item_type: str, item_id: int):
        """انتخاب آیتم در درخت."""
        def find_recursive(item):
            data = item.data(0, Qt.UserRole)
            if (data and data.get("type") == item_type
                    and data.get("id") == item_id):
                return item
            for i in range(item.childCount()):
                found = find_recursive(item.child(i))
                if found:
                    return found
            return None

        for i in range(self.tree_widget.topLevelItemCount()):
            found = find_recursive(self.tree_widget.topLevelItem(i))
            if found:
                self.tree_widget.setCurrentItem(found)
                self.tree_widget.scrollToItem(found)
                parent = found.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
                found.setExpanded(True)
                break

    # ==================== Signal Handlers ====================
    def on_well_changed(self, well_id, well_data):
        if well_data and isinstance(well_data, dict):
            self.current_well = well_data
        else:
            self.current_well = {'id': well_id, 'name': str(well_id)}
        
        if hasattr(self, 'current_well_label'):
            name = self.current_well.get('name', 'Unknown')
            self.current_well_label.setText(f"🛢️ Well: {name}")
        
        self.current_report_id = None

    def on_section_changed(self, section_id, section_data):
        pass

    def set_current_well(self, well_id, well_data):
        self.sel_manager.select_well(well_id, well_data)
        if hasattr(self, 'current_well_label') and well_data:
            self.current_well_label.setText(
                f"🛢️ Well: {well_data.get('name', 'Unknown')}"
            )

    def clear_current_well(self):
        self.current_well = None
        if hasattr(self, 'current_well_label'):
            self.current_well_label.setText("🛢️ No well selected")

    # ==================== Edit Actions ====================

    def undo_action(self):
        focused = self.focusWidget()
        if hasattr(focused, 'undo'):
            focused.undo()

    def redo_action(self):
        focused = self.focusWidget()
        if hasattr(focused, 'redo'):
            focused.redo()

    def cut_action(self):
        focused = self.focusWidget()
        if hasattr(focused, 'cut'):
            focused.cut()

    def copy_action(self):
        focused = self.focusWidget()
        if hasattr(focused, 'copy'):
            focused.copy()

    def paste_action(self):
        focused = self.focusWidget()
        if hasattr(focused, 'paste'):
            focused.paste()

    # ==================== Recent ====================

    def update_recent_menu(self):
        if not hasattr(self, 'recent_menu'):
            return
        self.recent_menu.clear()
        no_act = QAction("No recent wells", self)
        no_act.setEnabled(False)
        self.recent_menu.addAction(no_act)

    # ==================== Backup ====================

    def backup_database(self):
        import shutil
        try:
            src = "drillmaster.db"
            if not os.path.exists(src):
                QMessageBox.warning(self, "Backup", "Database not found!")
                return
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save Backup",
                f"drillmaster_backup_{timestamp}.db",
                "Database Files (*.db)"
            )
            if filename:
                shutil.copy2(src, filename)
                self.status_manager.show_success(
                    "MainWindow", f"Backup saved: {filename}"
                )
        except Exception as e:
            logger.error(f"Backup error: {e}")

    # ==================== Cleanup ====================

    def cleanup(self):
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if hasattr(tab, 'cleanup'):
                try:
                    tab.cleanup()
                except Exception:
                    pass

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(50, self.ensure_menubar_visible)

    def _auto_backup(self):
        try:
            if self.db_manager:
                path = self.db_manager.auto_backup()
                if path:
                    logger.info(f"Auto-backup: {path}")
        except Exception as e:
            logger.error(f"Auto-backup error: {e}")

    def apply_viewer_mode(self):
        """غیرفعال کردن edit برای viewer"""
        if hasattr(self, 'auto_save_action'):
            self.auto_save_action.setEnabled(False)
            self.auto_save_action.setText("💾 View Only")

        self.status_label.setText("👁️ View Only Mode")
        self.status_label.setStyleSheet(
            "color: #e67e22; font-weight: bold;"
        )

    def _is_worker_valid(self, worker) -> bool:
        """بررسی معتبر بودن worker از نظر Qt/Python"""
        try:
            return worker is not None and isValid(worker)
        except Exception:
            return False

    def _cleanup_hierarchy_worker(self, *args):
        """پاکسازی reference مربوط به hierarchy worker"""
        worker = getattr(self, '_hierarchy_worker', None)
        if worker is None:
            return

        try:
            if self._is_worker_valid(worker):
                worker.deleteLater()
        except RuntimeError:
            pass
        except Exception as e:
            logger.debug(f"Hierarchy worker cleanup warning: {e}")

        self._hierarchy_worker = None