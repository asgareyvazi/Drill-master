# tabs/w3c_section_data.py
"""
Section Data Tab‌  
"""

import logging
import json
from datetime import datetime, date, timezone

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

from core.database import DatabaseManager, ServiceCompany
from core.managers import (
    StatusBarManager, ExportManager, TableManager,
    DrillingManager, AutoSaveManager
)
from core.base_tab import DrillTabBase
from core.selection_manager import SelectionManager

from core.text_utils import wrap_text, wrap_html

logger = logging.getLogger(__name__)

# ==================== 1. CementReportTab ====================
class CementReportTab(QWidget):
    """تب گزارش سیمان - section level"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.parent = parent
        self.current_well = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        cl = QVBoxLayout(content)

        hg = QGroupBox("🏗️ Cement Job Information")
        hl = QGridLayout()
        hl.addWidget(QLabel("Report Name:"), 0, 0)
        self.report_name = QLineEdit()
        hl.addWidget(self.report_name, 0, 1)
        hl.addWidget(QLabel("Cement Type:"), 0, 2)
        self.cement_type = QComboBox()
        self.cement_type.addItems(["Class G", "Class H", "Class A", "Class C", "Special"])
        hl.addWidget(self.cement_type, 0, 3)
        hl.addWidget(QLabel("Job Type:"), 1, 0)
        self.job_type = QComboBox()
        self.job_type.addItems(["Primary Cementing", "Squeeze", "Plug Back", "Liner", "Stage Cementing"])
        hl.addWidget(self.job_type, 1, 1)
        hl.addWidget(QLabel("Date:"), 1, 2)
        self.report_date = QDateEdit()
        self.report_date.setDate(QDate.currentDate())
        self.report_date.setCalendarPopup(True)
        hl.addWidget(self.report_date, 1, 3)
        hg.setLayout(hl)
        cl.addWidget(hg)

        mg = QGroupBox("🧱 Cement Materials")
        ml = QVBoxLayout()
        self.materials_table = QTableWidget(0, 7)
        self.materials_table.setHorizontalHeaderLabels(["Material", "Type", "Received", "Consumed", "Backload", "Inventory", "Unit"])
        self.materials_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        ml.addWidget(self.materials_table)
        mb = QHBoxLayout()
        ab = QPushButton("➕ Add"); ab.clicked.connect(self.add_material_row)
        rb = QPushButton("➖ Remove"); rb.clicked.connect(self.remove_material_row)
        mb.addWidget(ab); mb.addWidget(rb); mb.addStretch()
        ml.addLayout(mb)
        mg.setLayout(ml)
        cl.addWidget(mg)

        pg = QGroupBox("⚙️ Parameters")
        pl = QGridLayout()
        self.slurry_density = QDoubleSpinBox(); self.slurry_density.setRange(0,200); self.slurry_density.setValue(120)
        self.slurry_yield = QDoubleSpinBox(); self.slurry_yield.setRange(0,10); self.slurry_yield.setDecimals(2); self.slurry_yield.setValue(1.18)
        self.mix_water = QDoubleSpinBox(); self.mix_water.setRange(0,20); self.mix_water.setValue(5.2)
        self.thickening_hours = QSpinBox(); self.thickening_hours.setRange(0,24); self.thickening_hours.setValue(4)
        self.thickening_minutes = QSpinBox(); self.thickening_minutes.setRange(0,59); self.thickening_minutes.setValue(30)
        self.compressive_strength = QDoubleSpinBox(); self.compressive_strength.setRange(0,10000); self.compressive_strength.setValue(2500)
        self.fluid_loss = QDoubleSpinBox(); self.fluid_loss.setRange(0,500)
        pl.addWidget(QLabel("Slurry Density (pcf):"),0,0); pl.addWidget(self.slurry_density,0,1)
        pl.addWidget(QLabel("Slurry Yield:"),0,2); pl.addWidget(self.slurry_yield,0,3)
        pl.addWidget(QLabel("Mix Water:"),1,0); pl.addWidget(self.mix_water,1,1)
        tl = QHBoxLayout(); tl.addWidget(self.thickening_hours); tl.addWidget(QLabel("hr")); tl.addWidget(self.thickening_minutes); tl.addWidget(QLabel("min")); tl.addStretch()
        pl.addWidget(QLabel("Thickening Time:"),1,2); pl.addLayout(tl,1,3)
        pl.addWidget(QLabel("Comp. Strength:"),2,0); pl.addWidget(self.compressive_strength,2,1)
        pl.addWidget(QLabel("Fluid Loss:"),2,2); pl.addWidget(self.fluid_loss,2,3)
        pg.setLayout(pl)
        cl.addWidget(pg)

        vg = QGroupBox("📊 Volumes")
        vl = QGridLayout()
        self.cement_volume = QDoubleSpinBox(); self.cement_volume.setRange(0,10000)
        self.displacement_volume = QDoubleSpinBox(); self.displacement_volume.setRange(0,5000); self.displacement_volume.setDecimals(1)
        self.top_of_cement = QDoubleSpinBox(); self.top_of_cement.setRange(0,20000); self.top_of_cement.setDecimals(2)
        self.bottom_of_cement = QDoubleSpinBox(); self.bottom_of_cement.setRange(0,20000); self.bottom_of_cement.setDecimals(2)
        vl.addWidget(QLabel("Cement Vol (sacks):"),0,0); vl.addWidget(self.cement_volume,0,1)
        vl.addWidget(QLabel("Displacement (bbl):"),0,2); vl.addWidget(self.displacement_volume,0,3)
        vl.addWidget(QLabel("Top of Cement (m):"),1,0); vl.addWidget(self.top_of_cement,1,1)
        vl.addWidget(QLabel("Bottom (m):"),1,2); vl.addWidget(self.bottom_of_cement,1,3)
        vg.setLayout(vl)
        cl.addWidget(vg)

        sg = QGroupBox("📝 Summary")
        sl = QVBoxLayout(); self.cement_summary = QTextEdit(); self.cement_summary.setMaximumHeight(120)
        sl.addWidget(self.cement_summary); sg.setLayout(sl)
        cl.addWidget(sg)

        bl = QHBoxLayout()
        sb = QPushButton("💾 Save"); sb.clicked.connect(self.save_data)
        lb = QPushButton("📂 Load"); lb.clicked.connect(self.load_data)
        bl.addWidget(sb); bl.addWidget(lb); bl.addStretch()
        cl.addLayout(bl); cl.addStretch()
        scroll.setWidget(content); layout.addWidget(scroll)

    def add_material_row(self, material="", mt="", received=0, consumed=0, backload=0, inventory=0, unit="kg"):
        row = self.materials_table.rowCount(); self.materials_table.insertRow(row)
        self.materials_table.setCellWidget(row, 0, QLineEdit(material or f"Material_{row+1}"))
        tc = QComboBox(); tc.addItems(["Cement","Additive","Mix Water","Spacer","Chemical"]); tc.setCurrentText(mt)
        self.materials_table.setCellWidget(row, 1, tc)
        for col, val, ro in [(2,received,False),(3,consumed,False),(4,backload,False),(5,inventory,True)]:
            sp = QDoubleSpinBox(); sp.setRange(-10000,10000); sp.setValue(val)
            if ro: sp.setReadOnly(True)
            if col in [2,3]: sp.valueChanged.connect(lambda v,r=row: self._calc_inv(r))
            self.materials_table.setCellWidget(row, col, sp)
        uc = QComboBox(); uc.addItems(["sacks","kg","lb","bbl","gal"]); uc.setCurrentText(unit)
        self.materials_table.setCellWidget(row, 6, uc)

    def _calc_inv(self, row):
        r=self.materials_table.cellWidget(row,2); c=self.materials_table.cellWidget(row,3); i=self.materials_table.cellWidget(row,5)
        if r and c and i: i.setValue(r.value()-c.value())

    def remove_material_row(self):
        r=self.materials_table.currentRow()
        if r>=0: self.materials_table.removeRow(r)

    def load_for_report(self, report_id):
        if self.db_manager:
            data = self.db_manager.get_cement_report(report_id=report_id)
            if data: self.load_from_dict(data)
            else: self.clear_form()

    def save_data_for_report(self, report_id):
        if not self.current_well: return False
        mats = []
        for row in range(self.materials_table.rowCount()):
            mats.append({k: (self.materials_table.cellWidget(row,c).text() if isinstance(self.materials_table.cellWidget(row,c),QLineEdit) else self.materials_table.cellWidget(row,c).value() if isinstance(self.materials_table.cellWidget(row,c),QDoubleSpinBox) else self.materials_table.cellWidget(row,c).currentText()) for c,k in enumerate(["material","type","received","consumed","backload","inventory","unit"])})
        d = {"well_id":self.current_well,"report_id":report_id,"report_date":date.today(),"report_name":self.report_name.text(),"cement_type":self.cement_type.currentText(),"job_type":self.job_type.currentText(),"materials_json":json.dumps(mats),"slurry_density":self.slurry_density.value(),"slurry_yield":self.slurry_yield.value(),"mix_water":self.mix_water.value(),"thickening_time":f"{self.thickening_hours.value():02d}:{self.thickening_minutes.value():02d}","compressive_strength":self.compressive_strength.value(),"fluid_loss":self.fluid_loss.value(),"cement_volume":self.cement_volume.value(),"displacement_volume":self.displacement_volume.value(),"top_of_cement":self.top_of_cement.value(),"bottom_of_cement":self.bottom_of_cement.value(),"summary":self.cement_summary.toPlainText()}
        return self.db_manager.save_cement_report(d) is not None

    def save_data(self):
        if self.parent and hasattr(self.parent,'current_section_id') and self.parent.current_section_id:
            return self.save_data_for_report(None)
        return False

    def save_data_with_section(self, well_id, section_id):
        """ذخیره با section_id"""
        mats = []
        for row in range(self.materials_table.rowCount()):
            mats.append({k: (self.materials_table.cellWidget(row,c).text() if isinstance(self.materials_table.cellWidget(row,c),QLineEdit) else self.materials_table.cellWidget(row,c).value() if isinstance(self.materials_table.cellWidget(row,c),QDoubleSpinBox) else self.materials_table.cellWidget(row,c).currentText()) for c,k in enumerate(["material","type","received","consumed","backload","inventory","unit"])})
        d = {
            "well_id": well_id,
            "section_id": section_id,
            "report_date": date.today(),
            "report_name": self.report_name.text(),
            "cement_type": self.cement_type.currentText(),
            "job_type": self.job_type.currentText(),
            "materials_json": json.dumps(mats),
            "slurry_density": self.slurry_density.value(),
            "slurry_yield": self.slurry_yield.value(),
            "mix_water": self.mix_water.value(),
            "thickening_time": f"{self.thickening_hours.value():02d}:{self.thickening_minutes.value():02d}",
            "compressive_strength": self.compressive_strength.value(),
            "fluid_loss": self.fluid_loss.value(),
            "cement_volume": self.cement_volume.value(),
            "displacement_volume": self.displacement_volume.value(),
            "top_of_cement": self.top_of_cement.value(),
            "bottom_of_cement": self.bottom_of_cement.value(),
            "summary": self.cement_summary.toPlainText(),
        }
        return self.db_manager.save_cement_report(d) if self.db_manager else None
        
    def load_data(self):
        if self.current_well:
            data = self.db_manager.get_cement_report(well_id=self.current_well) if self.db_manager else None
            if data: self.load_from_dict(data)

    def load_from_dict(self, data):
        def sv(k,d=0):
            v=data.get(k); 
            try: return float(v) if v is not None else d
            except: return d
        self.report_name.setText(str(data.get("report_name","") or ""))
        self.cement_type.setCurrentText(str(data.get("cement_type","") or ""))
        self.job_type.setCurrentText(str(data.get("job_type","") or ""))
        self.slurry_density.setValue(sv("slurry_density",120)); self.slurry_yield.setValue(sv("slurry_yield",1.18))
        self.mix_water.setValue(sv("mix_water",5.2))
        tp=str(data.get("thickening_time","04:30") or "04:30").split(":")
        try: self.thickening_hours.setValue(int(tp[0])); self.thickening_minutes.setValue(int(tp[1]))
        except: pass
        self.compressive_strength.setValue(sv("compressive_strength",2500)); self.fluid_loss.setValue(sv("fluid_loss"))
        self.cement_volume.setValue(sv("cement_volume")); self.displacement_volume.setValue(sv("displacement_volume"))
        self.top_of_cement.setValue(sv("top_of_cement")); self.bottom_of_cement.setValue(sv("bottom_of_cement"))
        self.cement_summary.setPlainText(str(data.get("summary","") or ""))
        mj=data.get("materials_json")
        if mj:
            self.materials_table.setRowCount(0)
            try:
                ms=json.loads(mj) if isinstance(mj,str) else mj
                for m in ms: self.add_material_row(m.get("material",""),m.get("type",""),float(m.get("received",0) or 0),float(m.get("consumed",0) or 0),float(m.get("backload",0) or 0),float(m.get("inventory",0) or 0),m.get("unit","kg"))
            except: pass

    def clear_form(self):
        self.report_name.clear(); self.cement_type.setCurrentIndex(0); self.job_type.setCurrentIndex(0)
        for sp in [self.slurry_density,self.slurry_yield,self.mix_water,self.compressive_strength,self.fluid_loss,self.cement_volume,self.displacement_volume,self.top_of_cement,self.bottom_of_cement]: sp.setValue(0)
        self.slurry_density.setValue(120); self.slurry_yield.setValue(1.18); self.mix_water.setValue(5.2); self.compressive_strength.setValue(2500)
        self.materials_table.setRowCount(0); self.cement_summary.clear()

    def refresh(self): self.load_data()


# ==================== 2. CasingReportTab ====================
class CasingReportTab(QWidget):
    """تب گزارش کیسینگ - section level"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.parent = parent
        self.current_well = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); cl = QVBoxLayout(content)

        hg = QGroupBox("🔩 Casing Job Information")
        hl = QGridLayout()
        hl.addWidget(QLabel("Report Name:"),0,0)
        self.report_name = QLineEdit(); hl.addWidget(self.report_name,0,1)
        hl.addWidget(QLabel("Casing Type:"),0,2)
        self.casing_type = QComboBox(); self.casing_type.addItems(["Surface","Intermediate","Production","Liner","Tieback"])
        hl.addWidget(self.casing_type,0,3)
        hg.setLayout(hl); cl.addWidget(hg)

        dg = QGroupBox("📐 Casing String Design")
        dl = QVBoxLayout()
        self.casing_table = QTableWidget(0,10)
        self.casing_table.setHorizontalHeaderLabels(["Size","OD","ID","Weight","Grade","Connection","From(m)","To(m)","Shoe(m)","Remarks"])
        self.casing_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        dl.addWidget(self.casing_table)
        cb = QHBoxLayout()
        ab = QPushButton("➕ Add"); ab.clicked.connect(self.add_casing_row)
        rb = QPushButton("➖ Remove"); rb.clicked.connect(self.remove_casing_row)
        cb.addWidget(ab); cb.addWidget(rb); cb.addStretch()
        dl.addLayout(cb); dg.setLayout(dl); cl.addWidget(dg)

        pg = QGroupBox("⚙️ Properties")
        pl = QGridLayout()
        self.burst_pressure=QDoubleSpinBox();self.burst_pressure.setRange(0,20000)
        self.collapse_pressure=QDoubleSpinBox();self.collapse_pressure.setRange(0,20000)
        self.tensile_strength=QDoubleSpinBox();self.tensile_strength.setRange(0,5000)
        self.makeup_torque=QDoubleSpinBox();self.makeup_torque.setRange(0,50000)
        self.drift_diameter=QDoubleSpinBox();self.drift_diameter.setRange(0,100);self.drift_diameter.setDecimals(3)
        self.internal_yield=QDoubleSpinBox();self.internal_yield.setRange(0,20000)
        self.running_speed=QDoubleSpinBox();self.running_speed.setRange(0,50);self.running_speed.setDecimals(1)
        self.fillup_frequency=QSpinBox();self.fillup_frequency.setRange(0,100)
        self.centralizer_spacing=QDoubleSpinBox();self.centralizer_spacing.setRange(0,100)
        self.scratcher_spacing=QDoubleSpinBox();self.scratcher_spacing.setRange(0,100)
        for r,pairs in enumerate([("Burst:",self.burst_pressure,"Collapse:",self.collapse_pressure),("Tensile:",self.tensile_strength,"MU Torque:",self.makeup_torque),("Drift ID:",self.drift_diameter,"Int. Yield:",self.internal_yield),("Run Speed:",self.running_speed,"Fill-up:",self.fillup_frequency),("Centralizer:",self.centralizer_spacing,"Scratcher:",self.scratcher_spacing)]):
            pl.addWidget(QLabel(pairs[0]),r,0);pl.addWidget(pairs[1],r,1);pl.addWidget(QLabel(pairs[2]),r,2);pl.addWidget(pairs[3],r,3)
        pg.setLayout(pl); cl.addWidget(pg)

        sg=QGroupBox("📝 Summary");sl=QVBoxLayout()
        self.casing_summary=QTextEdit();self.casing_summary.setMaximumHeight(120)
        sl.addWidget(self.casing_summary);sg.setLayout(sl);cl.addWidget(sg)

        bl=QHBoxLayout()
        sb=QPushButton("💾 Save");sb.clicked.connect(self.save_data)
        lb=QPushButton("📂 Load");lb.clicked.connect(self.load_data)
        bl.addWidget(sb);bl.addWidget(lb);bl.addStretch()
        cl.addLayout(bl);cl.addStretch()
        scroll.setWidget(content);layout.addWidget(scroll)

    def add_casing_row(self,size=0,od=0,id_s=0,weight=0,grade="",conn="",from_d=0,to_d=0,shoe=0,remarks=""):
        row=self.casing_table.rowCount();self.casing_table.insertRow(row)
        for col,val,rng,dec in [(0,size,(0,100),3),(1,od,(0,100),3),(2,id_s,(0,100),3),(3,weight,(0,1000),1),(6,from_d,(0,20000),2),(7,to_d,(0,20000),2),(8,shoe,(0,20000),2)]:
            sp=QDoubleSpinBox();sp.setRange(*rng);sp.setValue(val);sp.setDecimals(dec);self.casing_table.setCellWidget(row,col,sp)
        for col,items,cur in [(4,["H-40","J-55","K-55","N-80","L-80","C-90","P-110","Q-125"],grade),(5,["BTC","LTC","STC","Premium","Integral","Buttress"],conn)]:
            cb=QComboBox();cb.addItems(items);cb.setCurrentText(cur);self.casing_table.setCellWidget(row,col,cb)
        self.casing_table.setCellWidget(row,9,QLineEdit(remarks))

    def remove_casing_row(self):
        r=self.casing_table.currentRow()
        if r>=0:self.casing_table.removeRow(r)

    def load_for_report(self,report_id):
        if self.db_manager:
            data=self.db_manager.get_casing_report(report_id=report_id)
            if data:self.load_from_dict(data)
            else:self.clear_form()

    def save_data_for_report(self,report_id):
        if not self.current_well:return False
        cd=[]
        for row in range(self.casing_table.rowCount()):
            cd.append({k:(self.casing_table.cellWidget(row,c).value() if isinstance(self.casing_table.cellWidget(row,c),QDoubleSpinBox) else self.casing_table.cellWidget(row,c).currentText() if isinstance(self.casing_table.cellWidget(row,c),QComboBox) else self.casing_table.cellWidget(row,c).text() if self.casing_table.cellWidget(row,c) else "") for c,k in enumerate(["size","od","id","weight","grade","connection","from","to","shoe","remarks"])})
        rpt={"well_id":self.current_well,"report_id":report_id,"report_date":date.today(),"report_name":self.report_name.text(),"casing_type":self.casing_type.currentText(),"casing_json":json.dumps(cd),"burst_pressure":self.burst_pressure.value(),"collapse_pressure":self.collapse_pressure.value(),"tensile_strength":self.tensile_strength.value(),"makeup_torque":self.makeup_torque.value(),"drift_diameter":self.drift_diameter.value(),"internal_yield":self.internal_yield.value(),"running_speed":self.running_speed.value(),"fillup_frequency":self.fillup_frequency.value(),"centralizer_spacing":self.centralizer_spacing.value(),"scratcher_spacing":self.scratcher_spacing.value(),"summary":self.casing_summary.toPlainText()}
        return self.db_manager.save_casing_report(rpt) is not None

    def save_data(self):
        if self.parent and hasattr(self.parent,'current_section_id'):
            return self.save_data_for_report(None)
        return False

    def save_data_with_section(self, well_id, section_id):
        """ذخیره با section_id"""
        cd = []
        for row in range(self.casing_table.rowCount()):
            cd.append({k:(self.casing_table.cellWidget(row,c).value() if isinstance(self.casing_table.cellWidget(row,c),QDoubleSpinBox) else self.casing_table.cellWidget(row,c).currentText() if isinstance(self.casing_table.cellWidget(row,c),QComboBox) else self.casing_table.cellWidget(row,c).text() if self.casing_table.cellWidget(row,c) else "") for c,k in enumerate(["size","od","id","weight","grade","connection","from","to","shoe","remarks"])})
        d = {
            "well_id": well_id,
            "section_id": section_id,
            "report_date": date.today(),
            "report_name": self.report_name.text(),
            "casing_type": self.casing_type.currentText(),
            "casing_json": json.dumps(cd),
            "burst_pressure": self.burst_pressure.value(),
            "collapse_pressure": self.collapse_pressure.value(),
            "tensile_strength": self.tensile_strength.value(),
            "makeup_torque": self.makeup_torque.value(),
            "drift_diameter": self.drift_diameter.value(),
            "internal_yield": self.internal_yield.value(),
            "running_speed": self.running_speed.value(),
            "fillup_frequency": self.fillup_frequency.value(),
            "centralizer_spacing": self.centralizer_spacing.value(),
            "scratcher_spacing": self.scratcher_spacing.value(),
            "summary": self.casing_summary.toPlainText(),
        }
        return self.db_manager.save_casing_report(d) if self.db_manager else None
        
    def load_data(self):
        if self.current_well and self.db_manager:
            data=self.db_manager.get_casing_report(well_id=self.current_well)
            if data:self.load_from_dict(data)

    def load_from_dict(self,data):
        def sv(k,d=0):
            v=data.get(k)
            try:return float(v) if v is not None else d
            except:return d
        self.report_name.setText(str(data.get("report_name","") or ""))
        self.casing_type.setCurrentText(str(data.get("casing_type","") or ""))
        for attr,key in [(self.burst_pressure,"burst_pressure"),(self.collapse_pressure,"collapse_pressure"),(self.tensile_strength,"tensile_strength"),(self.makeup_torque,"makeup_torque"),(self.drift_diameter,"drift_diameter"),(self.internal_yield,"internal_yield"),(self.running_speed,"running_speed"),(self.centralizer_spacing,"centralizer_spacing"),(self.scratcher_spacing,"scratcher_spacing")]:
            attr.setValue(sv(key))
        self.fillup_frequency.setValue(int(sv("fillup_frequency")))
        self.casing_summary.setPlainText(str(data.get("summary","") or ""))
        cj=data.get("casing_json")
        if cj:
            self.casing_table.setRowCount(0)
            try:
                cs=json.loads(cj) if isinstance(cj,str) else cj
                for c in cs:self.add_casing_row(float(c.get("size",0)or 0),float(c.get("od",0)or 0),float(c.get("id",0)or 0),float(c.get("weight",0)or 0),str(c.get("grade","")or""),str(c.get("connection","")or""),float(c.get("from",0)or 0),float(c.get("to",0)or 0),float(c.get("shoe",0)or 0),str(c.get("remarks","")or""))
            except Exception as e:logger.error(f"Casing JSON error: {e}")

    def clear_form(self):
        self.report_name.clear();self.casing_type.setCurrentIndex(0)
        for sp in [self.burst_pressure,self.collapse_pressure,self.tensile_strength,self.makeup_torque,self.drift_diameter,self.internal_yield,self.running_speed,self.centralizer_spacing,self.scratcher_spacing]:sp.setValue(0)
        self.fillup_frequency.setValue(0);self.casing_table.setRowCount(0);self.casing_summary.clear()

    def refresh(self):self.load_data()


# ==================== 3. CasingTallyWidget ====================
class CasingTallyWidget(QWidget):
    """ویجت Casing Tally - section level"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.current_well = None
        self.current_report_id = None
        self.stats_labels = {}
        self.init_ui()
        self.setup_connections()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        toolbar = QToolBar()
        for text, slot in [("💾 Save",self.save_tally_report),("📂 Load",self.load_tally_report),("📤 Export",self.export_tally_data),("🔄 Calculate",self.calculate_all)]:
            a=QAction(text,self);a.triggered.connect(slot);toolbar.addAction(a)
        toolbar.addSeparator()
        self.current_well_label = QLabel("No well selected")
        toolbar.addWidget(self.current_well_label)
        main_layout.addWidget(toolbar)

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.create_specifications_tab(), "🔧 Specifications")
        self.tab_widget.addTab(self.create_tally_details_tab(), "📊 Tally Details")
        self.tab_widget.addTab(self.create_summary_tab(), "📝 Summary")
        main_layout.addWidget(self.tab_widget)
        self.status_bar = QStatusBar(); self.status_bar.showMessage("Ready")
        main_layout.addWidget(self.status_bar)

    def create_specifications_tab(self):
        tab=QWidget();layout=QVBoxLayout(tab);scroll=QScrollArea();scroll.setWidgetResizable(True)
        content=QWidget();cl=QVBoxLayout(content)
        sg=QGroupBox("Casing Specifications");sl=QVBoxLayout()
        self.specs_table=QTableWidget(0,12)
        self.specs_table.setHorizontalHeaderLabels(["Size","ID","Weight","Drift ID","MU Torque","Burst","Collapse","Tensile","Coupling","Nominal OD","Grade","Connection"])
        self.specs_table.setAlternatingRowColors(True);sl.addWidget(self.specs_table)
        sb=QHBoxLayout()
        for text,slot in [("➕ Add",self.add_specification_row),("➖ Remove",self.remove_specification_row)]:
            b=QPushButton(text);b.clicked.connect(slot);sb.addWidget(b)
        sb.addStretch();sl.addLayout(sb);sg.setLayout(sl);cl.addWidget(sg)

        pg=QGroupBox("Parameters");pl=QGridLayout()
        self.rt_depth=QDoubleSpinBox();self.rt_depth.setRange(0,20000);self.rt_depth.setValue(3000);self.rt_depth.setSuffix(" m")
        self.mud_weight=QDoubleSpinBox();self.mud_weight.setRange(0,200);self.mud_weight.setValue(65);self.mud_weight.setSuffix(" pcf")
        self.steel_density=QDoubleSpinBox();self.steel_density.setRange(0,500);self.steel_density.setValue(490);self.steel_density.setSuffix(" lb/ft³")
        self.buoyancy_factor=QDoubleSpinBox();self.buoyancy_factor.setReadOnly(True);self.buoyancy_factor.setRange(0,1);self.buoyancy_factor.setDecimals(3)
        pl.addWidget(QLabel("RT Depth:"),0,0);pl.addWidget(self.rt_depth,0,1)
        pl.addWidget(QLabel("Mud Weight:"),0,2);pl.addWidget(self.mud_weight,0,3)
        pl.addWidget(QLabel("Steel Density:"),1,0);pl.addWidget(self.steel_density,1,1)
        pl.addWidget(QLabel("Buoyancy:"),1,2);pl.addWidget(self.buoyancy_factor,1,3)
        pg.setLayout(pl);cl.addWidget(pg)
        self.add_sample_specifications()
        scroll.setWidget(content);layout.addWidget(scroll);return tab

    def create_tally_details_tab(self):
        tab=QWidget();layout=QVBoxLayout(tab);scroll=QScrollArea();scroll.setWidgetResizable(True)
        content=QWidget();cl=QVBoxLayout(content)
        tg=QGroupBox("Casing Tally");tl=QVBoxLayout()
        self.tally_table=QTableWidget(0,12)
        self.tally_table.setHorizontalHeaderLabels(["No.","Size","Grade","Order No.","Joint Len(m)","Cum Length","Dist to RT","M/D Weight","String Cap","Centralizers","IN/OUT","Remarks"])
        self.tally_table.setAlternatingRowColors(True);tl.addWidget(self.tally_table)
        tb=QHBoxLayout()
        for text,slot in [("➕ Add Joint",self.add_tally_row),("➖ Remove",self.remove_tally_row),("🗑️ Clear",self.clear_tally_table),("🔄 Auto Fill",self.auto_fill_tally)]:
            b=QPushButton(text);b.clicked.connect(slot);tb.addWidget(b)
        tb.addStretch();tl.addLayout(tb);tg.setLayout(tl);cl.addWidget(tg)
        self.add_sample_tally_rows()
        scroll.setWidget(content);layout.addWidget(scroll);return tab

    def create_summary_tab(self):
        tab=QWidget();layout=QVBoxLayout(tab)
        rg=QGroupBox("Summary");rl=QVBoxLayout()
        self.summary_text=QTextEdit();self.summary_text.setMinimumHeight(200);self.summary_text.setReadOnly(True)
        rl.addWidget(self.summary_text)
        rb=QHBoxLayout()
        for text,slot in [("📊 Generate",self.generate_summary_report),("📤 Export",self.export_summary_report),("🖨️ Print",self.print_report)]:
            b=QPushButton(text);b.clicked.connect(slot);rb.addWidget(b)
        rb.addStretch();rl.addLayout(rb);rg.setLayout(rl);layout.addWidget(rg)
        stg=QGroupBox("Quick Statistics");stl=QGridLayout()
        for i,(label,key) in enumerate([("Total Joints:","total_joints"),("Total Length:","total_length"),("Total Weight:","total_weight"),("Total Capacity:","total_capacity"),("IN Joints:","in_joints"),("OUT Joints:","out_joints"),("Avg Joint Length:","avg_length"),("Buoyancy Factor:","buoyancy_factor")]):
            r,c=i//2,(i%2)*2;stl.addWidget(QLabel(label),r,c)
            vl=QLabel("0");vl.setStyleSheet("font-weight:bold;color:#0078d4;");stl.addWidget(vl,r,c+1);self.stats_labels[key]=vl
        stg.setLayout(stl);layout.addWidget(stg);return tab

    def setup_connections(self):
        self.rt_depth.valueChanged.connect(self.calculate_tally)
        self.mud_weight.valueChanged.connect(lambda:(self.calculate_buoyancy(),self.calculate_tally()))
        self.steel_density.valueChanged.connect(lambda:(self.calculate_buoyancy(),self.calculate_tally()))

    def add_sample_specifications(self):
        for spec in [(13.375,12.415,61,12.347,22700,6070,4810,1126000,"BTC",14.375,"P-110","Premium"),(9.625,8.835,47,8.729,17300,6070,7530,1225000,"BTC",10.625,"L-80","Premium"),(7.0,6.276,29,6.184,12500,6070,10810,924000,"BTC",7.625,"L-80","VAM")]:
            self.add_specification_row(*spec)

    def add_specification_row(self,size=13.375,id_s=12.415,weight=61,drift=12.347,torque=22700,burst=6070,collapse=4810,tensile=1126000,coupling="BTC",nom_od=14.375,grade="P-110",connection="Premium"):
        row=self.specs_table.rowCount();self.specs_table.insertRow(row)
        for col,val,rng,dec in [(0,size,(0,100),3),(1,id_s,(0,100),3),(2,weight,(0,1000),2),(3,drift,(0,100),3),(4,torque,(0,100000),0),(5,burst,(0,20000),0),(6,collapse,(0,20000),0),(7,tensile,(0,5000000),0),(9,nom_od,(0,100),3)]:
            sp=QDoubleSpinBox();sp.setRange(*rng);sp.setValue(val);sp.setDecimals(dec)
            if col in [0,1,2]:sp.valueChanged.connect(lambda:self.calculate_tally())
            self.specs_table.setCellWidget(row,col,sp)
        for col,items,cur in [(8,["BTC","LTC","STC","Premium","Integral","Buttress"],coupling),(10,["H-40","J-55","K-55","N-80","L-80","C-90","P-110","Q-125"],grade),(11,["VAM","Hydril","Grant","Tenaris","Premium","Other"],connection)]:
            cb=QComboBox();cb.addItems(items);cb.setCurrentText(cur);self.specs_table.setCellWidget(row,col,cb)

    def remove_specification_row(self):
        r=self.specs_table.currentRow()
        if r>=0:self.specs_table.removeRow(r)

    def add_sample_tally_rows(self):
        for i in range(5):self.add_tally_row(i+1)

    def add_tally_row(self,joint_no=None):
        if joint_no is None:joint_no=self.tally_table.rowCount()+1
        row=self.tally_table.rowCount();self.tally_table.insertRow(row)
        ni=QTableWidgetItem(str(joint_no));ni.setTextAlignment(Qt.AlignCenter);self.tally_table.setItem(row,0,ni)
        sc=QComboBox();sc.addItems(["13.375","9.625","7.000","5.500"]);sc.currentTextChanged.connect(lambda:self.calculate_tally());self.tally_table.setCellWidget(row,1,sc)
        gc=QComboBox();gc.addItems(["P-110","L-80","N-80","K-55"]);self.tally_table.setCellWidget(row,2,gc)
        oe=QLineEdit(f"ORD-{joint_no:03d}");self.tally_table.setCellWidget(row,3,oe)
        ls=QDoubleSpinBox();ls.setRange(0,50);ls.setValue(12.0);ls.setDecimals(2);ls.valueChanged.connect(self.calculate_tally);self.tally_table.setCellWidget(row,4,ls)
        for col in [5,6,7,8]:
            it=QTableWidgetItem("0.00");it.setTextAlignment(Qt.AlignCenter);self.tally_table.setItem(row,col,it)
        cc=QComboBox();cc.addItems(["Yes","No"]);self.tally_table.setCellWidget(row,9,cc)
        ic=QComboBox();ic.addItems(["IN","OUT"]);ic.currentTextChanged.connect(lambda:self.calculate_tally());self.tally_table.setCellWidget(row,10,ic)
        re=QLineEdit();self.tally_table.setCellWidget(row,11,re)
        self.calculate_tally()

    def remove_tally_row(self):
        r=self.tally_table.currentRow()
        if r>=0:self.tally_table.removeRow(r);self.calculate_tally()

    def clear_tally_table(self):
        if QMessageBox.question(self,"Clear","Clear all?")==QMessageBox.Yes:self.tally_table.setRowCount(0)

    def auto_fill_tally(self):
        if QMessageBox.question(self,"Auto Fill","Add 20 joints?")==QMessageBox.Yes:
            for i in range(20):self.add_tally_row()

    def calculate_buoyancy(self):
        mud=self.mud_weight.value();steel=self.steel_density.value()
        if steel>0:
            bf=1-(mud/steel);self.buoyancy_factor.setValue(bf)
            if "buoyancy_factor" in self.stats_labels:self.stats_labels["buoyancy_factor"].setText(f"{bf:.3f}")

    def calculate_tally(self):
        rt=self.rt_depth.value();bf=self.buoyancy_factor.value();cum_l=cum_w=cum_c=0.0
        for row in range(self.tally_table.rowCount()):
            sc=self.tally_table.cellWidget(row,1);lw=self.tally_table.cellWidget(row,4);io=self.tally_table.cellWidget(row,10)
            if not all([sc,lw,io]):continue
            st=sc.currentText();jl=lw.value();inout=io.currentText()
            if inout=="OUT":
                for col,val in [(5,cum_l),(6,rt-cum_l),(7,cum_w),(8,cum_c)]:self.tally_table.item(row,col).setText(f"{val:.2f}")
                continue
            wpf=id_i=0.0
            for sr in range(self.specs_table.rowCount()):
                ss=self.specs_table.cellWidget(sr,0)
                if ss and abs(ss.value()-float(st))<0.001:wpf=self.specs_table.cellWidget(sr,2).value();id_i=self.specs_table.cellWidget(sr,1).value();break
            cum_l+=jl;jlf=jl*3.28084;aw=wpf*jlf;bw=(aw/1000)*bf;cum_w+=bw
            idf=id_i/12.0;vol=3.1416*(idf/2)**2*jlf;vb=vol/5.615;cum_c+=vb
            for col,val in [(5,cum_l),(6,rt-cum_l),(7,cum_w),(8,cum_c)]:
                it=self.tally_table.item(row,col)
                if it:it.setText(f"{val:.2f}" if col!=8 else f"{val:.3f}")
        self.update_statistics()

    def update_statistics(self):
        if not self.stats_labels:return
        total=self.tally_table.rowCount()
        inj=sum(1 for r in range(total) if self.tally_table.cellWidget(r,10) and self.tally_table.cellWidget(r,10).currentText()=="IN")
        tl=tw=tc=0.0
        if total>0:
            lr=total-1
            for col,attr in [(5,'tl'),(7,'tw'),(8,'tc')]:
                it=self.tally_table.item(lr,col)
                if it:
                    try:
                        v=float(it.text())
                        if col==5:tl=v
                        elif col==7:tw=v
                        else:tc=v
                    except:pass
        al=tl/inj if inj>0 else 0
        self.stats_labels["total_joints"].setText(str(total));self.stats_labels["total_length"].setText(f"{tl:.2f} m")
        self.stats_labels["total_weight"].setText(f"{tw:.2f} Klbs");self.stats_labels["total_capacity"].setText(f"{tc:.3f} bbl")
        self.stats_labels["in_joints"].setText(str(inj));self.stats_labels["out_joints"].setText(str(total-inj))
        self.stats_labels["avg_length"].setText(f"{al:.2f} m")

    def calculate_all(self):self.calculate_buoyancy();self.calculate_tally();self.generate_summary_report()

    def generate_summary_report(self):
        self.calculate_tally()
        self.summary_text.setPlainText(f"📊 CASING TALLY SUMMARY\nTotal: {self.stats_labels['total_joints'].text()} joints\nLength: {self.stats_labels['total_length'].text()}\nWeight: {self.stats_labels['total_weight'].text()}\nCapacity: {self.stats_labels['total_capacity'].text()}\nBuoyancy: {self.buoyancy_factor.value():.3f}")

    def save_tally_report(self):
        if not self.current_well:
            QMessageBox.warning(self, "Warning", "Select a well first.")
            return False
        
        # جمع‌آوری specs و tally...
        specs = []
        for row in range(self.specs_table.rowCount()):
            rd = {}
            for col in range(self.specs_table.columnCount()):
                w = self.specs_table.cellWidget(row, col)
                h = self.specs_table.horizontalHeaderItem(col).text()
                rd[h] = w.value() if isinstance(w, (QDoubleSpinBox, QSpinBox)) else w.currentText() if isinstance(w, QComboBox) else ""
            specs.append(rd)
        
        tally = []
        for row in range(self.tally_table.rowCount()):
            tally.append({
                "No": self.tally_table.item(row, 0).text(),
                "Size": self.tally_table.cellWidget(row, 1).currentText(),
                "Grade": self.tally_table.cellWidget(row, 2).currentText(),
                "Order No": self.tally_table.cellWidget(row, 3).text(),
                "Joint Len": self.tally_table.cellWidget(row, 4).value(),
                "Centralizers": self.tally_table.cellWidget(row, 9).currentText(),
                "IN/OUT": self.tally_table.cellWidget(row, 10).currentText(),
                "Remarks": self.tally_table.cellWidget(row, 11).text(),
            })
        
        full = json.dumps({
            "specifications": specs, "tally": tally,
            "parameters": {
                "rt_depth": self.rt_depth.value(),
                "mud_weight": self.mud_weight.value(),
                "steel_density": self.steel_density.value(),
                "buoyancy_factor": self.buoyancy_factor.value()
            }
        })
        
        # section_id از parent
        section_id = None
        if self.parent() and hasattr(self.parent(), 'current_section_id'):
            section_id = self.parent().current_section_id
        
        if self.db_manager:
            result = self.db_manager.save_casing_report({
                "well_id": self.current_well,
                "section_id": section_id,
                "report_id": self.current_report_id,
                "report_date": date.today(),
                "report_name": f"Tally {datetime.now():%Y-%m-%d}",
                "casing_type": "Tally",
                "tally_json": full,
                "summary": self.summary_text.toPlainText()
            })
            if result:
                self.status_bar.showMessage("Saved", 3000)
                return True
        return False
        
    def load_tally_report(self):
        if not self.current_well or not self.db_manager:return
        rpt=self.db_manager.get_casing_report(well_id=self.current_well)
        if not rpt or not rpt.get("tally_json"):return
        try:
            data=json.loads(rpt["tally_json"])
            self.tally_table.setRowCount(0)
            for j in data.get("tally",[]):
                self.add_tally_row();r=self.tally_table.rowCount()-1
                self.tally_table.cellWidget(r,1).setCurrentText(str(j.get("Size","13.375")))
                self.tally_table.cellWidget(r,2).setCurrentText(str(j.get("Grade","P-110")))
                self.tally_table.cellWidget(r,3).setText(str(j.get("Order No","")))
                self.tally_table.cellWidget(r,4).setValue(float(j.get("Joint Len",12.0)))
                self.tally_table.cellWidget(r,9).setCurrentText(str(j.get("Centralizers","Yes")))
                self.tally_table.cellWidget(r,10).setCurrentText(str(j.get("IN/OUT","IN")))
                self.tally_table.cellWidget(r,11).setText(str(j.get("Remarks","")))
            p=data.get("parameters",{})
            self.rt_depth.setValue(p.get("rt_depth",3000));self.mud_weight.setValue(p.get("mud_weight",65))
            self.calculate_tally()
        except Exception as e:logger.error(f"Load tally error: {e}")

    def load_tally_for_report(self,report_id):self.current_report_id=report_id;self.load_tally_report()
    def export_tally_data(self):ExportManager(self).export_table_with_dialog(self.tally_table,"casing_tally")
    def export_summary_report(self):
        fn,_=QFileDialog.getSaveFileName(self,"Export","tally_summary.txt","Text (*.txt)")
        if fn:
            with open(fn,"w",encoding="utf-8") as f:f.write(self.summary_text.toPlainText())
    def print_report(self):
        printer=QPrinter(QPrinter.HighResolution);dlg=QPrintDialog(printer,self)
        if dlg.exec()==QPrintDialog.Accepted:
            from PySide6.QtGui import QTextDocument
            doc=QTextDocument();doc.setHtml(f"<h1>Casing Tally</h1><pre>{self.summary_text.toPlainText()}</pre>");doc.print_(printer)

    def set_current_well(self,well_id,well_name=None):
        self.current_well=well_id;self.current_well_label.setText(f"Well: {well_name or well_id}");self.load_tally_report()


# ==================== 4. ServiceCompanyTab ====================
class ServiceCompanyTab(QWidget):
    """تب مدیریت شرکت‌های سرویس - section level"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.current_well_id = None
        self.current_report_id = None
        self.status_manager = StatusBarManager()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>🏢 Service Company Management</b>"))

        fl = QHBoxLayout()
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("Search...")
        self.search_input.textChanged.connect(self.filter_table)
        self.status_filter = QComboBox(); self.status_filter.addItems(["All","Active","Completed","Cancelled"])
        self.status_filter.currentTextChanged.connect(self.filter_table)
        fl.addWidget(self.search_input); fl.addWidget(self.status_filter); fl.addStretch()
        layout.addLayout(fl)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(["ID","Company","Service Type","Start","End","Contact","Phone","Email","Personnel","Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        bl = QHBoxLayout()
        for text, slot in [("➕ Add",self.add_company),("✏️ Edit",self.edit_company),("🗑️ Delete",self.delete_company),("🔄 Refresh",self.load_data),("📤 Export",self.export_data)]:
            b = QPushButton(text); b.clicked.connect(slot); bl.addWidget(b)
        bl.addStretch()
        layout.addLayout(bl)

        sl = QHBoxLayout()
        self.total_label = QLabel("Total: 0"); self.active_label = QLabel("Active: 0"); self.personnel_label = QLabel("Personnel: 0")
        sl.addWidget(self.total_label); sl.addWidget(self.active_label); sl.addWidget(self.personnel_label); sl.addStretch()
        layout.addLayout(sl)

    def set_current_well(self, well_id):
        self.current_well_id = well_id; self.load_data()

    def set_current_report(self, report_id):
        self.current_report_id = report_id

    def load_data(self):
        if not self.db or not self.current_well_id: self.table.setRowCount(0); return
        try:
            companies = self.db.get_service_companies(well_id=self.current_well_id, report_id=self.current_report_id)
            self.table.setRowCount(0); tp = ac = 0
            for c in companies:
                row = self.table.rowCount(); self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(str(c.get("id",""))))
                self.table.setItem(row, 1, QTableWidgetItem(c.get("company_name","")))
                self.table.setItem(row, 2, QTableWidgetItem(c.get("service_type","")))
                sd = c.get("start_datetime"); self.table.setItem(row, 3, QTableWidgetItem(str(sd) if sd else ""))
                ed = c.get("end_datetime"); self.table.setItem(row, 4, QTableWidgetItem(str(ed) if ed else ""))
                self.table.setItem(row, 5, QTableWidgetItem(c.get("contact_person","")))
                self.table.setItem(row, 6, QTableWidgetItem(c.get("contact_phone","")))
                self.table.setItem(row, 7, QTableWidgetItem(c.get("contact_email","")))
                p = c.get("personnel_count", 0); self.table.setItem(row, 8, QTableWidgetItem(str(p))); tp += p
                s = c.get("status",""); self.table.setItem(row, 9, QTableWidgetItem(s))
                if s == "Active": ac += 1
                cm = {"Active":"#d4edda","Completed":"#cce5ff","Cancelled":"#f8d7da"}.get(s)
                if cm:
                    for col in range(self.table.columnCount()):
                        it = self.table.item(row, col)
                        if it: it.setBackground(QColor(cm))
            self.total_label.setText(f"Total: {len(companies)}"); self.active_label.setText(f"Active: {ac}"); self.personnel_label.setText(f"Personnel: {tp}")
        except Exception as e: logger.error(f"Load service companies: {e}")

    def filter_table(self):
        st = self.search_input.text().lower(); sf = self.status_filter.currentText()
        for row in range(self.table.rowCount()):
            show = True
            if st:
                show = any(self.table.item(row,c) and st in self.table.item(row,c).text().lower() for c in range(self.table.columnCount()))
            if sf != "All":
                si = self.table.item(row, 9)
                if not si or si.text() != sf: show = False
            self.table.setRowHidden(row, not show)

    def add_company(self):
        if not self.current_well_id: QMessageBox.warning(self,"Warning","Select a well first"); return
        from dialogs.hierarchy_dialogs import BaseHierarchyDialog
        dlg = _ServiceCompanyDialog(self.db, self.current_well_id, self.current_report_id, self)
        if dlg.exec(): self.load_data()

    def edit_company(self):
        row = self.table.currentRow()
        if row < 0: return
        cid = int(self.table.item(row,0).text())
        dlg = _ServiceCompanyDialog(self.db, self.current_well_id, self.current_report_id, self, cid)
        if dlg.exec(): self.load_data()

    def delete_company(self):
        row = self.table.currentRow()
        if row < 0: return
        cid = int(self.table.item(row,0).text())
        if QMessageBox.question(self,"Delete","Delete this company?") == QMessageBox.Yes:
            if self.db.delete_service_company(cid): self.load_data()

    def export_data(self):
        ExportManager(self).export_table_with_dialog(self.table, "service_companies")


class _ServiceCompanyDialog(QDialog):
    """دیالوگ داخلی اضافه/ویرایش شرکت سرویس"""
    def __init__(self, db, well_id, report_id, parent=None, company_id=None):
        super().__init__(parent)
        self.db=db;self.well_id=well_id;self.report_id=report_id;self.company_id=company_id
        self.setWindowTitle("Service Company");self.setMinimumWidth(500)
        layout=QVBoxLayout(self);fl=QFormLayout()
        self.name_input=QLineEdit();fl.addRow("Company:",self.name_input)
        self.service_type=QComboBox();self.service_type.addItems(["Mud Logging","Wireline","Directional","Cementing","Casing","Mud Engineering","Well Testing","Other"]);self.service_type.setEditable(True);fl.addRow("Service:",self.service_type)
        self.contact=QLineEdit();fl.addRow("Contact:",self.contact)
        self.phone=QLineEdit();fl.addRow("Phone:",self.phone)
        self.email=QLineEdit();fl.addRow("Email:",self.email)
        self.personnel=QSpinBox();self.personnel.setRange(1,1000);fl.addRow("Personnel:",self.personnel)
        self.status=QComboBox();self.status.addItems(["Active","Completed","Cancelled"]);fl.addRow("Status:",self.status)
        self.description=QTextEdit();self.description.setMaximumHeight(80);fl.addRow("Description:",self.description)
        layout.addLayout(fl)
        bl=QHBoxLayout();sb=QPushButton("💾 Save");sb.clicked.connect(self._save);cb=QPushButton("Cancel");cb.clicked.connect(self.reject)
        bl.addStretch();bl.addWidget(sb);bl.addWidget(cb);layout.addLayout(bl)
        if company_id:self._load()

    def _load(self):
        cs=self.db.get_service_companies()
        c=next((x for x in cs if x.get("id")==self.company_id),None)
        if not c:return
        self.name_input.setText(c.get("company_name",""));self.contact.setText(c.get("contact_person",""))
        self.phone.setText(c.get("contact_phone",""));self.email.setText(c.get("contact_email",""))
        self.personnel.setValue(c.get("personnel_count",1));self.description.setText(c.get("description",""))
        for combo,key in [(self.service_type,"service_type"),(self.status,"status")]:
            idx=combo.findText(c.get(key,""));
            if idx>=0:combo.setCurrentIndex(idx)

    def _save(self):
        if not self.name_input.text().strip():QMessageBox.warning(self,"Error","Name required");return
        d={"well_id":self.well_id,"report_id":self.report_id,"company_name":self.name_input.text().strip(),"service_type":self.service_type.currentText(),"contact_person":self.contact.text(),"contact_phone":self.phone.text(),"contact_email":self.email.text(),"personnel_count":self.personnel.value(),"status":self.status.currentText(),"description":self.description.toPlainText()}
        if self.company_id:d["id"]=self.company_id
        if self.db.save_service_company(d):self.accept()

# ==================== 5. FailureReportTab ====================
class FailureReportTab(QWidget):
    """تب گزارش خرابی تجهیزات - section level"""

    CONDITION_OPTIONS = ["Repairable", "Need Service", "Damaged", "Scrapped", "Under Investigation"]
    FAILURE_LOCATIONS = ["In Site", "In Yard", "Transportation", "Workshop", "Storage"]
    CARRIER_TYPES = ["Truck", "Trailer", "Crane", "Forklift", "Ship", "Helicopter", "Other"]

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.parent = parent
        self.current_well = None
        self.current_section_id = None
        self.reports_list = []
        self.current_report_index = -1
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        cl = QVBoxLayout(content)

        # ===== Toolbar =====
        toolbar = QHBoxLayout()
        self.new_btn = QPushButton("📝 New Report")
        self.new_btn.setStyleSheet("background:#27ae60;color:white;font-weight:bold;padding:6px 12px;border-radius:3px;border:none;")
        self.new_btn.clicked.connect(self.new_report)
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setStyleSheet("background:#3498db;color:white;font-weight:bold;padding:6px 12px;border-radius:3px;border:none;")
        self.save_btn.clicked.connect(self.save_report)
        self.delete_btn = QPushButton("🗑️ Delete")
        self.delete_btn.clicked.connect(self.delete_report)
        self.export_btn = QPushButton("📤 Export PDF")
        self.export_btn.clicked.connect(self.export_pdf)
        self.print_btn = QPushButton("🖨️ Print")
        self.print_btn.clicked.connect(self.print_report)
        toolbar.addWidget(self.new_btn)
        toolbar.addWidget(self.save_btn)
        toolbar.addWidget(self.delete_btn)
        toolbar.addWidget(self.export_btn)
        toolbar.addWidget(self.print_btn)
        toolbar.addStretch()

        # Report selector
        toolbar.addWidget(QLabel("Report:"))
        self.report_selector = QComboBox()
        self.report_selector.setMinimumWidth(200)
        self.report_selector.currentIndexChanged.connect(self._on_report_selected)
        toolbar.addWidget(self.report_selector)
        cl.addLayout(toolbar)

        # ===== Header Section =====
        header_group = QGroupBox("📋 Equipment Failure Report Header")
        header_group.setStyleSheet("QGroupBox{font-weight:bold;color:#2c3e50;border:2px solid #e74c3c;border-radius:5px;margin-top:10px;padding-top:10px;}")
        hl = QGridLayout()

        hl.addWidget(QLabel("Damage Report No.:"), 0, 0)
        self.report_no = QLineEdit()
        self.report_no.setPlaceholderText("EFR-2024-001")
        hl.addWidget(self.report_no, 0, 1)

        hl.addWidget(QLabel("Date of Issue:"), 0, 2)
        self.issue_date = QDateEdit()
        self.issue_date.setDate(QDate.currentDate())
        self.issue_date.setCalendarPopup(True)
        hl.addWidget(self.issue_date, 0, 3)

        header_group.setLayout(hl)
        cl.addWidget(header_group)

        # ===== Location Section =====
        loc_group = QGroupBox("📍 Place of Occurred Failure/Damage")
        loc_layout = QVBoxLayout()

        # Location type radio buttons
        loc_type_layout = QHBoxLayout()
        self.loc_type_group = QButtonGroup()
        self.loc_radios = {}
        for loc in self.FAILURE_LOCATIONS:
            rb = QRadioButton(loc)
            self.loc_type_group.addButton(rb)
            self.loc_radios[loc] = rb
            loc_type_layout.addWidget(rb)
        self.loc_radios["In Site"].setChecked(True)
        loc_type_layout.addStretch()
        loc_layout.addLayout(loc_type_layout)

        # Location details grid
        loc_detail = QGridLayout()

        loc_detail.addWidget(QLabel("Project Name:"), 0, 0)
        self.loc_project = QLineEdit()
        loc_detail.addWidget(self.loc_project, 0, 1)

        loc_detail.addWidget(QLabel("Well Name:"), 0, 2)
        self.loc_well = QLineEdit()
        loc_detail.addWidget(self.loc_well, 0, 3)

        loc_detail.addWidget(QLabel("Yard Place:"), 1, 0)
        self.loc_yard = QLineEdit()
        loc_detail.addWidget(self.loc_yard, 1, 1)

        loc_detail.addWidget(QLabel("Carrier Type/No:"), 1, 2)
        self.loc_carrier = QComboBox()
        self.loc_carrier.addItems(self.CARRIER_TYPES)
        self.loc_carrier.setEditable(True)
        loc_detail.addWidget(self.loc_carrier, 1, 3)

        loc_detail.addWidget(QLabel("Carrier ID:"), 2, 0)
        self.carrier_id = QLineEdit()
        self.carrier_id.setPlaceholderText("e.g., TRK-2024-015")
        loc_detail.addWidget(self.carrier_id, 2, 1)

        loc_detail.addWidget(QLabel("Section/Area:"), 2, 2)
        self.loc_area = QLineEdit()
        self.loc_area.setPlaceholderText("e.g., Rig Floor, Mud Pit Area")
        loc_detail.addWidget(self.loc_area, 2, 3)

        loc_layout.addLayout(loc_detail)
        loc_group.setLayout(loc_layout)
        cl.addWidget(loc_group)

        # ===== Equipment/Material Table =====
        equip_group = QGroupBox("🔧 Damaged Equipment / Materials")
        equip_layout = QVBoxLayout()

        self.equip_table = QTableWidget(0, 7)
        self.equip_table.setHorizontalHeaderLabels([
            "No.", "Material Code", "Material P/N",
            "Description", "Qty", "Unit", "Condition"
        ])
        self.equip_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.equip_table.setColumnWidth(0, 40)
        self.equip_table.setColumnWidth(1, 120)
        self.equip_table.setColumnWidth(2, 120)
        self.equip_table.setColumnWidth(4, 60)
        self.equip_table.setColumnWidth(5, 70)
        self.equip_table.setColumnWidth(6, 130)
        self.equip_table.setAlternatingRowColors(True)
        equip_layout.addWidget(self.equip_table)

        eb = QHBoxLayout()
        add_equip = QPushButton("➕ Add Item")
        add_equip.clicked.connect(self.add_equipment_row)
        rem_equip = QPushButton("➖ Remove")
        rem_equip.clicked.connect(self.remove_equipment_row)
        eb.addWidget(add_equip)
        eb.addWidget(rem_equip)
        eb.addStretch()
        equip_layout.addLayout(eb)
        equip_group.setLayout(equip_layout)
        cl.addWidget(equip_group)

        # ===== Analysis Section =====
        analysis_group = QGroupBox("🔍 Failure Analysis")
        al = QVBoxLayout()

        al.addWidget(QLabel("Cause of Failure:"))
        self.cause_text = QTextEdit()
        self.cause_text.setMaximumHeight(100)
        self.cause_text.setPlaceholderText(
            "Describe the root cause of failure in detail...\n"
            "e.g., Material fatigue, improper handling, manufacturing defect..."
        )
        al.addWidget(self.cause_text)

        al.addWidget(QLabel("How could cause of failure be prevented:"))
        self.prevention_text = QTextEdit()
        self.prevention_text.setMaximumHeight(100)
        self.prevention_text.setPlaceholderText(
            "Describe preventive measures...\n"
            "e.g., Regular inspection, proper training, improved procedures..."
        )
        al.addWidget(self.prevention_text)

        al.addWidget(QLabel("Any personal injuries? If so, was accident report submitted:"))
        injury_layout = QHBoxLayout()
        self.injury_yes = QRadioButton("Yes")
        self.injury_no = QRadioButton("No")
        self.injury_no.setChecked(True)
        self.injury_group = QButtonGroup()
        self.injury_group.addButton(self.injury_yes)
        self.injury_group.addButton(self.injury_no)
        injury_layout.addWidget(self.injury_yes)
        injury_layout.addWidget(self.injury_no)
        injury_layout.addWidget(QLabel("Accident Report No:"))
        self.accident_report_no = QLineEdit()
        self.accident_report_no.setPlaceholderText("If applicable")
        self.accident_report_no.setEnabled(False)
        injury_layout.addWidget(self.accident_report_no)
        injury_layout.addStretch()
        al.addLayout(injury_layout)
        self.injury_yes.toggled.connect(lambda c: self.accident_report_no.setEnabled(c))

        self.injury_details = QTextEdit()
        self.injury_details.setMaximumHeight(60)
        self.injury_details.setPlaceholderText("Injury details if applicable...")
        al.addWidget(self.injury_details)

        analysis_group.setLayout(al)
        cl.addWidget(analysis_group)

        # ===== Recommendations =====
        rec_group = QGroupBox("📝 Recommendation / Remarks")
        rl = QVBoxLayout()
        self.recommendation_text = QTextEdit()
        self.recommendation_text.setMaximumHeight(100)
        self.recommendation_text.setPlaceholderText(
            "Enter recommendations, follow-up actions, remarks..."
        )
        rl.addWidget(self.recommendation_text)
        rec_group.setLayout(rl)
        cl.addWidget(rec_group)

        # ===== Signatures =====
        sig_group = QGroupBox("✍️ Signatures")
        sig_layout = QGridLayout()

        sig_layout.addWidget(QLabel("<b>Filled By:</b>"), 0, 0, 1, 2)
        sig_layout.addWidget(QLabel("<b>Approved By:</b>"), 0, 2, 1, 2)

        sig_layout.addWidget(QLabel("Name:"), 1, 0)
        self.filled_by_name = QLineEdit()
        sig_layout.addWidget(self.filled_by_name, 1, 1)

        sig_layout.addWidget(QLabel("Name:"), 1, 2)
        self.approved_by_name = QLineEdit()
        sig_layout.addWidget(self.approved_by_name, 1, 3)

        sig_layout.addWidget(QLabel("Position:"), 2, 0)
        self.filled_by_position = QLineEdit()
        sig_layout.addWidget(self.filled_by_position, 2, 1)

        sig_layout.addWidget(QLabel("Position:"), 2, 2)
        self.approved_by_position = QLineEdit()
        sig_layout.addWidget(self.approved_by_position, 2, 3)

        sig_layout.addWidget(QLabel("Date:"), 3, 0)
        self.filled_date = QDateEdit()
        self.filled_date.setDate(QDate.currentDate())
        self.filled_date.setCalendarPopup(True)
        sig_layout.addWidget(self.filled_date, 3, 1)

        sig_layout.addWidget(QLabel("Date:"), 3, 2)
        self.approved_date = QDateEdit()
        self.approved_date.setDate(QDate.currentDate())
        self.approved_date.setCalendarPopup(True)
        sig_layout.addWidget(self.approved_date, 3, 3)

        sig_group.setLayout(sig_layout)
        cl.addWidget(sig_group)

        cl.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

    # ==================== Equipment Table ====================
    def add_equipment_row(self, data=None):
        row = self.equip_table.rowCount()
        self.equip_table.insertRow(row)

        no_item = QTableWidgetItem(str(row + 1))
        no_item.setTextAlignment(Qt.AlignCenter)
        no_item.setFlags(Qt.ItemIsEnabled)
        self.equip_table.setItem(row, 0, no_item)

        if data:
            self.equip_table.setItem(row, 1, QTableWidgetItem(str(data.get("material_code", ""))))
            self.equip_table.setItem(row, 2, QTableWidgetItem(str(data.get("part_number", ""))))
            self.equip_table.setItem(row, 3, QTableWidgetItem(str(data.get("description", ""))))
            qty_sp = QSpinBox(); qty_sp.setRange(0, 9999); qty_sp.setValue(int(data.get("qty", 1)))
            self.equip_table.setCellWidget(row, 4, qty_sp)
            unit_combo = QComboBox(); unit_combo.addItems(["pcs", "sets", "m", "ft", "kg", "lb", "ea"])
            unit_combo.setCurrentText(str(data.get("unit", "pcs")))
            self.equip_table.setCellWidget(row, 5, unit_combo)
            cond_combo = QComboBox(); cond_combo.addItems(self.CONDITION_OPTIONS)
            cond_combo.setCurrentText(str(data.get("condition", "Repairable")))
            self.equip_table.setCellWidget(row, 6, cond_combo)
        else:
            self.equip_table.setItem(row, 1, QTableWidgetItem(""))
            self.equip_table.setItem(row, 2, QTableWidgetItem(""))
            self.equip_table.setItem(row, 3, QTableWidgetItem(""))
            qty_sp = QSpinBox(); qty_sp.setRange(0, 9999); qty_sp.setValue(1)
            self.equip_table.setCellWidget(row, 4, qty_sp)
            unit_combo = QComboBox(); unit_combo.addItems(["pcs", "sets", "m", "ft", "kg", "lb", "ea"])
            self.equip_table.setCellWidget(row, 5, unit_combo)
            cond_combo = QComboBox(); cond_combo.addItems(self.CONDITION_OPTIONS)
            self.equip_table.setCellWidget(row, 6, cond_combo)

    def remove_equipment_row(self):
        row = self.equip_table.currentRow()
        if row >= 0:
            self.equip_table.removeRow(row)
            self._renumber_rows()

    def _renumber_rows(self):
        for row in range(self.equip_table.rowCount()):
            item = self.equip_table.item(row, 0)
            if item:
                item.setText(str(row + 1))

    # ==================== Data Operations ====================
    def _collect_data(self):
        loc_type = ""
        for name, rb in self.loc_radios.items():
            if rb.isChecked():
                loc_type = name
                break

        equipment = []
        for row in range(self.equip_table.rowCount()):
            equipment.append({
                "material_code": self.equip_table.item(row, 1).text() if self.equip_table.item(row, 1) else "",
                "part_number": self.equip_table.item(row, 2).text() if self.equip_table.item(row, 2) else "",
                "description": self.equip_table.item(row, 3).text() if self.equip_table.item(row, 3) else "",
                "qty": self.equip_table.cellWidget(row, 4).value() if self.equip_table.cellWidget(row, 4) else 1,
                "unit": self.equip_table.cellWidget(row, 5).currentText() if self.equip_table.cellWidget(row, 5) else "pcs",
                "condition": self.equip_table.cellWidget(row, 6).currentText() if self.equip_table.cellWidget(row, 6) else "Repairable",
            })

        return {
            "report_no": self.report_no.text(),
            "issue_date": self.issue_date.date().toString("yyyy-MM-dd"),
            "location_type": loc_type,
            "project_name": self.loc_project.text(),
            "well_name": self.loc_well.text(),
            "yard_place": self.loc_yard.text(),
            "carrier_type": self.loc_carrier.currentText(),
            "carrier_id": self.carrier_id.text(),
            "area": self.loc_area.text(),
            "equipment": equipment,
            "cause": self.cause_text.toPlainText(),
            "prevention": self.prevention_text.toPlainText(),
            "has_injury": self.injury_yes.isChecked(),
            "accident_report_no": self.accident_report_no.text(),
            "injury_details": self.injury_details.toPlainText(),
            "recommendation": self.recommendation_text.toPlainText(),
            "filled_by": self.filled_by_name.text(),
            "filled_position": self.filled_by_position.text(),
            "filled_date": self.filled_date.date().toString("yyyy-MM-dd"),
            "approved_by": self.approved_by_name.text(),
            "approved_position": self.approved_by_position.text(),
            "approved_date": self.approved_date.date().toString("yyyy-MM-dd"),
        }

    def _load_data(self, data):
        self.report_no.setText(data.get("report_no", ""))
        try:
            self.issue_date.setDate(QDate.fromString(data.get("issue_date", ""), "yyyy-MM-dd"))
        except: pass

        loc = data.get("location_type", "In Site")
        if loc in self.loc_radios:
            self.loc_radios[loc].setChecked(True)

        self.loc_project.setText(data.get("project_name", ""))
        self.loc_well.setText(data.get("well_name", ""))
        self.loc_yard.setText(data.get("yard_place", ""))
        self.loc_carrier.setCurrentText(data.get("carrier_type", ""))
        self.carrier_id.setText(data.get("carrier_id", ""))
        self.loc_area.setText(data.get("area", ""))

        self.equip_table.setRowCount(0)
        for eq in data.get("equipment", []):
            self.add_equipment_row(eq)

        self.cause_text.setPlainText(data.get("cause", ""))
        self.prevention_text.setPlainText(data.get("prevention", ""))
        self.injury_yes.setChecked(data.get("has_injury", False))
        self.injury_no.setChecked(not data.get("has_injury", False))
        self.accident_report_no.setText(data.get("accident_report_no", ""))
        self.injury_details.setPlainText(data.get("injury_details", ""))
        self.recommendation_text.setPlainText(data.get("recommendation", ""))
        self.filled_by_name.setText(data.get("filled_by", ""))
        self.filled_by_position.setText(data.get("filled_position", ""))
        self.approved_by_name.setText(data.get("approved_by", ""))
        self.approved_by_position.setText(data.get("approved_position", ""))

    def clear_form(self):
        self.report_no.clear()
        self.issue_date.setDate(QDate.currentDate())
        self.loc_radios["In Site"].setChecked(True)
        self.loc_project.clear(); self.loc_well.clear()
        self.loc_yard.clear(); self.carrier_id.clear(); self.loc_area.clear()
        self.equip_table.setRowCount(0)
        self.cause_text.clear(); self.prevention_text.clear()
        self.injury_no.setChecked(True)
        self.accident_report_no.clear(); self.injury_details.clear()
        self.recommendation_text.clear()
        self.filled_by_name.clear(); self.filled_by_position.clear()
        self.approved_by_name.clear(); self.approved_by_position.clear()

    # ==================== Save/Load (JSON in DailyReport.equipment_data) ====================
    def new_report(self):
        self.clear_form()
        count = self.report_selector.count()
        self.report_no.setText(f"EFR-{datetime.now().strftime('%Y')}-{count+1:03d}")
        if self.current_well and self.db_manager:
            well = self.db_manager.get_well_by_id(self.current_well)
            if well:
                self.loc_well.setText(well.get("name", ""))
                self.loc_project.setText(well.get("project_name", ""))

    def save_report(self):
        if not self.current_well:
            QMessageBox.warning(self, "Warning", "Select a well first")
            return False
        data = self._collect_data()
        if not data["report_no"]:
            QMessageBox.warning(self, "Warning", "Report number is required")
            return False

        idx = self.report_selector.currentIndex()
        if idx >= 0 and idx < len(self.reports_list):
            self.reports_list[idx] = data
        else:
            self.reports_list.append(data)

        self._save_all_to_db()
        self._refresh_selector()
        QMessageBox.information(self, "Saved", f"Failure Report {data['report_no']} saved")
        return True

    def delete_report(self):
        idx = self.report_selector.currentIndex()
        if idx < 0 or idx >= len(self.reports_list):
            return
        if QMessageBox.question(self, "Delete", "Delete this report?") == QMessageBox.Yes:
            self.reports_list.pop(idx)
            self._save_all_to_db()
            self._refresh_selector()
            self.clear_form()

    def _save_all_to_db(self):
        """ذخیره لیست reports به عنوان JSON"""
        if not self.db_manager or not self.current_well:
            return
        try:
            from core.database import EquipmentLog
            session = self.db_manager.create_session()
            existing = session.query(EquipmentLog).filter(
                EquipmentLog.well_id == self.current_well,
                EquipmentLog.equipment_type == "FAILURE_REPORTS"
            ).first()
            reports_json = json.dumps(self.reports_list, default=str)
            if existing:
                existing.notes = reports_json
                existing.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            else:
                new = EquipmentLog(
                    well_id=self.current_well,
                    equipment_type="FAILURE_REPORTS",
                    equipment_name="Failure Reports Storage",
                    notes=reports_json,
                    status="Active"
                )
                session.add(new)
            session.commit()
            session.close()
        except Exception as e:
            logger.error(f"Save failure reports error: {e}")

    def _load_from_db(self):
        if not self.db_manager or not self.current_well:
            return
        try:
            from core.database import EquipmentLog
            session = self.db_manager.create_session()
            existing = session.query(EquipmentLog).filter(
                EquipmentLog.well_id == self.current_well,
                EquipmentLog.equipment_type == "FAILURE_REPORTS"
            ).first()
            if existing and existing.notes:
                self.reports_list = json.loads(existing.notes)
            else:
                self.reports_list = []
            session.close()
            self._refresh_selector()
        except Exception as e:
            logger.error(f"Load failure reports error: {e}")
            self.reports_list = []

    def _refresh_selector(self):
        self.report_selector.blockSignals(True)
        self.report_selector.clear()
        for i, r in enumerate(self.reports_list):
            self.report_selector.addItem(
                f"{r.get('report_no', f'Report {i+1}')} - {r.get('issue_date', '')}"
            )
        self.report_selector.blockSignals(False)

    def _on_report_selected(self, index):
        if 0 <= index < len(self.reports_list):
            self._load_data(self.reports_list[index])
            self.current_report_index = index

    # ==================== Export/Print ====================
    def export_pdf(self):
        data = self._collect_data()
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Failure Report",
            f"EFR_{data['report_no']}_{data['issue_date']}.pdf",
            "PDF (*.pdf);;HTML (*.html)"
        )
        if not filename:
            return
        html = self._build_html(data)
        if filename.endswith('.html'):
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html)
        else:
            from PySide6.QtGui import QTextDocument
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(filename)
            printer.setPageSize(QPrinter.A4)
            doc = QTextDocument()
            doc.setHtml(html)
            doc.print_(printer)
        QMessageBox.information(self, "Exported", f"Saved: {filename}")

    def print_report(self):
        data = self._collect_data()
        html = self._build_html(data)
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QPrintDialog.Accepted:
            from PySide6.QtGui import QTextDocument
            doc = QTextDocument()
            doc.setHtml(html)
            doc.print_(printer)

    def _build_html(self, data):
        equip_rows = ""
        for i, eq in enumerate(data.get("equipment", [])):
            cond = eq.get("condition", "")
            cond_color = "#e74c3c" if cond == "Damaged" else "#f39c12" if cond == "Need Service" else "#27ae60"
            equip_rows += f"""<tr>
                <td align="center">{i+1}</td>
                <td>{eq.get('material_code','')}</td>
                <td>{eq.get('part_number','')}</td>
                <td>{eq.get('description','')}</td>
                <td align="center">{eq.get('qty',1)}</td>
                <td align="center">{eq.get('unit','pcs')}</td>
                <td style="color:{cond_color};font-weight:bold">{cond}</td>
            </tr>"""

        injury = "Yes" if data.get("has_injury") else "No"

        return f"""<html><head><style>
        body{{font-family:Arial;font-size:10pt;margin:20px;color:#2c3e50;}}
        h1{{color:#e74c3c;font-size:16pt;text-align:center;border-bottom:3px solid #e74c3c;}}
        h2{{color:#2c3e50;font-size:12pt;margin-top:15px;border-bottom:1px solid #bdc3c7;}}
        .ht{{width:100%;border-collapse:collapse;margin:8px 0;}}
        .ht td,.ht th{{padding:5px 8px;border:1px solid #bdc3c7;font-size:9pt;}}
        .ht th{{background:#2c3e50;color:white;}}
        .info-table td{{padding:4px 8px;border:1px solid #ddd;}}
        .sig-table{{width:100%;border-collapse:collapse;margin-top:20px;}}
        .sig-table td{{padding:15px;border:1px solid #ddd;text-align:center;width:50%;}}
        </style></head><body>
        <h1>⚠️ EQUIPMENT FAILURE REPORT</h1>
        <table class="info-table" width="100%">
        <tr><td><b>Report No:</b> {data.get('report_no','')}</td>
            <td><b>Date:</b> {data.get('issue_date','')}</td></tr>
        <tr><td><b>Location:</b> {data.get('location_type','')}</td>
            <td><b>Area:</b> {data.get('area','')}</td></tr>
        <tr><td><b>Project:</b> {data.get('project_name','')}</td>
            <td><b>Well:</b> {data.get('well_name','')}</td></tr>
        <tr><td><b>Yard:</b> {data.get('yard_place','')}</td>
            <td><b>Carrier:</b> {data.get('carrier_type','')} {data.get('carrier_id','')}</td></tr>
        </table>
        <h2>🔧 Damaged Equipment</h2>
        <table class="ht"><tr><th>No.</th><th>Code</th><th>P/N</th><th>Description</th><th>Qty</th><th>Unit</th><th>Condition</th></tr>
        {equip_rows}</table>
        <h2>🔍 Cause of Failure</h2><p>{wrap_html(data.get('cause',''))}</p>
        <h2>🛡️ Prevention</h2><p>{wrap_html(data.get('prevention',''))}</p>
        <h2>🏥 Personal Injuries</h2><p>{injury}{' - Report: '+data.get('accident_report_no','') if data.get('has_injury') else ''}</p>
        {('<p>'+data.get('injury_details','').replace(chr(10),'<br>')+'</p>') if data.get('injury_details') else ''}
        <h2>📝 Recommendations</h2><p>{wrap_html(data.get('recommendation',''))}</p>
        <table class="sig-table">
        <tr><td><b>Filled By</b></td><td><b>Approved By</b></td></tr>
        <tr><td>{data.get('filled_by','')}<br><small>{data.get('filled_position','')}</small><br>{data.get('filled_date','')}</td>
            <td>{data.get('approved_by','')}<br><small>{data.get('approved_position','')}</small><br>{data.get('approved_date','')}</td></tr>
        </table>
        <hr><p style="text-align:center;color:#999;font-size:8pt;">DrillMaster | {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        </body></html>"""

    def _wrap_html(self, text, width=80):
        """Wrap متن بلند برای HTML"""
        import textwrap
        if not text:
            return ""
        lines = []
        for paragraph in str(text).splitlines():
            if not paragraph.strip():
                lines.append("")
                continue
            lines.extend(textwrap.wrap(paragraph, width=width, break_long_words=False))
        return "<br>".join(lines)
        
    def load_data(self):
        self._load_from_db()

    def refresh(self):
        self._load_from_db()


# ==================== 6. BitRecordTab ====================
class BitRecordTab(QWidget):
    """تب Bit Record - section level"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.parent = parent
        self.current_well = None
        self.current_section_id = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Toolbar
        bl = QHBoxLayout()
        add_btn = QPushButton("➕ Add Bit")
        add_btn.setStyleSheet("background:#27ae60;color:white;padding:4px 10px;border-radius:3px;border:none;")
        add_btn.clicked.connect(self.add_bit)
        rem_btn = QPushButton("➖ Remove")
        rem_btn.clicked.connect(self.remove_bit)
        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self.save_data)
        export_btn = QPushButton("📤 Export")
        export_btn.clicked.connect(self.export_data)
        bl.addWidget(add_btn)
        bl.addWidget(rem_btn)
        bl.addWidget(save_btn)
        bl.addWidget(export_btn)
        bl.addStretch()
        layout.addLayout(bl)

        # Table
        self.headers = [
            "Bit No", "Size (in)", "Manufacture", "BHA No",
            "Type", "IADC Code", "Serial No", "Jets", "CMT",
            "Depth In (m)", "Depth Out (m)", "Formation",
            "Metres Drilled", "Hours", "ROP (m/hr)",
            "WOB Min (klb)", "WOB Max (klb)",
            "Rot. Min", "Rot. Max",
            "SPP Min (psi)", "SPP Max (psi)",
            "FR Min", "FR Max",
            "TQ Min (klb.ft)", "TQ Max (klb.ft)",
            "MW (pcf)", "TFA (in²)",
            "Dull Grade", "Reason Pulled", "Remarks"
        ]
        self.bit_table = QTableWidget(0, len(self.headers))
        self.bit_table.setHorizontalHeaderLabels(self.headers)
        self.bit_table.setAlternatingRowColors(True)
        self.bit_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.bit_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive
        )
        for col in range(len(self.headers)):
            self.bit_table.setColumnWidth(col, 90)
        layout.addWidget(self.bit_table)

    def add_bit(self):
        from dialogs.drilling_report_dialogs import AddBitRecordDialog
        bit_number = self.bit_table.rowCount() + 1
        dlg = AddBitRecordDialog(self, bit_number=bit_number)
        if dlg.exec():
            data = dlg.get_result()
            if data:
                row = self.bit_table.rowCount()
                self.bit_table.insertRow(row)
                for col, header in enumerate(self.headers):
                    val = data.get(header, "")
                    item = QTableWidgetItem(str(val))
                    item.setTextAlignment(Qt.AlignCenter)
                    self.bit_table.setItem(row, col, item)

    def remove_bit(self):
        row = self.bit_table.currentRow()
        if row >= 0:
            self.bit_table.removeRow(row)

    def save_data(self):
        if not self.current_well or not self.db_manager:
            return False
        records = self._get_all_data()
        if not records:
            return True
        import json
        data = {
            "report_date": date.today(),
            "report_name": f"Bit Report {date.today()}",
            "bit_records_json": records,
        }
        result = self.db_manager.save_bit_report(self.current_well, data)
        return result is not None

    def load_data(self):
        if not self.current_well or not self.db_manager:
            return
        report = self.db_manager.get_bit_report(well_id=self.current_well)
        self.bit_table.setRowCount(0)
        if not report or not report.get("bit_records_json"):
            return
        try:
            import json
            records = report["bit_records_json"]
            if isinstance(records, str):
                records = json.loads(records)
            for rec in records:
                row = self.bit_table.rowCount()
                self.bit_table.insertRow(row)
                for col, header in enumerate(self.headers):
                    val = rec.get(header, "")
                    item = QTableWidgetItem(str(val))
                    item.setTextAlignment(Qt.AlignCenter)
                    self.bit_table.setItem(row, col, item)
        except Exception as e:
            logger.error(f"Load bit record error: {e}")

    def export_data(self):
        from core.managers import ExportManager
        ExportManager(self).export_table_with_dialog(
            self.bit_table, "bit_record"
        )

    def _get_all_data(self):
        data = []
        for row in range(self.bit_table.rowCount()):
            row_data = {}
            for col, header in enumerate(self.headers):
                item = self.bit_table.item(row, col)
                row_data[header] = item.text() if item else ""
            data.append(row_data)
        return data

    def clear_form(self):
        self.bit_table.setRowCount(0)

    def refresh(self):
        self.load_data()
        
# ==================== 5. SectionDataWidget (Main) ====================
class SectionDataWidget(DrillTabBase):
    """تب اصلی Section Data"""

    def __init__(self, db_manager=None, parent=None):
        super().__init__("SectionDataWidget", db_manager, parent)
        self.current_well_id = None
        self.current_section_id = None
        self._tabs_ready = False

        try:
            self.cement_tab = CementReportTab(self.db, self)
            self.casing_tab = CasingReportTab(self.db, self)
            self.casing_tally_tab = CasingTallyWidget(self.db, self)
            self.service_company_tab = ServiceCompanyTab(self.db, self)
            self.failure_tab = FailureReportTab(self.db, self)
            self.bit_tab = BitRecordTab(self.db, self)
            self._tabs_ready = True
        except Exception as e:
            logger.error(f"Section sub-tabs error: {e}")

        self.init_ui()
    def init_ui(self):
        layout = QVBoxLayout(self)
        header = QWidget()
        header.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #8e44ad,stop:1 #9b59b6);border-radius:4px;")
        header.setMaximumHeight(45)
        hl = QHBoxLayout(header); hl.setContentsMargins(10,5,10,5)
        hl.addWidget(QLabel("<span style='color:white;font-size:14px;font-weight:bold'>📐 Section Data</span>"))
        hl.addWidget(QLabel("<span style='color:#d2b4de'>Section:</span>"))
        self.section_combo = QComboBox(); self.section_combo.setMinimumWidth(250)
        self.section_combo.setStyleSheet("background:#7d3c98;color:white;padding:4px;border-radius:3px;")
        self.section_combo.currentIndexChanged.connect(self._on_combo_changed)
        hl.addWidget(self.section_combo)
        self.section_info = QLabel(""); self.section_info.setStyleSheet("color:#d2b4de;font-size:11px;")
        hl.addWidget(self.section_info); hl.addStretch()
        sb = QPushButton("💾 Save Section Data")
        sb.setStyleSheet("background:#27ae60;color:white;font-weight:bold;padding:6px 14px;border-radius:3px;border:none;")
        sb.clicked.connect(self.save_data); hl.addWidget(sb)
        layout.addWidget(header)

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.cement_tab, "🏗️ Cement Report")
        self.tab_widget.addTab(self.casing_tally_tab, "📏 Casing Tally")
        self.tab_widget.addTab(self.casing_tab, "🔩 Casing Report")
        self.tab_widget.addTab(self.service_company_tab, "🏢 Service Companies")
        self.tab_widget.addTab(self.failure_tab, "⚠️ Failure Report")
        self.tab_widget.addTab(self.bit_tab, "🧱 Bit Record")
        layout.addWidget(self.tab_widget)

    def on_well_changed(self, well_id, well_data):
        self.current_well_id = well_id
        self._load_sections(well_id)
        if not self._tabs_ready:
            return
        for t in [self.cement_tab, self.casing_tab, self.casing_tally_tab]:
            if hasattr(t, 'current_well'):
                t.current_well = well_id
        self.service_company_tab.set_current_well(well_id)
        self.failure_tab.current_well = well_id
        self.bit_tab.current_well = well_id
        
    def on_section_changed(self, section_id, section_data):
        self.current_section_id = section_id
        self.section_combo.blockSignals(True)
        for i in range(self.section_combo.count()):
            if self.section_combo.itemData(i) == section_id:
                self.section_combo.setCurrentIndex(i)
                break
        self.section_combo.blockSignals(False)
        if section_data and isinstance(section_data, dict):
            self.section_info.setText(
                f"{section_data.get('name', '')} | "
                f"{section_data.get('depth_from', 0):.0f}-"
                f"{section_data.get('depth_to', 0):.0f} m"
            )
        self._load_section_data(section_id)
        
    def _on_combo_changed(self, index):
        sid = self.section_combo.currentData()
        if sid and sid != self.current_section_id:
            self.current_section_id = sid
            if self.db and self.current_well_id:
                ss = self.db.get_sections_by_well(self.current_well_id)
                sd = next((s for s in ss if s['id']==sid),{})
                self.sel_manager.select_section(sid, sd)
            self._load_section_data(sid)

    def _load_sections(self, well_id):
        self.section_combo.blockSignals(True)
        self.section_combo.clear()
        self.section_combo.addItem("-- Select Section --", None)
        if self.db and well_id:
            for s in self.db.get_sections_by_well(well_id):
                d = f"{s['name']}"
                if s.get('code'): d += f" ({s['code']})"
                d += f" | {s.get('depth_from',0):.0f}-{s.get('depth_to',0):.0f} m"
                self.section_combo.addItem(d, s['id'])
        self.section_combo.blockSignals(False)
        
    def _load_section_data(self, section_id):
        if not section_id or not self.current_well_id:
            return
        if not self._tabs_ready:
            return

        # Cement
        self.cement_tab.current_well = self.current_well_id
        self.cement_tab.load_data()

        # Casing
        self.casing_tab.current_well = self.current_well_id
        self.casing_tab.load_data()

        # Tally
        self.casing_tally_tab.current_well = self.current_well_id
        self.casing_tally_tab.load_tally_report()

        # Service Companies
        self.service_company_tab.set_current_well(self.current_well_id)

        # Failure Report
        self.failure_tab.current_well = self.current_well_id
        self.failure_tab.current_section_id = section_id
        self.failure_tab._load_from_db()

        # Bit Record
        self.bit_tab.current_well = self.current_well_id
        self.bit_tab.current_section_id = section_id
        self.bit_tab.load_data()
        
    def save_data(self):
        if not self.current_well_id:
            self.show_error("Select a well")
            return False
        if not self._tabs_ready:
            return False
        saved = 0
        for tab, method in [
            (self.cement_tab, 'save_data'),
            (self.casing_tab, 'save_data'),
            (self.casing_tally_tab, 'save_tally_report'),
            (self.bit_tab, 'save_data'),
        ]:
            try:
                if hasattr(tab, method):
                    r = getattr(tab, method)()
                    if r:
                        saved += 1
            except Exception as e:
                logger.error(f"Save error: {e}")
        self.show_success(f"Saved ({saved} tabs)")
        return saved > 0
        
    def refresh(self):
        if self.current_section_id:
            self._load_section_data(self.current_section_id)