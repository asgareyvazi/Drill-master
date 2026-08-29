"""MainWindow Toolbar — extracted from main_window.py for maintainability.

Provides toolbar creation and action definitions.
"""

import logging
from PySide6.QtWidgets import QToolBar, QAction, QLineEdit, QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import QSize, Qt

logger = logging.getLogger(__name__)


def create_main_toolbar(main_window) -> QToolBar:
    """Create the main toolbar with all actions."""
    toolbar = QToolBar("Main Toolbar")
    toolbar.setObjectName("MainToolbar")
    toolbar.setIconSize(QSize(24, 24))
    toolbar.setMovable(False)
    main_window.addToolBar(toolbar)

    def add_action(text, tooltip, slot, shortcut=None):
        act = QAction(text, main_window)
        act.setToolTip(tooltip)
        act.triggered.connect(slot)
        if shortcut:
            act.setShortcut(shortcut)
        toolbar.addAction(act)
        return act

    add_action("🏠 Home", "Return to startup", main_window.return_to_startup)
    toolbar.addSeparator()
    add_action("🏢 Company", "New Company", main_window.new_company_dialog)
    add_action("📁 Project", "New Project", main_window.new_project_dialog)
    add_action("🛢️ Well", "New Well (Ctrl+N)", main_window.new_well_dialog, "Ctrl+N")
    toolbar.addSeparator()
    add_action("📂 Open", "Open Well (Ctrl+O)", main_window.open_well_dialog, "Ctrl+O")
    toolbar.addSeparator()
    add_action("📋 Plan", "Well Plan", main_window.open_well_plan)
    toolbar.addSeparator()
    add_action("💾 Save", "Save (Ctrl+S)", main_window.save_current_tab, "Ctrl+S")
    add_action("💾 All", "Save All (Ctrl+Shift+S)", main_window.save_all_tabs, "Ctrl+Shift+S")
    toolbar.addSeparator()
    add_action("📅 Report", "New Daily Report (Ctrl+R)", main_window.new_daily_report_from_toolbar, "Ctrl+R")
    add_action("📋 Copy", "Copy Previous", main_window.copy_previous_from_toolbar)
    toolbar.addSeparator()
    add_action("📊 Import", "Import from Excel (Ctrl+I)", main_window.open_excel_import, "Ctrl+I")
    add_action("📤 Export", "Export (Ctrl+E)", main_window.open_export, "Ctrl+E")
    add_action("🖨️ Print", "Print (Ctrl+P)", main_window.print_report, "Ctrl+P")
    toolbar.addSeparator()
    add_action("🔄 Refresh", "Refresh (F5)", main_window.refresh_all_tabs, "F5")
    toolbar.addSeparator()

    # Toggle Hierarchy
    main_window.toggle_hierarchy_action = QAction("📂 Panel", main_window)
    main_window.toggle_hierarchy_action.setCheckable(True)
    main_window.toggle_hierarchy_action.setChecked(True)
    main_window.toggle_hierarchy_action.setToolTip("Show/Hide Hierarchy (Ctrl+H)")
    main_window.toggle_hierarchy_action.setShortcut("Ctrl+H")
    main_window.toggle_hierarchy_action.toggled.connect(main_window._toggle_hierarchy)
    toolbar.addAction(main_window.toggle_hierarchy_action)

    toolbar.addSeparator()
    add_action("⚙️ Settings", "Settings (Ctrl+,)", main_window.show_settings, "Ctrl+,")
    add_action("❓ Help", "Help (F1)", main_window.show_help, "F1")
    toolbar.addSeparator()

    main_window.auto_save_action = QAction("💾 Auto-save: ON", main_window)
    main_window.auto_save_action.setCheckable(True)
    main_window.auto_save_action.setChecked(True)
    main_window.auto_save_action.toggled.connect(main_window.toggle_auto_save)
    toolbar.addAction(main_window.auto_save_action)
    toolbar.addSeparator()

    # Global Search
    main_window.search_input = QLineEdit()
    main_window.search_input.setPlaceholderText("🔍 Search...")
    main_window.search_input.setFixedWidth(200)
    main_window.search_input.setStyleSheet(
        "border: 1px solid #bdc3c7; border-radius: 4px; padding: 4px 8px; font-size: 11px;"
    )
    main_window.search_input.returnPressed.connect(main_window._global_search)
    toolbar.addWidget(main_window.search_input)
    toolbar.addSeparator()

    # User label
    user_widget = QWidget()
    ul = QHBoxLayout(user_widget)
    ul.setContentsMargins(5, 0, 5, 0)
    ul.addWidget(QLabel("👤"))
    user_lbl = QLabel(f"{main_window.user['username']} ({main_window.user['role']})")
    user_lbl.setStyleSheet("font-weight: bold; color: #2c3e50;")
    ul.addWidget(user_lbl)
    toolbar.addWidget(user_widget)

    return toolbar
