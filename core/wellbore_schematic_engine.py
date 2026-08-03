# core/wellbore_schematic_engine.py
"""
Wellbore Schematic Engine - موتور رندر حرفه‌ای
قابلیت‌ها:
- Christmas Tree (Xmas Tree)
- Wellhead
- Casing strings (Conductor, Surface, Intermediate, Production)
- Tubing string
- Packers
- Perforations
- Cement
- Formation layers
- Completion equipment
- Auto-generate از DB
- Export به SVG/PNG/PDF
"""

import math
import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *
from PySide6.QtSvg import QSvgGenerator

logger = logging.getLogger(__name__)


# ==================== Enums ====================

class ElementType(Enum):
    """انواع المنت‌های شماتیک."""
    XMAS_TREE = "xmas_tree"
    WELLHEAD = "wellhead"
    CONDUCTOR = "conductor"
    SURFACE_CASING = "surface_casing"
    INTERMEDIATE_CASING = "intermediate_casing"
    PRODUCTION_CASING = "production_casing"
    LINER = "liner"
    TUBING = "tubing"
    PACKER = "packer"
    PERFORATIONS = "perforations"
    CEMENT = "cement"
    FORMATION = "formation"
    DRILL_STRING = "drill_string"
    BIT = "bit"
    MWD = "mwd"
    MOTOR = "motor"
    STABILIZER = "stabilizer"
    BRIDGE_PLUG = "bridge_plug"
    SAND_SCREEN = "sand_screen"
    SLIDING_SLEEVE = "sliding_sleeve"
    SAFETY_VALVE = "safety_valve"
    GAS_LIFT_VALVE = "gas_lift_valve"
    DEPTH_LABEL = "depth_label"
    ANNOTATION = "annotation"


# ==================== Data Classes ====================

@dataclass
class CasingData:
    """اطلاعات یک رشته کیسینگ."""
    name: str
    element_type: ElementType
    od_inch: float
    id_inch: float
    top_depth_m: float
    bottom_depth_m: float
    grade: str = "L-80"
    connection: str = "BTC"
    weight_ppf: float = 0.0
    cement_top_m: float = 0.0
    cement_bottom_m: float = 0.0
    show_cement: bool = True
    color: str = ""


@dataclass
class FormationLayer:
    """یک لایه سازند."""
    name: str
    top_depth_m: float
    bottom_depth_m: float
    lithology: str = "Shale"
    color: str = "#808080"
    hatch_pattern: str = "shale"


@dataclass
class CompletionItem:
    """یک المنت Completion."""
    element_type: ElementType
    depth_m: float
    od_inch: float = 0.0
    length_m: float = 1.0
    label: str = ""
    color: str = ""


@dataclass
class SchematicConfig:
    """تنظیمات ظاهری شماتیک."""
    # ابعاد
    total_width: int = 800
    total_height: int = 1200
    margin_top: int = 80
    margin_bottom: int = 50
    margin_left: int = 120
    margin_right: int = 120

    # مقیاس
    depth_scale: float = 0.0  # pixel per meter (auto-calculated)
    od_scale: float = 15.0    # pixel per inch OD

    # رنگ‌ها
    background_color: str = "#1e2a3a"
    text_color: str = "#ecf0f1"
    grid_color: str = "#2c3e50"
    depth_line_color: str = "#34495e"

    # فونت
    font_family: str = "Arial"
    font_size: int = 9
    title_font_size: int = 12

    # نمایش
    show_depth_scale: bool = True
    show_formations: bool = True
    show_cement: bool = True
    show_labels: bool = True
    show_grid: bool = True
    show_legend: bool = True
    dark_mode: bool = True

    use_tvd_for_display: bool = True
    show_depth_type: str = "TVD"  
    
@dataclass
class WellboreSchematic:
    """مدل کامل شماتیک چاه."""
    well_name: str = ""
    rig_name: str = ""
    total_depth_m: float = 3000.0
    water_depth_m: float = 0.0
    gle_msl_m: float = 10.0
    kb_msl_m: float = 15.0

    casings: List[CasingData] = field(default_factory=list)
    formations: List[FormationLayer] = field(default_factory=list)
    completion: List[CompletionItem] = field(default_factory=list)

    show_xmas_tree: bool = True
    show_wellhead: bool = True
    show_tubing: bool = True
    tubing_od_inch: float = 3.5
    tubing_bottom_m: float = 2800.0


# ==================== Colors & Patterns ====================

class SchematicColors:
    """رنگ‌های استاندارد المنت‌ها."""

    CONDUCTOR = "#8B4513"          # قهوه‌ای
    SURFACE_CASING = "#4682B4"     # آبی فولادی
    INTERMEDIATE_CASING = "#2E8B57"  # سبز دریایی
    PRODUCTION_CASING = "#DAA520"  # طلایی
    LINER = "#9370DB"              # بنفش
    TUBING = "#FF6347"             # قرمز گوجه

    CEMENT = "#C0C0C0"             # خاکستری نقره‌ای
    CEMENT_ALPHA = 160

    PACKER = "#FF4500"             # قرمز نارنجی
    PERFORATION = "#FFD700"        # طلایی
    BRIDGE_PLUG = "#8B008B"        # بنفش تیره
    SAFETY_VALVE = "#006400"       # سبز تیره

    XMAS_TREE = "#2F4F4F"          # سبز تیره
    WELLHEAD = "#696969"           # خاکستری

    # سازندها
    FORMATIONS = {
        "Shale": "#808080",
        "Sandstone": "#DEB887",
        "Limestone": "#87CEEB",
        "Dolomite": "#DEB887",
        "Salt": "#F0F0F0",
        "Anhydrite": "#E0E0E0",
        "Coal": "#2F2F2F",
        "Conglomerate": "#CD853F",
        "Marl": "#BDB76B",
        "Chalk": "#FFFFF0",
        "Granite": "#A0A0A0",
    }

    FORMATION_HATCHES = {
        "Shale": "horizontal",
        "Sandstone": "dots",
        "Limestone": "diagonal",
        "Salt": "cross",
        "Coal": "solid",
    }


# ==================== Main Renderer ====================

class WellboreSchematicRenderer:
    """
    موتور اصلی رندر Wellbore Schematic.
    """

    def __init__(self, schematic: WellboreSchematic, config: SchematicConfig = None):
        self.schematic = schematic
        self.config = config or SchematicConfig()
        self._calculate_scale()

    def _calculate_scale(self):
        """محاسبه مقیاس depth."""
        drawable_height = (
            self.config.total_height
            - self.config.margin_top
            - self.config.margin_bottom
        )
        if self.schematic.total_depth_m > 0:
            self.config.depth_scale = drawable_height / self.schematic.total_depth_m
        else:
            self.config.depth_scale = 0.3

    def depth_to_y(self, depth_m: float) -> float:
        """تبدیل عمق (متر) به مختصات Y."""
        return self.config.margin_top + depth_m * self.config.depth_scale

    def od_to_pixels(self, od_inch: float) -> float:
        """تبدیل OD (اینچ) به pixel."""
        return od_inch * self.config.od_scale

    def get_center_x(self) -> float:
        """مرکز محور چاه."""
        return self.config.total_width / 2

    def render(self, painter: QPainter):
        """رندر کامل شماتیک."""
        if self.config.dark_mode:
            painter.fillRect(
                0, 0,
                self.config.total_width, self.config.total_height,
                QColor(self.config.background_color)
            )
        else:
            painter.fillRect(
                0, 0,
                self.config.total_width, self.config.total_height,
                QColor("#f8f9fa")
            )

        # ترتیب رندر (پایین به بالا = ابتدا سازندها، سپس کیسینگ‌ها)
        if self.config.show_formations:
            self._draw_formations(painter)

        if self.config.show_cement:
            self._draw_all_cement(painter)

        self._draw_all_casings(painter)
        self._draw_open_hole(painter)

        if self.schematic.show_tubing:
            self._draw_tubing(painter)

        self._draw_completion(painter)
        self._draw_bit(painter)

        if self.schematic.show_wellhead:
            self._draw_wellhead(painter)

        if self.schematic.show_xmas_tree:
            self._draw_xmas_tree(painter)

        if self.config.show_depth_scale:
            self._draw_depth_scale(painter)

        if self.config.show_grid:
            self._draw_grid(painter)

        if self.config.show_labels:
            self._draw_labels(painter)

        self._draw_title(painter)

        if self.config.show_legend:
            self._draw_legend(painter)

    # ==================== Formations ====================

    def _draw_formations(self, painter: QPainter):
        """رندر لایه‌های سازند."""
        cx = self.get_center_x()
        formation_width = self.config.total_width - self.config.margin_left - self.config.margin_right

        for layer in self.schematic.formations:
            y_top = self.depth_to_y(layer.top_depth_m)
            y_bottom = self.depth_to_y(layer.bottom_depth_m)
            height = y_bottom - y_top

            if height <= 0:
                continue

            x_left = self.config.margin_left
            width = formation_width

            # رنگ سازند
            color = QColor(
                SchematicColors.FORMATIONS.get(layer.lithology, layer.color)
            )
            color.setAlpha(80)
            painter.fillRect(
                int(x_left), int(y_top),
                int(width), int(height),
                color
            )

            # الگوی هاشور
            self._draw_formation_hatch(
                painter, layer, x_left, y_top, width, height
            )

            # نام سازند
            if height > 20:
                painter.setPen(QColor("#bdc3c7"))
                font = QFont(self.config.font_family, self.config.font_size - 1)
                font.setItalic(True)
                painter.setFont(font)
                painter.drawText(
                    int(x_left + 5), int(y_top + height / 2 + 4),
                    layer.name
                )

    def _draw_formation_hatch(
        self, painter, layer, x, y, width, height
    ):
        """رسم الگوی هاشور سازند."""
        hatch = SchematicColors.FORMATION_HATCHES.get(
            layer.lithology, "horizontal"
        )
        color = QColor(layer.color)
        color.setAlpha(120)
        pen = QPen(color, 0.5)
        painter.setPen(pen)

        if hatch == "horizontal":
            step = 6
            for yi in range(int(y), int(y + height), step):
                painter.drawLine(int(x), yi, int(x + width), yi)

        elif hatch == "diagonal":
            step = 8
            for xi in range(int(x - height), int(x + width), step):
                painter.drawLine(
                    int(xi), int(y),
                    int(xi + height), int(y + height)
                )

        elif hatch == "dots":
            step = 8
            for yi in range(int(y), int(y + height), step):
                for xi in range(int(x), int(x + width), step):
                    painter.drawEllipse(xi, yi, 2, 2)

        elif hatch == "cross":
            step = 8
            for yi in range(int(y), int(y + height), step):
                painter.drawLine(int(x), yi, int(x + width), yi)
            for xi in range(int(x), int(x + width), step):
                painter.drawLine(xi, int(y), xi, int(y + height))

    # ==================== Cement ====================

    def _draw_all_cement(self, painter: QPainter):
        """رندر سیمان همه کیسینگ‌ها."""
        for casing in self.schematic.casings:
            if not casing.show_cement:
                continue
            if casing.cement_top_m >= casing.cement_bottom_m:
                continue
            self._draw_cement(painter, casing)

    def _draw_cement(self, painter: QPainter, casing: CasingData):
        """رندر سیمان یک کیسینگ."""
        cx = self.get_center_x()

        # پیدا کردن کیسینگ بزرگ‌تر (ظرف سیمان)
        outer_casing = self._find_outer_casing(casing)
        if outer_casing:
            outer_id_px = self.od_to_pixels(outer_casing.id_inch) / 2
        else:
            # Open hole
            outer_id_px = self.od_to_pixels(casing.od_inch * 1.5) / 2

        casing_od_px = self.od_to_pixels(casing.od_inch) / 2

        y_top = self.depth_to_y(casing.cement_top_m)
        y_bottom = self.depth_to_y(casing.cement_bottom_m)
        height = y_bottom - y_top

        if height <= 0:
            return

        cement_color = QColor(SchematicColors.CEMENT)
        cement_color.setAlpha(SchematicColors.CEMENT_ALPHA)

        # سمت چپ
        left_rect = QRectF(
            cx - outer_id_px, y_top,
            outer_id_px - casing_od_px, height
        )
        painter.fillRect(left_rect, cement_color)

        # سمت راست
        right_rect = QRectF(
            cx + casing_od_px, y_top,
            outer_id_px - casing_od_px, height
        )
        painter.fillRect(right_rect, cement_color)

        # الگوی سیمان (zigzag)
        self._draw_cement_pattern(
            painter, cx - outer_id_px, y_top,
            outer_id_px - casing_od_px, height, "left"
        )
        self._draw_cement_pattern(
            painter, cx + casing_od_px, y_top,
            outer_id_px - casing_od_px, height, "right"
        )

    def _draw_cement_pattern(
        self, painter, x, y, width, height, side
    ):
        """الگوی هاشور سیمان."""
        pen = QPen(QColor(160, 160, 160, 100), 0.5)
        painter.setPen(pen)
        step = 8
        for yi in range(int(y), int(y + height), step):
            if side == "left":
                painter.drawLine(
                    int(x), yi,
                    int(x + width), yi + 4
                )
            else:
                painter.drawLine(
                    int(x), yi + 4,
                    int(x + width), yi
                )

    def _find_outer_casing(
        self, inner_casing: CasingData
    ) -> Optional[CasingData]:
        """پیدا کردن کیسینگ بیرونی."""
        candidates = [
            c for c in self.schematic.casings
            if c.od_inch > inner_casing.od_inch
            and c.top_depth_m <= inner_casing.top_depth_m
            and c.bottom_depth_m >= inner_casing.cement_bottom_m * 0.5
        ]
        if candidates:
            return min(candidates, key=lambda c: c.od_inch)
        return None

    # ==================== Casings ====================

    def _draw_all_casings(self, painter: QPainter):
        """رندر همه کیسینگ‌ها."""
        # مرتب‌سازی: بزرگ‌ترین اول
        sorted_casings = sorted(
            self.schematic.casings,
            key=lambda c: c.od_inch,
            reverse=True
        )
        for casing in sorted_casings:
            self._draw_casing(painter, casing)

    def _draw_casing(self, painter: QPainter, casing: CasingData):
        """رندر یک رشته کیسینگ."""
        cx = self.get_center_x()
        od_px = self.od_to_pixels(casing.od_inch) / 2
        id_px = self.od_to_pixels(casing.id_inch) / 2
        wall_px = od_px - id_px

        y_top = self.depth_to_y(casing.top_depth_m)
        y_bottom = self.depth_to_y(casing.bottom_depth_m)
        height = y_bottom - y_top

        if height <= 0:
            return

        # تعیین رنگ
        color_map = {
            ElementType.CONDUCTOR: SchematicColors.CONDUCTOR,
            ElementType.SURFACE_CASING: SchematicColors.SURFACE_CASING,
            ElementType.INTERMEDIATE_CASING: SchematicColors.INTERMEDIATE_CASING,
            ElementType.PRODUCTION_CASING: SchematicColors.PRODUCTION_CASING,
            ElementType.LINER: SchematicColors.LINER,
        }
        color = QColor(
            casing.color or color_map.get(casing.element_type, "#4682B4")
        )

        # رسم دیواره کیسینگ (سمت چپ)
        left_wall = QRectF(cx - od_px, y_top, wall_px, height)
        painter.fillRect(left_wall, color)

        # رسم دیواره کیسینگ (سمت راست)
        right_wall = QRectF(cx + id_px, y_top, wall_px, height)
        painter.fillRect(right_wall, color)

        # کفشک (shoe) - انتهای کیسینگ
        self._draw_shoe(painter, cx, y_bottom, od_px, id_px, color)

        # خطوط مرز
        pen = QPen(color.darker(120), 1.0)
        painter.setPen(pen)

        # خط بیرونی چپ
        painter.drawLine(
            int(cx - od_px), int(y_top),
            int(cx - od_px), int(y_bottom)
        )
        # خط بیرونی راست
        painter.drawLine(
            int(cx + od_px), int(y_top),
            int(cx + od_px), int(y_bottom)
        )
        # خط داخلی چپ
        painter.drawLine(
            int(cx - id_px), int(y_top),
            int(cx - id_px), int(y_bottom)
        )
        # خط داخلی راست
        painter.drawLine(
            int(cx + id_px), int(y_top),
            int(cx + id_px), int(y_bottom)
        )

        # هدر کیسینگ در بالا
        if casing.top_depth_m == 0:
            self._draw_casing_head(painter, cx, y_top, od_px, color)

        # برچسب
        if self.config.show_labels:
            self._draw_casing_label(painter, casing, cx, y_top, od_px)

    def _draw_shoe(
        self, painter, cx, y, od_px, id_px, color
    ):
        """رسم کفشک کیسینگ (guide shoe)."""
        shoe_height = 12
        shoe_path = QPainterPath()
        # شکل مثلثی shoe
        shoe_path.moveTo(cx - od_px, y - shoe_height)
        shoe_path.lineTo(cx - od_px, y)
        shoe_path.lineTo(cx, y + shoe_height / 2)
        shoe_path.lineTo(cx + od_px, y)
        shoe_path.lineTo(cx + od_px, y - shoe_height)
        shoe_path.closeSubpath()

        painter.fillPath(shoe_path, color.darker(130))
        painter.setPen(QPen(color.darker(150), 1))
        painter.drawPath(shoe_path)

    def _draw_casing_head(
        self, painter, cx, y, od_px, color
    ):
        """رسم سر کیسینگ (casing head/spool)."""
        head_width = od_px * 1.3
        head_height = 15

        head_rect = QRectF(
            cx - head_width, y - head_height,
            head_width * 2, head_height
        )
        painter.fillRect(head_rect, color.darker(110))
        painter.setPen(QPen(color.darker(130), 1.5))
        painter.drawRect(head_rect)

    def _draw_casing_label(
        self, painter, casing, cx, y_top, od_px
    ):
        """برچسب کیسینگ."""
        label_text = (
            f'{casing.od_inch:.3f}" {casing.name}'
            if casing.name else
            f'{casing.od_inch:.3f}" Casing'
        )

        painter.setPen(QColor(self.config.text_color))
        font = QFont(self.config.font_family, self.config.font_size)
        font.setBold(True)
        painter.setFont(font)

        label_x = cx + od_px + 5
        label_y = y_top + 12
        painter.drawText(int(label_x), int(label_y), label_text)

        # خط راهنما
        pen = QPen(QColor(self.config.text_color), 0.5, Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(
            int(cx + od_px), int(y_top + 6),
            int(label_x - 3), int(y_top + 6)
        )

    # ==================== Open Hole ====================

    def _draw_open_hole(self, painter: QPainter):
        """رندر چاه باز (زیر آخرین کیسینگ)."""
        if not self.schematic.casings:
            return

        # عمیق‌ترین کیسینگ
        deepest = max(
            self.schematic.casings, key=lambda c: c.bottom_depth_m
        )
        oh_top = deepest.bottom_depth_m
        oh_bottom = self.schematic.total_depth_m

        if oh_bottom <= oh_top:
            return

        # قطر حفره باز (کمی بزرگتر از کوچک‌ترین کیسینگ)
        smallest_od = min(c.od_inch for c in self.schematic.casings)
        oh_radius_px = self.od_to_pixels(smallest_od * 0.85) / 2

        cx = self.get_center_x()
        y_top = self.depth_to_y(oh_top)
        y_bottom = self.depth_to_y(oh_bottom)

        # رنگ خاک
        dirt_color = QColor(139, 90, 43, 150)
        dirt_width = 20

        # سمت چپ
        painter.fillRect(
            int(cx - oh_radius_px - dirt_width), int(y_top),
            dirt_width, int(y_bottom - y_top),
            dirt_color
        )
        # سمت راست
        painter.fillRect(
            int(cx + oh_radius_px), int(y_top),
            dirt_width, int(y_bottom - y_top),
            dirt_color
        )

        # دیواره حفره
        pen = QPen(QColor(101, 67, 33), 2.0, Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(
            int(cx - oh_radius_px), int(y_top),
            int(cx - oh_radius_px), int(y_bottom)
        )
        painter.drawLine(
            int(cx + oh_radius_px), int(y_top),
            int(cx + oh_radius_px), int(y_bottom)
        )

        # برچسب
        if self.config.show_labels:
            painter.setPen(QColor("#e67e22"))
            font = QFont(self.config.font_family, self.config.font_size - 1)
            font.setItalic(True)
            painter.setFont(font)
            painter.drawText(
                int(cx + oh_radius_px + 8),
                int(y_top + 15),
                f"Open Hole {smallest_od * 0.85:.2f}\""
            )

    # ==================== Tubing ====================

    def _draw_tubing(self, painter: QPainter):
        """رندر رشته تیوبینگ."""
        cx = self.get_center_x()
        od_px = self.od_to_pixels(self.schematic.tubing_od_inch) / 2
        wall_px = max(2, od_px * 0.15)
        id_px = od_px - wall_px

        y_top = self.depth_to_y(0)
        y_bottom = self.depth_to_y(self.schematic.tubing_bottom_m)
        height = y_bottom - y_top

        if height <= 0:
            return

        color = QColor(SchematicColors.TUBING)

        # دیواره چپ
        painter.fillRect(
            int(cx - od_px), int(y_top),
            int(wall_px), int(height),
            color
        )
        # دیواره راست
        painter.fillRect(
            int(cx + id_px), int(y_top),
            int(wall_px), int(height),
            color
        )

        # خطوط مرز
        pen = QPen(color.darker(130), 1.0)
        painter.setPen(pen)
        painter.drawLine(int(cx - od_px), int(y_top), int(cx - od_px), int(y_bottom))
        painter.drawLine(int(cx + od_px), int(y_top), int(cx + od_px), int(y_bottom))
        painter.drawLine(int(cx - id_px), int(y_top), int(cx - id_px), int(y_bottom))
        painter.drawLine(int(cx + id_px), int(y_top), int(cx + id_px), int(y_bottom))

        # برچسب
        if self.config.show_labels:
            painter.setPen(QColor(SchematicColors.TUBING))
            font = QFont(self.config.font_family, self.config.font_size)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                int(cx - od_px - 70),
                int(y_top + 20),
                f'{self.schematic.tubing_od_inch:.2f}" Tubing'
            )

    # ==================== Completion ====================

    def _draw_completion(self, painter: QPainter):
        """رندر المنت‌های Completion."""
        for item in self.schematic.completion:
            if item.element_type == ElementType.PACKER:
                self._draw_packer(painter, item)
            elif item.element_type == ElementType.PERFORATIONS:
                self._draw_perforations(painter, item)
            elif item.element_type == ElementType.BRIDGE_PLUG:
                self._draw_bridge_plug(painter, item)
            elif item.element_type == ElementType.SAFETY_VALVE:
                self._draw_safety_valve(painter, item)
            elif item.element_type == ElementType.SAND_SCREEN:
                self._draw_sand_screen(painter, item)
            elif item.element_type == ElementType.GAS_LIFT_VALVE:
                self._draw_gas_lift_valve(painter, item)

    def _draw_packer(self, painter: QPainter, item: CompletionItem):
        """رندر Packer."""
        cx = self.get_center_x()
        y = self.depth_to_y(item.depth_m)

        # شکل packer
        od_px = self.od_to_pixels(item.od_inch or 4.5) / 2
        packer_height = 14

        packer_color = QColor(SchematicColors.PACKER)

        # شکل اصلی (مستطیل با زوایای گرد)
        packer_rect = QRectF(
            cx - od_px, y - packer_height / 2,
            od_px * 2, packer_height
        )
        painter.setBrush(QBrush(packer_color))
        painter.setPen(QPen(packer_color.darker(130), 1.5))
        painter.drawRoundedRect(packer_rect, 3, 3)

        # خطوط تزئینی
        pen = QPen(packer_color.darker(150), 1)
        painter.setPen(pen)
        for i in range(3):
            xi = cx - od_px + (i + 1) * od_px / 2
            painter.drawLine(
                int(xi), int(y - packer_height / 2),
                int(xi), int(y + packer_height / 2)
            )

        # برچسب
        if self.config.show_labels:
            painter.setPen(QColor(SchematicColors.PACKER))
            font = QFont(self.config.font_family, self.config.font_size - 1)
            painter.setFont(font)
            label = item.label or "Packer"
            painter.drawText(
                int(cx + od_px + 5),
                int(y + 4),
                f"{label} @ {item.depth_m:.0f}m"
            )

    def _draw_perforations(self, painter: QPainter, item: CompletionItem):
        """رندر Perforations."""
        cx = self.get_center_x()
        y_top = self.depth_to_y(item.depth_m)
        y_bottom = self.depth_to_y(item.depth_m + item.length_m)
        height = y_bottom - y_top

        if height <= 0:
            height = 20

        perf_color = QColor(SchematicColors.PERFORATION)
        casing_od_px = self.od_to_pixels(item.od_inch or 7.0) / 2

        # خطوط perforation
        num_perfs = max(3, int(height / 6))
        pen = QPen(perf_color, 1.5)
        painter.setPen(pen)

        step = height / num_perfs
        for i in range(num_perfs):
            y = y_top + i * step + step / 2
            perf_len = 15

            # چپ
            painter.drawLine(
                int(cx - casing_od_px - 2), int(y),
                int(cx - casing_od_px - perf_len), int(y)
            )
            # دایره کوچک در انتها
            painter.setBrush(QBrush(perf_color))
            painter.drawEllipse(
                int(cx - casing_od_px - perf_len - 2),
                int(y - 2), 4, 4
            )

            # راست
            painter.drawLine(
                int(cx + casing_od_px + 2), int(y),
                int(cx + casing_od_px + perf_len), int(y)
            )
            painter.drawEllipse(
                int(cx + casing_od_px + perf_len - 2),
                int(y - 2), 4, 4
            )

        # برچسب
        if self.config.show_labels:
            painter.setPen(perf_color)
            font = QFont(self.config.font_family, self.config.font_size - 1)
            painter.setFont(font)
            label = item.label or "Perforations"
            painter.drawText(
                int(cx + casing_od_px + 20),
                int(y_top + height / 2),
                f"{label}\n{item.depth_m:.0f}-{item.depth_m + item.length_m:.0f}m"
            )

    def _draw_bridge_plug(self, painter: QPainter, item: CompletionItem):
        """رندر Bridge Plug."""
        cx = self.get_center_x()
        y = self.depth_to_y(item.depth_m)
        od_px = self.od_to_pixels(item.od_inch or 6.0) / 2

        color = QColor(SchematicColors.BRIDGE_PLUG)

        # شکل مثلثی وارونه
        path = QPainterPath()
        path.moveTo(cx - od_px, y - 8)
        path.lineTo(cx + od_px, y - 8)
        path.lineTo(cx, y + 8)
        path.closeSubpath()

        painter.fillPath(path, color)
        painter.setPen(QPen(color.darker(130), 1.5))
        painter.drawPath(path)

        # برچسب
        if self.config.show_labels:
            painter.setPen(color)
            font = QFont(self.config.font_family, self.config.font_size - 1)
            painter.setFont(font)
            painter.drawText(
                int(cx + od_px + 5), int(y + 4),
                f"{item.label or 'Bridge Plug'} @ {item.depth_m:.0f}m"
            )

    def _draw_safety_valve(self, painter: QPainter, item: CompletionItem):
        """رندر Surface Safety Valve."""
        cx = self.get_center_x()
        y = self.depth_to_y(item.depth_m)
        tubing_od_px = self.od_to_pixels(
            self.schematic.tubing_od_inch
        ) / 2

        color = QColor(SchematicColors.SAFETY_VALVE)
        valve_height = 12
        valve_width = tubing_od_px * 2.5

        # مستطیل valve
        valve_rect = QRectF(
            cx - valve_width / 2, y - valve_height / 2,
            valve_width, valve_height
        )
        painter.fillRect(valve_rect, color)
        painter.setPen(QPen(color.darker(130), 1.5))
        painter.drawRect(valve_rect)

        # علامت V داخل
        pen = QPen(QColor("white"), 1.5)
        painter.setPen(pen)
        painter.drawLine(
            int(cx - 5), int(y - 4),
            int(cx), int(y + 4)
        )
        painter.drawLine(
            int(cx), int(y + 4),
            int(cx + 5), int(y - 4)
        )

        # برچسب
        if self.config.show_labels:
            painter.setPen(color)
            font = QFont(self.config.font_family, self.config.font_size - 1)
            painter.setFont(font)
            painter.drawText(
                int(cx + valve_width / 2 + 5), int(y + 4),
                f"{item.label or 'SSV'} @ {item.depth_m:.0f}m"
            )

    def _draw_sand_screen(self, painter: QPainter, item: CompletionItem):
        """رندر Sand Screen."""
        cx = self.get_center_x()
        y_top = self.depth_to_y(item.depth_m)
        y_bottom = self.depth_to_y(item.depth_m + item.length_m)
        od_px = self.od_to_pixels(item.od_inch or 4.0) / 2
        height = max(10, y_bottom - y_top)

        color = QColor("#00CED1")  # Dark Turquoise

        # دو خط موازی با الگوی مشبک
        pen = QPen(color, 2.0)
        painter.setPen(pen)
        painter.drawLine(
            int(cx - od_px), int(y_top),
            int(cx - od_px), int(y_top + height)
        )
        painter.drawLine(
            int(cx + od_px), int(y_top),
            int(cx + od_px), int(y_top + height)
        )

        # الگوی مشبک
        pen = QPen(color, 0.5)
        painter.setPen(pen)
        step = 6
        for yi in range(int(y_top), int(y_top + height), step):
            painter.drawLine(
                int(cx - od_px), yi,
                int(cx + od_px), yi
            )

    def _draw_gas_lift_valve(self, painter: QPainter, item: CompletionItem):
        """رندر Gas Lift Valve."""
        cx = self.get_center_x()
        y = self.depth_to_y(item.depth_m)
        tubing_od_px = self.od_to_pixels(self.schematic.tubing_od_inch) / 2

        color = QColor("#FF8C00")  # Dark Orange

        # دایره خارجی
        radius = 8
        painter.setPen(QPen(color.darker(120), 1.5))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(
            int(cx + tubing_od_px - 2), int(y - radius),
            radius * 2, radius * 2
        )

        # G داخل
        painter.setPen(QColor("white"))
        font = QFont(self.config.font_family, 7)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            int(cx + tubing_od_px + 3), int(y + 4), "GL"
        )

    # ==================== Wellhead ====================

    def _draw_wellhead(self, painter: QPainter):
        """رندر Wellhead کامل."""
        cx = self.get_center_x()
        y_surface = self.depth_to_y(0)

        # محاسبه عرض بر اساس بزرگ‌ترین کیسینگ
        max_od = max(
            (c.od_inch for c in self.schematic.casings), default=20.0
        )
        base_width = self.od_to_pixels(max_od) * 1.2

        self._draw_wellhead_assembly(painter, cx, y_surface, base_width)

    def _draw_wellhead_assembly(self, painter, cx, y_base, base_width):
        """رسم مجموعه Wellhead."""
        wh_color = QColor(SchematicColors.WELLHEAD)

        # لایه‌های Wellhead (از پایین به بالا)
        layers = [
            (base_width, 18, "Conductor Head"),
            (base_width * 0.82, 15, "Surface Head"),
            (base_width * 0.65, 15, "Intermediate Head"),
            (base_width * 0.50, 12, "Production Head"),
            (base_width * 0.40, 10, "Tubing Head"),
        ]

        y = y_base
        for i, (width, height, name) in enumerate(layers):
            if i >= len(self.schematic.casings) + 1:
                break

            rect = QRectF(
                cx - width / 2, y - height,
                width, height
            )
            painter.fillRect(rect, wh_color.lighter(100 + i * 8))
            painter.setPen(QPen(wh_color.darker(130), 1.5))
            painter.drawRect(rect)

            # پیچ‌های کنار
            bolt_color = QColor(150, 150, 150)
            for bolt_x in [cx - width / 2 + 4, cx + width / 2 - 4]:
                painter.setPen(QPen(bolt_color, 2))
                painter.drawLine(
                    int(bolt_x), int(y - height),
                    int(bolt_x), int(y)
                )
                painter.setBrush(QBrush(bolt_color))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(
                    int(bolt_x - 2), int(y - height + 2), 4, 4
                )
                painter.drawEllipse(
                    int(bolt_x - 2), int(y - 5), 4, 4
                )

            y -= height

        # برچسب Wellhead
        if self.config.show_labels:
            painter.setPen(QColor(SchematicColors.WELLHEAD))
            font = QFont(self.config.font_family, self.config.font_size)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                int(cx + base_width / 2 + 8),
                int(y_base - 30),
                "Wellhead"
            )

    # ==================== Christmas Tree ====================

    def _draw_xmas_tree(self, painter: QPainter):
        """رندر Christmas Tree (Xmas Tree) کامل."""
        cx = self.get_center_x()
        y_wellhead = self.depth_to_y(0)

        # محاسبه ارتفاع wellhead
        wellhead_height = min(70, len(self.schematic.casings) * 15 + 10)
        y_tree_base = y_wellhead - wellhead_height

        tubing_od_px = self.od_to_pixels(self.schematic.tubing_od_inch) / 2
        self._draw_xmas_tree_assembly(
            painter, cx, y_tree_base, tubing_od_px
        )

    def _draw_xmas_tree_assembly(
        self, painter, cx, y_base, tubing_px
    ):
        """رسم مجموعه Xmas Tree."""
        tree_color = QColor(SchematicColors.XMAS_TREE)
        valve_color = QColor("#2c2c2c")
        handle_color = QColor("#555555")

        body_width = tubing_px * 2 * 1.3
        body_height = 60

        # بدنه اصلی Xmas Tree
        body_rect = QRectF(
            cx - body_width / 2, y_base - body_height,
            body_width, body_height
        )
        painter.fillRect(body_rect, tree_color)
        painter.setPen(QPen(tree_color.darker(130), 1.5))
        painter.drawRect(body_rect)

        # ==================
        # Master Valve (پایین)
        # ==================
        valve_y = y_base - 15
        valve_width = body_width * 1.4
        valve_height = 12
        master_rect = QRectF(
            cx - valve_width / 2, valve_y - valve_height,
            valve_width, valve_height
        )
        painter.fillRect(master_rect, valve_color)
        painter.setPen(QPen(valve_color.darker(120), 1))
        painter.drawRect(master_rect)
        # هندل valve
        painter.setPen(QPen(handle_color, 3))
        painter.drawLine(
            int(cx), int(valve_y - valve_height - 2),
            int(cx), int(valve_y - valve_height - 12)
        )
        painter.drawLine(
            int(cx - 8), int(valve_y - valve_height - 12),
            int(cx + 8), int(valve_y - valve_height - 12)
        )
        # برچسب
        painter.setPen(QColor("#bdc3c7"))
        font = QFont(self.config.font_family, 7)
        painter.setFont(font)
        painter.drawText(
            int(cx - valve_width / 2 - 55),
            int(valve_y - 2),
            "Master Valve"
        )

        # ==================
        # Wing Valves (دو طرف)
        # ==================
        wing_y = y_base - 35
        wing_valve_width = 30
        wing_valve_height = 10

        for side in [-1, 1]:
            x_start = cx + side * body_width / 2
            x_end = cx + side * (body_width / 2 + 35)

            # لوله wing
            painter.setPen(QPen(tree_color, 4))
            painter.drawLine(
                int(x_start), int(wing_y),
                int(x_end), int(wing_y)
            )

            # Wing Valve
            wing_rect = QRectF(
                x_end - wing_valve_width / 2 * (1 + side * 0.5) + side * 10,
                wing_y - wing_valve_height / 2,
                wing_valve_width, wing_valve_height
            )
            painter.fillRect(wing_rect, valve_color)
            painter.setPen(QPen(valve_color.darker(120), 1))
            painter.drawRect(wing_rect)

            # هندل wing valve
            handle_x = x_end + side * (wing_valve_width / 2)
            painter.setPen(QPen(handle_color, 2.5))
            painter.drawLine(
                int(handle_x), int(wing_y - 2),
                int(handle_x), int(wing_y - 12)
            )
            painter.drawLine(
                int(handle_x - 6), int(wing_y - 12),
                int(handle_x + 6), int(wing_y - 12)
            )

        # ==================
        # Swab Valve (بالا)
        # ==================
        swab_y = y_base - body_height - 8
        swab_rect = QRectF(
            cx - body_width * 0.6 / 2,
            swab_y - 10,
            body_width * 0.6, 10
        )
        painter.fillRect(swab_rect, valve_color)
        painter.setPen(QPen(valve_color.darker(120), 1))
        painter.drawRect(swab_rect)

        # ==================
        # Cap بالای Xmas Tree
        # ==================
        cap_width = body_width * 0.5
        cap_height = 8
        cap_rect = QRectF(
            cx - cap_width / 2, swab_y - 10 - cap_height,
            cap_width, cap_height
        )
        painter.fillRect(cap_rect, tree_color.darker(120))

        # ==================
        # Pressure Gauges
        # ==================
        gauge_color = QColor("#f39c12")
        for pos_y, side in [
            (y_base - 25, -1),
            (y_base - 45, 1),
        ]:
            gauge_x = cx + side * (body_width / 2 + 5)
            painter.setPen(QPen(gauge_color, 1.5))
            painter.setBrush(QBrush(QColor(50, 50, 50)))
            painter.drawEllipse(
                int(gauge_x - 6), int(pos_y - 6), 12, 12
            )
            painter.setPen(QPen(gauge_color, 1))
            # خط نشانگر
            painter.drawLine(
                int(gauge_x), int(pos_y),
                int(gauge_x + side * 4), int(pos_y - 3)
            )

        # برچسب Xmas Tree
        if self.config.show_labels:
            painter.setPen(QColor("#2ecc71"))
            font = QFont(self.config.font_family, self.config.font_size)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                int(cx - body_width / 2 - 75),
                int(y_base - body_height / 2),
                "Xmas Tree"
            )

    # ==================== Bit ====================

    def _draw_bit(self, painter: QPainter):
        """رندر Bit."""
        cx = self.get_center_x()
        y_bottom = self.depth_to_y(self.schematic.total_depth_m)
        bit_width = 20
        bit_height = 18

        bit_color = QColor("#2F4F4F")

        # شکل مثلثی bit
        path = QPainterPath()
        path.moveTo(cx - bit_width, y_bottom)
        path.lineTo(cx, y_bottom + bit_height)
        path.lineTo(cx + bit_width, y_bottom)
        path.closeSubpath()

        painter.fillPath(path, bit_color)
        painter.setPen(QPen(bit_color.lighter(130), 1.5))
        painter.drawPath(path)

        # نازل‌ها
        nozzle_color = QColor("#4169E1")
        for nx in [cx - 5, cx, cx + 5]:
            painter.setPen(QPen(nozzle_color, 2))
            painter.drawLine(
                int(nx), int(y_bottom),
                int(nx), int(y_bottom + 6)
            )

    # ==================== Depth Scale ====================

    def _draw_depth_scale(self, painter: QPainter):
        """رندر مقیاس عمق در سمت چپ."""
        x_scale = self.config.margin_left - 10

        # تعیین فواصل مقیاس
        total_depth = self.schematic.total_depth_m
        if total_depth <= 500:
            interval = 50
        elif total_depth <= 1000:
            interval = 100
        elif total_depth <= 3000:
            interval = 250
        elif total_depth <= 6000:
            interval = 500
        else:
            interval = 1000

        painter.setPen(QColor(self.config.text_color))
        font = QFont(self.config.font_family, self.config.font_size - 1)
        painter.setFont(font)

        depth = 0
        while depth <= total_depth:
            y = self.depth_to_y(depth)

            # خط تیک
            tick_color = QColor(self.config.depth_line_color)
            pen = QPen(tick_color, 0.5, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(
                self.config.margin_left - 5, int(y),
                self.config.total_width - self.config.margin_right, int(y)
            )

            # برچسب عمق
            painter.setPen(QColor(self.config.text_color))
            depth_text = f"{depth:.0f}m"
            painter.drawText(
                int(x_scale - 40), int(y + 4), depth_text
            )

            depth += interval

        # عنوان محور
        painter.save()
        painter.translate(15, self.config.total_height // 2)
        painter.rotate(-90)
        painter.setPen(QColor(self.config.text_color))
        font_title = QFont(self.config.font_family, self.config.font_size)
        font_title.setBold(True)
        painter.setFont(font_title)
        painter.drawText(-50, 0, "Depth (m MD)")
        painter.restore()

    # ==================== Grid ====================

    def _draw_grid(self, painter: QPainter):
        """رندر خطوط راهنما."""
        pen = QPen(QColor(self.config.grid_color), 0.3, Qt.DotLine)
        painter.setPen(pen)

        cx = self.get_center_x()

        # خط مرکزی
        painter.drawLine(
            int(cx), self.config.margin_top,
            int(cx), self.config.total_height - self.config.margin_bottom
        )

    # ==================== Labels ====================

    def _draw_labels(self, painter: QPainter):
        """رندر برچسب‌های عمق کیسینگ‌ها."""
        for casing in self.schematic.casings:
            cx = self.get_center_x()
            od_px = self.od_to_pixels(casing.od_inch) / 2
            y_bottom = self.depth_to_y(casing.bottom_depth_m)

            # عمق پاشنه
            painter.setPen(QColor(self.config.text_color))
            font = QFont(self.config.font_family, self.config.font_size - 1)
            painter.setFont(font)

            label_x = cx - od_px - 5
            label_text = f"{casing.bottom_depth_m:.0f}m"
            painter.drawText(
                int(label_x - 35), int(y_bottom + 4), label_text
            )

            # خط اتصال
            pen = QPen(QColor(self.config.text_color), 0.3, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(
                int(label_x - 3), int(y_bottom),
                int(cx - od_px), int(y_bottom)
            )

    # ==================== Title ====================

    def _draw_title(self, painter: QPainter):
        """رندر عنوان شماتیک."""
        painter.setPen(QColor(self.config.text_color))
        font = QFont(
            self.config.font_family, self.config.title_font_size
        )
        font.setBold(True)
        painter.setFont(font)

        title = (
            f"Wellbore Schematic - {self.schematic.well_name}"
            if self.schematic.well_name else "Wellbore Schematic"
        )
        painter.drawText(
            self.config.margin_left, 25, title
        )

        if self.schematic.rig_name:
            font_small = QFont(self.config.font_family, self.config.font_size)
            painter.setFont(font_small)
            painter.setPen(QColor(self.config.text_color).darker(130))
            painter.drawText(
                self.config.margin_left, 42,
                f"Rig: {self.schematic.rig_name}"
            )

    # ==================== Legend ====================

    def _draw_legend(self, painter: QPainter):
        """رندر راهنمای رنگ‌ها."""
        legend_x = self.config.total_width - self.config.margin_right + 5
        legend_y = self.config.margin_top + 10

        items = [
            ("Conductor", SchematicColors.CONDUCTOR),
            ("Surface CSG", SchematicColors.SURFACE_CASING),
            ("Interm. CSG", SchematicColors.INTERMEDIATE_CASING),
            ("Prod. CSG", SchematicColors.PRODUCTION_CASING),
            ("Liner", SchematicColors.LINER),
            ("Tubing", SchematicColors.TUBING),
            ("Cement", SchematicColors.CEMENT),
            ("Packer", SchematicColors.PACKER),
            ("Perfs", SchematicColors.PERFORATION),
        ]

        font = QFont(self.config.font_family, self.config.font_size - 2)
        painter.setFont(font)

        for i, (label, color) in enumerate(items):
            y = legend_y + i * 18

            # مربع رنگی
            rect = QRectF(legend_x, y, 12, 10)
            painter.fillRect(rect, QColor(color))
            painter.setPen(QPen(QColor(color).darker(130), 0.5))
            painter.drawRect(rect)

            # متن
            painter.setPen(QColor(self.config.text_color))
            painter.drawText(int(legend_x + 16), int(y + 9), label)


# ==================== Auto Builder ====================

class SchematicAutoBuilder:
    """
    ساخت خودکار شماتیک از داده‌های دیتابیس.
    """

    def __init__(self, db_manager):
        self.db = db_manager

    def build_from_well(self, well_id: int) -> WellboreSchematic:
        """ساخت شماتیک از داده‌های چاه."""
        well = self.db.get_well_by_id(well_id)
        if not well:
            return WellboreSchematic()

        schematic = WellboreSchematic(
            well_name=well.get("name", ""),
            rig_name=well.get("rig_name", ""),
            total_depth_m=well.get("target_depth", 3000) or 3000,
            water_depth_m=well.get("water_depth", 0) or 0,
            gle_msl_m=well.get("gle_msl", 10) or 10,
            kb_msl_m=well.get("rte_msl", 15) or 15,
        )

        # کیسینگ‌ها از DB
        self._add_casings_from_db(schematic, well_id)

        # سازندها از DB
        self._add_formations_from_db(schematic, well_id)

        # Completion از DB
        self._add_completion_from_db(schematic, well_id)

        # اگر کیسینگ نداشت، داده‌های پیش‌فرض
        if not schematic.casings:
            self._add_default_casings(schematic)

        return schematic

    def _add_casings_from_db(
        self, schematic: WellboreSchematic, well_id: int
    ):
        """اضافه کردن کیسینگ‌ها از دیتابیس."""
        try:
            casing_report = self.db.get_casing_report(well_id=well_id)
            if not casing_report:
                return

            import json
            casing_json = casing_report.get("casing_json")
            if not casing_json:
                return

            casings_data = json.loads(casing_json) if isinstance(casing_json, str) else casing_json
            if not isinstance(casings_data, list):
                return

            # نگاشت نوع کیسینگ
            type_map = {
                "Conductor": ElementType.CONDUCTOR,
                "Surface": ElementType.SURFACE_CASING,
                "Surface Casing": ElementType.SURFACE_CASING,
                "Intermediate": ElementType.INTERMEDIATE_CASING,
                "Intermediate Casing": ElementType.INTERMEDIATE_CASING,
                "Production": ElementType.PRODUCTION_CASING,
                "Production Casing": ElementType.PRODUCTION_CASING,
                "Liner": ElementType.LINER,
            }

            for i, c in enumerate(casings_data):
                od = float(c.get("od", c.get("size", 0)) or 0)
                id_ = float(c.get("id", 0) or 0)
                from_d = float(c.get("from", c.get("depth_in", 0)) or 0)
                to_d = float(c.get("to", c.get("depth_out", 500)) or 500)
                ctype = c.get("type", "")

                if od <= 0:
                    continue

                element_type = type_map.get(
                    ctype, ElementType.SURFACE_CASING
                )

                schematic.casings.append(CasingData(
                    name=ctype,
                    element_type=element_type,
                    od_inch=od,
                    id_inch=id_ if id_ > 0 else od * 0.9,
                    top_depth_m=from_d,
                    bottom_depth_m=to_d,
                    grade=c.get("grade", "L-80"),
                    connection=c.get("connection", "BTC"),
                    cement_top_m=0,
                    cement_bottom_m=to_d,
                    show_cement=True,
                ))

        except Exception as e:
            logger.error(f"Error loading casings: {e}")

    def _add_formations_from_db(
        self, schematic: WellboreSchematic, well_id: int
    ):
        """اضافه کردن سازندها از دیتابیس."""
        try:
            formation_report = self.db.get_formation_report(well_id)
            if not formation_report:
                return

            formations = formation_report.get("formations", [])
            if isinstance(formations, str):
                import json
                formations = json.loads(formations)

            for f in formations:
                top = float(f.get("top", f.get("Top MD (m)", 0)) or 0)
                base = float(f.get("base", f.get("Base MD (m)", 100)) or 100)
                litho = f.get("lithology", f.get("Lithology", "Shale"))
                color = f.get("color", f.get("Color", ""))
                name = f.get("name", f.get("Formation Name", f.get("name", "")))

                if base <= top:
                    continue

                schematic.formations.append(FormationLayer(
                    name=name,
                    top_depth_m=top,
                    bottom_depth_m=base,
                    lithology=litho,
                    color=color or SchematicColors.FORMATIONS.get(litho, "#808080"),
                ))

        except Exception as e:
            logger.error(f"Error loading formations: {e}")

    def _add_completion_from_db(
        self, schematic: WellboreSchematic, well_id: int
    ):
        """اضافه کردن Completion از دیتابیس."""
        try:
            session = self.db.create_session()
            from core.database import DownholeEquipment
            eq_records = session.query(DownholeEquipment).filter(
                DownholeEquipment.well_id == well_id
            ).all()
            for eq in eq_records:
                if eq.equipment_data_json:
                    items = eq.equipment_data_json if isinstance(eq.equipment_data_json, list) else [eq.equipment_data_json]
                    for it in items:
                        if isinstance(it, dict):
                            depth = float(it.get("depth", 0) or it.get("depth_m", 0) or 0)
                            if depth > 0:
                                elem_type = ElementType.PACKER if "packer" in str(it.get("type", "")).lower() else ElementType.TUBING
                                schematic.completions.append(
                                    CompletionItem(
                                        element_type=elem_type,
                                        depth_m=depth,
                                        od_inch=float(it.get("od_inch", 4.5) or 4.5),
                                        length_m=float(it.get("length_m", 2.0) or 2.0),
                                        label=str(it.get("name", "") or it.get("type", "Tubing")),
                                        color=str(it.get("color", "") or "#27ae60")
                                    )
                                )

            session.close()
        except Exception as e:
            logger.error(f"Error loading completion: {e}")

    def _add_default_casings(self, schematic: WellboreSchematic):
        """اضافه کردن کیسینگ‌های پیش‌فرض."""
        td = schematic.total_depth_m
        schematic.casings = [
            CasingData(
                name="Conductor",
                element_type=ElementType.CONDUCTOR,
                od_inch=20.0, id_inch=18.73,
                top_depth_m=0, bottom_depth_m=min(80, td * 0.05),
                cement_top_m=0, cement_bottom_m=min(80, td * 0.05),
            ),
            CasingData(
                name="Surface Casing",
                element_type=ElementType.SURFACE_CASING,
                od_inch=13.375, id_inch=12.415,
                top_depth_m=0, bottom_depth_m=min(500, td * 0.2),
                cement_top_m=0, cement_bottom_m=min(500, td * 0.2),
            ),
            CasingData(
                name="Intermediate Casing",
                element_type=ElementType.INTERMEDIATE_CASING,
                od_inch=9.625, id_inch=8.835,
                top_depth_m=0, bottom_depth_m=min(2000, td * 0.65),
                cement_top_m=min(200, td * 0.1),
                cement_bottom_m=min(2000, td * 0.65),
            ),
            CasingData(
                name="Production Casing",
                element_type=ElementType.PRODUCTION_CASING,
                od_inch=7.0, id_inch=6.276,
                top_depth_m=0, bottom_depth_m=td,
                cement_top_m=min(1500, td * 0.5),
                cement_bottom_m=td,
            ),
        ]