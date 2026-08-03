# core/common_widgets.py - فایل جدید
"""
Common reusable widgets برای استفاده در همه تب‌ها
"""
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from core.managers import ExportManager
import csv
import logging

logger = logging.getLogger(__name__)


class CommonTableWidget(QWidget):
    """
    جدول استاندارد با Add/Remove/Export/Import
    برای استفاده در همه تب‌ها به جای کد تکراری
    """

    row_added = Signal(int)        # row index
    row_removed = Signal(int)      # row index
    data_changed = Signal()

    def __init__(
        self,
        headers: list,
        parent=None,
        show_toolbar: bool = True,
        alternating_colors: bool = True,
        min_height: int = 200,
    ):
        super().__init__(parent)
        self.headers = headers
        self._setup_ui(show_toolbar, alternating_colors, min_height)

    def _setup_ui(self, show_toolbar, alternating_colors, min_height):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        # Toolbar
        if show_toolbar:
            self.toolbar = self._create_toolbar()
            layout.addWidget(self.toolbar)

        # Table
        self.table = QTableWidget(0, len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(alternating_colors)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self.table.setMinimumHeight(min_height)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #dee2e6;
            }
            QTableWidget::item:selected {
                background: #0078d4;
                color: white;
            }
            QHeaderView::section {
                background: #2c3e50;
                color: white;
                padding: 5px;
                font-weight: bold;
                border: none;
            }
        """)

        layout.addWidget(self.table)

        # Summary label
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(
            "color: #666; font-size: 10px; padding: 2px;"
        )
        layout.addWidget(self.summary_label)

    def _create_toolbar(self) -> QWidget:
        toolbar = QWidget()
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(0, 0, 0, 3)
        layout.setSpacing(5)

        self.add_btn = QPushButton("➕ Add")
        self.add_btn.setStyleSheet(
            "background: #27ae60; color: white; "
            "padding: 4px 10px; border-radius: 3px; border: none;"
        )
        self.add_btn.clicked.connect(self._on_add_clicked)

        self.remove_btn = QPushButton("➖ Remove")
        self.remove_btn.setStyleSheet(
            "background: #e74c3c; color: white; "
            "padding: 4px 10px; border-radius: 3px; border: none;"
        )
        self.remove_btn.clicked.connect(self._on_remove_clicked)

        self.export_btn = QPushButton("📤 Export")
        self.export_btn.setStyleSheet(
            "background: #3498db; color: white; "
            "padding: 4px 10px; border-radius: 3px; border: none;"
        )
        self.export_btn.clicked.connect(self._on_export_clicked)

        self.import_btn = QPushButton("📥 Import")
        self.import_btn.setStyleSheet(
            "background: #9b59b6; color: white; "
            "padding: 4px 10px; border-radius: 3px; border: none;"
        )
        self.import_btn.clicked.connect(self._on_import_clicked)

        layout.addWidget(self.add_btn)
        layout.addWidget(self.remove_btn)
        layout.addWidget(self.export_btn)
        layout.addWidget(self.import_btn)
        layout.addStretch()

        return toolbar

    # ==================== Public API ====================

    def add_row(self, data: list = None) -> int:
        """اضافه کردن ردیف جدید."""
        row = self.table.rowCount()
        self.table.insertRow(row)

        if data:
            for col, val in enumerate(data):
                if col < self.table.columnCount():
                    item = QTableWidgetItem(str(val) if val is not None else "")
                    item.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row, col, item)

        self._update_summary()
        self.row_added.emit(row)
        self.data_changed.emit()
        return row

    def remove_selected_row(self) -> bool:
        """حذف ردیف انتخاب‌شده."""
        row = self.table.currentRow()
        if row < 0:
            return False
        self.table.removeRow(row)
        self._update_summary()
        self.row_removed.emit(row)
        self.data_changed.emit()
        return True

    def get_all_data(self) -> list:
        """دریافت همه داده‌های جدول."""
        data = []
        for row in range(self.table.rowCount()):
            row_data = {}
            for col in range(self.table.columnCount()):
                header = self.headers[col] if col < len(self.headers) else f"col_{col}"
                item = self.table.item(row, col)
                row_data[header] = item.text() if item else ""
            data.append(row_data)
        return data

    def load_data(self, data: list):
        """بارگذاری داده‌ها در جدول."""
        self.table.setRowCount(0)
        if not data:
            return
        for row_data in data:
            row = self.table.rowCount()
            self.table.insertRow(row)
            if isinstance(row_data, dict):
                for col, header in enumerate(self.headers):
                    val = row_data.get(header, "")
                    item = QTableWidgetItem(str(val) if val is not None else "")
                    item.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row, col, item)
            elif isinstance(row_data, (list, tuple)):
                for col, val in enumerate(row_data):
                    if col < self.table.columnCount():
                        item = QTableWidgetItem(str(val) if val is not None else "")
                        item.setTextAlignment(Qt.AlignCenter)
                        self.table.setItem(row, col, item)
        self._update_summary()

    def clear(self):
        """پاک کردن جدول."""
        self.table.setRowCount(0)
        self._update_summary()

    def row_count(self) -> int:
        return self.table.rowCount()

    def set_column_width(self, col: int, width: int):
        self.table.setColumnWidth(col, width)

    def hide_column(self, col: int):
        self.table.setColumnHidden(col, True)

    def set_cell_widget(self, row: int, col: int, widget: QWidget):
        self.table.setCellWidget(row, col, widget)

    def cell_widget(self, row: int, col: int):
        return self.table.cellWidget(row, col)

    def item(self, row: int, col: int):
        return self.table.item(row, col)

    def set_item(self, row: int, col: int, text: str):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, col, item)

    # ==================== Private ====================

    def _on_add_clicked(self):
        """Override این متد برای رفتار سفارشی Add."""
        self.add_row()

    def _on_remove_clicked(self):
        """Override این متد برای رفتار سفارشی Remove."""
        self.remove_selected_row()

    def _on_export_clicked(self):
        """Export جدول به CSV."""
        from PySide6.QtWidgets import QFileDialog
        from datetime import datetime
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export",
            f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )
        if filename:
            try:
                data = self.get_all_data()
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    if data:
                        writer = csv.DictWriter(f, fieldnames=self.headers)
                        writer.writeheader()
                        writer.writerows(data)
                logger.info(f"Exported to {filename}")
            except Exception as e:
                logger.error(f"Export error: {e}")

    def _on_import_clicked(self):
        """Import از CSV."""
        from PySide6.QtWidgets import QFileDialog
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import", "",
            "CSV Files (*.csv);;Excel Files (*.xlsx)"
        )
        if not filename:
            return
        try:
            if filename.endswith('.xlsx'):
                import pandas as pd
                df = pd.read_excel(filename)
                data = df.to_dict('records')
            else:
                with open(filename, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    data = list(reader)
            self.load_data(data)
        except ImportError:
            # Fallback CSV only
            try:
                with open(filename, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    data = list(reader)
                self.load_data(data)
            except Exception as e:
                logger.error(f"Import error: {e}")
        except Exception as e:
            logger.error(f"Import error: {e}")

    def _update_summary(self):
        """به‌روزرسانی label خلاصه."""
        count = self.table.rowCount()
        self.summary_label.setText(f"Total rows: {count}")


class KPICard(QFrame):
    """
    کارت KPI استاندارد - جایگزین کدهای تکراری create_kpi_card در همه تب‌ها
    """

    def __init__(
        self,
        icon: str,
        title: str,
        value: str = "0",
        unit: str = "",
        color: str = "#3498db",
        parent=None
    ):
        super().__init__(parent)
        self.color = color
        self._setup_ui(icon, title, value, unit)

    def _setup_ui(self, icon, title, value, unit):
        self.setStyleSheet(f"""
            QFrame {{
                background: {self.color}20;
                border-left: 4px solid {self.color};
                border-radius: 6px;
                padding: 10px;
                margin: 3px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # Header
        header_layout = QHBoxLayout()
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: 22px; color: {self.color};")
        title_label = QLabel(title)
        title_label.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #7f8c8d;"
        )
        header_layout.addWidget(icon_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Value
        self.value_label = QLabel(f"<b>{value}</b>")
        self.value_label.setStyleSheet(
            f"font-size: 22px; color: {self.color}; font-weight: bold;"
        )
        layout.addWidget(self.value_label)

        # Unit
        if unit:
            self.unit_label = QLabel(unit)
            self.unit_label.setStyleSheet("font-size: 11px; color: #95a5a6;")
            layout.addWidget(self.unit_label)

    def set_value(self, value: str):
        """به‌روزرسانی مقدار."""
        self.value_label.setText(f"<b>{value}</b>")

    def set_color(self, color: str):
        """تغییر رنگ."""
        self.color = color
        self.setStyleSheet(f"""
            QFrame {{
                background: {color}20;
                border-left: 4px solid {color};
                border-radius: 6px;
                padding: 10px;
                margin: 3px;
            }}
        """)
        self.value_label.setStyleSheet(
            f"font-size: 22px; color: {color}; font-weight: bold;"
        )


class SectionGroupBox(QGroupBox):
    """
    GroupBox استاندارد با استایل یکپارچه
    """

    STYLES = {
        "primary": "#3498db",
        "success": "#27ae60",
        "warning": "#f39c12",
        "danger": "#e74c3c",
        "info": "#1abc9c",
        "purple": "#9b59b6",
        "dark": "#2c3e50",
    }

    def __init__(self, title: str, style: str = "primary", parent=None):
        super().__init__(title, parent)
        color = self.STYLES.get(style, self.STYLES["primary"])
        self.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                font-size: 12px;
                border: 2px solid {color};
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: {color};
            }}
        """)
        

def safe_replace_chart(container_widget, new_canvas):
    """
    جایگزینی ایمن canvas matplotlib در یک container widget.
    جلوگیری از memory leak با حذف صحیح ویجت‌های قبلی.
    """
    from PySide6.QtWidgets import QVBoxLayout
    
    if container_widget.layout() is None:
        container_widget.setLayout(QVBoxLayout())
        container_widget.layout().setContentsMargins(0, 0, 0, 0)
    
    layout = container_widget.layout()
    
    while layout.count():
        child = layout.takeAt(0)
        widget = child.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
    
    if new_canvas is not None:
        layout.addWidget(new_canvas)