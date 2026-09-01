# tabs/w15_Reference_Tables.py
"""
Reference Tables & Database
جداول مرجع مهندسی حفاری
منابع: API 5CT, API 5DP, Drilling Data Handbook, Well Engineers Notebook
"""
import logging
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from core.base_tab import DrillTabBase
from core.managers import ExportManager

logger = logging.getLogger(__name__)


class ReferenceTablesWidget(DrillTabBase):
    """تب جداول مرجع مهندسی حفاری"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__("ReferenceTablesWidget", db_manager, parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)

        # Header
        header = QLabel("📚 Drilling Reference Tables & Database")
        header.setStyleSheet("""
            QLabel {
                font-size: 15px; font-weight: bold; color: #ecf0f1;
                padding: 8px; border: none;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #2c3e50, stop:1 #34495e);
                border-radius: 5px;
            }
        """)
        layout.addWidget(header)

        # Search
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍 Search:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search in tables... (e.g., 9-5/8, P-110, NC50)")
        self.search_box.textChanged.connect(self._filter_current_table)
        search_layout.addWidget(self.search_box)

        export_btn = QPushButton("📤 Export Current Table")
        export_btn.clicked.connect(self._export_current)
        search_layout.addWidget(export_btn)
        layout.addLayout(search_layout)

        # Main tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab { padding: 6px 14px; font-size: 11px; font-weight: bold; }
            QTabBar::tab:selected { background: #3498db; color: white; }
        """)

        self.tabs.addTab(self._create_casing_tab(), "🛢️ Casing (API 5CT)")
        self.tabs.addTab(self._create_drillpipe_tab(), "🔩 Drill Pipe (API 5DP)")
        self.tabs.addTab(self._create_collar_tab(), "⚫ Drill Collars")
        self.tabs.addTab(self._create_connections_tab(), "🔗 Connections")
        self.tabs.addTab(self._create_bit_tab(), "🔵 Bit Data")
        self.tabs.addTab(self._create_cement_tab(), "🧱 Cement")
        self.tabs.addTab(self._create_mud_tab(), "🧪 Mud Additives")
        self.tabs.addTab(self._create_formulas_tab(), "📐 Quick Formulas")
        self.tabs.addTab(self._create_conversion_tab(), "📏 Unit Conversion")
        self.tabs.addTab(self._create_hole_casing_tab(), "📐 Hole/CSG Sizing")
        self.tabs.addTab(self._create_torque_tab(), "🔧 MU Torque")
        self.tabs.addTab(self._create_fluid_tab(), "💧 Fluid Properties")
        
        layout.addWidget(self.tabs)

    # ==================== Helper ====================

    def _make_table(self, headers, data, color="#2c3e50"):
        """ساخت جدول از داده"""
        table = QTableWidget(len(data), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSortingEnabled(True)
        table.setStyleSheet(f"""
            QHeaderView::section {{
                background: {color}; color: white;
                padding: 5px; font-weight: bold; font-size: 10px;
            }}
            QTableWidget {{ font-size: 10px; }}
            QTableWidget::item:selected {{ background: #3498db; color: white; }}
        """)

        for row_idx, row_data in enumerate(data):
            for col_idx, val in enumerate(row_data):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row_idx, col_idx, item)

        return table

    def _filter_current_table(self, text):
        """فیلتر جدول فعلی"""
        current_tab = self.tabs.currentWidget()
        if not current_tab:
            return
        tables = current_tab.findChildren(QTableWidget)
        for table in tables:
            for row in range(table.rowCount()):
                match = False
                for col in range(table.columnCount()):
                    item = table.item(row, col)
                    if item and text.lower() in item.text().lower():
                        match = True
                        break
                table.setRowHidden(row, not match)

    def _export_current(self):
        current_tab = self.tabs.currentWidget()
        if not current_tab:
            return
        tables = current_tab.findChildren(QTableWidget)
        if tables:
            export = ExportManager(self)
            tab_name = self.tabs.tabText(self.tabs.currentIndex())
            export.export_table_with_dialog(tables[0], f"reference_{tab_name}")

    # ==================== 1. Casing (API 5CT) ====================

    def _create_casing_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        info = QLabel("📋 API 5CT Casing & Tubing Specifications")
        info.setStyleSheet("font-weight: bold; padding: 3px; color: #2c3e50;")
        layout.addWidget(info)

        sub_tabs = QTabWidget()
        sub_tabs.setTabPosition(QTabWidget.West)

        # Performance Properties
        headers = [
            "Size (in)", "Weight (ppf)", "Grade", "Wall (in)", "ID (in)",
            "Drift (in)", "Burst (psi)", "Collapse (psi)", "Tensile (1000 lbs)",
            "Connection"
        ]

        data = [
            # Conductor
            ["20.000", "133.00", "K-55", "0.635", "18.730", "18.605", "3060", "1500", "2125", "BTC"],
            # Surface Casing
            ["13.375", "54.50", "J-55", "0.380", "12.615", "12.459", "2730", "1130", "1069", "BTC"],
            ["13.375", "61.00", "K-55", "0.430", "12.515", "12.359", "3090", "1540", "1222", "BTC"],
            ["13.375", "68.00", "L-80", "0.480", "12.415", "12.259", "5540", "2260", "1556", "BTC"],
            ["13.375", "68.00", "P-110", "0.480", "12.415", "12.259", "6820", "5380", "2138", "Premium"],
            ["13.375", "72.00", "L-80", "0.514", "12.347", "12.191", "5920", "2670", "1666", "BTC"],
            ["13.375", "72.00", "P-110", "0.514", "12.347", "12.191", "8140", "5880", "2290", "Premium"],
            # Intermediate Casing
            ["9.625", "36.00", "J-55", "0.352", "8.921", "8.765", "3520", "2020", "718", "LTC"],
            ["9.625", "40.00", "K-55", "0.395", "8.835", "8.679", "3950", "2570", "809", "BTC"],
            ["9.625", "40.00", "N-80", "0.395", "8.835", "8.679", "5750", "3090", "1178", "BTC"],
            ["9.625", "43.50", "L-80", "0.435", "8.755", "8.599", "6330", "4420", "1295", "BTC"],
            ["9.625", "43.50", "C-95", "0.435", "8.755", "8.599", "7510", "5300", "1538", "Premium"],
            ["9.625", "47.00", "L-80", "0.472", "8.681", "8.525", "6870", "5310", "1401", "BTC"],
            ["9.625", "47.00", "P-110", "0.472", "8.681", "8.525", "9440", "7330", "1926", "Premium"],
            ["9.625", "53.50", "L-80", "0.545", "8.535", "8.379", "7930", "7210", "1613", "BTC"],
            ["9.625", "53.50", "P-110", "0.545", "8.535", "8.379", "10900", "8830", "2218", "Premium"],
            ["9.625", "58.40", "P-110", "0.595", "8.435", "8.279", "11890", "10010", "2414", "Premium"],
            # Production Casing
            ["7.000", "17.00", "J-55", "0.231", "6.538", "6.413", "3170", "1420", "407", "LTC"],
            ["7.000", "20.00", "K-55", "0.272", "6.456", "6.331", "3740", "2030", "490", "BTC"],
            ["7.000", "23.00", "L-80", "0.317", "6.366", "6.241", "5930", "4060", "725", "BTC"],
            ["7.000", "23.00", "N-80", "0.317", "6.366", "6.241", "5930", "4060", "725", "BTC"],
            ["7.000", "26.00", "L-80", "0.362", "6.276", "6.151", "6770", "5410", "826", "BTC"],
            ["7.000", "26.00", "P-110", "0.362", "6.276", "6.151", "9300", "7440", "1136", "Premium"],
            ["7.000", "29.00", "L-80", "0.408", "6.184", "6.059", "7630", "7030", "924", "BTC"],
            ["7.000", "29.00", "P-110", "0.408", "6.184", "6.059", "10490", "8160", "1270", "Premium"],
            ["7.000", "32.00", "L-80", "0.453", "6.094", "5.969", "8460", "7930", "1020", "BTC"],
            ["7.000", "32.00", "P-110", "0.453", "6.094", "5.969", "11630", "9380", "1402", "Premium"],
            ["7.000", "35.00", "P-110", "0.498", "6.004", "5.879", "12780", "10780", "1531", "Premium"],
            ["7.000", "38.00", "P-110", "0.540", "5.920", "5.795", "13860", "11390", "1663", "Premium"],
            # Liner
            ["5.500", "14.00", "J-55", "0.244", "5.012", "4.887", "4270", "2490", "329", "LTC"],
            ["5.500", "15.50", "K-55", "0.275", "4.950", "4.825", "4810", "3060", "376", "BTC"],
            ["5.500", "17.00", "L-80", "0.304", "4.892", "4.767", "6340", "4500", "498", "BTC"],
            ["5.500", "20.00", "L-80", "0.361", "4.778", "4.653", "7580", "6200", "588", "BTC"],
            ["5.500", "23.00", "L-80", "0.415", "4.670", "4.545", "8700", "7850", "669", "BTC"],
            ["5.500", "23.00", "P-110", "0.415", "4.670", "4.545", "11970", "10000", "920", "Premium"],
            ["5.500", "26.00", "P-110", "0.476", "4.548", "4.423", "13710", "11310", "1050", "Premium"],
            # 4-1/2" Liner
            ["4.500", "9.50", "J-55", "0.205", "4.090", "3.965", "4380", "2370", "211", "LTC"],
            ["4.500", "10.50", "K-55", "0.224", "4.052", "3.927", "4790", "2870", "234", "LTC"],
            ["4.500", "11.60", "L-80", "0.250", "4.000", "3.875", "6400", "4110", "333", "BTC"],
            ["4.500", "12.60", "L-80", "0.271", "3.958", "3.833", "6720", "5320", "369", "BTC"],
            ["4.500", "13.50", "P-110", "0.290", "3.920", "3.795", "9870", "7200", "543", "Premium"],
        ]

        perf_table = self._make_table(headers, data, "#2c3e50")
        sub_tabs.addTab(perf_table, "Performance")

        # Grade Properties
        grade_headers = ["Grade", "Min Yield (psi)", "Max Yield (psi)", "Min Tensile (psi)", "Hardness (HRC)", "Type"]
        grade_data = [
            ["H-40", "40,000", "80,000", "60,000", "N/A", "Carbon Steel"],
            ["J-55", "55,000", "80,000", "75,000", "N/A", "Carbon Steel"],
            ["K-55", "55,000", "80,000", "95,000", "N/A", "Carbon Steel"],
            ["N-80", "80,000", "110,000", "100,000", "N/A", "Carbon Steel"],
            ["L-80", "80,000", "95,000", "95,000", "23 max", "Low Alloy (SSC resistant)"],
            ["C-90", "90,000", "105,000", "100,000", "25.4 max", "Low Alloy (SSC resistant)"],
            ["C-95", "95,000", "110,000", "105,000", "N/A", "Carbon Steel"],
            ["T-95", "95,000", "110,000", "105,000", "25.4 max", "Low Alloy (SSC resistant)"],
            ["P-110", "110,000", "140,000", "125,000", "N/A", "Carbon Steel"],
            ["Q-125", "125,000", "150,000", "135,000", "N/A", "Carbon Steel"],
            ["V-150", "150,000", "N/A", "160,000", "N/A", "High Strength"],
        ]
        grade_table = self._make_table(grade_headers, grade_data, "#8e44ad")
        sub_tabs.addTab(grade_table, "Grades")

        layout.addWidget(sub_tabs)
        return tab

    # ==================== 2. Drill Pipe (API 5DP) ====================

    def _create_drillpipe_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        headers = [
            "Size (in)", "Nom Wt (ppf)", "Grade", "ID (in)",
            "TJ OD (in)", "TJ ID (in)", "Adj Wt (ppf)",
            "Cap (bbl/ft)", "Disp (bbl/ft)", "Connection",
            "Tensile (lbs)", "Torsion (ft-lbs)"
        ]

        data = [
            ["2-3/8", "6.65", "E-75", "1.815", "3.063", "1.750", "7.44", "0.00320", "0.00354", "NC26", "135,900", "4,650"],
            ["2-3/8", "6.65", "X-95", "1.815", "3.063", "1.750", "7.44", "0.00320", "0.00354", "NC26", "172,140", "5,890"],
            ["2-3/8", "6.65", "S-135", "1.815", "3.063", "1.750", "7.44", "0.00320", "0.00354", "NC26", "244,620", "8,370"],
            ["2-7/8", "10.40", "E-75", "2.151", "3.668", "2.000", "11.72", "0.00449", "0.00556", "NC31", "213,000", "8,750"],
            ["2-7/8", "10.40", "S-135", "2.151", "3.668", "2.000", "11.72", "0.00449", "0.00556", "NC31", "383,400", "15,750"],
            ["3-1/2", "13.30", "E-75", "2.764", "4.668", "2.563", "15.11", "0.00742", "0.00753", "NC38", "271,000", "14,900"],
            ["3-1/2", "13.30", "S-135", "2.764", "4.668", "2.563", "15.11", "0.00742", "0.00753", "NC38", "488,700", "26,800"],
            ["3-1/2", "15.50", "S-135", "2.602", "4.668", "2.438", "17.53", "0.00658", "0.00897", "NC38", "575,100", "31,000"],
            ["4", "14.00", "E-75", "3.340", "4.968", "2.813", "16.05", "0.01084", "0.00815", "NC40", "287,000", "18,000"],
            ["4", "14.00", "S-135", "3.340", "4.968", "2.813", "16.05", "0.01084", "0.00815", "NC40", "516,600", "32,400"],
            ["4-1/2", "16.60", "E-75", "3.826", "6.375", "3.500", "19.38", "0.01422", "0.01017", "NC46", "339,000", "25,500"],
            ["4-1/2", "16.60", "S-135", "3.826", "6.375", "3.500", "19.38", "0.01422", "0.01017", "NC46", "610,200", "45,900"],
            ["4-1/2", "20.00", "S-135", "3.640", "6.375", "3.250", "23.26", "0.01287", "0.01224", "NC46", "743,580", "55,260"],
            ["5", "19.50", "E-75", "4.276", "6.625", "3.750", "22.64", "0.01776", "0.01242", "NC50", "399,000", "35,800"],
            ["5", "19.50", "G-105", "4.276", "6.625", "3.750", "22.64", "0.01776", "0.01242", "NC50", "558,600", "50,120"],
            ["5", "19.50", "S-135", "4.276", "6.625", "3.750", "22.64", "0.01776", "0.01242", "NC50", "718,200", "64,440"],
            ["5", "25.60", "S-135", "4.000", "6.625", "3.500", "29.19", "0.01553", "0.01630", "NC50", "950,400", "83,700"],
            ["5-1/2", "21.90", "E-75", "4.778", "7.000", "4.000", "25.05", "0.02218", "0.01388", "5-1/2 FH", "447,000", "44,000"],
            ["5-1/2", "21.90", "S-135", "4.778", "7.000", "4.000", "25.05", "0.02218", "0.01388", "5-1/2 FH", "804,600", "79,200"],
            ["5-1/2", "24.70", "S-135", "4.670", "7.000", "3.750", "28.33", "0.02118", "0.01618", "5-1/2 FH", "921,600", "90,200"],
            ["5-7/8", "23.40", "S-135", "5.153", "7.375", "4.250", "26.92", "0.02580", "0.01524", "5-1/2 FH", "858,600", "86,900"],
            ["6-5/8", "25.20", "E-75", "5.965", "8.000", "4.750", "28.72", "0.03456", "0.01588", "6-5/8 FH", "513,000", "56,600"],
            ["6-5/8", "25.20", "S-135", "5.965", "8.000", "4.750", "28.72", "0.03456", "0.01588", "6-5/8 FH", "923,400", "101,880"],
        ]

        table = self._make_table(headers, data, "#27ae60")
        layout.addWidget(table)
        return tab

    # ==================== 3. Drill Collars ====================

    def _create_collar_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        headers = [
            "OD (in)", "ID (in)", "Weight (ppf)", "Disp (bbl/ft)",
            "Cap (bbl/ft)", "Connection", "MU Torque (ft-lbs)", "Tensile (lbs)"
        ]

        data = [
            ["3-1/8", "1-1/4", "19", "0.00556", "0.00152", "NC26", "3,800", "93,000"],
            ["3-1/2", "1-1/2", "23", "0.00695", "0.00219", "NC26", "4,800", "109,000"],
            ["4-1/8", "1-1/2", "33", "0.00985", "0.00219", "NC31", "7,500", "162,000"],
            ["4-3/4", "2-1/4", "40", "0.01262", "0.00492", "NC38", "11,400", "174,000"],
            ["4-3/4", "2-13/16", "36", "0.01126", "0.00769", "NC38", "10,200", "144,000"],
            ["6", "2-1/4", "73", "0.02098", "0.00492", "NC46", "22,200", "341,000"],
            ["6", "2-13/16", "66", "0.01936", "0.00769", "NC46", "20,000", "280,000"],
            ["6-1/2", "2-1/4", "87", "0.02482", "0.00492", "NC50", "28,800", "411,000"],
            ["6-1/2", "2-13/16", "80", "0.02320", "0.00769", "NC50", "26,500", "350,000"],
            ["6-3/4", "2-1/4", "94", "0.02698", "0.00492", "NC50", "31,000", "447,000"],
            ["6-3/4", "2-13/16", "87", "0.02536", "0.00769", "NC50", "29,000", "386,000"],
            ["7", "2-13/16", "93", "0.02756", "0.00769", "NC50", "32,000", "421,000"],
            ["7-1/4", "2-13/16", "100", "0.02981", "0.00769", "6-5/8 Reg", "35,000", "459,000"],
            ["8", "2-13/16", "124", "0.03667", "0.00769", "6-5/8 Reg", "50,000", "578,000"],
            ["8", "3", "120", "0.03600", "0.00874", "6-5/8 Reg", "48,500", "553,000"],
            ["9", "3", "153", "0.04598", "0.00874", "7-5/8 Reg", "61,600", "726,000"],
            ["9-1/2", "3", "171", "0.05128", "0.00874", "7-5/8 Reg", "72,300", "816,000"],
            ["11", "3", "233", "0.06945", "0.00874", "7-5/8 Reg", "100,000", "1,108,000"],
            ["12", "3", "280", "0.08301", "0.00874", "8-5/8 Reg", "130,000", "1,344,000"],
        ]

        table = self._make_table(headers, data, "#e74c3c")
        layout.addWidget(table)
        return tab

    # ==================== 4. Connections ====================

    def _create_connections_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        sub_tabs = QTabWidget()

        # API Rotary Shoulder
        conn_headers = ["Connection", "OD (in)", "ID (in)", "Pin Nose (in)",
                         "Bevel Dia (in)", "MU Torque (ft-lbs)", "Tensile (lbs)"]
        conn_data = [
            ["NC23 (2-3/8 IF)", "3.063", "1.250", "2.000", "2.438", "5,000", "132,000"],
            ["NC26 (2-7/8 IF)", "3.375", "1.500", "2.250", "2.750", "7,500", "176,000"],
            ["NC31 (3-1/2 IF)", "4.000", "1.750", "2.625", "3.250", "12,000", "270,000"],
            ["NC38 (4 IF)", "4.750", "2.000", "3.125", "3.875", "18,000", "404,000"],
            ["NC40 (4-1/2 IF)", "5.000", "2.250", "3.375", "4.125", "22,000", "470,000"],
            ["NC46 (4 FH)", "6.000", "2.750", "3.625", "5.125", "31,200", "776,000"],
            ["NC50 (4-1/2 FH)", "6.625", "3.000", "4.000", "5.500", "40,000", "978,000"],
            ["NC56 (5-1/2 FH)", "7.250", "3.250", "4.375", "6.000", "51,000", "1,200,000"],
            ["6-5/8 FH", "8.000", "3.750", "4.875", "6.625", "67,100", "1,506,000"],
            ["4-1/2 API Reg", "4.750", "2.375", "3.375", "4.125", "18,100", "332,000"],
            ["6-5/8 API Reg", "8.000", "3.000", "5.500", "6.625", "55,700", "976,000"],
            ["7-5/8 API Reg", "9.500", "3.250", "6.250", "7.750", "80,000", "1,412,000"],
            ["8-5/8 API Reg", "10.625", "3.750", "7.250", "8.750", "110,000", "1,834,000"],
        ]
        conn_table = self._make_table(conn_headers, conn_data, "#2c3e50")
        sub_tabs.addTab(conn_table, "API Rotary Shoulder")

        # Casing Connections
        csg_conn_headers = ["Connection", "Type", "Seal", "Tension (%)", "Pressure (%)", "Application"]
        csg_conn_data = [
            ["STC", "API Threaded", "Thread", "100%", "100%", "Standard"],
            ["LTC", "API Threaded", "Thread", "100%", "100%", "Long Thread"],
            ["BTC", "API Buttress", "Thread", "100%", "100%", "High Tension"],
            ["VAM TOP", "Premium", "Metal-Metal", "100%", "100%", "High Performance"],
            ["VAM SLIJ-II", "Premium", "Metal-Metal", "100%", "100%", "Slim Hole"],
            ["Hunting SEAL-LOCK", "Premium", "Metal-Metal", "100%", "100%", "Gas Tight"],
            ["Tenaris Blue", "Premium", "Metal-Metal", "100%", "100%", "HPHT"],
            ["Hydril 563", "Premium", "Metal-Metal", "100%", "100%", "High Collapse"],
            ["Grant Prideco XT", "Premium", "Metal-Metal", "100%", "100%", "Torque Shoulder"],
        ]
        csg_conn_table = self._make_table(csg_conn_headers, csg_conn_data, "#9b59b6")
        sub_tabs.addTab(csg_conn_table, "Casing Connections")

        layout.addWidget(sub_tabs)
        return tab

    # ==================== 5. Bit Data ====================

    def _create_bit_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        sub_tabs = QTabWidget()

        # Bit Sizes
        bit_headers = ["Hole Size (in)", "Bit OD (in)", "Recommended CSG", "CSG OD (in)", "Clearance (in)"]
        bit_data = [
            ["36\"", "36.000", "30\" Conductor", "30.000", "3.000"],
            ["26\"", "26.000", "20\" Surface", "20.000", "3.000"],
            ["17-1/2\"", "17.500", "13-3/8\" CSG", "13.375", "2.063"],
            ["16\"", "16.000", "13-3/8\" CSG", "13.375", "1.313"],
            ["14-3/4\"", "14.750", "11-3/4\" CSG", "11.750", "1.500"],
            ["12-1/4\"", "12.250", "9-5/8\" CSG", "9.625", "1.313"],
            ["9-7/8\"", "9.875", "7-5/8\" CSG", "7.625", "1.125"],
            ["8-3/4\"", "8.750", "7\" CSG", "7.000", "0.875"],
            ["8-1/2\"", "8.500", "7\" CSG", "7.000", "0.750"],
            ["6-1/8\"", "6.125", "5\" Liner", "5.000", "0.563"],
            ["6\"", "6.000", "4-1/2\" Liner", "4.500", "0.750"],
        ]
        bit_table = self._make_table(bit_headers, bit_data, "#e67e22")
        sub_tabs.addTab(bit_table, "Bit Sizes")

        # Nozzle TFA
        nzl_headers = ["Nozzle (1/32\")", "Diameter (in)", "Area per Nozzle (in²)", "3 Nozzle TFA", "4 Nozzle TFA", "6 Nozzle TFA"]
        nzl_data = []
        import math
        for size in range(6, 33):
            d = size / 32.0
            area = math.pi / 4 * d**2
            nzl_data.append([
                str(size), f"{d:.4f}", f"{area:.4f}",
                f"{area*3:.4f}", f"{area*4:.4f}", f"{area*6:.4f}"
            ])
        nzl_table = self._make_table(nzl_headers, nzl_data, "#3498db")
        sub_tabs.addTab(nzl_table, "Nozzle TFA Table")

        layout.addWidget(sub_tabs)
        return tab

    # ==================== 6. Cement ====================

    def _create_cement_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        headers = [
            "Class", "Water Req (gal/sk)", "Density (pcf)", "Yield (ft³/sk)",
            "Temp Range (°F)", "Depth Range (ft)", "Thickening Time",
            "Application"
        ]

        data = [
            ["Class A", "5.2", "15.6 ppg", "1.18", "60-170", "0-6,000", "45-90 min", "Surface to moderate depth"],
            ["Class B", "5.2", "15.6 ppg", "1.18", "60-170", "0-6,000", "45-90 min", "Moderate sulfate resistance"],
            ["Class C", "6.3", "14.8 ppg", "1.32", "60-170", "0-6,000", "45-90 min", "High early strength"],
            ["Class D", "4.3", "16.4 ppg", "1.05", "170-290", "6,000-10,000", "120-180 min", "Moderate depth, high temp"],
            ["Class E", "4.3", "16.4 ppg", "1.05", "170-290", "6,000-14,000", "120-180 min", "High temp, high pressure"],
            ["Class F", "4.3", "16.4 ppg", "1.05", "230-320", "10,000-16,000", "180-240 min", "Very high temp"],
            ["Class G", "5.0", "15.8 ppg", "1.15", "80-200", "0-8,000", "90-120 min", "Basic cement (most common)"],
            ["Class H", "4.3", "16.4 ppg", "1.06", "80-200", "0-8,000", "90-120 min", "Basic cement (coarse grind)"],
        ]

        table = self._make_table(headers, data, "#e67e22")

        info = QLabel("📌 Source: API Specification 10A | All values at standard conditions")
        info.setStyleSheet("color: #7f8c8d; font-size: 9px; padding: 3px;")

        layout.addWidget(table)
        layout.addWidget(info)
        return tab

    # ==================== 7. Mud Additives ====================

    def _create_mud_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        headers = [
            "Product", "Category", "Function", "Concentration",
            "Specific Gravity", "Mud Type"
        ]

        data = [
            ["Bentonite (Gel)", "Viscosifier", "Viscosity & filtration", "15-25 ppb", "2.65", "WBM"],
            ["Barite (BaSO4)", "Weighting", "Increase mud weight", "As needed", "4.20", "WBM/OBM"],
            ["Calcium Carbonate", "Weighting/LCM", "Weight/bridging", "As needed", "2.71", "WBM/OBM"],
            ["Hematite", "Weighting", "High density weighting", "As needed", "5.05", "WBM/OBM"],
            ["CMC-LV", "Filtration", "Fluid loss control", "0.5-2 ppb", "N/A", "WBM"],
            ["CMC-HV", "Viscosifier", "Viscosity builder", "0.5-2 ppb", "N/A", "WBM"],
            ["PAC-R", "Viscosifier", "Rheology control", "0.5-2 ppb", "N/A", "WBM"],
            ["PAC-L", "Filtration", "Fluid loss control", "0.5-1 ppb", "N/A", "WBM"],
            ["Xanthan Gum", "Viscosifier", "Viscosity (shear thin)", "0.5-2 ppb", "N/A", "WBM"],
            ["Caustic Soda (NaOH)", "Alkalinity", "pH control", "0.25-1 ppb", "2.13", "WBM"],
            ["Soda Ash (Na2CO3)", "Alkalinity", "Hardness removal", "0.5-2 ppb", "2.53", "WBM"],
            ["KCl", "Shale Inhibitor", "Shale stabilization", "3-15%", "1.98", "WBM"],
            ["NaCl", "Salinity", "Salinity control", "As needed", "2.16", "WBM"],
            ["Mica (Fine/Med/Coarse)", "LCM", "Lost circulation", "5-50 ppb", "2.80", "WBM/OBM"],
            ["Nut Plug (Fine/Med)", "LCM", "Lost circulation", "5-30 ppb", "1.30", "WBM/OBM"],
            ["Gilsonite", "LCM/Stabilizer", "Lost circ/wellbore", "5-25 ppb", "1.05", "WBM/OBM"],
            ["Lime (Ca(OH)2)", "Alkalinity", "Alkalinity/pH", "0.5-5 ppb", "2.34", "OBM"],
            ["Emulsifier (Primary)", "Emulsifier", "Create emulsion", "4-8 ppb", "N/A", "OBM"],
            ["Wetting Agent", "Emulsifier", "Oil-wet solids", "1-4 ppb", "N/A", "OBM"],
            ["Organophilic Clay", "Viscosifier", "Viscosity in OBM", "2-8 ppb", "N/A", "OBM"],
            ["Lignosulfonate", "Deflocculant", "Thin mud/reduce vis", "2-6 ppb", "N/A", "WBM"],
            ["PHPA", "Encapsulator", "Shale encapsulation", "0.5-2 ppb", "N/A", "WBM"],
            ["Defoamer", "Defoamer", "Remove foam", "0.05-0.5 ppb", "N/A", "WBM/OBM"],
            ["Pipe-Lax (Lubricant)", "Lubricant", "Reduce torque/drag", "1-3%", "N/A", "WBM/OBM"],
        ]

        table = self._make_table(headers, data, "#27ae60")
        layout.addWidget(table)
        return tab

    # ==================== 8. Quick Formulas ====================

    def _create_formulas_tab(self):
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)

        formulas = [
            ("📊 Volume & Capacity", [
                ("Pipe Capacity (bbl/ft)", "ID² / 1029.4"),
                ("Pipe Capacity (bbl/m)", "ID² × 3.281 / 1029.4"),
                ("Annular Capacity (bbl/ft)", "(Dh² - Dp²) / 1029.4"),
                ("Displacement (bbl/ft)", "(OD² - ID²) / 1029.4"),
                ("Pump Output — Triplex (bbl/stk)", "0.000243 × Liner² × Stroke × Eff"),
                ("Pump Output — Duplex (bbl/stk)", "0.000162 × Stroke × (2×Liner² − Rod²) × Eff"),
                ("Flow Rate (gpm)", "Pump Output × SPM × 42"),
            ]),
            ("💧 Hydraulics", [
                ("Annular Velocity (ft/min)", "24.5 × GPM / (Dh² - Dp²)"),
                ("Pipe Velocity (ft/min)", "24.5 × GPM / ID²"),
                ("Bit Pressure Loss (psi)", "GPM² × MW / (10858 × TFA²)"),
                ("TFA (in²)", "π/4 × Σ(di²)  [di = nozzle diameter]"),
                ("Bit HHP", "GPM × ΔP / 1714"),
                ("HSI (hp/in²)", "GPM × ΔP / (1346 × Bit OD²)"),
                ("Jet Velocity (ft/s)", "GPM / (3.117 × TFA)"),
                ("Impact Force (lbs)", "MW × GPM × Vn / 1930"),
                ("ECD (ppg)", "MW + APL / (0.052 × TVD)"),
            ]),
            ("⚖️ Weight & Buoyancy", [
                ("Buoyancy Factor", "1 - (MW / 489.5)  [MW in pcf]"),
                ("Buoyancy Factor", "1 - (MW / 65.5)   [MW in ppg]"),
                ("Hook Load (lbs)", "String Wt × BF + TDS Wt"),
                ("Adjusted Weight (ppf)", "2.67 × (OD² - ID²)"),
                ("Hydrostatic (psi)", "0.052 × MW(ppg) × TVD(ft)"),
                ("Hydrostatic (psi)", "0.00695 × MW(pcf) × TVD(m)"),
            ]),
            ("🛡️ Well Control", [
                ("Kill MW (ppg)", "OMW + SIDPP / (0.052 × TVD)"),
                ("ICP (psi)", "SCR + SIDPP"),
                ("FCP (psi)", "SCR × (KMW / OMW)"),
                ("MAASP (psi)", "(FG - MW × 0.052) × Shoe TVD"),
                ("Kick Intensity", "FracMW - CurrentMW"),
                ("Pressure Gradient", "P(psi) / TVD(ft)"),
            ]),
            ("🧪 Mud Calculations", [
                ("PV (cp)", "θ600 - θ300"),
                ("YP (lb/100ft²)", "θ300 - PV"),
                ("n (Power Law)", "3.32 × log(θ600/θ300)"),
                ("K", "511 × θ300 / (511^n)"),
                ("Barite (sacks)", "Vol(bbl) × 42 × (TargetMW - CurrentMW) / (1470 - TargetMW) / 100"),
                ("MW Conversion", "ppg × 7.48 = pcf | ppg × 0.12 = sg"),
            ]),
            ("📐 Directional", [
                ("Build Rate (°/100ft)", "(Inc2 - Inc1) / ΔMD × 100"),
                ("Build Rate (°/30m)", "(Inc2 - Inc1) / ΔMD × 30"),
                ("DLS (°/100ft)", "acos(cosβ) / ΔMD × 100"),
                ("cosβ", "sinI1·sinI2·cos(A2-A1) + cosI1·cosI2"),
                ("RF (Ratio Factor)", "2/β × tan(β/2)"),
            ]),
            ("📏 Conversions", [
                ("m → ft", "× 3.28084"),
                ("ft → m", "× 0.3048"),
                ("bbl → m³", "× 0.158987"),
                ("gal → liters", "× 3.7854"),
                ("ppg → pcf", "× 7.48052"),
                ("ppg → sg", "× 0.11982"),
                ("ppg → psi/ft", "× 0.052"),
                ("psi → bar", "× 0.06895"),
                ("psi → kPa", "× 6.8948"),
                ("°F → °C", "(°F - 32) × 5/9"),
                ("in → mm", "× 25.4"),
            ]),
        ]

        for category, items in formulas:
            group = QGroupBox(category)
            group.setStyleSheet("QGroupBox { font-weight: bold; color: #2c3e50; }")
            grid = QGridLayout(group)
            for i, (name, formula) in enumerate(items):
                name_label = QLabel(name)
                name_label.setStyleSheet("font-size: 10px; color: #2c3e50;")
                formula_label = QLabel(formula)
                formula_label.setStyleSheet(
                    "font-size: 10px; font-family: Consolas; color: #e74c3c; "
                    "font-weight: bold; background: #f8f9fa; padding: 2px 6px; "
                    "border-radius: 3px;"
                )
                grid.addWidget(name_label, i, 0)
                grid.addWidget(formula_label, i, 1)
            layout.addWidget(group)

        scroll.setWidget(content)
        tab_layout = QVBoxLayout(tab)
        tab_layout.addWidget(scroll)
        return tab

    # ==================== 9. Unit Conversion ====================

    def _create_conversion_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        headers = ["From", "To", "Multiply by", "Example"]
        data = [
            # Length
            ["meters (m)", "feet (ft)", "3.28084", "100 m = 328.08 ft"],
            ["feet (ft)", "meters (m)", "0.3048", "100 ft = 30.48 m"],
            ["inches (in)", "millimeters (mm)", "25.4", "1 in = 25.4 mm"],
            ["millimeters (mm)", "inches (in)", "0.03937", "25.4 mm = 1 in"],
            # Volume
            ["barrels (bbl)", "cubic meters (m³)", "0.15899", "100 bbl = 15.9 m³"],
            ["barrels (bbl)", "gallons (gal)", "42", "1 bbl = 42 gal"],
            ["barrels (bbl)", "liters (L)", "158.987", "1 bbl = 159 L"],
            ["gallons (gal)", "liters (L)", "3.7854", "1 gal = 3.79 L"],
            ["cubic feet (ft³)", "barrels (bbl)", "0.17811", "5.615 ft³ = 1 bbl"],
            # Weight/Density
            ["ppg", "pcf", "7.48052", "10 ppg = 74.8 pcf"],
            ["ppg", "sg", "0.11982", "8.33 ppg = 1.0 sg"],
            ["ppg", "kg/m³", "119.826", "10 ppg = 1198 kg/m³"],
            ["pcf", "ppg", "0.13368", "75 pcf = 10.03 ppg"],
            ["pcf", "kg/m³", "16.0185", "62.4 pcf = 1000 kg/m³"],
            # Pressure
            ["psi", "bar", "0.06895", "1000 psi = 68.95 bar"],
            ["psi", "kPa", "6.89476", "1000 psi = 6894.76 kPa"],
            ["psi", "MPa", "0.00689", "1000 psi = 6.89 MPa"],
            ["bar", "psi", "14.5038", "100 bar = 1450.38 psi"],
            ["atm", "psi", "14.696", "1 atm = 14.696 psi"],
            # Flow
            ["gpm", "L/min", "3.7854", "100 gpm = 378.5 L/min"],
            ["gpm", "bbl/min", "0.02381", "42 gpm = 1 bbl/min"],
            ["bbl/min", "gpm", "42", "1 bbl/min = 42 gpm"],
            # Temperature
            ["°F", "°C", "(°F - 32) × 5/9", "212°F = 100°C"],
            ["°C", "°F", "°C × 9/5 + 32", "100°C = 212°F"],
            # Force/Torque
            ["ft-lbs", "N-m", "1.3558", "1000 ft-lbs = 1356 N-m"],
            ["lbs", "kg", "0.4536", "1000 lbs = 454 kg"],
            ["klbs", "tonnes", "0.4536", "100 klbs = 45.4 tonnes"],
            ["short ton", "metric ton", "0.9072", "1 short ton = 0.907 MT"],
        ]

        table = self._make_table(headers, data, "#3498db")
        layout.addWidget(table)
        return tab

    def _create_hole_casing_tab(self):
        """جدول سایزبندی حفره و کیسینگ"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        headers = [
            "Hole Size (in)", "Pilot Hole (in)", "Casing OD (in)", "Casing ID (in)",
            "Weight Range (ppf)", "Drift (in)", "Bit-CSG Clear (in)", "Common Grade"
        ]

        data = [
            ["36\"", "26\"", "30.000", "29.000", "250-310", "28.750", "3.000", "X-52/K-55"],
            ["26\"", "17-1/2\"", "20.000", "18.730", "94-133", "18.605", "3.000", "K-55/L-80"],
            ["17-1/2\"", "12-1/4\"", "13.375", "12.415", "54-72", "12.259", "2.063", "K-55/P-110"],
            ["16\"", "12-1/4\"", "13.375", "12.415", "54-72", "12.259", "1.313", "K-55/P-110"],
            ["14-3/4\"", "12-1/4\"", "11.750", "10.772", "42-60", "10.616", "1.489", "N-80/P-110"],
            ["12-1/4\"", "8-1/2\"", "9.625", "8.535", "36-58", "8.379", "1.313", "L-80/P-110"],
            ["9-7/8\"", "8-1/2\"", "7.625", "6.765", "24-39", "6.640", "1.125", "L-80/P-110"],
            ["8-3/4\"", "6\"", "7.000", "6.094", "23-38", "5.969", "0.875", "L-80/P-110"],
            ["8-1/2\"", "6\"", "7.000", "6.094", "23-38", "5.969", "0.750", "L-80/P-110"],
            ["6-1/8\"", "4-1/2\"", "5.000", "4.276", "15-23", "4.151", "0.563", "L-80/P-110"],
            ["6\"", "4-1/2\"", "4.500", "3.920", "11-15", "3.795", "0.750", "L-80/P-110"],
            ["4-3/4\"", "3-7/8\"", "3.500", "2.992", "9-13", "2.867", "0.625", "L-80/P-110"],
        ]

        table = self._make_table(headers, data, "#e67e22")
        layout.addWidget(table)
        return tab

    def _create_torque_tab(self):
        """جدول MU Torque"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        sub_tabs = QTabWidget()

        # DP Connections
        dp_headers = ["Connection", "Size (in)", "OD (in)", "ID (in)", "MU Torque (ft-lbs)", "Tensile (lbs)", "Torsion (ft-lbs)"]
        dp_data = [
            ["NC26", "2-3/8", "3.063", "1.250", "5,000-6,800", "132,000", "6,200"],
            ["NC31", "2-7/8", "3.375", "1.500", "7,500-10,200", "176,000", "9,600"],
            ["NC38", "3-1/2", "4.000", "1.750", "12,000-16,300", "270,000", "16,000"],
            ["NC40", "4", "5.000", "2.250", "18,000-24,500", "470,000", "21,500"],
            ["NC46", "4-1/2", "6.000", "2.750", "31,200-42,400", "776,000", "36,000"],
            ["NC50", "5", "6.625", "3.000", "40,000-54,400", "978,000", "48,000"],
            ["5-1/2 FH", "5-1/2", "7.250", "3.250", "51,000-69,400", "1,200,000", "63,000"],
            ["6-5/8 FH", "6-5/8", "8.000", "3.750", "67,100-91,300", "1,506,000", "82,000"],
            ["6-5/8 Reg", "6-5/8", "8.000", "3.000", "55,700-75,800", "976,000", "65,000"],
            ["7-5/8 Reg", "7-5/8", "9.500", "3.250", "80,000-108,800", "1,412,000", "100,000"],
        ]
        dp_table = self._make_table(dp_headers, dp_data, "#e74c3c")
        sub_tabs.addTab(dp_table, "DP Connections")

        # Casing Connections
        csg_headers = ["Size (in)", "Weight (ppf)", "Grade", "Connection", "MU Torque (ft-lbs)", "Min MU", "Max MU"]
        csg_data = [
            ["13-3/8", "61", "P-110", "BTC", "11,150", "9,200", "13,100"],
            ["13-3/8", "68", "P-110", "BTC", "12,700", "10,500", "14,900"],
            ["9-5/8", "40", "K-55", "BTC", "7,050", "5,800", "8,300"],
            ["9-5/8", "43.5", "L-80", "BTC", "10,000", "8,250", "11,750"],
            ["9-5/8", "47", "L-80", "BTC", "10,900", "9,000", "12,800"],
            ["9-5/8", "47", "P-110", "Premium", "12,500", "10,300", "14,700"],
            ["7", "23", "L-80", "BTC", "5,600", "4,600", "6,600"],
            ["7", "26", "L-80", "BTC", "6,500", "5,400", "7,600"],
            ["7", "29", "L-80", "BTC", "7,400", "6,100", "8,700"],
            ["7", "29", "P-110", "TPCQ", "10,160", "8,400", "12,400"],
            ["7", "32", "P-110", "Premium", "11,500", "9,500", "13,500"],
            ["5-1/2", "17", "L-80", "BTC", "4,200", "3,500", "4,900"],
            ["5-1/2", "20", "L-80", "BTC", "5,100", "4,200", "6,000"],
            ["5-1/2", "23", "P-110", "Premium", "8,200", "6,800", "9,600"],
            ["4-1/2", "11.6", "L-80", "BTC", "3,100", "2,600", "3,600"],
            ["4-1/2", "13.5", "P-110", "BTC", "5,200", "4,300", "6,100"],
        ]
        csg_table = self._make_table(csg_headers, csg_data, "#3498db")
        sub_tabs.addTab(csg_table, "Casing MU Torque")

        layout.addWidget(sub_tabs)
        return tab

    def _create_fluid_tab(self):
        """خواص سیالات و تبدیل وزن گل"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        sub_tabs = QTabWidget()

        # MW Conversion
        mw_headers = ["ppg", "pcf", "SG", "psi/ft", "kPa/m"]
        mw_data = []
        for ppg_x10 in range(70, 210, 5):
            ppg = ppg_x10 / 10.0
            pcf = ppg * 7.48052
            sg = ppg * 0.11982
            psi_ft = ppg * 0.052
            kpa_m = ppg * 1.175
            mw_data.append([f"{ppg:.1f}", f"{pcf:.1f}", f"{sg:.3f}", f"{psi_ft:.4f}", f"{kpa_m:.2f}"])
        mw_table = self._make_table(mw_headers, mw_data, "#1abc9c")
        sub_tabs.addTab(mw_table, "MW Conversion")

        # Hydrostatic
        hp_headers = ["Depth (ft)", "8.33 ppg", "9.0 ppg", "10.0 ppg", "11.0 ppg", "12.0 ppg", "13.0 ppg", "14.0 ppg", "15.0 ppg", "16.0 ppg"]
        hp_data = []
        for depth in [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 12000, 14000, 16000, 18000, 20000]:
            row = [str(depth)]
            for mw in [8.33, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]:
                hp = 0.052 * mw * depth
                row.append(f"{hp:.0f}")
            hp_data.append(row)
        hp_table = self._make_table(hp_headers, hp_data, "#e74c3c")
        sub_tabs.addTab(hp_table, "Hydrostatic Pressure")

        # Temperature
        temp_headers = ["Depth (ft)", "Grad 1.0°F/100ft", "Grad 1.2°F/100ft", "Grad 1.5°F/100ft", "Grad 1.8°F/100ft"]
        temp_data = []
        surface_temp = 70
        for depth in [1000, 2000, 3000, 4000, 5000, 6000, 8000, 10000, 12000, 15000, 18000, 20000]:
            row = [str(depth)]
            for grad in [1.0, 1.2, 1.5, 1.8]:
                temp = surface_temp + grad * depth / 100
                row.append(f"{temp:.0f} °F ({(temp-32)*5/9:.0f} °C)")
            temp_data.append(row)
        temp_table = self._make_table(temp_headers, temp_data, "#f39c12")
        sub_tabs.addTab(temp_table, "BHT Estimation")

        layout.addWidget(sub_tabs)
        return tab
    # ==================== DrillTabBase ====================

    def on_well_changed(self, well_id, well_data):
        pass

    def save_data(self):
        return True

    def refresh(self):
        pass