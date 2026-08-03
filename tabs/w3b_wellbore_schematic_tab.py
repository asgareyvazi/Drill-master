# tabs/w3b_wellbore_schematic_tab.py
"""
Wellbore Schematic Tab - تب رسم حرفه‌ای شماتیک چاه
"""
import json
import logging
from typing import Optional

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtSvg import QSvgGenerator

from core.base_tab import DrillTabBase
from core.wellbore_schematic_engine import (
    WellboreSchematic, WellboreSchematicRenderer, SchematicConfig,
    SchematicAutoBuilder, CasingData, FormationLayer, CompletionItem,
    ElementType, SchematicColors,
)

logger = logging.getLogger(__name__)


class WellboreSchematicTab(DrillTabBase):
    """تب حرفه‌ای Wellbore Schematic."""

    def __init__(self, db_manager=None, parent=None):
        super().__init__("WellboreSchematicTab", db_manager, parent)
        self.schematic = WellboreSchematic()
        self.config = SchematicConfig()
        self.renderer = None
        self._is_loading = False

        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ========== پنل چپ: کنترل‌ها ==========
        left_panel = self._create_left_panel()
        left_panel.setMaximumWidth(300)
        main_layout.addWidget(left_panel)

        # ========== پنل راست: Canvas ==========
        right_panel = self._create_right_panel()
        main_layout.addWidget(right_panel, 1)

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: #f8f9fa;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

        # ===== Header =====
        header = QLabel("⚙️ Schematic Controls")
        header.setStyleSheet(
            "font-weight: bold; font-size: 13px; "
            "color: #2c3e50; padding: 5px;"
        )
        layout.addWidget(header)

        # ===== Tabs =====
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabBar::tab { padding: 5px 8px; font-size: 10px; }
            QTabBar::tab:selected { background: #3498db; color: white; }
        """)

        # تب Auto-Generate
        tabs.addTab(self._create_auto_tab(), "🤖 Auto")
        # تب Casing
        tabs.addTab(self._create_casing_tab(), "🛢️ Casings")
        # تب Formation
        tabs.addTab(self._create_formation_tab(), "🏔️ Formations")
        # تب Completion
        tabs.addTab(self._create_completion_tab(), "✅ Completion")
        # تب Settings
        tabs.addTab(self._create_settings_tab(), "⚙️ Settings")

        layout.addWidget(tabs, 1)

        # ===== دکمه‌های پایین =====
        btn_layout = QVBoxLayout()

        refresh_btn = QPushButton("🔄 Refresh Drawing")
        refresh_btn.setStyleSheet(
            "background: #3498db; color: white; "
            "font-weight: bold; padding: 8px; "
            "border-radius: 4px; border: none;"
        )
        refresh_btn.clicked.connect(self.refresh_drawing)

        export_btn = QPushButton("📤 Export")
        export_btn.setStyleSheet(
            "background: #27ae60; color: white; "
            "font-weight: bold; padding: 8px; "
            "border-radius: 4px; border: none;"
        )
        export_btn.clicked.connect(self.export_schematic)

        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(export_btn)
        layout.addLayout(btn_layout)

        return panel

    def _create_auto_tab(self) -> QWidget:
        """تب Auto-Generate از DB."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        info = QLabel(
            "Auto-generate schematic from\nyour well data in database."
        )
        info.setStyleSheet("color: #666; font-size: 10px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        auto_btn = QPushButton("🤖 Auto-Generate from DB")
        auto_btn.setStyleSheet(
            "background: #9b59b6; color: white; "
            "font-weight: bold; padding: 8px; "
            "border-radius: 4px; border: none;"
        )
        auto_btn.clicked.connect(self.auto_generate)
        layout.addWidget(auto_btn)

        # Well info manual
        g = QGroupBox("Well Parameters")
        f = QFormLayout(g)

        self.well_name_edit = QLineEdit()
        self.well_name_edit.setPlaceholderText("Well Name")
        f.addRow("Well:", self.well_name_edit)

        self.td_spin = QDoubleSpinBox()
        self.td_spin.setRange(0, 20000)
        self.td_spin.setValue(3000)
        self.td_spin.setSuffix(" m")
        f.addRow("Total Depth:", self.td_spin)

        self.tubing_od_spin = QDoubleSpinBox()
        self.tubing_od_spin.setRange(0, 20)
        self.tubing_od_spin.setValue(3.5)
        self.tubing_od_spin.setDecimals(3)
        self.tubing_od_spin.setSuffix("\"")
        f.addRow("Tubing OD:", self.tubing_od_spin)

        self.show_tubing_cb = QCheckBox("Show Tubing")
        self.show_tubing_cb.setChecked(True)
        f.addRow(self.show_tubing_cb)

        self.show_xmas_cb = QCheckBox("Show Xmas Tree")
        self.show_xmas_cb.setChecked(True)
        f.addRow(self.show_xmas_cb)

        self.show_wh_cb = QCheckBox("Show Wellhead")
        self.show_wh_cb.setChecked(True)
        f.addRow(self.show_wh_cb)

        layout.addWidget(g)

        apply_btn = QPushButton("✅ Apply Changes")
        apply_btn.clicked.connect(self._apply_manual_changes)
        layout.addWidget(apply_btn)

        layout.addStretch()
        return tab

    def _create_casing_tab(self) -> QWidget:
        """تب مدیریت کیسینگ‌ها."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # جدول کیسینگ‌ها
        self.casing_table = QTableWidget(0, 5)
        self.casing_table.setHorizontalHeaderLabels([
            "Type", "OD\"", "ID\"", "Top", "Bottom"
        ])
        self.casing_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.casing_table.setMaximumHeight(250)
        self.casing_table.setEditTriggers(QTableWidget.DoubleClicked)
        self.casing_table.itemChanged.connect(self._on_casing_table_changed)
        layout.addWidget(self.casing_table)

        # دکمه‌ها
        btn_layout = QHBoxLayout()

        add_types = [
            ("🟤 Conductor", ElementType.CONDUCTOR, 20.0, 18.73),
            ("🔵 Surface", ElementType.SURFACE_CASING, 13.375, 12.415),
            ("🟢 Interm.", ElementType.INTERMEDIATE_CASING, 9.625, 8.835),
            ("🟡 Prod.", ElementType.PRODUCTION_CASING, 7.0, 6.276),
            ("🟣 Liner", ElementType.LINER, 5.0, 4.276),
        ]

        combo = QComboBox()
        for name, _, _, _ in add_types:
            combo.addItem(name)
        self._casing_add_combo = combo
        self._casing_add_types = add_types
        btn_layout.addWidget(combo)

        add_btn = QPushButton("➕")
        add_btn.setFixedWidth(30)
        add_btn.clicked.connect(self._add_casing_from_combo)
        btn_layout.addWidget(add_btn)

        rem_btn = QPushButton("🗑️")
        rem_btn.setFixedWidth(30)
        rem_btn.clicked.connect(self._remove_casing)
        btn_layout.addWidget(rem_btn)

        layout.addLayout(btn_layout)

        # Cement controls
        g_cement = QGroupBox("Cement Settings")
        cf = QFormLayout(g_cement)
        self.cement_top_spin = QDoubleSpinBox()
        self.cement_top_spin.setRange(0, 20000)
        self.cement_top_spin.setSuffix(" m")
        cf.addRow("Cement Top:", self.cement_top_spin)
        self.show_cement_cb = QCheckBox("Show Cement")
        self.show_cement_cb.setChecked(True)
        cf.addRow(self.show_cement_cb)
        layout.addWidget(g_cement)

        layout.addStretch()
        return tab

    def _create_formation_tab(self) -> QWidget:
        """تب مدیریت سازندها."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.formation_table = QTableWidget(0, 4)
        self.formation_table.setHorizontalHeaderLabels([
            "Name", "Top(m)", "Base(m)", "Lithology"
        ])
        self.formation_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.formation_table.setMaximumHeight(250)
        self.formation_table.itemChanged.connect(
            self._on_formation_table_changed
        )
        layout.addWidget(self.formation_table)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("➕ Add Formation")
        add_btn.clicked.connect(self._add_formation)
        rem_btn = QPushButton("🗑️ Remove")
        rem_btn.clicked.connect(self._remove_formation)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(rem_btn)
        layout.addLayout(btn_layout)

        # پیش‌تعریف‌ها
        preset_group = QGroupBox("Quick Add")
        preset_layout = QGridLayout(preset_group)
        presets = [
            ("Shale", "#808080"), ("Sandstone", "#DEB887"),
            ("Limestone", "#87CEEB"), ("Dolomite", "#DEB887"),
            ("Salt", "#F0F0F0"), ("Coal", "#2F2F2F"),
        ]
        for i, (name, color) in enumerate(presets):
            btn = QPushButton(name)
            btn.setStyleSheet(
                f"background: {color}; color: #333; "
                f"padding: 3px; border-radius: 2px; font-size: 10px;"
            )
            btn.clicked.connect(
                lambda checked, n=name, c=color: self._add_formation_preset(n, c)
            )
            preset_layout.addWidget(btn, i // 2, i % 2)
        layout.addWidget(preset_group)

        layout.addStretch()
        return tab

    def _create_completion_tab(self) -> QWidget:
        """تب Completion."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.completion_table = QTableWidget(0, 3)
        self.completion_table.setHorizontalHeaderLabels([
            "Type", "Depth(m)", "Length(m)"
        ])
        self.completion_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.completion_table.setMaximumHeight(200)
        layout.addWidget(self.completion_table)

        # دکمه‌های اضافه کردن
        completion_items = [
            ("🔴 Packer", ElementType.PACKER),
            ("⭐ Perfs", ElementType.PERFORATIONS),
            ("🟤 Bridge Plug", ElementType.BRIDGE_PLUG),
            ("🟢 Safety Valve", ElementType.SAFETY_VALVE),
            ("🔵 Sand Screen", ElementType.SAND_SCREEN),
            ("🟠 Gas Lift Valve", ElementType.GAS_LIFT_VALVE),
        ]

        btn_grid = QGridLayout()
        for i, (label, etype) in enumerate(completion_items):
            btn = QPushButton(label)
            btn.setStyleSheet(
                "font-size: 10px; padding: 4px; "
                "border: 1px solid #ddd; border-radius: 3px;"
            )
            btn.clicked.connect(
                lambda checked, e=etype: self._add_completion_item(e)
            )
            btn_grid.addWidget(btn, i // 2, i % 2)

        layout.addLayout(btn_grid)

        rem_btn = QPushButton("🗑️ Remove Selected")
        rem_btn.clicked.connect(self._remove_completion_item)
        layout.addWidget(rem_btn)

        layout.addStretch()
        return tab

    def _create_settings_tab(self) -> QWidget:
        """تب تنظیمات ظاهری."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QFormLayout(content)

        # Dark Mode
        self.dark_mode_cb = QCheckBox("Dark Mode")
        self.dark_mode_cb.setChecked(True)
        self.dark_mode_cb.stateChanged.connect(self.refresh_drawing)
        content_layout.addRow(self.dark_mode_cb)

        # Show options
        self.show_formations_cb = QCheckBox("Show Formations")
        self.show_formations_cb.setChecked(True)
        content_layout.addRow(self.show_formations_cb)

        self.show_cement_setting_cb = QCheckBox("Show Cement")
        self.show_cement_setting_cb.setChecked(True)
        content_layout.addRow(self.show_cement_setting_cb)

        self.show_legend_cb = QCheckBox("Show Legend")
        self.show_legend_cb.setChecked(True)
        content_layout.addRow(self.show_legend_cb)

        self.show_depth_scale_cb = QCheckBox("Show Depth Scale")
        self.show_depth_scale_cb.setChecked(True)
        content_layout.addRow(self.show_depth_scale_cb)

        self.show_labels_cb = QCheckBox("Show Labels")
        self.show_labels_cb.setChecked(True)
        content_layout.addRow(self.show_labels_cb)

        # Width & Height
        self.width_spin = QSpinBox()
        self.width_spin.setRange(400, 2000)
        self.width_spin.setValue(800)
        self.width_spin.setSingleStep(50)
        content_layout.addRow("Width:", self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(600, 4000)
        self.height_spin.setValue(1200)
        self.height_spin.setSingleStep(100)
        content_layout.addRow("Height:", self.height_spin)

        # OD Scale
        self.od_scale_spin = QDoubleSpinBox()
        self.od_scale_spin.setRange(5, 30)
        self.od_scale_spin.setValue(15)
        self.od_scale_spin.setDecimals(1)
        content_layout.addRow("OD Scale:", self.od_scale_spin)

        # Font size
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(7, 16)
        self.font_size_spin.setValue(9)
        content_layout.addRow("Font Size:", self.font_size_spin)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        apply_btn = QPushButton("✅ Apply Settings")
        apply_btn.clicked.connect(self.refresh_drawing)
        layout.addWidget(apply_btn)

        return tab

    def _create_right_panel(self) -> QWidget:
        """پنل راست شامل Canvas."""
        panel = QWidget()
        panel.setStyleSheet("background: #1e2a3a;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar کوچک بالای Canvas
        canvas_toolbar = QWidget()
        canvas_toolbar.setStyleSheet("background: #2c3e50; padding: 4px;")
        canvas_toolbar_layout = QHBoxLayout(canvas_toolbar)
        canvas_toolbar_layout.setContentsMargins(5, 3, 5, 3)

        zoom_in_btn = QPushButton("🔍+")
        zoom_in_btn.setFixedSize(30, 24)
        zoom_in_btn.clicked.connect(lambda: self._zoom(1.2))

        zoom_out_btn = QPushButton("🔍-")
        zoom_out_btn.setFixedSize(30, 24)
        zoom_out_btn.clicked.connect(lambda: self._zoom(0.8))

        fit_btn = QPushButton("⊞ Fit")
        fit_btn.setFixedWidth(50)
        fit_btn.clicked.connect(self._fit_to_view)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet("color: white; font-size: 11px;")

        for w in [zoom_in_btn, zoom_out_btn, fit_btn, self.zoom_label]:
            canvas_toolbar_layout.addWidget(w)
        canvas_toolbar_layout.addStretch()

        # وضعیت
        self.canvas_status = QLabel("Select a well to generate schematic")
        self.canvas_status.setStyleSheet(
            "color: #95a5a6; font-size: 10px; padding: 0 10px;"
        )
        canvas_toolbar_layout.addWidget(self.canvas_status)

        layout.addWidget(canvas_toolbar)

        # Graphics View
        self.scene = QGraphicsScene()
        self.view = WellboreGraphicsView(self.scene)
        self.view.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.view)

        return panel

    # ==================== Actions ====================

    def on_well_changed(self, well_id, well_data):
        """وقتی چاه تغییر می‌کند، شماتیک را به‌روز می‌کنیم."""
        self.current_well_id = well_id
        if well_id and well_data:
            self.well_name_edit.setText(well_data.get("name", ""))
            td = well_data.get("target_depth", 3000) or 3000
            self.td_spin.setValue(td)
            # Auto-generate
            QTimer.singleShot(500, self.auto_generate)

    def auto_generate(self):
        """ساخت خودکار شماتیک از DB."""
        if not self.current_well_id or not self.db:
            self.canvas_status.setText("No well selected")
            return

        self.canvas_status.setText("🔄 Generating...")
        QApplication.processEvents()

        try:
            builder = SchematicAutoBuilder(self.db)
            self.schematic = builder.build_from_well(self.current_well_id)

            self._sync_tables_to_schematic()
            self.refresh_drawing()
            self.canvas_status.setText(
                f"✅ Generated: "
                f"{len(self.schematic.casings)} casings, "
                f"{len(self.schematic.formations)} formations"
            )

        except Exception as e:
            logger.error(f"Auto-generate error: {e}")
            self.canvas_status.setText(f"❌ Error: {str(e)[:50]}")

    def _apply_manual_changes(self):
        """اعمال تغییرات دستی."""
        self.schematic.well_name = self.well_name_edit.text()
        self.schematic.total_depth_m = self.td_spin.value()
        self.schematic.tubing_od_inch = self.tubing_od_spin.value()
        self.schematic.show_tubing = self.show_tubing_cb.isChecked()
        self.schematic.show_xmas_tree = self.show_xmas_cb.isChecked()
        self.schematic.show_wellhead = self.show_wh_cb.isChecked()
        self.refresh_drawing()

    def refresh_drawing(self):
        """رندر مجدد شماتیک."""
        self.config.dark_mode = self.dark_mode_cb.isChecked()
        self.config.show_formations = self.show_formations_cb.isChecked()
        self.config.show_cement = self.show_cement_setting_cb.isChecked()
        self.config.show_legend = self.show_legend_cb.isChecked()
        self.config.show_depth_scale = self.show_depth_scale_cb.isChecked()
        self.config.show_labels = self.show_labels_cb.isChecked()
        self.config.total_width = self.width_spin.value()
        self.config.total_height = self.height_spin.value()
        self.config.od_scale = self.od_scale_spin.value()
        self.config.font_size = self.font_size_spin.value()

        if self.config.dark_mode:
            self.config.background_color = "#1e2a3a"
            self.config.text_color = "#ecf0f1"
        else:
            self.config.background_color = "#ffffff"
            self.config.text_color = "#2c3e50"

        self.view.setStyleSheet(
            f"background: {self.config.background_color}; border: none;"
        )

        painter = None
        try:
            pixmap = QPixmap(self.config.total_width, self.config.total_height)
            pixmap.fill(QColor(self.config.background_color))

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)

            renderer = WellboreSchematicRenderer(self.schematic, self.config)
            renderer.render(painter)

        except Exception as e:
            logger.error(f"Refresh drawing error: {e}")
            self.canvas_status.setText(f"❌ Drawing error: {str(e)[:50]}")
            return

        finally:
            if painter is not None and painter.isActive():
                painter.end()

        self.scene.clear()
        self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(
            0, 0, self.config.total_width, self.config.total_height
        )

    def export_schematic(self):
        """اکسپورت شماتیک."""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Wellbore Schematic",
            f"wellbore_{self.schematic.well_name or 'schematic'}.png",
            "PNG Image (*.png);;SVG Vector (*.svg);;PDF Document (*.pdf)"
        )
        if not filename:
            return

        try:
            if filename.endswith('.svg'):
                self._export_svg(filename)
            elif filename.endswith('.pdf'):
                self._export_pdf(filename)
            else:
                self._export_png(filename)

            self.show_success(f"Schematic exported: {filename}")

        except Exception as e:
            logger.error(f"Export error: {e}")
            self.show_error(f"Export failed: {str(e)}")

    def _export_png(self, filename: str):
        """اکسپورت PNG با رزولوشن بالا."""
        scale = 2.0  # High-DPI
        w = int(self.config.total_width * scale)
        h = int(self.config.total_height * scale)

        pixmap = QPixmap(w, h)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(QColor(self.config.background_color))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.scale(scale, scale)

        renderer = WellboreSchematicRenderer(self.schematic, self.config)
        renderer.render(painter)
        painter.end()

        pixmap.save(filename, "PNG")

    def _export_svg(self, filename: str):
        """اکسپورت SVG."""
        generator = QSvgGenerator()
        generator.setFileName(filename)
        generator.setSize(QSize(self.config.total_width, self.config.total_height))
        generator.setViewBox(
            QRect(0, 0, self.config.total_width, self.config.total_height)
        )
        generator.setTitle(
            f"Wellbore Schematic - {self.schematic.well_name}"
        )

        painter = QPainter(generator)
        painter.setRenderHint(QPainter.Antialiasing)

        renderer = WellboreSchematicRenderer(self.schematic, self.config)
        renderer.render(painter)
        painter.end()

    def _export_pdf(self, filename: str):
        """اکسپورت PDF."""
        from PySide6.QtPrintSupport import QPrinter

        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(filename)
        printer.setPageSize(QPrinter.A3)

        painter = QPainter(printer)
        renderer = WellboreSchematicRenderer(self.schematic, self.config)
        renderer.render(painter)
        painter.end()

    # ==================== Table Management ====================

    def _sync_tables_to_schematic(self):
        """همگام‌سازی جداول UI با شماتیک."""
        self._is_loading = True

        # Casing table
        self.casing_table.setRowCount(0)
        for c in self.schematic.casings:
            row = self.casing_table.rowCount()
            self.casing_table.insertRow(row)
            type_names = {
                ElementType.CONDUCTOR: "Conductor",
                ElementType.SURFACE_CASING: "Surface",
                ElementType.INTERMEDIATE_CASING: "Intermediate",
                ElementType.PRODUCTION_CASING: "Production",
                ElementType.LINER: "Liner",
            }
            self.casing_table.setItem(
                row, 0, QTableWidgetItem(
                    type_names.get(c.element_type, c.name)
                )
            )
            self.casing_table.setItem(
                row, 1, QTableWidgetItem(f"{c.od_inch:.3f}")
            )
            self.casing_table.setItem(
                row, 2, QTableWidgetItem(f"{c.id_inch:.3f}")
            )
            self.casing_table.setItem(
                row, 3, QTableWidgetItem(f"{c.top_depth_m:.0f}")
            )
            self.casing_table.setItem(
                row, 4, QTableWidgetItem(f"{c.bottom_depth_m:.0f}")
            )

        # Formation table
        self.formation_table.setRowCount(0)
        for f in self.schematic.formations:
            row = self.formation_table.rowCount()
            self.formation_table.insertRow(row)
            self.formation_table.setItem(row, 0, QTableWidgetItem(f.name))
            self.formation_table.setItem(
                row, 1, QTableWidgetItem(f"{f.top_depth_m:.0f}")
            )
            self.formation_table.setItem(
                row, 2, QTableWidgetItem(f"{f.bottom_depth_m:.0f}")
            )
            self.formation_table.setItem(
                row, 3, QTableWidgetItem(f.lithology)
            )

        self._is_loading = False

    def _on_casing_table_changed(self, item):
        """وقتی جدول کیسینگ تغییر می‌کند."""
        if self._is_loading:
            return
        self._update_casings_from_table()
        self.refresh_drawing()

    def _update_casings_from_table(self):
        """به‌روزرسانی شماتیک از جدول."""
        if len(self.schematic.casings) != self.casing_table.rowCount():
            return

        type_map = {
            "Conductor": ElementType.CONDUCTOR,
            "Surface": ElementType.SURFACE_CASING,
            "Intermediate": ElementType.INTERMEDIATE_CASING,
            "Production": ElementType.PRODUCTION_CASING,
            "Liner": ElementType.LINER,
        }

        for i, casing in enumerate(self.schematic.casings):
            try:
                type_item = self.casing_table.item(i, 0)
                od_item = self.casing_table.item(i, 1)
                id_item = self.casing_table.item(i, 2)
                top_item = self.casing_table.item(i, 3)
                bot_item = self.casing_table.item(i, 4)

                if type_item:
                    casing.element_type = type_map.get(
                        type_item.text(), casing.element_type
                    )
                if od_item:
                    casing.od_inch = float(od_item.text())
                if id_item:
                    casing.id_inch = float(id_item.text())
                if top_item:
                    casing.top_depth_m = float(top_item.text())
                if bot_item:
                    casing.bottom_depth_m = float(bot_item.text())
                    casing.cement_bottom_m = float(bot_item.text())

            except (ValueError, IndexError):
                pass

    def _on_formation_table_changed(self, item):
        """وقتی جدول سازند تغییر می‌کند."""
        if self._is_loading:
            return
        self._update_formations_from_table()
        self.refresh_drawing()

    def _update_formations_from_table(self):
        """به‌روزرسانی سازندها از جدول."""
        new_formations = []
        for row in range(self.formation_table.rowCount()):
            try:
                name = self.formation_table.item(row, 0)
                top = self.formation_table.item(row, 1)
                base = self.formation_table.item(row, 2)
                litho = self.formation_table.item(row, 3)

                if name and top and base:
                    new_formations.append(FormationLayer(
                        name=name.text(),
                        top_depth_m=float(top.text()),
                        bottom_depth_m=float(base.text()),
                        lithology=litho.text() if litho else "Shale",
                        color=SchematicColors.FORMATIONS.get(
                            litho.text() if litho else "Shale", "#808080"
                        ),
                    ))
            except (ValueError, AttributeError):
                pass

        self.schematic.formations = new_formations

    def _add_casing_from_combo(self):
        """اضافه کردن کیسینگ از combo."""
        idx = self._casing_add_combo.currentIndex()
        name, etype, od, id_ = self._casing_add_types[idx]

        last_bottom = max(
            (c.bottom_depth_m for c in self.schematic.casings), default=0
        )
        new_bottom = min(
            last_bottom + 500, self.schematic.total_depth_m
        )

        new_casing = CasingData(
            name=name.split()[-1],
            element_type=etype,
            od_inch=od, id_inch=id_,
            top_depth_m=0, bottom_depth_m=new_bottom,
            cement_top_m=max(0, new_bottom - 300),
            cement_bottom_m=new_bottom,
        )
        self.schematic.casings.append(new_casing)
        self._sync_tables_to_schematic()
        self.refresh_drawing()

    def _remove_casing(self):
        """حذف کیسینگ انتخاب‌شده."""
        row = self.casing_table.currentRow()
        if 0 <= row < len(self.schematic.casings):
            self.schematic.casings.pop(row)
            self._sync_tables_to_schematic()
            self.refresh_drawing()

    def _add_formation(self):
        """اضافه کردن سازند جدید."""
        last_base = max(
            (f.bottom_depth_m for f in self.schematic.formations), default=0
        )
        new_formation = FormationLayer(
            name=f"Formation {len(self.schematic.formations) + 1}",
            top_depth_m=last_base,
            bottom_depth_m=last_base + 200,
            lithology="Shale",
            color="#808080",
        )
        self.schematic.formations.append(new_formation)
        self._sync_tables_to_schematic()
        self.refresh_drawing()

    def _add_formation_preset(self, lithology: str, color: str):
        """اضافه کردن سازند از preset."""
        last_base = max(
            (f.bottom_depth_m for f in self.schematic.formations), default=0
        )
        self.schematic.formations.append(FormationLayer(
            name=lithology,
            top_depth_m=last_base,
            bottom_depth_m=last_base + 200,
            lithology=lithology,
            color=color,
        ))
        self._sync_tables_to_schematic()
        self.refresh_drawing()

    def _remove_formation(self):
        """حذف سازند."""
        row = self.formation_table.currentRow()
        if 0 <= row < len(self.schematic.formations):
            self.schematic.formations.pop(row)
            self._sync_tables_to_schematic()
            self.refresh_drawing()

    def _add_completion_item(self, etype: ElementType):
        """اضافه کردن المنت Completion."""
        dlg = CompletionItemDialog(etype, self.schematic.total_depth_m, self)
        if dlg.exec():
            item = dlg.get_item()
            if item:
                self.schematic.completion.append(item)
                row = self.completion_table.rowCount()
                self.completion_table.insertRow(row)
                self.completion_table.setItem(
                    row, 0, QTableWidgetItem(etype.value)
                )
                self.completion_table.setItem(
                    row, 1, QTableWidgetItem(f"{item.depth_m:.0f}")
                )
                self.completion_table.setItem(
                    row, 2, QTableWidgetItem(f"{item.length_m:.0f}")
                )
                self.refresh_drawing()

    def _remove_completion_item(self):
        """حذف المنت Completion."""
        row = self.completion_table.currentRow()
        if 0 <= row < len(self.schematic.completion):
            self.schematic.completion.pop(row)
            self.completion_table.removeRow(row)
            self.refresh_drawing()

    # ==================== Zoom ====================

    def _zoom(self, factor: float):
        self.view.scale(factor, factor)
        current_scale = self.view.transform().m11()
        self.zoom_label.setText(f"{current_scale * 100:.0f}%")

    def _fit_to_view(self):
        self.view.fitInView(
            self.scene.sceneRect(), Qt.KeepAspectRatio
        )
        current_scale = self.view.transform().m11()
        self.zoom_label.setText(f"{current_scale * 100:.0f}%")

    def save_data(self) -> bool:
        """ذخیره شماتیک در DB."""
        if not self.current_well_id or not self.db:
            return False

        try:
            schematic_data = {
                "well_id": self.current_well_id,
                "report_date": __import__('datetime').date.today(),
                "schematic_name": f"Schematic_{self.schematic.well_name}",
                "elements_json": json.dumps({
                    "casings": [
                        {
                            "name": c.name,
                            "type": c.element_type.value,
                            "od": c.od_inch,
                            "id": c.id_inch,
                            "top": c.top_depth_m,
                            "bottom": c.bottom_depth_m,
                            "cement_top": c.cement_top_m,
                            "cement_bottom": c.cement_bottom_m,
                        }
                        for c in self.schematic.casings
                    ],
                    "formations": [
                        {
                            "name": f.name,
                            "top": f.top_depth_m,
                            "bottom": f.bottom_depth_m,
                            "lithology": f.lithology,
                            "color": f.color,
                        }
                        for f in self.schematic.formations
                    ],
                    "completion": [
                        {
                            "type": i.element_type.value,
                            "depth": i.depth_m,
                            "length": i.length_m,
                        }
                        for i in self.schematic.completion
                    ],
                    "config": {
                        "total_depth": self.schematic.total_depth_m,
                        "well_name": self.schematic.well_name,
                        "show_tubing": self.schematic.show_tubing,
                        "show_xmas_tree": self.schematic.show_xmas_tree,
                    }
                }, default=str),
            }
            result = self.db.save_wellbore_schematic(schematic_data)
            if result:
                self.show_success("Schematic saved")
                return True
        except Exception as e:
            logger.error(f"Save schematic error: {e}")
            self.show_error(f"Save failed: {str(e)}")
        return False

    def refresh(self):
        if self.current_well_id:
            QTimer.singleShot(200, self.auto_generate)


# ==================== Graphics View با Zoom/Pan ====================

class WellboreGraphicsView(QGraphicsView):
    """
    Graphics View با قابلیت Zoom و Pan.
    """

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._zoom_factor = 1.0

    def wheelEvent(self, event):
        """Zoom با mouse wheel."""
        if event.modifiers() == Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 0.87
            self.scale(factor, factor)
            self._zoom_factor *= factor
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        """Keyboard shortcuts."""
        if event.key() == Qt.Key_Plus and event.modifiers() == Qt.ControlModifier:
            self.scale(1.2, 1.2)
        elif event.key() == Qt.Key_Minus and event.modifiers() == Qt.ControlModifier:
            self.scale(0.8, 0.8)
        elif event.key() == Qt.Key_0 and event.modifiers() == Qt.ControlModifier:
            self.resetTransform()
        else:
            super().keyPressEvent(event)


# ==================== Completion Item Dialog ====================

class CompletionItemDialog(QDialog):
    """دیالوگ اضافه کردن المنت Completion."""

    def __init__(self, etype: ElementType, max_depth: float, parent=None):
        super().__init__(parent)
        self.etype = etype
        self.max_depth = max_depth
        self._item = None

        self.setWindowTitle(f"Add {etype.value}")
        self.setFixedSize(300, 220)
        self._init_ui()

    def _init_ui(self):
        layout = QFormLayout(self)

        layout.addRow(
            QLabel(f"Type: {self.etype.value}")
        )

        self.depth_spin = QDoubleSpinBox()
        self.depth_spin.setRange(0, self.max_depth)
        self.depth_spin.setValue(self.max_depth * 0.8)
        self.depth_spin.setSuffix(" m")
        layout.addRow("Depth:", self.depth_spin)

        self.od_spin = QDoubleSpinBox()
        self.od_spin.setRange(0, 20)
        self.od_spin.setValue(4.5)
        self.od_spin.setDecimals(3)
        self.od_spin.setSuffix("\"")
        layout.addRow("OD:", self.od_spin)

        self.length_spin = QDoubleSpinBox()
        self.length_spin.setRange(0.1, 500)
        self.length_spin.setValue(
            20 if self.etype == ElementType.PERFORATIONS else 1
        )
        self.length_spin.setSuffix(" m")
        layout.addRow("Length:", self.length_spin)

        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("Optional label")
        layout.addRow("Label:", self.label_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_ok(self):
        self._item = CompletionItem(
            element_type=self.etype,
            depth_m=self.depth_spin.value(),
            od_inch=self.od_spin.value(),
            length_m=self.length_spin.value(),
            label=self.label_edit.text(),
        )
        self.accept()

    def get_item(self) -> Optional[CompletionItem]:
        return self._item