"""
Database - SQLAlchemy ORM setup and DatabaseManager class
"""
import random
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple
from datetime import date as DateType

from pathlib import Path

def _now_utc() -> datetime:
    """برگرداندن زمان UTC بدون tzinfo (برای SQLite سازگاری)"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
    
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Date,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
    Text,
    Time,
)
from sqlalchemy.orm import sessionmaker, relationship, Session, declarative_base, backref
from sqlalchemy.pool import StaticPool
import json

import hashlib
import os
import secrets
try:
    import bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    _BCRYPT_AVAILABLE = False
    import logging
    logging.getLogger(__name__).warning(
        "bcrypt not installed. Using SHA-256 (less secure). "
        "Install with: pip install bcrypt"
    )

from contextlib import contextmanager
logger = logging.getLogger(__name__)

Base = declarative_base()
# ==================== Constants ====================
class DBConstants:
    """ثابت‌های دیتابیس"""
    # Backup
    MAX_BACKUP_FILES = 10
    
    # Audit
    MAX_AUDIT_DETAILS_LENGTH = 500
    
    # Search
    MIN_SEARCH_LENGTH = 2
    MAX_SEARCH_RESULTS = 50
    MAX_SEARCH_PER_TABLE = 10
    
    # Report
    MAX_REPORT_SUMMARY_TRUNCATE = 100
    MAX_RECENT_REPORTS = 50
    
    # Cache
    HIERARCHY_CACHE_TTL = 30.0  # ثانیه
    
class AuditLog(Base):
    """ثبت تغییرات کاربران"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String(50))
    action = Column(String(50), nullable=False)  # create, update, delete, login, logout
    entity_type = Column(String(50))  # well, report, section, ...
    entity_id = Column(Integer)
    entity_name = Column(String(200))
    details = Column(Text)
    ip_address = Column(String(50))
    timestamp = Column(DateTime, default=_now_utc)

    user = relationship("User", backref="audit_logs")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100))
    email = Column(String(100))
    role = Column(String(50), default="user")  # admin, manager, engineer, viewer
    department = Column(String(100))
    phone = Column(String(50))
    is_active = Column(Boolean, default=True)
    permissions = Column(JSON, nullable=True)  # اضافه شد
    created_at = Column(DateTime, default=_now_utc)
    last_login = Column(DateTime)
    
class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    code = Column(String(50), unique=True)
    address = Column(Text)
    contact_person = Column(String(100))
    contact_email = Column(String(100))
    contact_phone = Column(String(50))
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)

    projects = relationship(
        "Project", back_populates="company", cascade="all, delete-orphan"
    )


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    company_id = Column(
        Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(100), nullable=False)
    code = Column(String(50), unique=True)
    location = Column(Text)
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(50), default="Active")
    manager = Column(String(100))
    budget = Column(Float, default=0.0)
    currency = Column(String(10), default="USD")
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)

    company = relationship("Company", back_populates="projects")
    wells = relationship("Well", back_populates="project", cascade="all, delete-orphan")


class Well(Base):
    __tablename__ = "wells"

    id = Column(Integer, primary_key=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(100), nullable=False)
    code = Column(String(50), unique=True)
    field_name = Column(String(100))
    location = Column(Text)
    coordinates = Column(String(100))
    elevation = Column(Float, default=0.0)
    water_depth = Column(Float, default=0.0)
    spud_date = Column(Date)
    target_depth = Column(Float, default=0.0)
    status = Column(String(50), default="Planning")
    well_type = Column(String(50))
    purpose = Column(String(100))
    well_type_field = Column(String(50), default="Onshore")
    section_name = Column(String(100))
    client = Column(String(100))
    client_rep = Column(String(100))
    operator = Column(String(100))
    project_name = Column(String(100))
    rig_name = Column(String(100))
    drilling_contractor = Column(String(100))
    report_no = Column(String(100))
    rig_type = Column(String(50))
    well_shape = Column(String(50))
    gle_msl = Column(Float)
    rte_msl = Column(Float)
    gle_rte = Column(Float)
    estimated_final_depth = Column(Float)
    derrick_height = Column(Integer)
    lta_day = Column(Integer)
    actual_rig_days = Column(Integer)
    rig_heading = Column(Float)
    kop1 = Column(Float)
    kop2 = Column(Float)
    formation = Column(String(100))
    latitude = Column(Float)
    longitude = Column(Float)
    northing = Column(Float)
    easting = Column(Float)
    start_hole_date = Column(Date)
    rig_move_date = Column(Date)
    report_date = Column(Date)
    operation_manager = Column(String(100))
    superintendent = Column(String(100))
    supervisor_day = Column(String(100))
    supervisor_night = Column(String(100))
    geologist1 = Column(String(100))
    geologist2 = Column(String(100))
    tool_pusher_day = Column(String(100))
    tool_pusher_night = Column(String(100))
    objectives = Column(Text)

    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)

    project = relationship("Project", back_populates="wells")
    sections = relationship(
        "Section", back_populates="well", cascade="all, delete-orphan"
    )
    daily_reports = relationship(
        "DailyReport", back_populates="well", cascade="all, delete-orphan"
    )


class Section(Base):
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    code = Column(String(50))
    depth_from = Column(Float, default=0.0)
    depth_to = Column(Float, default=0.0)
    diameter = Column(Float)
    hole_size = Column(Float)
    purpose = Column(String(100))
    description = Column(Text)
    planned_days = Column(Float, default=0.0)  
    planned_rop = Column(Float, default=50.0)  
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)

    well = relationship("Well", back_populates="sections")
    daily_reports = relationship("DailyReport", back_populates="section", cascade="all, delete-orphan")

class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True)
    well_id = Column(
        Integer, ForeignKey("wells.id", ondelete="CASCADE"), nullable=False
    )
    section_id = Column(
        Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=True
    )
    report_date = Column(Date, nullable=False)
    report_number = Column(Integer, default=1)
    rig_day = Column(Integer, default=1)
    report_title = Column(String(200))
    depth_0000 = Column(Float, default=0.0)
    depth_0600 = Column(Float, default=0.0)
    depth_2400 = Column(Float, default=0.0)
    summary = Column(Text)
    status = Column(String(50), default="Draft")
    rop_meter = Column(Float, default=0.0)
    wob = Column(Float, default=0.0)
    rpm = Column(Float, default=0.0)
    torque = Column(Float, default=0.0)
    pressure = Column(Float, default=0.0)
    mud_weight_in = Column(Float, default=0.0)
    mud_weight_out = Column(Float, default=0.0)
    bit_number = Column(String(50))
    equipment_data = Column(JSON, nullable=True)
    header_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))


    well = relationship("Well", back_populates="daily_reports")
    section = relationship("Section", back_populates="daily_reports")
    creator = relationship("User", foreign_keys=[created_by])
    time_logs_24h = relationship(
        "TimeLog24H", back_populates="report", cascade="all, delete-orphan"
    )
    time_logs_morning = relationship(
        "TimeLogMorning", back_populates="report", cascade="all, delete-orphan"
    )

class ReportRevision(Base):
    """Immutable snapshot of a daily report for audit/version history."""
    __tablename__ = "report_revisions"
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=False)
    revision_no = Column(Integer, nullable=False)
    status = Column(String(30), default="Draft", nullable=False)
    snapshot = Column(JSON, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=_now_utc, nullable=False)
    comment = Column(Text)


class ApprovalAction(Base):
    """Approval/rejection history; never overwrite actions."""
    __tablename__ = "approval_actions"
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(20), nullable=False)  # submit, approve, reject
    status = Column(String(30), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    comment = Column(Text)
    created_at = Column(DateTime, default=_now_utc, nullable=False)


class TimeLog24H(Base):
    __tablename__ = "time_logs_24h"

    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True)
    time_from = Column(Time, nullable=False)
    time_to = Column(Time, nullable=False)
    duration = Column(Float)
    main_phase = Column(String(100))
    main_code = Column(String(100))
    sub_code = Column(String(100))
    status = Column(String(50))
    is_npt = Column(Boolean, default=False)
    npt_category = Column(String(100), nullable=True)
    activity_description = Column(Text)
    contractor = Column(String(100), nullable=True)

    report = relationship("DailyReport", back_populates="time_logs_24h")


class TimeLogMorning(Base):
    __tablename__ = "time_logs_morning"

    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=False)
    time_from = Column(Time, nullable=False)
    time_to = Column(Time, nullable=False)
    duration = Column(Float)
    main_phase = Column(String(100))
    main_code = Column(String(100))
    sub_code = Column(String(100))
    status = Column(String(50))
    is_npt = Column(Boolean, default=False)
    npt_category = Column(String(100), nullable=True)
    activity_description = Column(Text)
    contractor = Column(String(100), nullable=True)

    report = relationship("DailyReport", back_populates="time_logs_morning")

class DrillingParameters(Base):
    __tablename__ = "drilling_parameters"

    id = Column(Integer, primary_key=True)
    well_id = Column(
        Integer, ForeignKey("wells.id", ondelete="CASCADE"), nullable=False
    )
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    report_date = Column(Date, nullable=False)
    bit_no = Column(String(50))
    bit_rerun = Column(Integer, default=1)
    bit_size = Column(Float)
    bit_type = Column(String(50))
    manufacturer = Column(String(100))
    iadc_code = Column(String(50))
    nozzles_json = Column(Text)
    tfa = Column(Float)
    depth_in = Column(Float)
    depth_out = Column(Float)
    bit_drilled = Column(Float)
    cum_drilled = Column(Float)
    hours_on_bottom = Column(Float)
    cum_hours = Column(Float)
    wob_min = Column(Float)
    wob_max = Column(Float)
    rpm_min = Column(Float)
    rpm_max = Column(Float)
    torque_min = Column(Float)
    torque_max = Column(Float)
    pump_pressure_min = Column(Float)
    pump_pressure_max = Column(Float)
    pump_output_min = Column(Float)
    pump_output_max = Column(Float)
    pump1_spm = Column(Float)
    pump1_spp = Column(Float)
    pump2_spm = Column(Float)
    pump2_spp = Column(Float)
    pump3_spm = Column(Float)
    pump3_spp = Column(Float)
    avg_rop = Column(Float)
    hsi = Column(Float)
    annular_velocity = Column(Float)
    bit_revolution = Column(Float)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("drilling_parameters", cascade="all, delete-orphan")
    )
    creator = relationship("User", foreign_keys=[created_by])


class MudReport(Base):
    __tablename__ = "mud_reports"

    id = Column(Integer, primary_key=True)
    well_id = Column(
        Integer, ForeignKey("wells.id", ondelete="CASCADE"), nullable=False
    )
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    report_date = Column(Date, nullable=False)
    mud_type = Column(String(50))
    sample_time = Column(Time)
    mw = Column(Float)
    pv = Column(Float)
    yp = Column(Float)
    funnel_vis = Column(Float)
    gel_10s = Column(Float)
    gel_10m = Column(Float)
    fl = Column(Float)
    cake_thickness = Column(Float)
    ph = Column(Float)
    temperature = Column(Float)
    solid_percent = Column(Float)
    oil_percent = Column(Float)
    water_percent = Column(Float)
    chloride = Column(Float)
    volume_hole = Column(Float)
    total_circulated = Column(Float)
    loss_downhole = Column(Float)
    loss_surface = Column(Float)
    chemicals_json = Column(Text)
    summary = Column(Text)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("mud_reports", cascade="all, delete-orphan")
    )
    creator = relationship("User", foreign_keys=[created_by])


class CementReport(Base):
    __tablename__ = "cement_reports"

    id = Column(Integer, primary_key=True)
    well_id = Column(
        Integer, ForeignKey("wells.id", ondelete="CASCADE"), nullable=False
    )
    section_id = Column(
        Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=True
    )
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    report_date = Column(Date, nullable=False)
    report_name = Column(String(100))
    cement_type = Column(String(50))
    job_type = Column(String(100))
    materials_json = Column(Text)
    slurry_density = Column(Float)
    slurry_yield = Column(Float)
    mix_water = Column(Float)
    thickening_time = Column(String(20))
    compressive_strength = Column(Float)
    fluid_loss = Column(Float)
    cement_volume = Column(Float)
    displacement_volume = Column(Float)
    top_of_cement = Column(Float)
    bottom_of_cement = Column(Float)
    summary = Column(Text)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("cement_reports", cascade="all, delete-orphan")
    )
    creator = relationship("User", foreign_keys=[created_by])


class CasingReport(Base):
    __tablename__ = "casing_reports"

    id = Column(Integer, primary_key=True)
    well_id = Column(
        Integer, ForeignKey("wells.id", ondelete="CASCADE"), nullable=False
    )
    section_id = Column(
        Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=True
    )
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    report_date = Column(Date, nullable=False)
    report_name = Column(String(100))
    casing_type = Column(String(50))
    casing_json = Column(Text)
    tally_json = Column(Text)
    burst_pressure = Column(Float)
    collapse_pressure = Column(Float)
    tensile_strength = Column(Float)
    makeup_torque = Column(Float)
    drift_diameter = Column(Float)
    internal_yield = Column(Float)
    running_speed = Column(Float)
    fillup_frequency = Column(Integer)
    centralizer_spacing = Column(Float)
    scratcher_spacing = Column(Float)
    summary = Column(Text)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("casing_reports", cascade="all, delete-orphan")
    )
    creator = relationship("User", foreign_keys=[created_by])

class WellboreSchematic(Base):
    __tablename__ = "wellbore_schematics"

    id = Column(Integer, primary_key=True)
    well_id = Column(
        Integer, ForeignKey("wells.id", ondelete="CASCADE"), nullable=False
    )
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    report_date = Column(Date, nullable=False)
    schematic_name = Column(String(100))
    image_data = Column(Text)
    layers_json = Column(Text)
    elements_json = Column(Text)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("wellbore_schematics", cascade="all, delete-orphan")
    )
    creator = relationship("User", foreign_keys=[created_by])


class TripSheetEntry(Base):
    __tablename__ = "trip_sheet_entries"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    time = Column(Time, nullable=False)
    activity = Column(String(200), nullable=False)
    depth = Column(Float, default=0.0)
    cum_trip = Column(Float, default=0.0)
    duration = Column(Float, default=0.0)
    remarks = Column(Text)
    supervisor = Column(String(100))
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("trip_sheet_entries", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="trip_sheet_entries")
    report = relationship("DailyReport", backref="trip_sheet_entries")
    creator = relationship("User", foreign_keys=[created_by])


class SurveyPoint(Base):
    __tablename__ = "survey_points"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    calculation_id = Column(
        Integer, ForeignKey("trajectory_calculations.id"), nullable=True
    )
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    md = Column(Float, nullable=False)
    inc = Column(Float, nullable=False)
    azi = Column(Float, nullable=False)
    tvd = Column(Float, default=0.0)
    north = Column(Float, default=0.0)
    east = Column(Float, default=0.0)
    vs = Column(Float, default=0.0)
    hd = Column(Float, default=0.0)
    dls = Column(Float, default=0.0)
    tool = Column(String(50), default="MWD")
    remarks = Column(Text)
    measured_at = Column(DateTime)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("survey_points", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="survey_points")
    calculation = relationship("TrajectoryCalculation", backref="survey_points")
    creator = relationship("User", foreign_keys=[created_by])


class TrajectoryCalculation(Base):
    __tablename__ = "trajectory_calculations"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    method = Column(String(50), default="Minimum Curvature")
    calculation_date = Column(Date, nullable=False)
    parameters_json = Column(JSON, nullable=True)
    results_json = Column(JSON, nullable=True)
    target_north = Column(Float)
    target_east = Column(Float)
    target_tvd = Column(Float)
    total_hd = Column(Float)
    total_tvd = Column(Float)
    total_md = Column(Float)
    calculated_by = Column(Integer, ForeignKey("users.id"))
    description = Column(Text)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)

    well = relationship(
        "Well",
        backref=backref("trajectory_calculations", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="trajectory_calculations")
    calculator = relationship("User", foreign_keys=[calculated_by])


class TrajectoryPlot(Base):
    __tablename__ = "trajectory_plots"

    id = Column(Integer, primary_key=True)
    calculation_id = Column(Integer, ForeignKey("trajectory_calculations.id"))
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    plot_type = Column(String(50))
    title = Column(String(200))
    plot_data_json = Column(JSON)
    image_data = Column(Text)
    image_format = Column(String(10))
    created_at = Column(DateTime, default=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    calculation = relationship("TrajectoryCalculation", backref="plots")
    creator = relationship("User", foreign_keys=[created_by])


class BitReport(Base):
    __tablename__ = "bit_reports"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    report_date = Column(Date, nullable=False)
    report_name = Column(String(200))
    bit_records_json = Column(JSON)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)

    well = relationship(
        "Well",
        backref=backref("bit_reports", cascade="all, delete-orphan")
    )

class BHAReport(Base):
    __tablename__ = "bha_reports"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    bha_name = Column(String(100), nullable=False)
    bha_data_json = Column(JSON)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)

    well = relationship(
        "Well",
        backref=backref("bha_reports", cascade="all, delete-orphan")
    )

class DownholeEquipment(Base):
    __tablename__ = "downhole_equipment"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    equipment_data_json = Column(JSON)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)

    well = relationship(
        "Well",
        backref=backref("downhole_equipment", cascade="all, delete-orphan")
    )

class FormationReport(Base):
    __tablename__ = "formation_reports"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    report_name = Column(String(200))
    formations_json = Column(JSON)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)

    well = relationship(
        "Well",
        backref=backref("formation_reports", cascade="all, delete-orphan")
    )

class LogisticsPersonnel(Base):
    __tablename__ = "logistics_personnel"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    name = Column(String(100), nullable=False)
    position = Column(String(100))
    company = Column(String(100))
    arrival_date = Column(Date)
    departure_date = Column(Date)
    contact_info = Column(String(200))
    remarks = Column(Text)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("logistics_personnel", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="logistics_personnel")
    report = relationship("DailyReport", backref="logistics_personnel")
    creator = relationship("User", foreign_keys=[created_by])


class ServiceCompanyPOB(Base):
    __tablename__ = "service_company_pob"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    company_name = Column(String(100), nullable=False)
    service_type = Column(String(100))
    personnel_count = Column(Integer, default=0)
    date_in = Column(Date)
    date_out = Column(Date)
    remarks = Column(Text)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("service_company_pob", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="service_company_pob")
    report = relationship("DailyReport", backref="service_company_pob")
    creator = relationship("User", foreign_keys=[created_by])


class FuelWaterInventory(Base):
    __tablename__ = "fuel_water_inventory"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    report_date = Column(Date, nullable=False)
    fuel_type = Column(String(50), default="Diesel")
    fuel_consumed = Column(Float, default=0.0)
    fuel_stock = Column(Float, default=0.0)
    fuel_received = Column(Float, default=0.0)
    water_consumed = Column(Float, default=0.0)
    water_stock = Column(Float, default=0.0)
    water_received = Column(Float, default=0.0)
    fuel_remaining = Column(Float, default=0.0)
    water_remaining = Column(Float, default=0.0)
    days_remaining_fuel = Column(Float, default=0.0)
    days_remaining_water = Column(Float, default=0.0)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("fuel_water_inventory", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="fuel_water_inventory")
    report = relationship("DailyReport", backref="fuel_water_inventory")
    creator = relationship("User", foreign_keys=[created_by])


class BulkMaterials(Base):
    __tablename__ = "bulk_materials"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    report_date = Column(Date, nullable=False)
    material_name = Column(String(100), nullable=False)
    unit = Column(String(50), default="kg")
    initial_stock = Column(Float, default=0.0)
    received = Column(Float, default=0.0)
    used = Column(Float, default=0.0)
    current_stock = Column(Float, default=0.0)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("bulk_materials", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="bulk_materials")
    report = relationship("DailyReport", backref="bulk_materials")
    creator = relationship("User", foreign_keys=[created_by])


class TransportLog(Base):
    __tablename__ = "transport_logs"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    log_date = Column(Date, nullable=False)
    vehicle_type = Column(String(50), nullable=False)
    vehicle_name = Column(String(100), nullable=False)
    vehicle_id = Column(String(50))
    arrival_time = Column(Time)
    departure_time = Column(Time)
    duration = Column(Float)
    passengers_in = Column(Integer, default=0)
    passengers_out = Column(Integer, default=0)
    cargo_description = Column(Text)
    status = Column(String(50), default="Scheduled")
    purpose = Column(String(200))
    remarks = Column(Text)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("transport_logs", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="transport_logs")
    report = relationship("DailyReport", backref="transport_logs")
    creator = relationship("User", foreign_keys=[created_by])


class TransportNotes(Base):
    __tablename__ = "transport_notes"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    note_date = Column(Date, nullable=False)
    title = Column(String(200))
    content = Column(Text, nullable=False)
    category = Column(String(50), default="General")
    priority = Column(String(20), default="Normal")
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("transport_notes", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="transport_notes")
    report = relationship("DailyReport", backref="transport_notes")
    creator = relationship("User", foreign_keys=[created_by])


class SafetyReport(Base):
    __tablename__ = "safety_reports"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    report_date = Column(Date, nullable=False)
    report_type = Column(String(50), default="Daily")
    title = Column(String(200))
    last_fire_drill = Column(Date)
    last_bop_drill = Column(Date)
    last_h2s_drill = Column(Date)
    days_without_lti = Column(Integer, default=0)
    lti_count = Column(Integer, default=0)
    near_miss_count = Column(Integer, default=0)
    last_rams_test = Column(Date)
    test_pressure = Column(Float, default=0.0)
    last_koomey_test = Column(Date)
    days_since_last_test = Column(Integer, default=0)
    bop_stack_json = Column(JSON)
    recycled_volume = Column(Float, default=0.0)
    waste_ph = Column(Float, default=7.0)
    turbidity = Column(String(100))
    hardness = Column(String(100))
    cutting_volume = Column(Float, default=0.0)
    oil_content = Column(Float, default=0.0)
    waste_type = Column(String(100))
    disposal_method = Column(String(100))
    waste_history_json = Column(JSON)
    safety_observations = Column(Text)
    incidents_json = Column(JSON)
    equipment_checks = Column(JSON)
    status = Column(String(50), default="Draft")
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("safety_reports", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="safety_reports")
    report = relationship("DailyReport", backref="safety_reports")
    creator = relationship("User", foreign_keys=[created_by])


class SafetyIncident(Base):
    __tablename__ = "safety_incidents"

    id = Column(Integer, primary_key=True)
    safety_report_id = Column(
        Integer, ForeignKey("safety_reports.id"), nullable=False
    )
    incident_date = Column(Date, nullable=False)
    incident_time = Column(Time, nullable=False)
    incident_type = Column(String(100), nullable=False)
    severity = Column(String(50), default="Minor")
    location = Column(String(200))
    description = Column(Text, nullable=False)
    personnel_involved = Column(Text)
    injuries = Column(Text)
    immediate_response = Column(Text)
    corrective_actions = Column(Text)
    root_cause = Column(Text)
    investigator = Column(String(100))
    status = Column(String(50), default="Open")
    resolved_date = Column(Date)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    safety_report = relationship("SafetyReport", backref="incidents")
    creator = relationship("User", foreign_keys=[created_by])


class BOPComponent(Base):
    __tablename__ = "bop_components"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    safety_report_id = Column(Integer, ForeignKey("safety_reports.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    component_name = Column(String(100), nullable=False)
    component_type = Column(String(50), nullable=False)
    working_pressure = Column(Float, nullable=False)
    size = Column(String(50))
    ram_type = Column(String(100))
    manufacturer = Column(String(100))
    serial_number = Column(String(100))
    last_test_date = Column(Date)
    next_test_due = Column(Date)
    test_pressure = Column(Float)
    test_result = Column(String(50), default="Pass")
    status = Column(String(50), default="Operational")
    remarks = Column(Text)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("bop_components", cascade="all, delete-orphan")
    )
    safety_report = relationship("SafetyReport", backref="bop_components")
    creator = relationship("User", foreign_keys=[created_by])


class WasteRecord(Base):
    __tablename__ = "waste_records"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    safety_report_id = Column(Integer, ForeignKey("safety_reports.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    record_date = Column(Date, nullable=False)
    waste_type = Column(String(100), nullable=False)
    volume = Column(Float, nullable=False)
    unit = Column(String(20), default="BBL")
    ph = Column(Float)
    turbidity = Column(String(100))
    hardness = Column(String(100))
    oil_content = Column(Float)
    disposal_method = Column(String(100))
    disposal_date = Column(Date)
    disposal_company = Column(String(100))
    waste_ticket_number = Column(String(100))
    manifest_number = Column(String(100))
    remarks = Column(Text)
    status = Column(String(50), default="Pending Disposal")
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("waste_records", cascade="all, delete-orphan")
    )
    safety_report = relationship("SafetyReport", backref="waste_records")
    creator = relationship("User", foreign_keys=[created_by])


class ServiceCompany(Base):
    __tablename__ = "service_companies"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    company_name = Column(String(200), nullable=False)
    service_type = Column(String(100))
    start_datetime = Column(DateTime)
    end_datetime = Column(DateTime)
    contact_person = Column(String(100))
    contact_phone = Column(String(50))
    contact_email = Column(String(100))
    equipment_used = Column(Text)
    personnel_count = Column(Integer, default=1)
    status = Column(String(50), default="Active")
    description = Column(Text)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("service_companies", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="service_companies")
    report = relationship("DailyReport", backref="service_companies")
    creator = relationship("User", foreign_keys=[created_by])


class ServiceNote(Base):
    __tablename__ = "service_notes"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    note_number = Column(Integer, nullable=False)
    note_type = Column(String(50), default="General")
    content = Column(Text, nullable=False)
    priority = Column(String(20), default="Medium")
    status = Column(String(50), default="Active")
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("service_notes", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="service_notes")
    report = relationship("DailyReport", backref="service_notes")
    creator = relationship("User", foreign_keys=[created_by])


class MaterialRequest(Base):
    __tablename__ = "material_requests"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    request_date = Column(Date, nullable=False)
    requested_items = Column(Text)
    requested_quantity = Column(Float, default=0.0)
    requested_unit = Column(String(50), default="units")
    outstanding_items = Column(Text)
    outstanding_quantity = Column(Float, default=0.0)
    received_items = Column(Text)
    received_quantity = Column(Float, default=0.0)
    received_date = Column(Date)
    backload_items = Column(Text)
    backload_quantity = Column(Float, default=0.0)
    backload_date = Column(Date)
    remarks = Column(Text)
    status = Column(String(50), default="Pending")
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("material_requests", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="material_requests")
    report = relationship("DailyReport", backref="material_requests")
    creator = relationship("User", foreign_keys=[created_by])


class EquipmentLog(Base):
    __tablename__ = "equipment_logs"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    equipment_type = Column(String(100))
    equipment_name = Column(String(200), nullable=False)
    equipment_id = Column(String(100))
    manufacturer = Column(String(100))
    serial_number = Column(String(100))
    service_date = Column(Date)
    service_type = Column(String(100))
    service_provider = Column(String(200))
    hours_worked = Column(Float, default=0.0)
    status = Column(String(50), default="Operational")
    notes = Column(Text)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("equipment_logs", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="equipment_logs")
    report = relationship("DailyReport", backref="equipment_logs")
    creator = relationship("User", foreign_keys=[created_by])


class SevenDaysLookahead(Base):
    __tablename__ = "seven_days_lookahead"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    plan_date = Column(Date, nullable=False)
    day_number = Column(Integer, nullable=False)
    activity = Column(Text, nullable=False)
    tools = Column(Text)
    responsible = Column(String(200))
    remarks = Column(Text)
    status = Column(String(50), default="Planned")
    priority = Column(String(20), default="Normal")
    progress_percentage = Column(Integer, default=0)
    actual_start = Column(DateTime)
    actual_end = Column(DateTime)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("lookahead_plans", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="lookahead_plans")
    report = relationship("DailyReport", backref="lookahead_plans")
    creator = relationship("User", foreign_keys=[created_by])


class NPTReport(Base):
    __tablename__ = "npt_reports"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    npt_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    duration_hours = Column(Float, nullable=False)
    npt_category = Column(String(100), nullable=False)
    npt_code = Column(String(50), nullable=False)
    npt_description = Column(Text, nullable=False)
    responsible_party = Column(String(200))
    department = Column(String(100))
    cost_impact = Column(Float, default=0.0)
    delay_days = Column(Float, default=0.0)
    safety_incident = Column(Boolean, default=False)
    root_cause = Column(Text)
    corrective_action = Column(Text)
    prevention_plan = Column(Text)
    status = Column(String(50), default="Active")
    resolved_date = Column(Date)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("npt_reports", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="npt_reports")
    report = relationship("DailyReport", backref="npt_reports")
    creator = relationship("User", foreign_keys=[created_by])


class ActivityCode(Base):
    __tablename__ = "activity_codes"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    main_phase = Column(String(100), nullable=False)
    main_code = Column(String(50), nullable=False)
    sub_code = Column(String(50), nullable=False)
    code_name = Column(String(200), nullable=False)
    code_description = Column(Text)
    is_productive = Column(Boolean, default=True)
    is_npt = Column(Boolean, default=False)
    color_code = Column(String(10), default="#0078D4")
    usage_count = Column(Integer, default=0)
    total_hours = Column(Float, default=0.0)
    last_used = Column(Date)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("activity_codes", cascade="all, delete-orphan")
    )
    creator = relationship("User", foreign_keys=[created_by])


class TimeDepthData(Base):
    __tablename__ = "time_depth_data"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    timestamp = Column(DateTime, nullable=False)
    depth = Column(Float, nullable=False)
    activity_code = Column(String(50))
    rop = Column(Float)
    wob = Column(Float)
    rpm = Column(Float)
    torque = Column(Float)
    cumulative_time = Column(Float)
    daily_progress = Column(Float)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("time_depth_data", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="time_depth_data")
    creator = relationship("User", foreign_keys=[created_by])


class ROPAnalysis(Base):
    __tablename__ = "rop_analysis"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    report_id = Column(
        Integer, ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=True
    )
    analysis_date = Column(Date, nullable=False)
    start_depth = Column(Float, nullable=False)
    end_depth = Column(Float, nullable=False)
    avg_rop = Column(Float)
    max_rop = Column(Float)
    min_rop = Column(Float)
    rop_std_dev = Column(Float)
    formation_type = Column(String(100))
    bit_type = Column(String(50))
    hydraulics_efficiency = Column(Float)
    drill_string_config = Column(String(200))
    rop_chart_data = Column(JSON)
    depth_chart_data = Column(JSON)
    recommendations = Column(Text)
    efficiency_score = Column(Integer)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("rop_analysis", cascade="all, delete-orphan")
    )
    section = relationship("Section", backref="rop_analysis")
    creator = relationship("User", foreign_keys=[created_by])

class ExportTemplate(Base):
    __tablename__ = "export_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    template_type = Column(String(50))
    description = Column(Text)
    well_selection = Column(JSON)
    report_selection = Column(JSON)
    date_range = Column(JSON)
    format_settings = Column(JSON)
    options = Column(JSON)
    layout_config = Column(JSON)
    styling = Column(JSON)
    headers_footers = Column(JSON)
    is_default = Column(Boolean, default=False)
    is_shared = Column(Boolean, default=False)
    shared_with = Column(JSON)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    creator = relationship("User", foreign_keys=[created_by])

class PlannedActivity(Base):
    """فعالیت‌های برنامه‌ریزی شده برای هر چاه و سکشن"""
    __tablename__ = "planned_activities"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=True)
    plan_id = Column(Integer, ForeignKey("well_plans.id", ondelete="CASCADE"), nullable=True)  # ← اضافه شد
    
    # اطلاعات فعالیت
    activity_name = Column(String(200), nullable=False)
    activity_code = Column(String(50))
    phase_code = Column(String(100))
    
    # زمان‌بندی برنامه
    planned_start = Column(DateTime, nullable=False)
    planned_end = Column(DateTime, nullable=False)
    planned_duration_hours = Column(Float, default=0.0)
    
    # اطلاعات عمق
    planned_depth_from = Column(Float, default=0.0)
    planned_depth_to = Column(Float, default=0.0)
    
    # پیشرفت
    progress_percent = Column(Float, default=0.0)
    is_completed = Column(Boolean, default=False)
    actual_duration_hours = Column(Float, default=0.0)
    
    # ارتباطات
    well = relationship(
        "Well",
        backref=backref("planned_activities", cascade="all, delete-orphan")
    )    
    
    
    section = relationship("Section", backref="planned_activities")
    plan = relationship("WellPlan", back_populates="activities") 
    
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)

class WellPlan(Base):
    """برنامه حفاری کلی چاه"""
    __tablename__ = "well_plans"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id", ondelete="CASCADE"), nullable=False)
    plan_name = Column(String(200), nullable=False)
    plan_version = Column(String(50), default="1.0")
    
    # اطلاعات کلی برنامه
    planned_spud_date = Column(Date)
    planned_finish_date = Column(Date)
    planned_total_days = Column(Float, default=0.0)
    planned_final_depth = Column(Float, default=0.0)
    
    # وضعیت
    is_active = Column(Boolean, default=True)
    description = Column(Text)
    
    well = relationship(
        "Well",
        backref=backref("plans", cascade="all, delete-orphan")
    )
    activities = relationship("PlannedActivity", back_populates="plan", cascade="all, delete-orphan") 
    
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    

# ==================== DWI/Procedure Tables ====================

class OperationalProcedure(Base):
    """جدول اصلی پروسیجرهای عملیاتی"""
    __tablename__ = "operational_procedures"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)
    
    # اطلاعات کلی
    title = Column(String(300), nullable=False)
    procedure_type = Column(String(100))  # liner_running, cementing, casing_running, ...
    revision = Column(String(20), default="Rev 0")
    revision_date = Column(Date)
    
    # اطلاعات چاه (auto-fill)
    rig_name = Column(String(100))
    well_name = Column(String(100))
    field_name = Column(String(100))
    
    # وضعیت
    status = Column(String(50), default="Draft")  # Draft, Under Review, Approved, Superseded
    
    # افراد مسئول
    prepared_by = Column(String(100))
    checked_by = Column(String(100))
    approved_by = Column(String(100))
    
    # محتوا
    objective = Column(Text)
    hse_focus = Column(Text)
    general_notes = Column(Text)
    
    # تاریخچه
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    # روابط
    well = relationship(
        "Well",
        backref=backref("procedures", cascade="all, delete-orphan")
    )    
    steps = relationship("ProcedureStep", back_populates="procedure", 
                        cascade="all, delete-orphan", order_by="ProcedureStep.step_number")
    checklist_items = relationship("ProcedureChecklist", back_populates="procedure",
                                   cascade="all, delete-orphan")
    approvals = relationship("ProcedureApproval", back_populates="procedure",
                             cascade="all, delete-orphan")
    pjsm_meetings = relationship("PJSMRecord", back_populates="procedure",
                                  cascade="all, delete-orphan")


class ProcedureStep(Base):
    """مراحل پروسیجر"""
    __tablename__ = "procedure_steps"

    id = Column(Integer, primary_key=True)
    procedure_id = Column(Integer, ForeignKey("operational_procedures.id", ondelete="CASCADE"), 
                         nullable=False)
    
    step_number = Column(Integer, nullable=False)
    activity_description = Column(Text, nullable=False)
    parallel_activities = Column(Text)  # موارد موازی/یادآوری
    caution_notes = Column(Text)        # هشدارها
    
    # وضعیت اجرا
    is_completed = Column(Boolean, default=False)
    completed_by = Column(String(100))
    completed_at = Column(DateTime)
    remarks = Column(Text)
    
    created_at = Column(DateTime, default=_now_utc)
    
    procedure = relationship("OperationalProcedure", back_populates="steps")


class ProcedureChecklist(Base):
    """چک‌لیست پروسیجر"""
    __tablename__ = "procedure_checklists"

    id = Column(Integer, primary_key=True)
    procedure_id = Column(Integer, ForeignKey("operational_procedures.id", ondelete="CASCADE"),
                         nullable=False)
    
    category = Column(String(100))       # Equipment, HSE, Personnel, Materials
    item_description = Column(Text, nullable=False)
    responsible = Column(String(100))
    
    # تأیید
    verified = Column(Boolean, default=False)
    verified_by = Column(String(100))
    verified_at = Column(DateTime)
    
    # N/A
    not_applicable = Column(Boolean, default=False)
    remarks = Column(Text)
    
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=_now_utc)
    
    procedure = relationship("OperationalProcedure", back_populates="checklist_items")


class ProcedureApproval(Base):
    """تأییدیه‌های پروسیجر"""
    __tablename__ = "procedure_approvals"

    id = Column(Integer, primary_key=True)
    procedure_id = Column(Integer, ForeignKey("operational_procedures.id", ondelete="CASCADE"),
                         nullable=False)
    
    role = Column(String(50))   # Prepared by, Checked by, Approved by
    name = Column(String(100))
    title = Column(String(100))
    signature_date = Column(Date)
    is_signed = Column(Boolean, default=False)
    comments = Column(Text)
    
    created_at = Column(DateTime, default=_now_utc)
    
    procedure = relationship("OperationalProcedure", back_populates="approvals")


class PJSMRecord(Base):
    """Pre-Job Safety Meeting"""
    __tablename__ = "pjsm_records"

    id = Column(Integer, primary_key=True)
    procedure_id = Column(Integer, ForeignKey("operational_procedures.id", ondelete="CASCADE"),
                         nullable=False)
    
    meeting_date = Column(DateTime, default=_now_utc)
    meeting_location = Column(String(200))
    conducted_by = Column(String(100))
    
    # شرکت‌کنندگان (JSON)
    attendees_json = Column(JSON)
    
    # موضوعات (JSON list)
    topics_discussed_json = Column(JSON)
    
    # اقدامات (JSON list)
    action_items_json = Column(JSON)
    
    hse_concerns = Column(Text)
    general_notes = Column(Text)
    
    created_at = Column(DateTime, default=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))
    
    procedure = relationship("OperationalProcedure", back_populates="pjsm_meetings")


class ProcedureTemplate(Base):
    """قالب‌های آماده پروسیجر"""
    __tablename__ = "procedure_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    procedure_type = Column(String(100), nullable=False)
    description = Column(Text)
    
    # محتوای قالب (JSON)
    template_steps_json = Column(JSON)
    template_checklist_json = Column(JSON)
    template_hse_json = Column(JSON)
    
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

class CostRecord(Base):
    """رکورد هزینه"""
    __tablename__ = "cost_records"

    id = Column(Integer, primary_key=True)
    well_id = Column(Integer, ForeignKey("wells.id", ondelete="CASCADE"), nullable=False)
    
    category = Column(String(100), nullable=False)
    description = Column(Text)
    planned_cost = Column(Float, default=0.0)
    actual_cost = Column(Float, default=0.0)
    variance = Column(Float, default=0.0)
    currency = Column(String(10), default="USD")
    
    cost_date = Column(Date)
    afe_number = Column(String(50))
    vendor = Column(String(200))
    invoice_number = Column(String(100))
    
    cost_type = Column(String(50), default="OPEX")
    status = Column(String(50), default="Pending")
    
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)
    created_by = Column(Integer, ForeignKey("users.id"))

    well = relationship(
        "Well",
        backref=backref("cost_records", cascade="all, delete-orphan")
    )    
# ----------------------------------------------------------------------
# DatabaseManager class with updated save/get methods for key tables
# ----------------------------------------------------------------------
class DatabaseManager:
    def __init__(self):
        self.engine = None
        self.Session = None

        base_dir = Path(__file__).resolve().parent.parent
        self.db_path = str(base_dir / "drillmaster.db")

    @property
    def _get_current_user_info(self):
        """دریافت اطلاعات کاربر جاری به صورت lazy"""
        try:
            from core.permissions import permissions
            return {
                'user_id': permissions.user_id,
                'username': permissions.username,
            }
        except Exception:
            return {'user_id': None, 'username': 'system'}
            
    def initialize(self):
        try:
            self.engine = create_engine(
                f"sqlite:///{self.db_path}",
                connect_args={
                    "check_same_thread": False,
                    "timeout": 30,
                },
                poolclass=StaticPool,
                echo=False,
                pool_pre_ping=True,
            )

            from sqlalchemy import event, text

            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=10000")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

            self.Session = sessionmaker(
                bind=self.engine,
                autoflush=False, 
                autocommit=False,
            )
            Base.metadata.create_all(self.engine)
            self.create_default_data()
            return True

        except Exception as e:
            logger.error(f"Database initialization failed: {str(e)}")
            return False
    
    def create_default_data(self):
        session = self.create_session()
        try:
            if session.query(User).count() == 0:
                import os

                admin_password = os.environ.get(
                    "DRILLMASTER_ADMIN_PASSWORD",
                    "admin123"
                )
                user_password = os.environ.get(
                    "DRILLMASTER_USER_PASSWORD",
                    "user123"
                )

                if admin_password == "admin123":
                    logger.warning(
                        "⚠️ Using default admin password. "
                        "Set DRILLMASTER_ADMIN_PASSWORD env var for production."
                    )

                users = [
                    User(
                        username="admin",
                        password_hash=self._hash_password(admin_password),
                        full_name="Administrator",
                        email="admin@drillmaster.com",
                        role="admin",
                        department="Management",
                        permissions={
                            "can_create_well": True,
                            "can_delete_well": True,
                            "can_edit_reports": True,
                            "can_approve_reports": True,
                            "can_manage_users": True,
                            "can_export": True,
                            "can_import": True,
                        }
                    ),
                    User(
                        username="engineer",
                        password_hash=self._hash_password(user_password),
                        full_name="Drilling Engineer",
                        email="engineer@drillmaster.com",
                        role="engineer",
                        department="Operations",
                        permissions={
                            "can_create_well": True,
                            "can_delete_well": False,
                            "can_edit_reports": True,
                            "can_approve_reports": False,
                            "can_manage_users": False,
                            "can_export": True,
                            "can_import": True,
                        }
                    ),
                    User(
                        username="viewer",
                        password_hash=self._hash_password("viewer123"),
                        full_name="Report Viewer",
                        email="viewer@drillmaster.com",
                        role="viewer",
                        department="Management",
                        permissions={
                            "can_create_well": False,
                            "can_delete_well": False,
                            "can_edit_reports": False,
                            "can_approve_reports": False,
                            "can_manage_users": False,
                            "can_export": True,
                            "can_import": False,
                        }
                    ),
                ]
                for user in users:
                    session.add(user)

                company = Company(
                    name="Default Company",
                    code="DC001",
                    address="123 Industry St, Houston, TX",
                    contact_person="John Smith",
                    contact_email="info@company.com",
                    contact_phone="+1-234-567-8900",
                )
                session.add(company)
                project = Project(
                    company=company,
                    name="Default Project",
                    code="DP001",
                    location="Gulf of Mexico",
                    start_date=datetime(2024, 1, 1).date(),
                    status="Active",
                    manager="Jane Doe",
                    budget=5000000.00,
                    currency="USD",
                )
                session.add(project)
                well = Well(
                    project=project,
                    name="Default Well",
                    code="DW001",
                    field_name="Default Field",
                    location="Block A-12",
                    coordinates="28.5, -88.5",
                    elevation=10.5,
                    water_depth=1500.0,
                    spud_date=datetime(2024, 3, 1).date(),
                    target_depth=3500.0,
                    status="Planning",
                    well_type="Exploration",
                    purpose="Oil Production",
                    well_type_field="Offshore",
                )
                session.add(well)
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating default data: {str(e)}")
        finally:
            session.close()

    def create_session(self) -> Session:
        """ایجاد session - از session_scope استفاده کن تا tracking درست باشد"""
        return self.Session()

    def release_session(self, session):
        """بستن session"""
        try:
            session.close()
        except Exception:
            pass

    @contextmanager
    def session_scope(self):
        """
        Context manager برای session ایمن با tracking.
        
        استفاده:
            with db.session_scope() as session:
                data = session.query(Well).all()
        """
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            
    def _hash_password(self, password: str) -> str:
        """Hash password - bcrypt اگر موجود باشد، وگرنه SHA-256"""
        if _BCRYPT_AVAILABLE:
            # ✅ bcrypt با per-password salt
            salt = bcrypt.gensalt(rounds=12)
            return bcrypt.hashpw(
                password.encode('utf-8'), salt
            ).decode('utf-8')
        else:
            # ✅ SHA-256 با per-password random salt (بهتر از static salt)
            salt = secrets.token_hex(32)
            hashed = hashlib.sha256(
                f"{salt}{password}".encode('utf-8')
            ).hexdigest()
            return f"sha256:{salt}:{hashed}"

    def _verify_password(self, password: str, stored_hash: str) -> bool:
        """تأیید password - سازگار با هر دو فرمت"""
        if _BCRYPT_AVAILABLE and not stored_hash.startswith("sha256:"):
            try:
                return bcrypt.checkpw(
                    password.encode('utf-8'),
                    stored_hash.encode('utf-8')
                )
            except Exception:
                pass

        # fallback برای SHA-256
        if stored_hash.startswith("sha256:"):
            parts = stored_hash.split(":", 2)
            if len(parts) == 3:
                _, salt, expected = parts
                actual = hashlib.sha256(
                    f"{salt}{password}".encode('utf-8')
                ).hexdigest()
                return secrets.compare_digest(actual, expected)

        # سازگاری با hash قدیمی (static salt)
        old_salt = "DrillMaster_2024_Salt"
        old_hash = hashlib.sha256(
            f"{old_salt}{password}".encode('utf-8')
        ).hexdigest()
        return secrets.compare_digest(old_hash, stored_hash)

    def authenticate_user(self, username: str, password: str)-> Optional[Any]:
        session = self.create_session()
        try:
            user = (
                session.query(User)
                .filter(
                    User.username == username,
                    User.is_active == True,
                )
                .first()
            )

            if user and self._verify_password(
                password, user.password_hash
            ):
                user_data = {
                    "id": user.id,
                    "username": user.username,
                    "full_name": getattr(user, 'full_name', user.username),
                    "role": getattr(user, 'role', 'user'),
                    "email": getattr(
                        user, 'email',
                        f'{user.username}@drillmaster.com'
                    ),
                    "permissions": user.permissions or {},
                }
                try:
                    user.last_login = datetime.now(
                        __import__('datetime').timezone.utc
                    ).replace(tzinfo=None)
                    session.commit()
                except Exception:
                    session.rollback()
                return type("UserObject", (), user_data)()
            return None
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return None
        finally:
            session.close()
            
    def generic_save(self, model, data: dict):
        """Persist a mapped model using only columns declared by its table."""
        valid = {column.name for column in model.__table__.columns}
        values = {k: v for k, v in (data or {}).items() if k in valid and k != "id"}
        with self.session_scope() as session:
            obj = session.get(model, data.get("id")) if data and data.get("id") else None
            if obj is None:
                obj = model(**values)
                session.add(obj)
                session.flush()
            else:
                for key, value in values.items():
                    setattr(obj, key, value)
                session.flush()
            return obj.id

    def generic_get_list(self, model, filters=None, limit=None):
        with self.session_scope() as session:
            query = session.query(model)
            for key, value in (filters or {}).items():
                if hasattr(model, key):
                    query = query.filter(getattr(model, key) == value)
            if limit:
                query = query.limit(int(limit))
            return [{column.name: getattr(row, column.name) for column in model.__table__.columns} for row in query.all()]

    def generic_delete(self, model, object_id):
        with self.session_scope() as session:
            obj = session.get(model, object_id)
            if obj is None:
                return False
            session.delete(obj)
            return True

    def get_hierarchy(self):
        """دریافت hierarchy - با session_scope"""
        try:
            with self.session_scope() as session:
                companies = session.query(Company).all()
                hierarchy = []
                for company in companies:
                    company_data = {
                        "id": company.id,
                        "name": company.name,
                        "code": company.code,
                        "projects": [],
                    }
                    for project in company.projects:
                        project_data = {
                            "id": project.id,
                            "name": project.name,
                            "code": project.code,
                            "wells": [],
                        }
                        for well in project.wells:
                            project_data["wells"].append({
                                "id": well.id,
                                "name": well.name,
                                "code": well.code,
                                "status": well.status,
                            })
                        company_data["projects"].append(project_data)
                    hierarchy.append(company_data)
                return hierarchy
        except Exception as e:
            logger.error(f"Error getting hierarchy: {str(e)}")
            return []
            
    def get_full_hierarchy(self):
        """
        ✅ بارگذاری کامل hierarchy در یک query با eager loading
        جایگزین N+1 query pattern
        """
        from sqlalchemy.orm import joinedload
        
        session = self.create_session()
        try:
            companies = session.query(Company).options(
                joinedload(Company.projects)
                .joinedload(Project.wells)
                .joinedload(Well.sections)
                .joinedload(Section.daily_reports)
            ).all()
            
            hierarchy = []
            for company in companies:
                company_data = {
                    "id": company.id,
                    "name": company.name,
                    "code": company.code,
                    "projects": [],
                }
                for project in company.projects:
                    project_data = {
                        "id": project.id,
                        "name": project.name,
                        "code": project.code,
                        "wells": [],
                    }
                    for well in project.wells:
                        well_data = {
                            "id": well.id,
                            "name": well.name,
                            "code": well.code,
                            "status": well.status,
                            "sections": [],
                        }
                        for section in sorted(well.sections, key=lambda s: s.depth_from or 0):
                            section_data = {
                                "id": section.id,
                                "name": section.name,
                                "well_id": well.id,
                                "reports": [
                                    {
                                        "id": r.id,
                                        "report_date": r.report_date,
                                        "report_number": r.report_number,
                                        "section_id": section.id,
                                        "well_id": well.id,
                                    }
                                    for r in sorted(
                                        section.daily_reports,
                                        key=lambda r: r.report_date or date.min,
                                        reverse=True
                                    )[:50]
                                ],
                            }
                            well_data["sections"].append(section_data)
                        project_data["wells"].append(well_data)
                    company_data["projects"].append(project_data)
                hierarchy.append(company_data)
            return hierarchy
        except Exception as e:
            logger.error(f"Error getting full hierarchy: {e}")
            return []
        finally:
            session.close()
            
    def get_all_projects(self):
        session = self.create_session()
        try:
            projects = session.query(Project).all()
            return [{"id": p.id, "name": p.name, "code": p.code} for p in projects]
        except Exception as e:
            logger.error(f"Error getting projects: {str(e)}")
            return []
        finally:
            session.close()

    def get_well_by_id(self, well_id: int)-> Optional[Dict[str, Any]]:
        session = self.create_session()
        try:
            well = session.query(Well).filter(Well.id == well_id).first()
            if well:
                # ✅ خودکار از ستون‌های مدل dict بساز
                result = {}
                for column in Well.__table__.columns:
                    result[column.name] = getattr(well, column.name)
                return result
            return None
        except Exception as e:
            logger.error(f"Error getting well {well_id}: {e}")
            return None
        finally:
            session.close()
            
    def get_sections_by_well(self, well_id: int)-> List[Dict[str, Any]]:
        session = self.create_session()
        try:
            sections = session.query(Section).filter(Section.well_id == well_id).order_by(Section.depth_from).all()
            return [
                {
                    "id": s.id,
                    "name": s.name,
                    "code": s.code,
                    "depth_from": s.depth_from,
                    "depth_to": s.depth_to,
                    "diameter": s.diameter,
                    "hole_size": s.hole_size,
                    "purpose": s.purpose,
                    "description": s.description,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                }
                for s in sections
            ]
        except Exception as e:
            logger.error(f"Error getting sections for well {well_id}: {str(e)}")
            return []
        finally:
            session.close()
    
    def save_section(self, section_data: dict):
        """Save or update a section"""
        session = self.create_session()
        try:
            if section_data.get("id"):
                section = session.query(Section).filter(Section.id == section_data["id"]).first()
                if section:
                    for key, value in section_data.items():
                        if key != "id" and hasattr(section, key):
                            setattr(section, key, value)
                    section.updated_at = _now_utc()
            else:
                valid_keys = {column.name for column in Section.__table__.columns}
                section = Section(**{k: v for k, v in section_data.items() if k in valid_keys and k != "id"})
                session.add(section)
                session.flush()
            session.commit()
            return section.id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving section: {e}")
            return None
        finally:
            session.close()
        
    def get_daily_reports_by_section(self, section_id: int)-> List[Dict[str, Any]]:
        session = self.create_session()
        try:
            reports = (
                session.query(DailyReport)
                .filter(DailyReport.section_id == section_id)
                .order_by(DailyReport.report_date.desc())
                .all()
            )
            return [
                {
                    "id": r.id,
                    "report_date": r.report_date,
                    "report_number": r.report_number,
                    "report_title": r.report_title,
                    "rig_day": r.rig_day,
                    "depth_2400": r.depth_2400,
                    "summary": r.summary,
                    "status": r.status,
                    "well_id": r.well_id,
                    "section_id": r.section_id,
                }
                for r in reports
            ]
        except Exception as e:
            logger.error(f"Error getting daily reports for section {section_id}: {str(e)}")
            return []
        finally:
            session.close()
            

    def save_well(self, well_data: dict) -> bool:
        date_fields = ['spud_date', 'start_hole_date', 'rig_move_date', 'report_date']
        for field in date_fields:
            if field in well_data:
                val = well_data[field]
                if isinstance(val, str):
                    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
                        try:
                            well_data[field] = datetime.strptime(val, fmt).date()
                            break
                        except ValueError:
                            continue
                    else:
                        well_data[field] = None
                elif isinstance(val, datetime):
                    well_data[field] = val.date()
                elif isinstance(val, date):
                    pass
                elif val is None:
                    pass
                else:
                    well_data[field] = None

        # فیلتر فیلدهای نامعتبر
        valid_keys = {c.name for c in Well.__table__.columns}
        filtered_data = {k: v for k, v in well_data.items() if k in valid_keys}

        session = self.create_session()
        try:
            well_id = filtered_data.get("id")
            if well_id:
                well = session.query(Well).filter(Well.id == well_id).first()
                if not well:
                    return False
                for key, value in filtered_data.items():
                    if key != "id" and hasattr(well, key):
                        setattr(well, key, value)
                well.updated_at = _now_utc()
            else:
                well = Well(**filtered_data)
                session.add(well)
            session.commit()
            
            user_info = self._get_current_user_info
            self.log_audit(
                action="update" if well_id else "create",
                entity_type="well",
                entity_id=well.id if hasattr(well, 'id') else well_id,
                entity_name=filtered_data.get("name", ""),
                user_id=user_info['user_id'],
                username=user_info['username'],
            )

            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving well: {e}")
            return False
        finally:
            session.close()
    
    def delete_well(self, well_id: int) -> bool:
        try:
            with self.session_scope() as session:
                well = session.query(Well).filter(
                    Well.id == well_id
                ).first()
                if well:
                    session.delete(well)
                    return True
                return False
        except Exception as e:
            logger.error(f"Error deleting well: {e}")
            return False
            
    def close(self):
        if self.engine:
            self.engine.dispose()

    # ---------- Daily Report methods (unchanged except for title in queries) ----------
    def get_daily_reports_by_well(self, well_id: int):
        session = self.create_session()
        try:
            reports = (
                session.query(DailyReport)
                .filter(DailyReport.well_id == well_id)
                .order_by(DailyReport.report_date.desc())
                .all()
            )
            return [
                {
                    "id": r.id,
                    "report_date": r.report_date,
                    "report_title": r.report_title,
                    "rig_day": r.rig_day,
                    "depth_2400": r.depth_2400,
                    "summary": (r.summary[:100] + "..." if r.summary and len(r.summary) > 100 else (r.summary or "")),
                    "status": r.status,
                }
                for r in reports
            ]
        except Exception as e:
            logger.error(f"Error getting daily reports for well {well_id}: {str(e)}")
            return []
        finally:
            session.close()

    def save_daily_report(self, data: dict):
        session = self.create_session()
        try:
            if "report_date" in data and isinstance(data["report_date"], str):
                try:
                    data["report_date"] = datetime.strptime(
                        data["report_date"], "%Y-%m-%d"
                    ).date()
                except ValueError:
                    pass

            report_id = data.get("id")
            if report_id:
                report = session.query(DailyReport).filter(
                    DailyReport.id == report_id
                ).first()
                if not report:
                    return None
                valid_keys = {c.name for c in DailyReport.__table__.columns}
                for k, v in data.items():
                    if k != 'id' and k in valid_keys and hasattr(report, k):
                        setattr(report, k, v)
                report.updated_at = _now_utc()
            else:
                valid_keys = {c.name for c in DailyReport.__table__.columns}
                filtered_data = {
                    k: v for k, v in data.items() if k in valid_keys
                }
                report = DailyReport(**filtered_data)
                session.add(report)
                session.flush()

            session.commit()
            
            from core.permissions import permissions
            self.log_audit(
                action="update" if report_id else "create",
                entity_type="daily_report",
                entity_id=report.id,
                entity_name=f"Report #{report.report_number}",
                user_id=permissions.user_id,
                username=permissions.username,
            )
            
            return {
                "id": report.id,
                "report_number": report.report_number,
                "report_date": report.report_date,
                "rig_day": report.rig_day,
                "depth_0000": report.depth_0000 or 0,
                "depth_0600": report.depth_0600 or 0,
                "depth_2400": report.depth_2400 or 0,
                "summary": report.summary or "",
                "status": report.status or "Draft",
                "well_id": report.well_id,
                "section_id": report.section_id,
            }
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving daily report: {e}")
            return None
        finally:
            session.close()
            
    def get_daily_report_by_id(self, report_id: int):
        session = self.create_session()
        try:
            report = session.query(DailyReport).filter(
                DailyReport.id == report_id
            ).first()
            if report:
                result = {}
                for col in DailyReport.__table__.columns:
                    result[col.name] = getattr(report, col.name)
                return result
            return None
        finally:
            session.close()
 

    def create_report_revision(self, report_id: int, status="Draft", comment=""):
        """Store an immutable report snapshot and return its revision id."""
        with self.session_scope() as session:
            report = session.get(DailyReport, report_id)
            if report is None:
                return None
            columns = {column.name for column in DailyReport.__table__.columns}
            snapshot = {}
            for name in columns:
                value = getattr(report, name)
                snapshot[name] = value.isoformat() if isinstance(value, (date, datetime, time)) else value
            latest = session.query(ReportRevision).filter_by(report_id=report_id).order_by(ReportRevision.revision_no.desc()).first()
            revision = ReportRevision(report_id=report_id, revision_no=(latest.revision_no + 1 if latest else 1), status=status, snapshot=snapshot, comment=comment)
            session.add(revision)
            session.flush()
            return revision.id

    def set_report_status(self, report_id: int, status: str, user_id=None, comment=""):
        """Change workflow state and persist an approval action."""
        allowed = {"Draft", "Submitted", "Under Review", "Rejected", "Approved", "Final"}
        if status not in allowed:
            raise ValueError(f"Unsupported report status: {status}")
        with self.session_scope() as session:
            report = session.get(DailyReport, report_id)
            if report is None:
                return False
            if report.status == "Final" and status != "Final":
                raise ValueError("Final reports cannot be downgraded")
            report.status = status
            action = "submit" if status == "Submitted" else "approve" if status in {"Approved", "Final"} else "reject" if status == "Rejected" else "update"
            session.add(ApprovalAction(report_id=report_id, action=action, status=status, user_id=user_id, comment=comment))
            return True

    def get_report_revisions(self, report_id: int):
        with self.session_scope() as session:
            rows = session.query(ReportRevision).filter_by(report_id=report_id).order_by(ReportRevision.revision_no.desc()).all()
            return [{"id": r.id, "revision_no": r.revision_no, "status": r.status, "snapshot": r.snapshot, "created_at": r.created_at, "comment": r.comment} for r in rows]

    def get_approval_history(self, report_id: int):
        with self.session_scope() as session:
            rows = session.query(ApprovalAction).filter_by(report_id=report_id).order_by(ApprovalAction.created_at.desc()).all()
            return [{"id": a.id, "action": a.action, "status": a.status, "user_id": a.user_id, "comment": a.comment, "created_at": a.created_at} for a in rows]

    def save_imported_multi_tab_data(self, well_id: int, report_id: int, extracted: dict) -> dict:
        """
        ذخیره‌سازی یکپارچه داده‌های واردشده از اکسل برای تمامی تب‌های برنامه
        (Surveys, POB, Casing, Cement, Bit, BHA, Bulk, Fuel/Water, Safety, BOP, Cost, Services)
        """
        results = {"failed": 0}
        try:
            def count_result(key, value):
                if value:
                    results[key] = results.get(key, 0) + 1
                else:
                    results["failed"] += 1

            # 1. Trajectory / Surveys -> SurveyPoint
            surveys = extracted.get("surveys", [])
            if surveys:
                for s in surveys:
                    if isinstance(s, dict):
                        s["well_id"] = well_id
                        s["report_id"] = report_id
                if self.save_survey_points(surveys):
                    results["surveys"] = len(surveys)
                else:
                    results["failed"] += len(surveys)

            # 2. Logistics / POB -> ServiceCompanyPOB
            pobs = extracted.get("pob_records", [])
            if pobs:
                saved_pobs = 0
                for p in pobs:
                    if isinstance(p, dict):
                        p["well_id"] = well_id
                        p["report_id"] = report_id
                        saved_pobs += bool(self.save_service_company_pob(p))
                results["pob_records"] = saved_pobs
                results["failed"] += len(pobs) - saved_pobs

            # 2b. Services -> ServiceCompany
            service_companies = extracted.get("service_companies", [])
            if service_companies:
                saved_services = 0
                for company_data in service_companies:
                    if not isinstance(company_data, dict):
                        continue
                    item = dict(company_data)
                    item["well_id"] = well_id
                    item["report_id"] = report_id
                    if self.save_service_company(item):
                        saved_services += 1
                results["service_companies"] = saved_services

            # 3. Casing Report -> CasingReport
            casing = extracted.get("casing_report")
            if casing and isinstance(casing, dict):
                casing["well_id"] = well_id
                casing["report_id"] = report_id
                self.save_casing_report(casing)
                results["casing_report"] = 1

            # 4. Cement Report -> CementReport
            cement = extracted.get("cement_report")
            if cement and isinstance(cement, dict):
                cement["well_id"] = well_id
                cement["report_id"] = report_id
                self.save_cement_report(cement)
                results["cement_report"] = 1

            # 5. Bit Report -> BitReport
            bit = extracted.get("bit_report")
            if bit and isinstance(bit, dict):
                self.save_bit_report(well_id, bit)
                results["bit_report"] = 1

            # 6. BHA Report -> BHAReport
            bha = extracted.get("bha_report")
            if bha and isinstance(bha, dict):
                self.save_bha_report(well_id, bha)
                results["bha_report"] = 1

            # 7. Logistics Bulk Materials -> BulkMaterials
            bulks = extracted.get("bulk_materials", [])
            if bulks:
                for b in bulks:
                    if isinstance(b, dict):
                        b["well_id"] = well_id
                        b["report_id"] = report_id
                        self.save_bulk_material(b)
                results["bulk_materials"] = len(bulks)

            # 8. Fuel & Water Inventory -> FuelWaterInventory
            fw = extracted.get("fuel_water")
            if fw and isinstance(fw, dict):
                fw["well_id"] = well_id
                fw["report_id"] = report_id
                self.save_fuel_water_inventory(fw)
                results["fuel_water"] = 1

            # 9. Safety Report & BOP -> SafetyReport, BOPComponent, WasteRecord
            safety = extracted.get("safety_report")
            if safety and isinstance(safety, dict):
                safety["well_id"] = well_id
                safety["report_id"] = report_id
                self.save_safety_report(safety)
                results["safety_report"] = 1

            bops = extracted.get("bop_components", [])
            if bops:
                for bp in bops:
                    if isinstance(bp, dict):
                        bp["well_id"] = well_id
                        bp["report_id"] = report_id
                        self.save_bop_component(bp)
                results["bop_components"] = len(bops)

            wastes = extracted.get("waste_records", [])
            if wastes:
                for w in wastes:
                    if isinstance(w, dict):
                        w["well_id"] = well_id
                        w["report_id"] = report_id
                        self.save_waste_record(w)
                results["waste_records"] = len(wastes)

            # 10. Cost Records -> CostRecord
            costs = extracted.get("cost_records", [])
            if costs:
                for c in costs:
                    if isinstance(c, dict):
                        c["well_id"] = well_id
                        self.save_cost_record(c)
                results["cost_records"] = len(costs)

            # 11. Equipment module records -> EquipmentLog
            equipment_logs = extracted.get("equipment_logs", [])
            if equipment_logs:
                saved_equipment = 0
                for log_data in equipment_logs:
                    if not isinstance(log_data, dict):
                        continue
                    item = dict(log_data)
                    item["well_id"] = well_id
                    item["report_id"] = report_id
                    if self.save_equipment_log(item):
                        saved_equipment += 1
                results["equipment_logs"] = saved_equipment

            # 12. Downhole Equipment -> DownholeEquipment
            downhole = extracted.get("downhole_equipment")
            if downhole and isinstance(downhole, dict):
                self.save_downhole_equipment(well_id, downhole)
                results["downhole_equipment"] = 1

        except Exception as e:
            logger.error(f"Error saving imported multi-tab data: {e}")
        return results
        
    # ---------- Drilling Parameters ----------
    def save_drilling_parameters(self, data: dict):
        session = self.create_session()
        try:
            if data.get('report_id'):
                existing = session.query(DrillingParameters).filter(
                    DrillingParameters.report_id == data['report_id']
                ).first()
            elif data.get('well_id') and data.get('report_date'):
                existing = session.query(DrillingParameters).filter(
                    DrillingParameters.well_id == data['well_id'],
                    DrillingParameters.report_date == data['report_date'],
                ).first()
            else:
                existing = None

            if existing:
                for key, value in data.items():
                    if hasattr(existing, key) and key not in ['id', 'well_id', 'report_date', 'report_id']:
                        setattr(existing, key, value)
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                new_record = DrillingParameters(**data)
                session.add(new_record)
                session.flush()
                record_id = new_record.id

            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving drilling parameters: {e}")
            return None
        finally:
            session.close()

    def get_drilling_parameters(
        self,
        well_id: int = None,
        report_id: int = None,
        report_date=None
    ) -> Optional[Dict[str, Any]]:
        session = self.create_session()
        try:
            query = session.query(DrillingParameters)
            if report_id:
                query = query.filter(
                    DrillingParameters.report_id == report_id
                )
            elif well_id:
                query = query.filter(
                    DrillingParameters.well_id == well_id
                )
                if report_date:
                    query = query.filter(
                        DrillingParameters.report_date == report_date
                    )
            params = query.order_by(
                DrillingParameters.report_date.desc()
            ).first()

            if params:
                result = {}
                for column in DrillingParameters.__table__.columns:
                    result[column.name] = getattr(params, column.name)
                return result
            return None
        except Exception as e:
            logger.error(f"Error getting drilling parameters: {e}")
            return None
        finally:
            session.close()

    # ---------- Mud Report ----------
    def save_mud_report(self, data: dict):
        session = self.create_session()
        try:
            if data.get('report_id'):
                existing = session.query(MudReport).filter(
                    MudReport.report_id == data['report_id']
                ).first()
            elif data.get('well_id') and data.get('report_date'):
                existing = session.query(MudReport).filter(
                    MudReport.well_id == data['well_id'],
                    MudReport.report_date == data['report_date'],
                ).first()
            else:
                existing = None

            if existing:
                for key, value in data.items():
                    if hasattr(existing, key) and key not in ['id', 'well_id', 'report_date', 'report_id']:
                        setattr(existing, key, value)
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                new_record = MudReport(**data)
                session.add(new_record)
                session.flush()
                record_id = new_record.id

            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving mud report: {e}")
            return None
        finally:
            session.close()

    def get_mud_report(self, well_id: int = None, report_id: int = None, report_date=None):
        session = self.create_session()
        try:
            query = session.query(MudReport)
            if report_id:
                query = query.filter(MudReport.report_id == report_id)
            elif well_id:
                query = query.filter(MudReport.well_id == well_id)
                if report_date:
                    query = query.filter(MudReport.report_date == report_date)
            report = query.order_by(MudReport.report_date.desc()).first()
            if report:
                return {
                    "id": report.id,
                    "well_id": report.well_id,
                    "report_id": report.report_id,
                    "report_date": report.report_date,
                    "mud_type": report.mud_type,
                    "sample_time": report.sample_time,
                    "mw": report.mw,
                    "pv": report.pv,
                    "yp": report.yp,
                    "funnel_vis": report.funnel_vis,
                    "gel_10s": report.gel_10s,
                    "gel_10m": report.gel_10m,
                    "fl": report.fl,
                    "cake_thickness": report.cake_thickness,
                    "ph": report.ph,
                    "temperature": report.temperature,
                    "solid_percent": report.solid_percent,
                    "oil_percent": report.oil_percent,
                    "water_percent": report.water_percent,
                    "chloride": report.chloride,
                    "volume_hole": report.volume_hole,
                    "total_circulated": report.total_circulated,
                    "loss_downhole": report.loss_downhole,
                    "loss_surface": report.loss_surface,
                    "chemicals_json": report.chemicals_json,
                    "summary": report.summary,
                    "created_at": report.created_at,
                    "updated_at": report.updated_at,
                }
            return None
        except Exception as e:
            logger.error(f"Error getting mud report: {e}")
            return None
        finally:
            session.close()

    # ---------- Cement Report ----------
    def save_cement_report(self, data: dict):
        session = self.create_session()
        try:
            existing = None
            if data.get('section_id') and data.get('well_id'):
                existing = session.query(CementReport).filter(
                    CementReport.well_id == data['well_id'],
                    CementReport.section_id == data['section_id']
                ).first()
            elif data.get('report_id'):
                existing = session.query(CementReport).filter(
                    CementReport.report_id == data['report_id']
                ).first()

            if existing:
                for key, value in data.items():
                    if hasattr(existing, key) and key not in ['id']:
                        setattr(existing, key, value)
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                valid_keys = {c.name for c in CementReport.__table__.columns}
                filtered = {k: v for k, v in data.items() if k in valid_keys}
                new_record = CementReport(**filtered)
                session.add(new_record)
                session.flush()
                record_id = new_record.id

            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving cement report: {e}")
            return None
        finally:
            session.close()

    def get_cement_report(self, well_id=None, section_id=None,
                           report_id=None, report_date=None):
        session = self.create_session()
        try:
            query = session.query(CementReport)
            if section_id:
                query = query.filter(
                    CementReport.section_id == section_id
                )
            elif report_id:
                query = query.filter(
                    CementReport.report_id == report_id
                )
            elif well_id:
                query = query.filter(
                    CementReport.well_id == well_id
                )
            report = query.order_by(
                CementReport.report_date.desc()
            ).first()
            if report:
                result = {}
                for col in CementReport.__table__.columns:
                    result[col.name] = getattr(report, col.name)
                return result
            return None
        except Exception as e:
            logger.error(f"Error getting cement report: {e}")
            return None
        finally:
            session.close()
    # ---------- Casing Report ----------
    def save_casing_report(self, data: dict):
        session = self.create_session()
        try:
            existing = None
            if data.get('section_id') and data.get('well_id'):
                existing = session.query(CasingReport).filter(
                    CasingReport.well_id == data['well_id'],
                    CasingReport.section_id == data['section_id']
                ).first()
            elif data.get('report_id'):
                existing = session.query(CasingReport).filter(
                    CasingReport.report_id == data['report_id']
                ).first()

            if existing:
                for key, value in data.items():
                    if hasattr(existing, key) and key not in ['id']:
                        setattr(existing, key, value)
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                valid_keys = {c.name for c in CasingReport.__table__.columns}
                filtered = {k: v for k, v in data.items() if k in valid_keys}
                new_record = CasingReport(**filtered)
                session.add(new_record)
                session.flush()
                record_id = new_record.id

            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving casing report: {e}")
            return None
        finally:
            session.close()

    def get_casing_report(self, well_id=None, section_id=None,
                           report_id=None, report_date=None):
        session = self.create_session()
        try:
            query = session.query(CasingReport)
            if section_id:
                query = query.filter(
                    CasingReport.section_id == section_id
                )
            elif report_id:
                query = query.filter(
                    CasingReport.report_id == report_id
                )
            elif well_id:
                query = query.filter(
                    CasingReport.well_id == well_id
                )
            report = query.order_by(
                CasingReport.report_date.desc()
            ).first()
            if report:
                result = {}
                for col in CasingReport.__table__.columns:
                    result[col.name] = getattr(report, col.name)
                return result
            return None
        except Exception as e:
            logger.error(f"Error getting casing report: {e}")
            return None
        finally:
            session.close()
    # ---------- Wellbore Schematic ----------
    def save_wellbore_schematic(self, data: dict):
        session = self.create_session()
        try:
            if data.get('report_id'):
                existing = session.query(WellboreSchematic).filter(
                    WellboreSchematic.report_id == data['report_id']
                ).first()
            elif data.get('well_id') and data.get('report_date'):
                existing = session.query(WellboreSchematic).filter(
                    WellboreSchematic.well_id == data['well_id'],
                    WellboreSchematic.report_date == data['report_date'],
                ).first()
            else:
                existing = None

            if existing:
                for key, value in data.items():
                    if hasattr(existing, key) and key not in ['id', 'well_id', 'report_date', 'report_id']:
                        setattr(existing, key, value)
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                new_schematic = WellboreSchematic(**data)
                session.add(new_schematic)
                session.flush()
                record_id = new_schematic.id

            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving wellbore schematic: {e}")
            return None
        finally:
            session.close()

    def get_wellbore_schematic(self, well_id: int = None, report_id: int = None, report_date=None):
        session = self.create_session()
        try:
            query = session.query(WellboreSchematic)
            if report_id:
                query = query.filter(WellboreSchematic.report_id == report_id)
            elif well_id:
                query = query.filter(WellboreSchematic.well_id == well_id)
                if report_date:
                    query = query.filter(WellboreSchematic.report_date == report_date)
            schematic = query.order_by(WellboreSchematic.report_date.desc()).first()
            if schematic:
                return {
                    "id": schematic.id,
                    "well_id": schematic.well_id,
                    "report_id": schematic.report_id,
                    "report_date": schematic.report_date,
                    "schematic_name": schematic.schematic_name,
                    "image_data": schematic.image_data,
                    "layers_json": schematic.layers_json,
                    "elements_json": schematic.elements_json,
                }
            return None
        except Exception as e:
            logger.error(f"Error getting wellbore schematic: {e}")
            return None
        finally:
            session.close()


    # ========== Bit Report ==========
    def save_bit_report(self, well_id: int, report_data: dict):
        session = self.create_session()
        try:
            existing = None
            if report_data.get('report_id'):
                existing = session.query(BitReport).filter(
                    BitReport.report_id == report_data['report_id']
                ).first()
            elif report_data.get('id'):
                existing = session.query(BitReport).filter(
                    BitReport.id == report_data['id']
                ).first()
            
            bit_records = report_data.get('bit_records_json')
            if isinstance(bit_records, (dict, list)):
                bit_records_json = json.dumps(bit_records, indent=2, default=str)
            elif isinstance(bit_records, str):
                bit_records_json = bit_records
            else:
                bit_records_json = "[]"
            
            logger.debug(f"Saving bit report JSON length: {len(bit_records_json)}")
            
            if existing:
                existing.report_date = report_data.get('report_date', existing.report_date)
                existing.report_name = report_data.get('report_name', existing.report_name)
                existing.bit_records_json = bit_records_json
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                new_report = BitReport(
                    well_id=well_id,
                    report_id=report_data.get('report_id'),
                    report_date=report_data.get('report_date', date.today()),
                    report_name=report_data.get('report_name', f"Bit_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"),
                    bit_records_json=bit_records_json,
                    created_at=_now_utc()
                )
                session.add(new_report)
                session.flush()
                record_id = new_report.id
            
            session.commit()
            logger.debug(f"Bit report saved with ID: {record_id}")
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving bit report: {e}")
            return None
        finally:
            session.close()
    # ========== BHA Report ==========
    def save_bha_report(self, well_id: int, bha_data: dict):
        session = self.create_session()
        try:
            if bha_data.get('report_id'):
                existing = session.query(BHAReport).filter(
                    BHAReport.report_id == bha_data['report_id']
                ).first()
            elif well_id and bha_data.get('bha_name'):
                existing = session.query(BHAReport).filter(
                    BHAReport.well_id == well_id,
                    BHAReport.bha_name == bha_data.get('bha_name'),
                ).first()
            else:
                existing = None

            if existing:
                existing.bha_name = bha_data.get('bha_name', existing.bha_name)
                existing.bha_data_json = bha_data.get('bha_data', existing.bha_data_json)
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                report = BHAReport(
                    well_id=well_id,
                    report_id=bha_data.get('report_id'),
                    bha_name=bha_data.get('bha_name', 'Unnamed BHA'),
                    bha_data_json=bha_data.get('bha_data', {}),
                    created_at=_now_utc()
                )
                session.add(report)
                session.flush()
                record_id = report.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving BHA report: {e}")
            return None
        finally:
            session.close()

    def get_bha_report(self, well_id: int, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(BHAReport).filter(
                BHAReport.well_id == well_id
            )
            if report_id:
                query = query.filter(BHAReport.report_id == report_id)
            bha = query.order_by(BHAReport.updated_at.desc()).first()
            if bha:
                return {
                    "id": bha.id,
                    "well_id": bha.well_id,
                    "report_id": bha.report_id,
                    "bha_name": bha.bha_name,
                    "bha_configs": bha.bha_data_json,
                    "created_at": bha.created_at,
                    "updated_at": bha.updated_at
                }
            return None
        except Exception as e:
            logger.error(f"Error getting BHA report: {e}")
            return None
        finally:
            session.close()
            
    # ========== Downhole Equipment ==========
    def save_downhole_equipment(self, well_id: int, equipment_data: dict):
        session = self.create_session()
        try:
            if equipment_data.get('report_id'):
                existing = session.query(DownholeEquipment).filter(
                    DownholeEquipment.report_id == equipment_data['report_id']
                ).first()
            elif well_id:
                existing = session.query(DownholeEquipment).filter(
                    DownholeEquipment.well_id == well_id
                ).first()
            else:
                existing = None

            if existing:
                existing.equipment_data_json = equipment_data.get('equipment_data_json', existing.equipment_data_json)
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                equip = DownholeEquipment(
                    well_id=well_id,
                    report_id=equipment_data.get('report_id'),
                    equipment_data_json=equipment_data.get('equipment_data_json', {}),
                    created_at=_now_utc()
                )
                session.add(equip)
                session.flush()
                record_id = equip.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving downhole equipment: {e}")
            return None
        finally:
            session.close()

    def get_downhole_equipment(self, well_id: int, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(DownholeEquipment).filter(
                DownholeEquipment.well_id == well_id
            )
            if report_id:
                query = query.filter(
                    DownholeEquipment.report_id == report_id
                )
            equip = query.order_by(
                DownholeEquipment.updated_at.desc()
            ).first()
            if equip:
                return {
                    "id": equip.id,
                    "well_id": equip.well_id,
                    "report_id": equip.report_id,
                    "equipment_data": equip.equipment_data_json,
                    "created_at": equip.created_at,
                    "updated_at": equip.updated_at
                }
            return None
        except Exception as e:
            logger.error(f"Error getting downhole equipment: {e}")
            return None
        finally:
            session.close()

 
    # ========== Formation Report ==========
    def save_formation_report(self, well_id: int, formation_data: dict):
        session = self.create_session()
        try:
            if formation_data.get('report_id'):
                existing = session.query(FormationReport).filter(
                    FormationReport.report_id == formation_data['report_id']
                ).first()
            elif well_id and formation_data.get('report_name'):
                existing = session.query(FormationReport).filter(
                    FormationReport.well_id == well_id,
                    FormationReport.report_name == formation_data['report_name'],
                ).first()
            else:
                existing = None

            if existing:
                existing.report_name = formation_data.get('report_name', existing.report_name)
                existing.formations_json = formation_data.get('formations', existing.formations_json)
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                report = FormationReport(
                    well_id=well_id,
                    report_id=formation_data.get('report_id'),
                    report_name=formation_data.get('report_name', f"Formation_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"),
                    formations_json=formation_data.get('formations', []),
                    created_at=_now_utc()
                )
                session.add(report)
                session.flush()
                record_id = report.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving formation report: {e}")
            return None
        finally:
            session.close()

    def get_formation_report(self, well_id: int):
        session = self.create_session()
        try:
            report = session.query(FormationReport).filter(
                FormationReport.well_id == well_id
            ).first()
            if report:
                return {
                    "id": report.id,
                    "well_id": report.well_id,
                    "report_name": report.report_name,
                    "formations": report.formations_json or [],
                    "created_at": report.created_at,
                    "updated_at": report.updated_at,
                }
            return None
        except Exception as e:
            logger.error(f"Error getting formation report: {e}")
            return None
        finally:
            session.close()
        
    # ========== Trip Sheet ==========
    def save_trip_sheet_entries(self, entries: list):
        session = self.create_session()
        try:
            for entry_data in entries:
                # اصلاح: استفاده از dict access به جای object access
                report_id = entry_data.get('report_id') if isinstance(entry_data, dict) else getattr(entry_data, 'report_id', None)
                well_id = entry_data.get('well_id') if isinstance(entry_data, dict) else getattr(entry_data, 'well_id', None)
                time_val = entry_data.get('time') if isinstance(entry_data, dict) else getattr(entry_data, 'time', None)
                activity = entry_data.get('activity') if isinstance(entry_data, dict) else getattr(entry_data, 'activity', '')

                if isinstance(time_val, str):
                    from datetime import datetime
                    time_val = datetime.strptime(time_val, "%H:%M").time()

                depth = entry_data.get('depth', 0) if isinstance(entry_data, dict) else getattr(entry_data, 'depth', 0)
                cum_trip = entry_data.get('cum_trip', 0) if isinstance(entry_data, dict) else getattr(entry_data, 'cum_trip', 0)
                duration = entry_data.get('duration', 0) if isinstance(entry_data, dict) else getattr(entry_data, 'duration', 0)
                remarks = entry_data.get('remarks', '') if isinstance(entry_data, dict) else getattr(entry_data, 'remarks', '')
                supervisor = entry_data.get('supervisor', '') if isinstance(entry_data, dict) else getattr(entry_data, 'supervisor', '')
                verified = entry_data.get('verified', False) if isinstance(entry_data, dict) else getattr(entry_data, 'verified', False)
                section_id = entry_data.get('section_id') if isinstance(entry_data, dict) else getattr(entry_data, 'section_id', None)
                created_by = entry_data.get('created_by') if isinstance(entry_data, dict) else getattr(entry_data, 'created_by', None)

                new_entry = TripSheetEntry(
                    well_id=well_id,
                    section_id=section_id,
                    report_id=report_id,
                    time=time_val,
                    activity=activity,
                    depth=depth,
                    cum_trip=cum_trip,
                    duration=duration,
                    remarks=remarks,
                    supervisor=supervisor,
                    verified=verified,
                    created_by=created_by
                )
                session.add(new_entry)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving trip sheet entries: {e}")
            return False
        finally:
            session.close()


    def load_trip_sheet_entries(self, well_id: int = None, section_id: int = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(TripSheetEntry)
            if report_id:
                query = query.filter(TripSheetEntry.report_id == report_id)
            elif well_id:
                query = query.filter(TripSheetEntry.well_id == well_id)
            if section_id:
                query = query.filter(TripSheetEntry.section_id == section_id)
            entries = query.order_by(TripSheetEntry.time).all()
            return [
                {
                    'id': e.id,
                    'well_id': e.well_id,
                    'section_id': e.section_id,
                    'report_id': e.report_id,
                    'time': e.time.strftime("%H:%M") if e.time else "",
                    'activity': e.activity,
                    'depth': e.depth,
                    'cum_trip': e.cum_trip,
                    'duration': e.duration,
                    'remarks': e.remarks,
                    'supervisor': e.supervisor,
                    'verified': e.verified,
                    'created_at': e.created_at,
                    'updated_at': e.updated_at
                }
                for e in entries
            ]
        except Exception as e:
            logger.error(f"Error loading trip sheet entries: {e}")
            return []
        finally:
            session.close()

    # ========== Survey Points ==========
    def save_survey_points(self, points: list):
        session = self.create_session()
        try:
            for point_data in points:
                # اصلاح: پشتیبانی از dict و object
                def get_val(key, default=None):
                    if isinstance(point_data, dict):
                        return point_data.get(key, default)
                    return getattr(point_data, key, default)

                well_id = get_val('well_id')
                md = get_val('md')
                report_id = get_val('report_id')

                existing = None
                if report_id:
                    existing = session.query(SurveyPoint).filter(
                        SurveyPoint.well_id == well_id,
                        SurveyPoint.report_id == report_id,
                        SurveyPoint.md == md
                    ).first()
                else:
                    existing = session.query(SurveyPoint).filter(
                        SurveyPoint.well_id == well_id,
                        SurveyPoint.md == md
                    ).first()

                if existing:
                    existing.inc = get_val('inc', 0)
                    existing.azi = get_val('azi', 0)
                    existing.tvd = get_val('tvd', 0)
                    existing.north = get_val('north', 0)
                    existing.east = get_val('east', 0)
                    existing.vs = get_val('vs', 0)
                    existing.hd = get_val('hd', 0)
                    existing.dls = get_val('dls', 0)
                    existing.tool = get_val('tool', 'MWD')
                    existing.remarks = get_val('remarks', '')
                    existing.updated_at = _now_utc()
                else:
                    new_point = SurveyPoint(
                        well_id=well_id,
                        section_id=get_val('section_id'),
                        calculation_id=get_val('calculation_id'),
                        report_id=report_id,
                        md=md,
                        inc=get_val('inc', 0),
                        azi=get_val('azi', 0),
                        tvd=get_val('tvd', 0),
                        north=get_val('north', 0),
                        east=get_val('east', 0),
                        vs=get_val('vs', 0),
                        hd=get_val('hd', 0),
                        dls=get_val('dls', 0),
                        tool=get_val('tool', 'MWD'),
                        remarks=get_val('remarks', ''),
                        measured_at=get_val('measured_at', _now_utc()),
                        created_by=get_val('created_by')
                    )
                    session.add(new_point)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving survey points: {e}")
            return False
        finally:
            session.close()

    def load_survey_points(self, well_id: int = None, calculation_id: int = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(SurveyPoint)
            if report_id:
                query = query.filter(SurveyPoint.report_id == report_id)
            elif well_id:
                query = query.filter(SurveyPoint.well_id == well_id)
            if calculation_id:
                query = query.filter(SurveyPoint.calculation_id == calculation_id)
            points = query.order_by(SurveyPoint.md).all()
            return [
                {
                    'id': p.id,
                    'well_id': p.well_id,
                    'section_id': p.section_id,
                    'calculation_id': p.calculation_id,
                    'report_id': p.report_id,
                    'md': p.md,
                    'inc': p.inc,
                    'azi': p.azi,
                    'tvd': p.tvd,
                    'north': p.north,
                    'east': p.east,
                    'vs': p.vs,
                    'hd': p.hd,
                    'dls': p.dls,
                    'tool': p.tool,
                    'remarks': p.remarks,
                    'measured_at': p.measured_at,
                    'created_at': p.created_at,
                    'updated_at': p.updated_at
                }
                for p in points
            ]
        except Exception as e:
            logger.error(f"Error loading survey points: {e}")
            return []
        finally:
            session.close()

    # ========== Trajectory Calculation ==========
    def save_trajectory_calculation(self, calculation_data: dict):
        session = self.create_session()
        try:
            if calculation_data.get('report_id'):
                existing = session.query(TrajectoryCalculation).filter(
                    TrajectoryCalculation.report_id == calculation_data['report_id']
                ).first()
            elif calculation_data.get('well_id') and calculation_data.get('calculation_date'):
                existing = session.query(TrajectoryCalculation).filter(
                    TrajectoryCalculation.well_id == calculation_data['well_id'],
                    TrajectoryCalculation.calculation_date == calculation_data['calculation_date']
                ).first()
            else:
                existing = None

            if existing:
                existing.method = calculation_data.get('method', existing.method)
                existing.parameters_json = calculation_data.get('parameters', existing.parameters_json)
                existing.results_json = calculation_data.get('results', existing.results_json)
                existing.target_north = calculation_data.get('target_north', existing.target_north)
                existing.target_east = calculation_data.get('target_east', existing.target_east)
                existing.target_tvd = calculation_data.get('target_tvd', existing.target_tvd)
                existing.total_hd = calculation_data.get('total_hd', existing.total_hd)
                existing.total_tvd = calculation_data.get('total_tvd', existing.total_tvd)
                existing.total_md = calculation_data.get('total_md', existing.total_md)
                existing.description = calculation_data.get('description', existing.description)
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                calc = TrajectoryCalculation(
                    well_id=calculation_data['well_id'],
                    section_id=calculation_data.get('section_id'),
                    report_id=calculation_data.get('report_id'),
                    method=calculation_data.get('method', 'Minimum Curvature'),
                    calculation_date=calculation_data.get('calculation_date', date.today()),
                    parameters_json=calculation_data.get('parameters', {}),
                    results_json=calculation_data.get('results', {}),
                    target_north=calculation_data.get('target_north'),
                    target_east=calculation_data.get('target_east'),
                    target_tvd=calculation_data.get('target_tvd'),
                    total_hd=calculation_data.get('total_hd'),
                    total_tvd=calculation_data.get('total_tvd'),
                    total_md=calculation_data.get('total_md'),
                    description=calculation_data.get('description', ''),
                    calculated_by=calculation_data.get('calculated_by')
                )
                session.add(calc)
                session.flush()
                record_id = calc.id

                # Save associated survey points
                survey_points = calculation_data.get('survey_points', [])
                for point in survey_points:
                    new_point = SurveyPoint(
                        well_id=calc.well_id,
                        section_id=calc.section_id,
                        calculation_id=record_id,
                        report_id=calculation_data.get('report_id'),
                        md=point['md'],
                        inc=point['inc'],
                        azi=point['azi'],
                        tvd=point.get('tvd'),
                        north=point.get('north'),
                        east=point.get('east'),
                        vs=point.get('vs'),
                        hd=point.get('hd'),
                        dls=point.get('dls'),
                        tool=point.get('tool', 'MWD'),
                        remarks=point.get('remarks')
                    )
                    session.add(new_point)

            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving trajectory calculation: {e}")
            return None
        finally:
            session.close()

    def load_trajectory_calculations(self, well_id: int = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(TrajectoryCalculation)
            if report_id:
                query = query.filter(TrajectoryCalculation.report_id == report_id)
            elif well_id:
                query = query.filter(TrajectoryCalculation.well_id == well_id)
            calcs = query.order_by(TrajectoryCalculation.calculation_date.desc()).all()
            return [
                {
                    'id': c.id,
                    'well_id': c.well_id,
                    'section_id': c.section_id,
                    'report_id': c.report_id,
                    'method': c.method,
                    'calculation_date': c.calculation_date,
                    'parameters': c.parameters_json or {},
                    'results': c.results_json or {},
                    'target_north': c.target_north,
                    'target_east': c.target_east,
                    'target_tvd': c.target_tvd,
                    'total_hd': c.total_hd,
                    'total_tvd': c.total_tvd,
                    'total_md': c.total_md,
                    'description': c.description,
                    'calculated_by': c.calculated_by,
                    'created_at': c.created_at,
                    'updated_at': c.updated_at,
                    'survey_points': self.load_survey_points(calculation_id=c.id, report_id=report_id)
                }
                for c in calcs
            ]
        except Exception as e:
            logger.error(f"Error loading trajectory calculations: {e}")
            return []
        finally:
            session.close()

    # ========== Trajectory Plot ==========
    def save_trajectory_plot(self, plot_data: dict):
        session = self.create_session()
        try:
            plot = TrajectoryPlot(
                calculation_id=plot_data.get('calculation_id'),
                report_id=plot_data.get('report_id'),
                plot_type=plot_data.get('plot_type'),
                title=plot_data.get('title', 'Trajectory Plot'),
                plot_data_json=plot_data.get('plot_data', {}),
                image_data=plot_data.get('image_data'),
                image_format=plot_data.get('image_format', 'png'),
                created_by=plot_data.get('created_by')
            )
            session.add(plot)
            session.commit()
            return plot.id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving trajectory plot: {e}")
            return None
        finally:
            session.close()

    def load_trajectory_plots(self, calculation_id: int = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(TrajectoryPlot)
            if report_id:
                query = query.filter(TrajectoryPlot.report_id == report_id)
            elif calculation_id:
                query = query.filter(TrajectoryPlot.calculation_id == calculation_id)
            plots = query.order_by(TrajectoryPlot.created_at.desc()).all()
            return [
                {
                    'id': p.id,
                    'calculation_id': p.calculation_id,
                    'report_id': p.report_id,
                    'plot_type': p.plot_type,
                    'title': p.title,
                    'plot_data': p.plot_data_json or {},
                    'image_data': p.image_data,
                    'image_format': p.image_format,
                    'created_at': p.created_at
                }
                for p in plots
            ]
        except Exception as e:
            logger.error(f"Error loading trajectory plots: {e}")
            return []
        finally:
            session.close()

    # ========== Logistics Personnel ==========
    def save_logistics_personnel(self, personnel_data: dict):
        session = self.create_session()
        try:
            if personnel_data.get("id"):
                personnel = session.query(LogisticsPersonnel).filter(
                    LogisticsPersonnel.id == personnel_data["id"]
                ).first()
                if personnel:
                    for key, value in personnel_data.items():
                        if hasattr(personnel, key) and key != 'id':
                            setattr(personnel, key, value)
                    personnel.updated_at = _now_utc()
                    record_id = personnel.id
                else:
                    return None
            else:
                personnel = LogisticsPersonnel(
                    well_id=personnel_data["well_id"],
                    section_id=personnel_data.get("section_id"),
                    report_id=personnel_data.get("report_id"),
                    name=personnel_data["name"],
                    position=personnel_data.get("position", ""),
                    company=personnel_data.get("company", ""),
                    arrival_date=personnel_data.get("arrival_date"),
                    departure_date=personnel_data.get("departure_date"),
                    contact_info=personnel_data.get("contact_info", ""),
                    remarks=personnel_data.get("remarks", ""),
                    created_by=personnel_data.get("created_by")
                )
                session.add(personnel)
                session.flush()
                record_id = personnel.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving logistics personnel: {e}")
            return None
        finally:
            session.close()

    def get_logistics_personnel(self, well_id: int = None, section_id: int = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(LogisticsPersonnel)
            if report_id:
                query = query.filter(LogisticsPersonnel.report_id == report_id)
            elif well_id:
                query = query.filter(LogisticsPersonnel.well_id == well_id)
            if section_id:
                query = query.filter(LogisticsPersonnel.section_id == section_id)
            personnel = query.order_by(LogisticsPersonnel.arrival_date.desc()).all()
            return [
                {
                    "id": p.id,
                    "well_id": p.well_id,
                    "section_id": p.section_id,
                    "report_id": p.report_id,
                    "name": p.name,
                    "position": p.position,
                    "company": p.company,
                    "arrival_date": p.arrival_date,
                    "departure_date": p.departure_date,
                    "contact_info": p.contact_info,
                    "remarks": p.remarks,
                    "created_at": p.created_at,
                    "updated_at": p.updated_at
                }
                for p in personnel
            ]
        except Exception as e:
            logger.error(f"Error getting logistics personnel: {e}")
            return []
        finally:
            session.close()

    def delete_logistics_personnel(self, personnel_id: int):
        session = self.create_session()
        try:
            personnel = session.query(LogisticsPersonnel).filter(
                LogisticsPersonnel.id == personnel_id
            ).first()
            if personnel:
                session.delete(personnel)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting logistics personnel: {e}")
            return False
        finally:
            session.close()

    # ========== Service Company POB ==========
    def save_service_company_pob(self, pob_data: dict):
        session = self.create_session()
        try:
            if pob_data.get("id"):
                pob = session.query(ServiceCompanyPOB).filter(ServiceCompanyPOB.id == pob_data["id"]).first()
                if pob:
                    for key, value in pob_data.items():
                        if hasattr(pob, key) and key != 'id':
                            setattr(pob, key, value)
                    pob.updated_at = _now_utc()
                    record_id = pob.id
                else:
                    return None
            else:
                pob = ServiceCompanyPOB(
                    well_id=pob_data["well_id"],
                    section_id=pob_data.get("section_id"),
                    report_id=pob_data.get("report_id"),
                    company_name=pob_data["company_name"],
                    service_type=pob_data.get("service_type", ""),
                    personnel_count=pob_data.get("personnel_count", 0),
                    date_in=pob_data.get("date_in"),
                    date_out=pob_data.get("date_out"),
                    remarks=pob_data.get("remarks", ""),
                    created_by=pob_data.get("created_by")
                )
                session.add(pob)
                session.flush()
                record_id = pob.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving service company POB: {e}")
            return None
        finally:
            session.close()

    def get_service_company_pob(self, well_id: int = None, section_id: int = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(ServiceCompanyPOB)
            if report_id:
                query = query.filter(ServiceCompanyPOB.report_id == report_id)
            elif well_id:
                query = query.filter(ServiceCompanyPOB.well_id == well_id)
            if section_id:
                query = query.filter(ServiceCompanyPOB.section_id == section_id)
            pobs = query.order_by(ServiceCompanyPOB.date_in.desc()).all()
            return [
                {
                    "id": p.id,
                    "well_id": p.well_id,
                    "section_id": p.section_id,
                    "report_id": p.report_id,
                    "company_name": p.company_name,
                    "service_type": p.service_type,
                    "personnel_count": p.personnel_count,
                    "date_in": p.date_in,
                    "date_out": p.date_out,
                    "remarks": p.remarks,
                    "created_at": p.created_at,
                    "updated_at": p.updated_at
                }
                for p in pobs
            ]
        except Exception as e:
            logger.error(f"Error getting service company POB: {e}")
            return []
        finally:
            session.close()

    def calculate_total_pob(self, well_id: int = None, section_id: int = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(ServiceCompanyPOB)
            if report_id:
                query = query.filter(ServiceCompanyPOB.report_id == report_id)
            elif well_id:
                query = query.filter(ServiceCompanyPOB.well_id == well_id)
            if section_id:
                query = query.filter(ServiceCompanyPOB.section_id == section_id)
            pobs = query.all()
            return sum(p.personnel_count for p in pobs)
        except Exception as e:
            logger.error(f"Error calculating total POB: {e}")
            return 0
        finally:
            session.close()
    
    def delete_service_company_pob(self, pob_id: int):
        session = self.create_session()
        try:
            pob = session.query(ServiceCompanyPOB).filter(
                ServiceCompanyPOB.id == pob_id
            ).first()
            if pob:
                session.delete(pob)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting service company POB: {e}")
            return False
        finally:
            session.close()
            
    # ========== Fuel/Water Inventory ==========
    def save_fuel_water_inventory(self, inventory_data: dict):
        session = self.create_session()
        try:
            if 'report_id' in inventory_data and inventory_data['report_id']:
                existing = session.query(FuelWaterInventory).filter(
                    FuelWaterInventory.report_id == inventory_data['report_id']
                ).first()
            elif 'well_id' in inventory_data and 'report_date' in inventory_data:
                existing = session.query(FuelWaterInventory).filter(
                    FuelWaterInventory.well_id == inventory_data['well_id'],
                    FuelWaterInventory.report_date == inventory_data['report_date']
                ).first()
            else:
                existing = None

            fuel_consumed = inventory_data.get("fuel_consumed", 0.0)
            fuel_stock = inventory_data.get("fuel_stock", 0.0)
            water_consumed = inventory_data.get("water_consumed", 0.0)
            water_stock = inventory_data.get("water_stock", 0.0)
            fuel_remaining = fuel_stock - fuel_consumed
            water_remaining = water_stock - water_consumed
            days_remaining_fuel = fuel_remaining / fuel_consumed if fuel_consumed > 0 else 0
            days_remaining_water = water_remaining / water_consumed if water_consumed > 0 else 0

            if existing:
                for key, value in inventory_data.items():
                    if hasattr(existing, key) and key not in ['id', 'well_id', 'report_date', 'report_id']:
                        setattr(existing, key, value)
                existing.fuel_remaining = fuel_remaining
                existing.water_remaining = water_remaining
                existing.days_remaining_fuel = days_remaining_fuel
                existing.days_remaining_water = days_remaining_water
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                inventory = FuelWaterInventory(
                    well_id=inventory_data["well_id"],
                    section_id=inventory_data.get("section_id"),
                    report_id=inventory_data.get("report_id"),
                    report_date=inventory_data["report_date"],
                    fuel_type=inventory_data.get("fuel_type", "Diesel"),
                    fuel_consumed=fuel_consumed,
                    fuel_stock=fuel_stock,
                    fuel_received=inventory_data.get("fuel_received", 0.0),
                    water_consumed=water_consumed,
                    water_stock=water_stock,
                    water_received=inventory_data.get("water_received", 0.0),
                    fuel_remaining=fuel_remaining,
                    water_remaining=water_remaining,
                    days_remaining_fuel=days_remaining_fuel,
                    days_remaining_water=days_remaining_water,
                    created_by=inventory_data.get("created_by")
                )
                session.add(inventory)
                session.flush()
                record_id = inventory.id

            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving fuel/water inventory: {e}")
            return None
        finally:
            session.close()

    def get_fuel_water_inventory(self, well_id: int = None, report_id: int = None, report_date: date = None):
        session = self.create_session()
        try:
            query = session.query(FuelWaterInventory)
            if report_id:
                query = query.filter(FuelWaterInventory.report_id == report_id)
            elif well_id:
                query = query.filter(FuelWaterInventory.well_id == well_id)
                if report_date:
                    query = query.filter(FuelWaterInventory.report_date == report_date)
            inventories = query.order_by(FuelWaterInventory.report_date.desc()).all()
            return [
                {
                    "id": i.id,
                    "well_id": i.well_id,
                    "section_id": i.section_id,
                    "report_id": i.report_id,
                    "report_date": i.report_date,
                    "fuel_type": i.fuel_type,
                    "fuel_consumed": i.fuel_consumed,
                    "fuel_stock": i.fuel_stock,
                    "fuel_received": i.fuel_received,
                    "fuel_remaining": i.fuel_remaining,
                    "water_consumed": i.water_consumed,
                    "water_stock": i.water_stock,
                    "water_received": i.water_received,
                    "water_remaining": i.water_remaining,
                    "days_remaining_fuel": i.days_remaining_fuel,
                    "days_remaining_water": i.days_remaining_water,
                    "created_at": i.created_at,
                    "updated_at": i.updated_at
                }
                for i in inventories
            ]
        except Exception as e:
            logger.error(f"Error getting fuel/water inventory: {e}")
            return []
        finally:
            session.close()

    # ========== Bulk Materials ==========
    def save_bulk_material(self, material_data: dict):
        session = self.create_session()
        try:
            if material_data.get('report_id'):
                existing = session.query(BulkMaterials).filter(
                    BulkMaterials.report_id == material_data['report_id'],
                    BulkMaterials.material_name == material_data['material_name']
                ).first()
            elif material_data.get('well_id') and material_data.get('report_date'):
                existing = session.query(BulkMaterials).filter(
                    BulkMaterials.well_id == material_data['well_id'],
                    BulkMaterials.report_date == material_data['report_date'],
                    BulkMaterials.material_name == material_data['material_name']
                ).first()
            else:
                existing = None

            if existing:
                for key, value in material_data.items():
                    if hasattr(existing, key) and key not in ['id', 'well_id', 'report_date', 'report_id']:
                        setattr(existing, key, value)
                existing.current_stock = existing.initial_stock + existing.received - existing.used
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                initial_stock = material_data.get("initial_stock", 0.0)
                received = material_data.get("received", 0.0)
                used = material_data.get("used", 0.0)
                current_stock = initial_stock + received - used
                material = BulkMaterials(
                    well_id=material_data["well_id"],
                    section_id=material_data.get("section_id"),
                    report_id=material_data.get("report_id"),
                    report_date=material_data["report_date"],
                    material_name=material_data["material_name"],
                    unit=material_data.get("unit", "kg"),
                    initial_stock=initial_stock,
                    received=received,
                    used=used,
                    current_stock=current_stock,
                    created_by=material_data.get("created_by")
                )
                session.add(material)
                session.flush()
                record_id = material.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving bulk material: {e}")
            return None
        finally:
            session.close()

    def get_bulk_materials(self, well_id: int = None, report_id: int = None, report_date: date = None):
        session = self.create_session()
        try:
            query = session.query(BulkMaterials)
            if report_id:
                query = query.filter(BulkMaterials.report_id == report_id)
            elif well_id:
                query = query.filter(BulkMaterials.well_id == well_id)
                if report_date:
                    query = query.filter(BulkMaterials.report_date == report_date)
            materials = query.order_by(BulkMaterials.material_name).all()
            return [
                {
                    "id": m.id,
                    "well_id": m.well_id,
                    "section_id": m.section_id,
                    "report_id": m.report_id,
                    "report_date": m.report_date,
                    "material_name": m.material_name,
                    "unit": m.unit,
                    "initial_stock": m.initial_stock,
                    "received": m.received,
                    "used": m.used,
                    "current_stock": m.current_stock,
                    "created_at": m.created_at,
                    "updated_at": m.updated_at
                }
                for m in materials
            ]
        except Exception as e:
            logger.error(f"Error getting bulk materials: {e}")
            return []
        finally:
            session.close()

    def calculate_bulk_totals(self, well_id: int = None, report_id: int = None, report_date: date = None):
        session = self.create_session()
        try:
            query = session.query(BulkMaterials)
            if report_id:
                query = query.filter(BulkMaterials.report_id == report_id)
            elif well_id:
                query = query.filter(BulkMaterials.well_id == well_id)
                if report_date:
                    query = query.filter(BulkMaterials.report_date == report_date)
            materials = query.all()
            totals = {
                "total_initial_stock": 0.0,
                "total_received": 0.0,
                "total_used": 0.0,
                "total_current_stock": 0.0,
                "material_count": len(materials)
            }
            for m in materials:
                totals["total_initial_stock"] += m.initial_stock or 0
                totals["total_received"] += m.received or 0
                totals["total_used"] += m.used or 0
                totals["total_current_stock"] += m.current_stock or 0
            return totals
        except Exception as e:
            logger.error(f"Error calculating bulk totals: {e}")
            return {}
        finally:
            session.close()

    # ========== Transport Log ==========
    def save_transport_log(self, log_data: dict):
        session = self.create_session()
        try:
            if log_data.get("id"):
                log = session.query(TransportLog).filter(TransportLog.id == log_data["id"]).first()
                if log:
                    for key, value in log_data.items():
                        if hasattr(log, key) and key != 'id':
                            setattr(log, key, value)
                    log.updated_at = _now_utc()
                    record_id = log.id
                else:
                    return None
            else:
                log = TransportLog(
                    well_id=log_data["well_id"],
                    section_id=log_data.get("section_id"),
                    report_id=log_data.get("report_id"),
                    log_date=log_data["log_date"],
                    vehicle_type=log_data["vehicle_type"],
                    vehicle_name=log_data["vehicle_name"],
                    vehicle_id=log_data.get("vehicle_id"),
                    arrival_time=log_data.get("arrival_time"),
                    departure_time=log_data.get("departure_time"),
                    duration=log_data.get("duration"),
                    passengers_in=log_data.get("passengers_in", 0),
                    passengers_out=log_data.get("passengers_out", 0),
                    cargo_description=log_data.get("cargo_description", ""),
                    status=log_data.get("status", "Scheduled"),
                    purpose=log_data.get("purpose", ""),
                    remarks=log_data.get("remarks", ""),
                    created_by=log_data.get("created_by")
                )
                session.add(log)
                session.flush()
                record_id = log.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving transport log: {e}")
            return None
        finally:
            session.close()

    def get_transport_logs(self, well_id: int = None, vehicle_type: str = None, log_date: date = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(TransportLog)
            if report_id:
                query = query.filter(TransportLog.report_id == report_id)
            elif well_id:
                query = query.filter(TransportLog.well_id == well_id)
            if vehicle_type:
                query = query.filter(TransportLog.vehicle_type == vehicle_type)
            if log_date:
                query = query.filter(TransportLog.log_date == log_date)
            logs = query.order_by(TransportLog.log_date.desc(), TransportLog.arrival_time).all()
            return [
                {
                    "id": l.id,
                    "well_id": l.well_id,
                    "section_id": l.section_id,
                    "report_id": l.report_id,
                    "log_date": l.log_date,
                    "vehicle_type": l.vehicle_type,
                    "vehicle_name": l.vehicle_name,
                    "vehicle_id": l.vehicle_id,
                    "arrival_time": l.arrival_time.strftime("%H:%M") if l.arrival_time else "",
                    "departure_time": l.departure_time.strftime("%H:%M") if l.departure_time else "",
                    "duration": l.duration,
                    "passengers_in": l.passengers_in,
                    "passengers_out": l.passengers_out,
                    "cargo_description": l.cargo_description,
                    "status": l.status,
                    "purpose": l.purpose,
                    "remarks": l.remarks,
                    "created_at": l.created_at,
                    "updated_at": l.updated_at
                }
                for l in logs
            ]
        except Exception as e:
            logger.error(f"Error getting transport logs: {e}")
            return []
        finally:
            session.close()

    # ========== Transport Notes ==========
    def save_transport_note(self, note_data: dict):
        session = self.create_session()
        try:
            if note_data.get("id"):
                note = session.query(TransportNotes).filter(TransportNotes.id == note_data["id"]).first()
                if note:
                    for key, value in note_data.items():
                        if hasattr(note, key) and key != 'id':
                            setattr(note, key, value)
                    note.updated_at = _now_utc()
                    record_id = note.id
                else:
                    return None
            else:
                note = TransportNotes(
                    well_id=note_data["well_id"],
                    section_id=note_data.get("section_id"),
                    report_id=note_data.get("report_id"),
                    note_date=note_data["note_date"],
                    title=note_data.get("title", ""),
                    content=note_data["content"],
                    category=note_data.get("category", "General"),
                    priority=note_data.get("priority", "Normal"),
                    created_by=note_data.get("created_by")
                )
                session.add(note)
                session.flush()
                record_id = note.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving transport note: {e}")
            return None
        finally:
            session.close()

    def get_transport_notes(self, well_id: int = None, category: str = None, note_date: date = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(TransportNotes)
            if report_id:
                query = query.filter(TransportNotes.report_id == report_id)
            elif well_id:
                query = query.filter(TransportNotes.well_id == well_id)
            if category:
                query = query.filter(TransportNotes.category == category)
            if note_date:
                query = query.filter(TransportNotes.note_date == note_date)
            notes = query.order_by(TransportNotes.note_date.desc(), TransportNotes.priority).all()
            return [
                {
                    "id": n.id,
                    "well_id": n.well_id,
                    "section_id": n.section_id,
                    "report_id": n.report_id,
                    "note_date": n.note_date,
                    "title": n.title,
                    "content": n.content,
                    "category": n.category,
                    "priority": n.priority,
                    "created_at": n.created_at,
                    "updated_at": n.updated_at
                }
                for n in notes
            ]
        except Exception as e:
            logger.error(f"Error getting transport notes: {e}")
            return []
        finally:
            session.close()

    # ========== Safety Report ==========
    def save_safety_report(self, report_data: dict):
        session = self.create_session()
        try:
            if report_data.get('report_id'):
                existing = session.query(SafetyReport).filter(
                    SafetyReport.report_id == report_data['report_id']
                ).first()
            elif report_data.get('well_id') and report_data.get('report_date'):
                existing = session.query(SafetyReport).filter(
                    SafetyReport.well_id == report_data['well_id'],
                    SafetyReport.report_date == report_data['report_date'],
                    SafetyReport.report_type == report_data.get('report_type', 'Daily')
                ).first()
            else:
                existing = None

            if existing:
                for key, value in report_data.items():
                    if hasattr(existing, key) and key not in ['id', 'well_id', 'report_date', 'report_id']:
                        setattr(existing, key, value)
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                report = SafetyReport(**report_data)
                session.add(report)
                session.flush()
                record_id = report.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving safety report: {e}")
            return None
        finally:
            session.close()

    def get_safety_report(self, well_id: int = None, report_id: int = None, report_date: date = None, report_type: str = 'Daily'):
        session = self.create_session()
        try:
            query = session.query(SafetyReport)
            if report_id:
                query = query.filter(SafetyReport.report_id == report_id)
            elif well_id:
                query = query.filter(SafetyReport.well_id == well_id, SafetyReport.report_type == report_type)
                if report_date:
                    query = query.filter(SafetyReport.report_date == report_date)
            report = query.order_by(SafetyReport.report_date.desc()).first()
            if report:
                return {
                    'id': report.id,
                    'well_id': report.well_id,
                    'section_id': report.section_id,
                    'report_id': report.report_id,
                    'report_date': report.report_date,
                    'report_type': report.report_type,
                    'title': report.title,
                    'last_fire_drill': report.last_fire_drill,
                    'last_bop_drill': report.last_bop_drill,
                    'last_h2s_drill': report.last_h2s_drill,
                    'days_without_lti': report.days_without_lti,
                    'lti_count': report.lti_count,
                    'near_miss_count': report.near_miss_count,
                    'last_rams_test': report.last_rams_test,
                    'test_pressure': report.test_pressure,
                    'last_koomey_test': report.last_koomey_test,
                    'days_since_last_test': report.days_since_last_test,
                    'bop_stack_json': report.bop_stack_json,
                    'recycled_volume': report.recycled_volume,
                    'waste_ph': report.waste_ph,
                    'turbidity': report.turbidity,
                    'hardness': report.hardness,
                    'cutting_volume': report.cutting_volume,
                    'oil_content': report.oil_content,
                    'waste_type': report.waste_type,
                    'disposal_method': report.disposal_method,
                    'waste_history_json': report.waste_history_json,
                    'safety_observations': report.safety_observations,
                    'incidents_json': report.incidents_json,
                    'equipment_checks': report.equipment_checks,
                    'status': report.status,
                    'created_at': report.created_at,
                    'updated_at': report.updated_at,
                    'created_by': report.created_by
                }
            return None
        except Exception as e:
            logger.error(f"Error getting safety report: {e}")
            return None
        finally:
            session.close()

    # ========== BOP Component ==========
    def save_bop_component(self, component_data: dict):
        session = self.create_session()
        try:
            if component_data.get('id'):
                comp = session.query(BOPComponent).filter(BOPComponent.id == component_data['id']).first()
                if comp:
                    for key, value in component_data.items():
                        if hasattr(comp, key) and key != 'id':
                            setattr(comp, key, value)
                    comp.updated_at = _now_utc()
                    record_id = comp.id
                else:
                    return None
            else:
                comp = BOPComponent(**component_data)
                session.add(comp)
                session.flush()
                record_id = comp.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving BOP component: {e}")
            return None
        finally:
            session.close()

    def get_bop_components(self, well_id: int = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(BOPComponent)
            if report_id:
                query = query.filter(BOPComponent.report_id == report_id)
            elif well_id:
                query = query.filter(BOPComponent.well_id == well_id)
            comps = query.order_by(BOPComponent.component_type, BOPComponent.component_name).all()
            return [
                {
                    'id': c.id,
                    'well_id': c.well_id,
                    'safety_report_id': c.safety_report_id,
                    'report_id': c.report_id,
                    'component_name': c.component_name,
                    'component_type': c.component_type,
                    'working_pressure': c.working_pressure,
                    'size': c.size,
                    'ram_type': c.ram_type,
                    'manufacturer': c.manufacturer,
                    'serial_number': c.serial_number,
                    'last_test_date': c.last_test_date,
                    'next_test_due': c.next_test_due,
                    'test_pressure': c.test_pressure,
                    'test_result': c.test_result,
                    'status': c.status,
                    'remarks': c.remarks,
                    'created_at': c.created_at,
                    'updated_at': c.updated_at
                }
                for c in comps
            ]
        except Exception as e:
            logger.error(f"Error getting BOP components: {e}")
            return []
        finally:
            session.close()

    # ========== Waste Record ==========
    def save_waste_record(self, record_data: dict):
        session = self.create_session()
        try:
            record = WasteRecord(**record_data)
            session.add(record)
            session.commit()
            return record.id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving waste record: {e}")
            return None
        finally:
            session.close()

    def get_waste_records(self, well_id: int = None, start_date: date = None, end_date: date = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(WasteRecord)
            if report_id:
                query = query.filter(WasteRecord.report_id == report_id)
            elif well_id:
                query = query.filter(WasteRecord.well_id == well_id)
            if start_date:
                query = query.filter(WasteRecord.record_date >= start_date)
            if end_date:
                query = query.filter(WasteRecord.record_date <= end_date)
            records = query.order_by(WasteRecord.record_date.desc()).all()
            return [
                {
                    'id': r.id,
                    'well_id': r.well_id,
                    'safety_report_id': r.safety_report_id,
                    'report_id': r.report_id,
                    'record_date': r.record_date,
                    'waste_type': r.waste_type,
                    'volume': r.volume,
                    'unit': r.unit,
                    'ph': r.ph,
                    'turbidity': r.turbidity,
                    'hardness': r.hardness,
                    'oil_content': r.oil_content,
                    'disposal_method': r.disposal_method,
                    'disposal_date': r.disposal_date,
                    'disposal_company': r.disposal_company,
                    'waste_ticket_number': r.waste_ticket_number,
                    'manifest_number': r.manifest_number,
                    'remarks': r.remarks,
                    'status': r.status,
                    'created_at': r.created_at,
                    'updated_at': r.updated_at
                }
                for r in records
            ]
        except Exception as e:
            logger.error(f"Error getting waste records: {e}")
            return []
        finally:
            session.close()

    # ========== Safety Incident ==========
    def save_safety_incident(self, incident_data: dict):
        session = self.create_session()
        try:
            incident = SafetyIncident(**incident_data)
            session.add(incident)
            session.commit()
            return incident.id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving safety incident: {e}")
            return None
        finally:
            session.close()

    def get_safety_incidents(self, well_id: int = None, start_date: date = None, end_date: date = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(SafetyIncident).join(SafetyReport)
            if report_id:
                query = query.filter(SafetyReport.report_id == report_id)
            elif well_id:
                query = query.filter(SafetyReport.well_id == well_id)
            if start_date:
                query = query.filter(SafetyIncident.incident_date >= start_date)
            if end_date:
                query = query.filter(SafetyIncident.incident_date <= end_date)
            incidents = query.order_by(SafetyIncident.incident_date.desc(), SafetyIncident.incident_time.desc()).all()
            return [
                {
                    'id': i.id,
                    'safety_report_id': i.safety_report_id,
                    'incident_date': i.incident_date,
                    'incident_time': i.incident_time.strftime('%H:%M') if i.incident_time else '',
                    'incident_type': i.incident_type,
                    'severity': i.severity,
                    'location': i.location,
                    'description': i.description,
                    'personnel_involved': i.personnel_involved,
                    'injuries': i.injuries,
                    'immediate_response': i.immediate_response,
                    'corrective_actions': i.corrective_actions,
                    'root_cause': i.root_cause,
                    'investigator': i.investigator,
                    'status': i.status,
                    'resolved_date': i.resolved_date,
                    'created_at': i.created_at,
                    'updated_at': i.updated_at
                }
                for i in incidents
            ]
        except Exception as e:
            logger.error(f"Error getting safety incidents: {e}")
            return []
        finally:
            session.close()

    # ========== Service Company ==========
    def save_service_company(self, company_data: dict):
        session = self.create_session()
        try:
            if company_data.get("id"):
                company = session.query(ServiceCompany).filter(ServiceCompany.id == company_data["id"]).first()
                if company:
                    for key, value in company_data.items():
                        if hasattr(company, key) and key != 'id':
                            setattr(company, key, value)
                    company.updated_at = _now_utc()
                    record_id = company.id
                else:
                    return None
            else:
                company = ServiceCompany(
                    well_id=company_data["well_id"],
                    section_id=company_data.get("section_id"),
                    report_id=company_data.get("report_id"),
                    company_name=company_data["company_name"],
                    service_type=company_data.get("service_type", ""),
                    start_datetime=company_data.get("start_datetime"),
                    end_datetime=company_data.get("end_datetime"),
                    contact_person=company_data.get("contact_person", ""),
                    contact_phone=company_data.get("contact_phone", ""),
                    contact_email=company_data.get("contact_email", ""),
                    equipment_used=company_data.get("equipment_used", ""),
                    personnel_count=company_data.get("personnel_count", 1),
                    status=company_data.get("status", "Active"),
                    description=company_data.get("description", ""),
                    created_by=company_data.get("created_by")
                )
                session.add(company)
                session.flush()
                record_id = company.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving service company: {e}")
            return None
        finally:
            session.close()

    def get_service_companies(self, well_id: int = None, section_id: int = None, report_id: int = None, status: str = None):
        session = self.create_session()
        try:
            query = session.query(ServiceCompany)
            if report_id:
                query = query.filter(ServiceCompany.report_id == report_id)
            elif well_id:
                query = query.filter(ServiceCompany.well_id == well_id)
            if section_id:
                query = query.filter(ServiceCompany.section_id == section_id)
            if status:
                query = query.filter(ServiceCompany.status == status)
            companies = query.order_by(ServiceCompany.start_datetime.desc()).all()
            return [
                {
                    "id": c.id,
                    "well_id": c.well_id,
                    "section_id": c.section_id,
                    "report_id": c.report_id,
                    "company_name": c.company_name,
                    "service_type": c.service_type,
                    "start_datetime": c.start_datetime,
                    "end_datetime": c.end_datetime,
                    "contact_person": c.contact_person,
                    "contact_phone": c.contact_phone,
                    "contact_email": c.contact_email,
                    "equipment_used": c.equipment_used,
                    "personnel_count": c.personnel_count,
                    "status": c.status,
                    "description": c.description,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at
                }
                for c in companies
            ]
        except Exception as e:
            logger.error(f"Error getting service companies: {e}")
            return []
        finally:
            session.close()

    def delete_service_company(self, company_id: int):
        session = self.create_session()
        try:
            company = session.query(ServiceCompany).filter(ServiceCompany.id == company_id).first()
            if company:
                session.delete(company)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting service company: {e}")
            return False
        finally:
            session.close()

    # ========== Service Note ==========
    def save_service_note(self, note_data: dict):
        session = self.create_session()
        try:
            if note_data.get("id"):
                note = session.query(ServiceNote).filter(ServiceNote.id == note_data["id"]).first()
                if note:
                    for key, value in note_data.items():
                        if hasattr(note, key) and key != 'id':
                            setattr(note, key, value)
                    note.updated_at = _now_utc()
                    record_id = note.id
                else:
                    return None
            else:
                note = ServiceNote(
                    well_id=note_data["well_id"],
                    section_id=note_data.get("section_id"),
                    report_id=note_data.get("report_id"),
                    note_number=note_data["note_number"],
                    note_type=note_data.get("note_type", "General"),
                    content=note_data["content"],
                    priority=note_data.get("priority", "Medium"),
                    status=note_data.get("status", "Active"),
                    created_by=note_data.get("created_by")
                )
                session.add(note)
                session.flush()
                record_id = note.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving service note: {e}")
            return None
        finally:
            session.close()

    def get_service_notes(self, well_id: int = None, section_id: int = None, report_id: int = None, note_type: str = None):
        session = self.create_session()
        try:
            query = session.query(ServiceNote)
            if report_id:
                query = query.filter(ServiceNote.report_id == report_id)
            elif well_id:
                query = query.filter(ServiceNote.well_id == well_id)
            if section_id:
                query = query.filter(ServiceNote.section_id == section_id)
            if note_type:
                query = query.filter(ServiceNote.note_type == note_type)
            notes = query.order_by(ServiceNote.note_number).all()
            return [
                {
                    "id": n.id,
                    "well_id": n.well_id,
                    "section_id": n.section_id,
                    "report_id": n.report_id,
                    "note_number": n.note_number,
                    "note_type": n.note_type,
                    "content": n.content,
                    "priority": n.priority,
                    "status": n.status,
                    "created_at": n.created_at,
                    "updated_at": n.updated_at
                }
                for n in notes
            ]
        except Exception as e:
            logger.error(f"Error getting service notes: {e}")
            return []
        finally:
            session.close()

    def delete_service_note(self, note_id: int):
        session = self.create_session()
        try:
            note = session.query(ServiceNote).filter(ServiceNote.id == note_id).first()
            if note:
                session.delete(note)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting service note: {e}")
            return False
        finally:
            session.close()

    # ========== Material Request ==========
    def save_material_request(self, request_data: dict):
        session = self.create_session()
        try:
            if request_data.get("id"):
                request = session.query(MaterialRequest).filter(MaterialRequest.id == request_data["id"]).first()
                if request:
                    for key, value in request_data.items():
                        if hasattr(request, key) and key != 'id':
                            setattr(request, key, value)
                    request.updated_at = _now_utc()
                    record_id = request.id
                else:
                    return None
            else:
                request = MaterialRequest(
                    well_id=request_data["well_id"],
                    section_id=request_data.get("section_id"),
                    report_id=request_data.get("report_id"),
                    request_date=request_data["request_date"],
                    requested_items=request_data.get("requested_items", ""),
                    requested_quantity=request_data.get("requested_quantity", 0.0),
                    requested_unit=request_data.get("requested_unit", "units"),
                    outstanding_items=request_data.get("outstanding_items", ""),
                    outstanding_quantity=request_data.get("outstanding_quantity", 0.0),
                    received_items=request_data.get("received_items", ""),
                    received_quantity=request_data.get("received_quantity", 0.0),
                    received_date=request_data.get("received_date"),
                    backload_items=request_data.get("backload_items", ""),
                    backload_quantity=request_data.get("backload_quantity", 0.0),
                    backload_date=request_data.get("backload_date"),
                    remarks=request_data.get("remarks", ""),
                    status=request_data.get("status", "Pending"),
                    created_by=request_data.get("created_by")
                )
                session.add(request)
                session.flush()
                record_id = request.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving material request: {e}")
            return None
        finally:
            session.close()

    def get_material_requests(self, well_id: int = None, section_id: int = None, report_id: int = None, status: str = None, start_date=None, end_date=None):
        session = self.create_session()
        try:
            query = session.query(MaterialRequest)
            if report_id:
                query = query.filter(MaterialRequest.report_id == report_id)
            elif well_id:
                query = query.filter(MaterialRequest.well_id == well_id)
            if section_id:
                query = query.filter(MaterialRequest.section_id == section_id)
            if status:
                query = query.filter(MaterialRequest.status == status)
            if start_date:
                query = query.filter(MaterialRequest.request_date >= start_date)
            if end_date:
                query = query.filter(MaterialRequest.request_date <= end_date)
            requests = query.order_by(MaterialRequest.request_date.desc()).all()
            return [
                {
                    "id": r.id,
                    "well_id": r.well_id,
                    "section_id": r.section_id,
                    "report_id": r.report_id,
                    "request_date": r.request_date,
                    "requested_items": r.requested_items,
                    "requested_quantity": r.requested_quantity,
                    "requested_unit": r.requested_unit,
                    "outstanding_items": r.outstanding_items,
                    "outstanding_quantity": r.outstanding_quantity,
                    "received_items": r.received_items,
                    "received_quantity": r.received_quantity,
                    "received_date": r.received_date,
                    "backload_items": r.backload_items,
                    "backload_quantity": r.backload_quantity,
                    "backload_date": r.backload_date,
                    "remarks": r.remarks,
                    "status": r.status,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at
                }
                for r in requests
            ]
        except Exception as e:
            logger.error(f"Error getting material requests: {e}")
            return []
        finally:
            session.close()

    def calculate_material_balance(self, well_id: int = None, section_id: int = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(MaterialRequest)
            if report_id:
                query = query.filter(MaterialRequest.report_id == report_id)
            elif well_id:
                query = query.filter(MaterialRequest.well_id == well_id)
            if section_id:
                query = query.filter(MaterialRequest.section_id == section_id)
            requests = query.all()
            total_requested = sum(r.requested_quantity or 0 for r in requests)
            total_received = sum(r.received_quantity or 0 for r in requests)
            total_backload = sum(r.backload_quantity or 0 for r in requests)
            balance = total_requested - total_received + total_backload
            return {
                "total_requested": total_requested,
                "total_received": total_received,
                "total_backload": total_backload,
                "balance": balance,
                "request_count": len(requests)
            }
        except Exception as e:
            logger.error(f"Error calculating material balance: {e}")
            return {}
        finally:
            session.close()

    def delete_material_request(self, request_id: int):
        session = self.create_session()
        try:
            request = session.query(MaterialRequest).filter(MaterialRequest.id == request_id).first()
            if request:
                session.delete(request)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting material request: {e}")
            return False
        finally:
            session.close()

    # ========== Equipment Log ==========
    def save_equipment_log(self, log_data: dict):
        session = self.create_session()
        try:
            if log_data.get("id"):
                log = session.query(EquipmentLog).filter(EquipmentLog.id == log_data["id"]).first()
                if log:
                    for key, value in log_data.items():
                        if hasattr(log, key) and key != 'id':
                            setattr(log, key, value)
                    log.updated_at = _now_utc()
                    record_id = log.id
                else:
                    return None
            else:
                log = EquipmentLog(
                    well_id=log_data["well_id"],
                    section_id=log_data.get("section_id"),
                    report_id=log_data.get("report_id"),
                    equipment_type=log_data.get("equipment_type", ""),
                    equipment_name=log_data["equipment_name"],
                    equipment_id=log_data.get("equipment_id", ""),
                    manufacturer=log_data.get("manufacturer", ""),
                    serial_number=log_data.get("serial_number", ""),
                    service_date=log_data.get("service_date"),
                    service_type=log_data.get("service_type", ""),
                    service_provider=log_data.get("service_provider", ""),
                    hours_worked=log_data.get("hours_worked", 0.0),
                    status=log_data.get("status", "Operational"),
                    notes=log_data.get("notes", ""),
                    created_by=log_data.get("created_by")
                )
                session.add(log)
                session.flush()
                record_id = log.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving equipment log: {e}")
            return None
        finally:
            session.close()

    def get_equipment_logs(self, well_id: int = None, section_id: int = None, report_id: int = None, equipment_type: str = None, status: str = None):
        session = self.create_session()
        try:
            query = session.query(EquipmentLog)
            if report_id:
                query = query.filter(EquipmentLog.report_id == report_id)
            elif well_id:
                query = query.filter(EquipmentLog.well_id == well_id)
            if section_id:
                query = query.filter(EquipmentLog.section_id == section_id)
            if equipment_type:
                query = query.filter(EquipmentLog.equipment_type == equipment_type)
            if status:
                query = query.filter(EquipmentLog.status == status)
            logs = query.order_by(EquipmentLog.service_date.desc()).all()
            return [
                {
                    "id": l.id,
                    "well_id": l.well_id,
                    "section_id": l.section_id,
                    "report_id": l.report_id,
                    "equipment_type": l.equipment_type,
                    "equipment_name": l.equipment_name,
                    "equipment_id": l.equipment_id,
                    "manufacturer": l.manufacturer,
                    "serial_number": l.serial_number,
                    "service_date": l.service_date,
                    "service_type": l.service_type,
                    "service_provider": l.service_provider,
                    "hours_worked": l.hours_worked,
                    "status": l.status,
                    "notes": l.notes,
                    "created_at": l.created_at,
                    "updated_at": l.updated_at
                }
                for l in logs
            ]
        except Exception as e:
            logger.error(f"Error getting equipment logs: {e}")
            return []
        finally:
            session.close()

    def get_equipment_summary(self, well_id: int = None, section_id: int = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(EquipmentLog)
            if report_id:
                query = query.filter(EquipmentLog.report_id == report_id)
            elif well_id:
                query = query.filter(EquipmentLog.well_id == well_id)
            if section_id:
                query = query.filter(EquipmentLog.section_id == section_id)
            logs = query.all()
            summary = {
                "total_equipment": len(logs),
                "operational": 0,
                "under_maintenance": 0,
                "out_of_service": 0,
                "total_hours": 0.0,
                "by_type": {}
            }
            for l in logs:
                if l.status == "Operational":
                    summary["operational"] += 1
                elif l.status == "Under Maintenance":
                    summary["under_maintenance"] += 1
                elif l.status == "Out of Service":
                    summary["out_of_service"] += 1
                summary["total_hours"] += l.hours_worked or 0
                eq_type = l.equipment_type or "Unknown"
                if eq_type not in summary["by_type"]:
                    summary["by_type"][eq_type] = {"count": 0, "operational": 0, "total_hours": 0.0}
                summary["by_type"][eq_type]["count"] += 1
                if l.status == "Operational":
                    summary["by_type"][eq_type]["operational"] += 1
                summary["by_type"][eq_type]["total_hours"] += l.hours_worked or 0
            return summary
        except Exception as e:
            logger.error(f"Error getting equipment summary: {e}")
            return {}
        finally:
            session.close()

    def delete_equipment_log(self, log_id: int):
        session = self.create_session()
        try:
            log = session.query(EquipmentLog).filter(EquipmentLog.id == log_id).first()
            if log:
                session.delete(log)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting equipment log: {e}")
            return False
        finally:
            session.close()

    # ========== Seven Days Lookahead ==========
    def save_seven_days_lookahead(self, lookahead_data: dict):
        """
        ✅ FIX: حذف import PySide از داخل تابع دیتابیس
        تبدیل‌های نوع در لایه UI انجام می‌شوند.
        """
        session = self.create_session()
        try:
            from datetime import datetime, date

            def _to_python_date(val):
                """تبدیل ایمن به Python date"""
                if val is None:
                    return date.today()
                if isinstance(val, date):
                    return val
                if isinstance(val, str):
                    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
                        try:
                            return datetime.strptime(val, fmt).date()
                        except ValueError:
                            continue
                return date.today()

            def _to_python_datetime(val):
                """تبدیل ایمن به Python datetime"""
                if val is None:
                    return None
                if isinstance(val, datetime):
                    return val
                if isinstance(val, str):
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                        try:
                            return datetime.strptime(val, fmt)
                        except ValueError:
                            continue
                return None

            plan_date = _to_python_date(lookahead_data.get("plan_date"))
            actual_start = _to_python_datetime(lookahead_data.get("actual_start"))
            actual_end = _to_python_datetime(lookahead_data.get("actual_end"))

            record_id = lookahead_data.get("id")
            if record_id:
                plan = session.query(SevenDaysLookahead).filter(
                    SevenDaysLookahead.id == record_id
                ).first()
                if plan:
                    plan.well_id = lookahead_data.get("well_id", plan.well_id)
                    plan.section_id = lookahead_data.get("section_id", plan.section_id)
                    plan.report_id = lookahead_data.get("report_id", plan.report_id)
                    plan.plan_date = plan_date
                    plan.day_number = lookahead_data.get("day_number", plan.day_number)
                    plan.activity = lookahead_data.get("activity", plan.activity)
                    plan.tools = lookahead_data.get("tools", plan.tools)
                    plan.responsible = lookahead_data.get("responsible", plan.responsible)
                    plan.remarks = lookahead_data.get("remarks", plan.remarks)
                    plan.status = lookahead_data.get("status", plan.status)
                    plan.priority = lookahead_data.get("priority", plan.priority)
                    plan.progress_percentage = lookahead_data.get(
                        "progress_percentage", plan.progress_percentage
                    )
                    if actual_start is not None:
                        plan.actual_start = actual_start
                    if actual_end is not None:
                        plan.actual_end = actual_end
                    plan.updated_at = _now_utc()
                    session.commit()
                    return record_id
                else:
                    logger.error(f"SevenDaysLookahead id={record_id} not found")
                    return None

            well_id = lookahead_data.get("well_id")
            if not well_id:
                logger.error("well_id is required for SevenDaysLookahead")
                return None

            new_plan = SevenDaysLookahead(
                well_id=well_id,
                section_id=lookahead_data.get("section_id"),
                report_id=lookahead_data.get("report_id"),
                plan_date=plan_date,
                day_number=lookahead_data.get("day_number", 1),
                activity=lookahead_data.get("activity", ""),
                tools=lookahead_data.get("tools", ""),
                responsible=lookahead_data.get("responsible", ""),
                remarks=lookahead_data.get("remarks", ""),
                status=lookahead_data.get("status", "Planned"),
                priority=lookahead_data.get("priority", "Normal"),
                progress_percentage=lookahead_data.get("progress_percentage", 0),
                actual_start=actual_start,
                actual_end=actual_end,
                created_by=lookahead_data.get("created_by"),
                created_at=_now_utc(),
                updated_at=_now_utc()
            )
            session.add(new_plan)
            session.commit()
            return new_plan.id

        except Exception as e:
            session.rollback()
            logger.error(f"Error saving seven days lookahead: {e}")
            return None
        finally:
            session.close()
            
    def get_seven_days_lookahead(self, well_id: int = None, section_id: int = None, start_date: date = None, end_date: date = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(SevenDaysLookahead)
            if report_id:
                query = query.filter(SevenDaysLookahead.report_id == report_id)
            elif well_id:
                query = query.filter(SevenDaysLookahead.well_id == well_id)
            if section_id:
                query = query.filter(SevenDaysLookahead.section_id == section_id)
            if start_date:
                query = query.filter(SevenDaysLookahead.plan_date >= start_date)
            if end_date:
                query = query.filter(SevenDaysLookahead.plan_date <= end_date)
            plans = query.order_by(SevenDaysLookahead.plan_date, SevenDaysLookahead.day_number).all()
            return [
                {
                    "id": p.id,
                    "well_id": p.well_id,
                    "section_id": p.section_id,
                    "report_id": p.report_id,
                    "plan_date": p.plan_date,
                    "day_number": p.day_number,
                    "activity": p.activity,
                    "tools": p.tools,
                    "responsible": p.responsible,
                    "remarks": p.remarks,
                    "status": p.status,
                    "progress_percentage": p.progress_percentage,
                    "created_at": p.created_at,
                    "updated_at": p.updated_at
                }
                for p in plans
            ]
        except Exception as e:
            logger.error(f"Error getting seven days lookahead: {e}")
            return []
        finally:
            session.close()

    # ========== NPT Report ==========
    def save_npt_report(self, npt_data: dict):
        session = self.create_session()
        try:
            if npt_data.get("id"):
                report = session.query(NPTReport).filter(NPTReport.id == npt_data["id"]).first()
                if report:
                    for key, value in npt_data.items():
                        if hasattr(report, key) and key != 'id':
                            setattr(report, key, value)
                    report.updated_at = _now_utc()
                    record_id = report.id
                else:
                    return None
            else:
                report = NPTReport(
                    well_id=npt_data["well_id"],
                    section_id=npt_data.get("section_id"),
                    report_id=npt_data.get("report_id"),
                    npt_date=npt_data["npt_date"],
                    start_time=npt_data["start_time"],
                    end_time=npt_data["end_time"],
                    duration_hours=npt_data["duration_hours"],
                    npt_category=npt_data["npt_category"],
                    npt_code=npt_data["npt_code"],
                    npt_description=npt_data["npt_description"],
                    responsible_party=npt_data.get("responsible_party", ""),
                    cost_impact=npt_data.get("cost_impact", 0.0),
                    status=npt_data.get("status", "Active"),
                    created_by=npt_data.get("created_by")
                )
                session.add(report)
                session.flush()
                record_id = report.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving NPT report: {e}")
            return None
        finally:
            session.close()

    def get_npt_reports(self, well_id: int = None, start_date: date = None, end_date: date = None, npt_code: str = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(NPTReport)
            if report_id:
                query = query.filter(NPTReport.report_id == report_id)
            elif well_id:
                query = query.filter(NPTReport.well_id == well_id)
            if start_date:
                query = query.filter(NPTReport.npt_date >= start_date)
            if end_date:
                query = query.filter(NPTReport.npt_date <= end_date)
            if npt_code:
                query = query.filter(NPTReport.npt_code == npt_code)
            reports = query.order_by(NPTReport.npt_date.desc(), NPTReport.start_time).all()
            return [
                {
                    "id": r.id,
                    "well_id": r.well_id,
                    "section_id": r.section_id,
                    "report_id": r.report_id,
                    "npt_date": r.npt_date,
                    "start_time": r.start_time.strftime("%H:%M") if r.start_time else "",
                    "end_time": r.end_time.strftime("%H:%M") if r.end_time else "",
                    "duration_hours": r.duration_hours,
                    "npt_category": r.npt_category,
                    "npt_code": r.npt_code,
                    "npt_description": r.npt_description,
                    "responsible_party": r.responsible_party,
                    "cost_impact": r.cost_impact,
                    "status": r.status,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at
                }
                for r in reports
            ]
        except Exception as e:
            logger.error(f"Error getting NPT reports: {e}")
            return []
        finally:
            session.close()

    def calculate_npt_statistics(self, well_id: int = None, start_date: date = None, end_date: date = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(NPTReport)
            if report_id:
                query = query.filter(NPTReport.report_id == report_id)
            elif well_id:
                query = query.filter(NPTReport.well_id == well_id)
            if start_date:
                query = query.filter(NPTReport.npt_date >= start_date)
            if end_date:
                query = query.filter(NPTReport.npt_date <= end_date)
            reports = query.all()
            total_npt_hours = sum(r.duration_hours or 0 for r in reports)
            total_npt_events = len(reports)
            category_stats = {}
            for r in reports:
                cat = r.npt_category or "Unknown"
                category_stats[cat] = category_stats.get(cat, 0) + (r.duration_hours or 0)
            code_stats = {}
            for r in reports:
                code = r.npt_code or "Unknown"
                code_stats[code] = code_stats.get(code, 0) + (r.duration_hours or 0)
            return {
                "total_npt_hours": total_npt_hours,
                "total_npt_events": total_npt_events,
                "average_npt_per_event": total_npt_hours / total_npt_events if total_npt_events > 0 else 0,
                "category_stats": category_stats,
                "code_stats": code_stats,
                "reports": len(reports)
            }
        except Exception as e:
            logger.error(f"Error calculating NPT statistics: {e}")
            return {}
        finally:
            session.close()

    # ========== Activity Code ==========
    def save_activity_code(self, code_data: dict):
        session = self.create_session()
        try:
            existing = session.query(ActivityCode).filter(
                ActivityCode.well_id == code_data["well_id"],
                ActivityCode.main_phase == code_data["main_phase"],
                ActivityCode.main_code == code_data["main_code"],
                ActivityCode.sub_code == code_data["sub_code"]
            ).first()
            if existing:
                for key, value in code_data.items():
                    if hasattr(existing, key) and key not in ['id', 'well_id']:
                        setattr(existing, key, value)
                existing.updated_at = _now_utc()
                record_id = existing.id
            else:
                code = ActivityCode(
                    well_id=code_data["well_id"],
                    main_phase=code_data["main_phase"],
                    main_code=code_data["main_code"],
                    sub_code=code_data["sub_code"],
                    code_name=code_data["code_name"],
                    code_description=code_data.get("code_description", ""),
                    is_productive=code_data.get("is_productive", True),
                    is_npt=code_data.get("is_npt", False),
                    color_code=code_data.get("color_code", "#0078D4"),
                    created_by=code_data.get("created_by")
                )
                session.add(code)
                session.flush()
                record_id = code.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving activity code: {e}")
            return None
        finally:
            session.close()

    def get_activity_codes(self, well_id: int = None, main_phase: str = None):
        session = self.create_session()
        try:
            query = session.query(ActivityCode)
            if well_id:
                query = query.filter(ActivityCode.well_id == well_id)
            if main_phase:
                query = query.filter(ActivityCode.main_phase == main_phase)
            codes = query.order_by(ActivityCode.main_phase, ActivityCode.main_code, ActivityCode.sub_code).all()
            return [
                {
                    "id": c.id,
                    "well_id": c.well_id,
                    "main_phase": c.main_phase,
                    "main_code": c.main_code,
                    "sub_code": c.sub_code,
                    "code_name": c.code_name,
                    "code_description": c.code_description,
                    "is_productive": c.is_productive,
                    "is_npt": c.is_npt,
                    "color_code": c.color_code,
                    "usage_count": c.usage_count,
                    "total_hours": c.total_hours,
                    "last_used": c.last_used,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at
                }
                for c in codes
            ]
        except Exception as e:
            logger.error(f"Error getting activity codes: {e}")
            return []
        finally:
            session.close()

    def update_code_usage(self, well_id: int, code_data: list):
        session = self.create_session()
        try:
            for usage in code_data:
                code = session.query(ActivityCode).filter(
                    ActivityCode.well_id == well_id,
                    ActivityCode.sub_code == usage["sub_code"]
                ).first()
                if code:
                    code.usage_count += usage.get("count", 0)
                    code.total_hours += usage.get("hours", 0.0)
                    code.last_used = datetime.now().date()
                    code.updated_at = _now_utc()
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating code usage: {e}")
            return False
        finally:
            session.close()

    # ========== Time Depth Data ==========
    def save_time_depth_data(self, data: dict):
        session = self.create_session()
        try:
            point = TimeDepthData(
                well_id=data["well_id"],
                section_id=data.get("section_id"),
                report_id=data.get("report_id"),
                timestamp=data["timestamp"],
                depth=data["depth"],
                activity_code=data.get("activity_code"),
                rop=data.get("rop"),
                wob=data.get("wob"),
                rpm=data.get("rpm"),
                torque=data.get("torque"),
                cumulative_time=data.get("cumulative_time"),
                daily_progress=data.get("daily_progress"),
                created_by=data.get("created_by")
            )
            session.add(point)
            session.commit()
            return point.id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving time depth data: {e}")
            return None
        finally:
            session.close()

    def get_time_depth_data(self, well_id: int = None, report_id: int = None, start_date=None, end_date=None, min_depth=None, max_depth=None):
        session = self.create_session()
        try:
            query = session.query(TimeDepthData)
            if report_id:
                query = query.filter(TimeDepthData.report_id == report_id)
            elif well_id:
                query = query.filter(TimeDepthData.well_id == well_id)
            if start_date:
                query = query.filter(TimeDepthData.timestamp >= start_date)
            if end_date:
                query = query.filter(TimeDepthData.timestamp <= end_date)
            if min_depth:
                query = query.filter(TimeDepthData.depth >= min_depth)
            if max_depth:
                query = query.filter(TimeDepthData.depth <= max_depth)
            data = query.order_by(TimeDepthData.timestamp).all()
            return [
                {
                    "id": d.id,
                    "timestamp": d.timestamp,
                    "depth": d.depth,
                    "activity_code": d.activity_code,
                    "rop": d.rop,
                    "wob": d.wob,
                    "rpm": d.rpm,
                    "torque": d.torque,
                    "cumulative_time": d.cumulative_time,
                    "daily_progress": d.daily_progress
                }
                for d in data
            ]
        except Exception as e:
            logger.error(f"Error getting time depth data: {e}")
            return []
        finally:
            session.close()

    # ========== ROP Analysis ==========
    def save_rop_analysis(self, analysis_data: dict):
        session = self.create_session()
        try:
            analysis = ROPAnalysis(
                well_id=analysis_data["well_id"],
                section_id=analysis_data.get("section_id"),
                report_id=analysis_data.get("report_id"),
                analysis_date=analysis_data["analysis_date"],
                start_depth=analysis_data["start_depth"],
                end_depth=analysis_data["end_depth"],
                avg_rop=analysis_data.get("avg_rop"),
                max_rop=analysis_data.get("max_rop"),
                min_rop=analysis_data.get("min_rop"),
                rop_std_dev=analysis_data.get("rop_std_dev"),
                formation_type=analysis_data.get("formation_type"),
                bit_type=analysis_data.get("bit_type"),
                hydraulics_efficiency=analysis_data.get("hydraulics_efficiency"),
                drill_string_config=analysis_data.get("drill_string_config"),
                rop_chart_data=analysis_data.get("rop_chart_data"),
                depth_chart_data=analysis_data.get("depth_chart_data"),
                recommendations=analysis_data.get("recommendations"),
                efficiency_score=analysis_data.get("efficiency_score"),
                created_by=analysis_data.get("created_by")
            )
            session.add(analysis)
            session.commit()
            return analysis.id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving ROP analysis: {e}")
            return None
        finally:
            session.close()

    def get_rop_analysis(self, well_id: int = None, start_date: date = None, end_date: date = None, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(ROPAnalysis)
            if report_id:
                query = query.filter(ROPAnalysis.report_id == report_id)
            elif well_id:
                query = query.filter(ROPAnalysis.well_id == well_id)
            if start_date:
                query = query.filter(ROPAnalysis.analysis_date >= start_date)
            if end_date:
                query = query.filter(ROPAnalysis.analysis_date <= end_date)
            analyses = query.order_by(ROPAnalysis.analysis_date.desc()).all()
            return [
                {
                    "id": a.id,
                    "well_id": a.well_id,
                    "section_id": a.section_id,
                    "report_id": a.report_id,
                    "analysis_date": a.analysis_date,
                    "start_depth": a.start_depth,
                    "end_depth": a.end_depth,
                    "avg_rop": a.avg_rop,
                    "max_rop": a.max_rop,
                    "min_rop": a.min_rop,
                    "rop_std_dev": a.rop_std_dev,
                    "formation_type": a.formation_type,
                    "bit_type": a.bit_type,
                    "hydraulics_efficiency": a.hydraulics_efficiency,
                    "drill_string_config": a.drill_string_config,
                    "efficiency_score": a.efficiency_score,
                    "recommendations": a.recommendations,
                    "created_at": a.created_at,
                    "updated_at": a.updated_at
                }
                for a in analyses
            ]
        except Exception as e:
            logger.error(f"Error getting ROP analysis: {e}")
            return []
        finally:
            session.close()


    def generate_time_depth_chart_data(self, well_id: int):
        session = self.create_session()
        try:
            reports = session.query(DailyReport).filter_by(well_id=well_id)\
                             .order_by(DailyReport.report_date).all()
            data = {
                "timestamps": [],
                "depths": [],
                "rop": [],
                "data_points": 0
            }
            for r in reports:
                if r.report_date:
                    data["timestamps"].append(
                        datetime.combine(r.report_date, datetime.min.time())
                    )
                    data["depths"].append(r.depth_2400 or 0)
                    data["rop"].append(r.rop_meter or 0)
            data["data_points"] = len(data["timestamps"])
            return data if data["data_points"] > 0 else None
        except Exception as e:
            logger.error(f"Error generating time-depth chart: {e}")
            return None
        finally:
            session.close()

    def generate_rop_chart_data(self, well_id: int, section_id: int = None):
        session = self.create_session()
        try:
            query = session.query(DrillingParameters).filter(
                DrillingParameters.well_id == well_id
            )
            if section_id:
                # اصلاح: join صحیح
                query = query.join(
                    DailyReport, DrillingParameters.report_id == DailyReport.id
                ).filter(DailyReport.section_id == section_id)

            params = query.order_by(DrillingParameters.report_date).all()
            data = {
                "timestamps": [],
                "rop": [],
                "wob": [],
                "rpm": [],
                "depths": [],
                "data_points": 0
            }
            for p in params:
                if p.report_date:
                    data["timestamps"].append(datetime.combine(p.report_date, datetime.min.time()))
                    data["rop"].append(p.avg_rop or 0)
                    data["wob"].append((p.wob_min + p.wob_max) / 2 if p.wob_min and p.wob_max else 0)
                    data["rpm"].append((p.rpm_min + p.rpm_max) / 2 if p.rpm_min and p.rpm_max else 0)
                    data["depths"].append(p.depth_out or 0)
            data["data_points"] = len(data["timestamps"])
            return data if data["data_points"] > 0 else None
        except Exception as e:
            logger.error(f"Error generating ROP chart: {e}")
            return None
        finally:
            session.close()



    def auto_update_from_daily_report(self, report_id: int):
        session = self.create_session()
        try:
            report = session.query(DailyReport).filter(DailyReport.id == report_id).first()
            if not report:
                return False

            # NPT from time logs
            npt_logs = session.query(TimeLog24H).filter(
                TimeLog24H.report_id == report_id,
                TimeLog24H.is_npt == True
            ).all()
            for log in npt_logs:
                npt_data = {
                    "well_id": report.well_id,
                    "section_id": report.section_id,
                    "report_id": report_id,
                    "npt_date": report.report_date,
                    "start_time": log.time_from,
                    "end_time": log.time_to,
                    "duration_hours": log.duration or 0,
                    "npt_category": "Daily Report",
                    "npt_code": log.main_code or "NPT",
                    "npt_description": log.activity_description or "NPT from daily report",
                    "responsible_party": "System",
                    "status": "Active"
                }
                self.save_npt_report(npt_data)

            # Update activity code usage
            all_logs = session.query(TimeLog24H).filter(TimeLog24H.report_id == report_id).all()
            code_usage = {}
            for log in all_logs:
                code = log.main_code or "Unknown"
                code_usage.setdefault(code, {"count": 0, "hours": 0})
                code_usage[code]["count"] += 1
                code_usage[code]["hours"] += log.duration or 0
            usage_list = [{"sub_code": code, "count": data["count"], "hours": data["hours"]} for code, data in code_usage.items()]
            if usage_list:
                self.update_code_usage(report.well_id, usage_list)

            # Time vs Depth
            if report.depth_2400:
                self.save_time_depth_data({
                    "well_id": report.well_id,
                    "section_id": report.section_id,
                    "report_id": report_id,
                    "timestamp": datetime.combine(report.report_date, datetime.min.time()),
                    "depth": report.depth_2400,
                    "daily_progress": report.depth_2400 - (report.depth_0000 or 0),
                })

            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error auto-updating from daily report: {e}")
            return False
        finally:
            session.close()

    # ========== Export Templates ==========
    def save_export_template(self, template_data: dict):
        session = self.create_session()
        try:
            if template_data.get("id"):
                template = session.query(ExportTemplate).filter(ExportTemplate.id == template_data["id"]).first()
                if template:
                    for key, value in template_data.items():
                        if hasattr(template, key) and key != 'id':
                            setattr(template, key, value)
                    template.updated_at = _now_utc()
                    record_id = template.id
                else:
                    return None
            else:
                template = ExportTemplate(**template_data)
                session.add(template)
                session.flush()
                record_id = template.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving export template: {e}")
            return None
        finally:
            session.close()

    def get_export_templates(self, template_type: str = None, created_by: int = None):
        session = self.create_session()
        try:
            query = session.query(ExportTemplate)
            if template_type:
                query = query.filter(ExportTemplate.template_type == template_type)
            if created_by:
                query = query.filter(
                    (ExportTemplate.created_by == created_by) |
                    (ExportTemplate.is_shared == True)
                )
            templates = query.order_by(ExportTemplate.is_default.desc(), ExportTemplate.updated_at.desc()).all()
            return [
                {
                    "id": t.id,
                    "name": t.name,
                    "template_type": t.template_type,
                    "description": t.description,
                    "well_selection": t.well_selection,
                    "report_selection": t.report_selection,
                    "date_range": t.date_range,
                    "format_settings": t.format_settings,
                    "options": t.options,
                    "layout_config": t.layout_config,
                    "styling": t.styling,
                    "headers_footers": t.headers_footers,
                    "is_default": t.is_default,
                    "is_shared": t.is_shared,
                    "shared_with": t.shared_with,
                    "created_at": t.created_at,
                    "updated_at": t.updated_at,
                    "created_by": t.created_by
                }
                for t in templates
            ]
        except Exception as e:
            logger.error(f"Error getting export templates: {e}")
            return []
        finally:
            session.close()

    def get_export_template_by_id(self, template_id: int):
        session = self.create_session()
        try:
            template = session.query(ExportTemplate).filter(ExportTemplate.id == template_id).first()
            if template:
                return {
                    "id": template.id,
                    "name": template.name,
                    "template_type": template.template_type,
                    "description": template.description,
                    "well_selection": template.well_selection,
                    "report_selection": template.report_selection,
                    "date_range": template.date_range,
                    "format_settings": template.format_settings,
                    "options": template.options,
                    "layout_config": template.layout_config,
                    "styling": template.styling,
                    "headers_footers": template.headers_footers,
                    "is_default": template.is_default,
                    "is_shared": template.is_shared,
                    "shared_with": template.shared_with,
                    "created_at": template.created_at,
                    "updated_at": template.updated_at,
                    "created_by": template.created_by
                }
            return None
        except Exception as e:
            logger.error(f"Error getting export template: {e}")
            return None
        finally:
            session.close()

    def delete_export_template(self, template_id: int) -> bool:
        try:
            with self.session_scope() as session:
                template = session.query(ExportTemplate).filter(
                    ExportTemplate.id == template_id
                ).first()
                if template:
                    session.delete(template)
                    return True
                return False
        except Exception as e:
            logger.error(f"Error deleting export template: {e}")
            return False
            
    def set_default_template(self, template_id: int, template_type: str):
        session = self.create_session()
        try:
            session.query(ExportTemplate).filter(
                ExportTemplate.template_type == template_type,
                ExportTemplate.is_default == True
            ).update({"is_default": False})
            template = session.query(ExportTemplate).filter(ExportTemplate.id == template_id).first()
            if template:
                template.is_default = True
                template.updated_at = _now_utc()
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error setting default template: {e}")
            return False
        finally:
            session.close()

    def get_bit_report(self, well_id: int, report_id: int = None):
        session = self.create_session()
        try:
            query = session.query(BitReport).filter(BitReport.well_id == well_id)
            if report_id:
                query = query.filter(BitReport.report_id == report_id)
            report = query.order_by(BitReport.report_date.desc()).first()
            if report:
                return {
                    "id": report.id,
                    "well_id": report.well_id,
                    "report_id": report.report_id,
                    "report_date": report.report_date,
                    "report_name": report.report_name,
                    "bit_records_json": report.bit_records_json,
                    "created_at": report.created_at,
                    "updated_at": report.updated_at
                }
            return None
        finally:
            session.close()
            
    # ==================== Procedure Methods ====================

    def save_procedure(self, data: dict) -> int:
        """ذخیره یا آپدیت پروسیجر"""
        session = self.create_session()
        try:
            if data.get('id'):
                proc = session.query(OperationalProcedure).filter(
                    OperationalProcedure.id == data['id']
                ).first()
                if proc:
                    for key, value in data.items():
                        if key != 'id' and hasattr(proc, key):
                            setattr(proc, key, value)
                    proc.updated_at = _now_utc()
            else:
                proc = OperationalProcedure(**{
                    k: v for k, v in data.items() 
                    if hasattr(OperationalProcedure, k)
                })
                session.add(proc)
            
            session.flush()
            proc_id = proc.id
            session.commit()
            return proc_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving procedure: {e}")
            return None
        finally:
            session.close()

    def get_procedures_by_well(self, well_id: int) -> list:
        """دریافت همه پروسیجرهای یک چاه"""
        session = self.create_session()
        try:
            procs = session.query(OperationalProcedure).filter(
                OperationalProcedure.well_id == well_id
            ).order_by(OperationalProcedure.created_at.desc()).all()
            
            return [{
                "id": p.id,
                "title": p.title,
                "procedure_type": p.procedure_type,
                "revision": p.revision,
                "revision_date": p.revision_date,
                "status": p.status,
                "prepared_by": p.prepared_by,
                "approved_by": p.approved_by,
                "created_at": p.created_at,
            } for p in procs]
        except Exception as e:
            logger.error(f"Error getting procedures: {e}")
            return []
        finally:
            session.close()

    def get_procedure_by_id(self, proc_id: int) -> dict:
        """دریافت کامل یک پروسیجر"""
        session = self.create_session()
        try:
            p = session.query(OperationalProcedure).filter(
                OperationalProcedure.id == proc_id
            ).first()
            if not p:
                return None
            
            return {
                "id": p.id,
                "well_id": p.well_id,
                "section_id": p.section_id,
                "title": p.title,
                "procedure_type": p.procedure_type,
                "revision": p.revision,
                "revision_date": p.revision_date,
                "rig_name": p.rig_name,
                "well_name": p.well_name,
                "field_name": p.field_name,
                "status": p.status,
                "prepared_by": p.prepared_by,
                "checked_by": p.checked_by,
                "approved_by": p.approved_by,
                "objective": p.objective,
                "hse_focus": p.hse_focus,
                "general_notes": p.general_notes,
                "created_at": p.created_at,
            }
        except Exception as e:
            logger.error(f"Error getting procedure: {e}")
            return None
        finally:
            session.close()

    def delete_procedure(self, proc_id: int) -> bool:
        session = self.create_session()
        try:
            p = session.query(OperationalProcedure).filter(
                OperationalProcedure.id == proc_id
            ).first()
            if p:
                session.delete(p)
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error deleting procedure: {e}")
            return False
        finally:
            session.close()

    # -------- Steps --------
    def save_procedure_steps(self, proc_id: int, steps: list) -> bool:
        session = self.create_session()
        try:
            # حذف مراحل قبلی
            session.query(ProcedureStep).filter(
                ProcedureStep.procedure_id == proc_id
            ).delete()
            
            for i, step in enumerate(steps):
                s = ProcedureStep(
                    procedure_id=proc_id,
                    step_number=i + 1,
                    activity_description=step.get('activity_description', ''),
                    parallel_activities=step.get('parallel_activities', ''),
                    caution_notes=step.get('caution_notes', ''),
                    is_completed=step.get('is_completed', False),
                    completed_by=step.get('completed_by', ''),
                    remarks=step.get('remarks', ''),
                )
                session.add(s)
            
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving steps: {e}")
            return False
        finally:
            session.close()

    def get_procedure_steps(self, proc_id: int) -> list:
        session = self.create_session()
        try:
            steps = session.query(ProcedureStep).filter(
                ProcedureStep.procedure_id == proc_id
            ).order_by(ProcedureStep.step_number).all()
            
            return [{
                "id": s.id,
                "step_number": s.step_number,
                "activity_description": s.activity_description,
                "parallel_activities": s.parallel_activities,
                "caution_notes": s.caution_notes,
                "is_completed": s.is_completed,
                "completed_by": s.completed_by,
                "completed_at": s.completed_at,
                "remarks": s.remarks,
            } for s in steps]
        except Exception as e:
            logger.error(f"Error getting steps: {e}")
            return []
        finally:
            session.close()

    def update_step_completion(self, step_id: int, is_completed: bool, 
                                completed_by: str = "") -> bool:
        session = self.create_session()
        try:
            step = session.query(ProcedureStep).filter(
                ProcedureStep.id == step_id
            ).first()
            if step:
                step.is_completed = is_completed
                step.completed_by = completed_by
                step.completed_at = _now_utc() if is_completed else None
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating step: {e}")
            return False
        finally:
            session.close()

    # -------- Checklist --------
    def save_checklist_items(self, proc_id: int, items: list) -> bool:
        session = self.create_session()
        try:
            session.query(ProcedureChecklist).filter(
                ProcedureChecklist.procedure_id == proc_id
            ).delete()
            
            for i, item in enumerate(items):
                c = ProcedureChecklist(
                    procedure_id=proc_id,
                    category=item.get('category', ''),
                    item_description=item.get('item_description', ''),
                    responsible=item.get('responsible', ''),
                    verified=item.get('verified', False),
                    verified_by=item.get('verified_by', ''),
                    not_applicable=item.get('not_applicable', False),
                    remarks=item.get('remarks', ''),
                    sort_order=i,
                )
                session.add(c)
            
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving checklist: {e}")
            return False
        finally:
            session.close()

    def get_checklist_items(self, proc_id: int) -> list:
        session = self.create_session()
        try:
            items = session.query(ProcedureChecklist).filter(
                ProcedureChecklist.procedure_id == proc_id
            ).order_by(ProcedureChecklist.sort_order).all()
            
            return [{
                "id": i.id,
                "category": i.category,
                "item_description": i.item_description,
                "responsible": i.responsible,
                "verified": i.verified,
                "verified_by": i.verified_by,
                "verified_at": i.verified_at,
                "not_applicable": i.not_applicable,
                "remarks": i.remarks,
            } for i in items]
        except Exception as e:
            logger.error(f"Error getting checklist: {e}")
            return []
        finally:
            session.close()

    def update_checklist_item(self, item_id: int, verified: bool, 
                               verified_by: str = "", remarks: str = "") -> bool:
        session = self.create_session()
        try:
            item = session.query(ProcedureChecklist).filter(
                ProcedureChecklist.id == item_id
            ).first()
            if item:
                item.verified = verified
                item.verified_by = verified_by
                item.verified_at = _now_utc() if verified else None
                item.remarks = remarks
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating checklist item: {e}")
            return False
        finally:
            session.close()

    # -------- Templates --------
    def get_procedure_templates(self, procedure_type: str = None) -> list:
        session = self.create_session()
        try:
            query = session.query(ProcedureTemplate)
            if procedure_type:
                query = query.filter(ProcedureTemplate.procedure_type == procedure_type)
            templates = query.all()
            return [{
                "id": t.id,
                "name": t.name,
                "procedure_type": t.procedure_type,
                "description": t.description,
                "template_steps_json": t.template_steps_json,
                "template_checklist_json": t.template_checklist_json,
                "template_hse_json": t.template_hse_json,
            } for t in templates]
        except Exception as e:
            logger.error(f"Error getting templates: {e}")
            return []
        finally:
            session.close()

    def save_procedure_template(self, data: dict) -> int:
        session = self.create_session()
        try:
            template = ProcedureTemplate(
                name=data['name'],
                procedure_type=data['procedure_type'],
                description=data.get('description', ''),
                template_steps_json=data.get('steps', []),
                template_checklist_json=data.get('checklist', []),
                template_hse_json=data.get('hse', []),
            )
            session.add(template)
            session.commit()
            return template.id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving template: {e}")
            return None
        finally:
            session.close()

    # -------- PJSM --------
    def save_pjsm(self, data: dict) -> int:
        session = self.create_session()
        try:
            pjsm = PJSMRecord(
                procedure_id=data['procedure_id'],
                meeting_date=data.get('meeting_date', _now_utc()),
                meeting_location=data.get('meeting_location', ''),
                conducted_by=data.get('conducted_by', ''),
                attendees_json=data.get('attendees', []),
                topics_discussed_json=data.get('topics', []),
                action_items_json=data.get('action_items', []),
                hse_concerns=data.get('hse_concerns', ''),
                general_notes=data.get('general_notes', ''),
            )
            session.add(pjsm)
            session.commit()
            return pjsm.id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving PJSM: {e}")
            return None
        finally:
            session.close()

    def create_default_procedure_templates(self):
        """ایجاد قالب‌های پیش‌فرض"""
        session = self.create_session()
        try:
            if session.query(ProcedureTemplate).count() > 0:
                return
            
            templates = self._get_default_templates()
            for t in templates:
                template = ProcedureTemplate(**t)
                session.add(template)
            session.commit()
            logger.info(f"Created {len(templates)} default procedure templates")
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating templates: {e}")
        finally:
            session.close()

    def _get_default_templates(self) -> list:
        """قالب‌های پیش‌فرض پروسیجر"""
        return [
            {
                "name": "7\" Liner Running & Installation",
                "procedure_type": "liner_running",
                "description": "Complete procedure for 7-inch liner running and installation",
                "is_default": True,
                "template_hse_json": [
                    "There is always time to rig up and operate safely: Take 'time-out', if necessary.",
                    "Pre-plan the job ahead, don't run afterwards.",
                    "Focus on falling objects - Avoid loose items on rig-floor and all decks below.",
                    "All equipment used above 2m has to be secured with wire.",
                    "No work at two levels without a barrier in between.",
                    "Hold PJSM and make sure all personnel involved are aware of safety issues.",
                ],
                "template_checklist_json": [
                    {"category": "Safety", "item": "Ensure all personnel involved in the job have proper PPE.", "responsible": "WSS"},
                    {"category": "Safety", "item": "Justify everyone that HSE issues are superior to any other issues and hold PJSM before each job.", "responsible": "WSS"},
                    {"category": "Equipment", "item": "Ensure wear bushing is out.", "responsible": "Driller"},
                    {"category": "Equipment", "item": "Check all equipment is on-site and in good condition.", "responsible": "WSS"},
                    {"category": "Equipment", "item": "Gauge the OD of the liner drift. Refer to API Spec 5CT.", "responsible": "WSS"},
                    {"category": "Equipment", "item": "Rabbit/drift all liner and strap.", "responsible": "WSS"},
                    {"category": "Equipment", "item": "Check all liner threads.", "responsible": "WSS"},
                    {"category": "Equipment", "item": "Ensure no debris is inside liner joints.", "responsible": "WSS"},
                    {"category": "Equipment", "item": "Check liner hanger assembly and accessories.", "responsible": "Baker/Weatherford"},
                    {"category": "Equipment", "item": "Ensure the LDC, collar & shoe are PDC drillable.", "responsible": "WSS"},
                    {"category": "Equipment", "item": "Make sure power tong jaws are suitable for 7\" liner.", "responsible": "Driller"},
                    {"category": "Materials", "item": "Ensure enough number of stop collars are available.", "responsible": "WSS"},
                    {"category": "Materials", "item": "Centralizer types & program available & checked.", "responsible": "WSS"},
                    {"category": "Materials", "item": "Prepare, clean, drift and dope all the joints on pipe rack.", "responsible": "WSS"},
                    {"category": "Safety", "item": "Make sure the snub line is the correct size and length and certified.", "responsible": "Driller"},
                    {"category": "Safety", "item": "Make sure annular preventer functioning.", "responsible": "Driller"},
                ],
                "template_steps_json": [
                    {
                        "step_number": 1,
                        "activity": "Hold pre-job safety meeting for liner installation operations on rig floor.",
                        "parallel": "Focus on: Falling object & heavy equipment.",
                        "caution": ""
                    },
                    {
                        "step_number": 2,
                        "activity": "R/U liner running equipment. Use torque/turn monitoring system.",
                        "parallel": "Ensure wear bushing is out.\nCheck elevator and lock pins.\nCheck stabbing board.",
                        "caution": ""
                    },
                    {
                        "step_number": 3,
                        "activity": "M/U shoe & first joint. Use bakerlok for pin of 1st Joint on shoe. Run & check float with torchlight.",
                        "parallel": "Shoe & collar float valves should be inspected and checked before making up.\nVisually inspect shoe joint for debris.",
                        "caution": "Apply Bakerlok on pin of 1st Joint on shoe, pin of collar, pin of LDC."
                    },
                    {
                        "step_number": 4,
                        "activity": "M/U float collar. Use bakerlok for pin of float collar. Run & check float.",
                        "parallel": "While picking up, one signal man to guide crane operator to prevent breaking the shoe.",
                        "caution": "Clean thread of shoe and collar completely."
                    },
                    {
                        "step_number": 5,
                        "activity": "M/U LDC. Use bakerlok for pin of LDC. Break circulation and check float valve.",
                        "parallel": "",
                        "caution": "Liner Tally must be followed. Any changes to be noted and WSS informed immediately."
                    },
                    {
                        "step_number": 6,
                        "activity": "Run liner as per Tally. F/U all first 5 joints, then F/U every 7 joints. Install centralizers per program.",
                        "parallel": "Mud loggers to prepare swab/surge calculations.\nRunning speed: max 8 stands/hr.",
                        "caution": "Do not exceed 300-500 psi during circulation."
                    },
                    {
                        "step_number": 7,
                        "activity": "M/U liner hanger assembly as per job specialist instruction.",
                        "parallel": "Ensure the tally is followed.",
                        "caution": "Make sure of proper connection between hanger and setting tool before removing the slips."
                    },
                    {
                        "step_number": 8,
                        "activity": "Continue RIH on 5\" DPs. F/U each 10 stands. Break circulation and check free circulation.",
                        "parallel": "Running speed: max 10 stands/hr excluding F/U time.",
                        "caution": "Rotary table should be locked during liner job. Avoid any Left Hand Rotation."
                    },
                    {
                        "step_number": 9,
                        "activity": "Continue RIH to liner setting depth. Wash down last stand to bottom. Tag bottom (max 10klb).",
                        "parallel": "Confirm hole bottom by tagging.\nMinimize stopping time in open hole.",
                        "caution": "Do not jerk the string at any time."
                    },
                    {
                        "step_number": 10,
                        "activity": "Drop ball and continue circulation to land the ball on LDC ball catcher. Set liner hanger.",
                        "parallel": "In case of failure in setting the hanger, contact office for contingency plan.",
                        "caution": "Increase pressure to 1500 psi to set liner hanger. Then increase to 3000 psi to shear ball catcher."
                    },
                    {
                        "step_number": 11,
                        "activity": "Release setting tool by rotating string 20 turns forwards. Make sure it is free.",
                        "parallel": "Mark DP at surface - be cautious not to pull setting tool out of POB.",
                        "caution": "Prepare cement slurry so cementing can start ASAP after liner setting."
                    },
                    {
                        "step_number": 12,
                        "activity": "Make up cement head and prepare for cement job. Hold pre-cement safety meeting.",
                        "parallel": "Connect cementing lines to cement manifold.",
                        "caution": "Check number of liner joints left on racks with pipe tally."
                    },
                ]
            },
            {
                "name": "Surface Casing Running",
                "procedure_type": "casing_running",
                "description": "Procedure for running and cementing surface casing",
                "is_default": True,
                "template_hse_json": [
                    "Ensure all personnel have valid certifications.",
                    "Hold PJSM before operation.",
                    "Monitor casing weights during running.",
                ],
                "template_checklist_json": [
                    {"category": "Safety", "item": "Hold PJSM for casing running operations.", "responsible": "WSS"},
                    {"category": "Equipment", "item": "Drift and strap all casing joints.", "responsible": "WSS"},
                    {"category": "Equipment", "item": "Check float equipment (shoe, collar).", "responsible": "WSS"},
                    {"category": "Equipment", "item": "Prepare centralizer program.", "responsible": "Engineer"},
                    {"category": "Equipment", "item": "Check power tong for correct dies.", "responsible": "Driller"},
                ],
                "template_steps_json": [
                    {"step_number": 1, "activity": "Hold pre-job safety meeting.", "parallel": "Review hazards.", "caution": ""},
                    {"step_number": 2, "activity": "R/U casing running equipment.", "parallel": "Check elevator.", "caution": ""},
                    {"step_number": 3, "activity": "M/U shoe joint and float collar.", "parallel": "Test floats.", "caution": ""},
                    {"step_number": 4, "activity": "Run casing as per tally.", "parallel": "Fill up every 5 joints.", "caution": "Monitor surge pressures."},
                ]
            },
            {
                "name": "Primary Cementing",
                "procedure_type": "cementing",
                "description": "Primary cementing procedure for casing strings",
                "is_default": True,
                "template_hse_json": [
                    "Hold PJSM with all cementing crew.",
                    "Ensure all pressure equipment is tested.",
                    "Have kill line available.",
                ],
                "template_checklist_json": [
                    {"category": "Safety", "item": "Hold PJSM for cementing operations.", "responsible": "WSS"},
                    {"category": "Equipment", "item": "Test cement head and all connections.", "responsible": "Cementer"},
                    {"category": "Materials", "item": "Confirm cement design and additives on location.", "responsible": "Cementer"},
                    {"category": "Equipment", "item": "Check displacement calculations.", "responsible": "Cementer"},
                ],
                "template_steps_json": [
                    {"step_number": 1, "activity": "Hold pre-job safety meeting.", "parallel": "", "caution": ""},
                    {"step_number": 2, "activity": "Mix and pump spacer.", "parallel": "Monitor returns.", "caution": ""},
                    {"step_number": 3, "activity": "Release top plug.", "parallel": "", "caution": ""},
                    {"step_number": 4, "activity": "Displace cement.", "parallel": "Monitor ECD.", "caution": "Do not exceed max ECD."},
                    {"step_number": 5, "activity": "Bump top plug. Record final pressure.", "parallel": "", "caution": ""},
                    {"step_number": 6, "activity": "WOC (Wait on Cement).", "parallel": "", "caution": ""},
                ]
            },
            {
                "name": "BOP Test Procedure",
                "procedure_type": "bop_test",
                "description": "Routine BOP pressure testing procedure",
                "is_default": True,
                "template_hse_json": [
                    "Ensure all personnel are clear of BOP area during testing.",
                    "Have kill line and choke manifold ready.",
                    "Verify all gauges are calibrated.",
                ],
                "template_checklist_json": [
                    {"category": "Safety", "item": "Hold PJSM for BOP test.", "responsible": "WSS"},
                    {"category": "Equipment", "item": "Verify all BOP components are properly installed.", "responsible": "Company Man"},
                    {"category": "Equipment", "item": "Check accumulator pressure (min 200 psi above WHP).", "responsible": "Driller"},
                    {"category": "Equipment", "item": "Test all pressure gauges.", "responsible": "Driller"},
                ],
                "template_steps_json": [
                    {"step_number": 1, "activity": "Hold PJSM.", "parallel": "", "caution": ""},
                    {"step_number": 2, "activity": "Function test annular preventer - open and close.", "parallel": "", "caution": ""},
                    {"step_number": 3, "activity": "Function test pipe rams.", "parallel": "", "caution": ""},
                    {"step_number": 4, "activity": "Pressure test annular to low test pressure (200-300 psi) for 5 min.", "parallel": "", "caution": ""},
                    {"step_number": 5, "activity": "Pressure test pipe rams to rated WP.", "parallel": "", "caution": "Hold for 10 minutes."},
                    {"step_number": 6, "activity": "Test choke and kill lines.", "parallel": "", "caution": ""},
                    {"step_number": 7, "activity": "Function test shear rams.", "parallel": "", "caution": "Do NOT pressure test shear rams."},
                    {"step_number": 8, "activity": "Record all test results and report to Company Man.", "parallel": "", "caution": ""},
                ]
            },
            {
                "name": "Well Kill - Driller's Method",
                "procedure_type": "well_kill",
                "description": "Well kill using Driller's Method (two circulation method)",
                "is_default": True,
                "template_hse_json": [
                    "Immediately alert all personnel on rig floor.",
                    "Close BOP - do not stop pumps abruptly.",
                    "Record SIDPP and SICP.",
                    "Calculate kill mud weight.",
                    "No smoking near degasser.",
                ],
                "template_checklist_json": [
                    {"category": "Safety", "item": "All personnel at stations.", "responsible": "Company Man"},
                    {"category": "Equipment", "item": "BOP closed and confirmed.", "responsible": "Driller"},
                    {"category": "Equipment", "item": "Kill sheet completed.", "responsible": "WSS"},
                    {"category": "Equipment", "item": "SCR test recent and valid.", "responsible": "Driller"},
                ],
                "template_steps_json": [
                    {"step_number": 1, "activity": "Detect kick. Stop rotation. Pick up off bottom.", "parallel": "Alert Company Man immediately.", "caution": ""},
                    {"step_number": 2, "activity": "Flow check. If flowing, shut in well.", "parallel": "Do not shut in with string in OH if possible.", "caution": ""},
                    {"step_number": 3, "activity": "Close pipe rams (or annular). Record SIDPP and SICP.", "parallel": "Record after pressures stabilize.", "caution": ""},
                    {"step_number": 4, "activity": "Calculate: Kill MW = Original MW + SIDPP/(0.052×TVD)", "parallel": "Complete kill sheet.", "caution": ""},
                    {"step_number": 5, "activity": "FIRST CIRCULATION: Circulate kick out with original mud weight.", "parallel": "Maintain constant BHP by holding SIDPP constant.", "caution": "Monitor choke pressure continuously."},
                    {"step_number": 6, "activity": "Weight up mud to kill weight.", "parallel": "Continue circulating if needed.", "caution": ""},
                    {"step_number": 7, "activity": "SECOND CIRCULATION: Circulate kill weight mud around.", "parallel": "Keep BHP constant.", "caution": "Reduce choke gradually as kill mud reaches bit."},
                    {"step_number": 8, "activity": "Verify well is dead. Bleed off pressure slowly.", "parallel": "", "caution": ""},
                    {"step_number": 9, "activity": "Open BOP. Resume normal operations.", "parallel": "Document all events.", "caution": ""},
                ]
            },
            {
                "name": "Tripping Out of Hole",
                "procedure_type": "tripping",
                "description": "Standard POOH procedure",
                "is_default": True,
                "template_hse_json": [
                    "Flow check before and during tripping.",
                    "Monitor pit levels continuously.",
                    "Fill hole every 5 stands.",
                ],
                "template_checklist_json": [
                    {"category": "Safety", "item": "Short trip completed and results satisfactory.", "responsible": "WSS"},
                    {"category": "Equipment", "item": "Fill-up pump ready.", "responsible": "Driller"},
                    {"category": "Equipment", "item": "Trip tank calibrated.", "responsible": "Mud Logger"},
                ],
                "template_steps_json": [
                    {"step_number": 1, "activity": "Condition mud. Perform flow check.", "parallel": "Verify mud weight.", "caution": ""},
                    {"step_number": 2, "activity": "Pull out slowly. Observe for swab.", "parallel": "Monitor trip tank.", "caution": ""},
                    {"step_number": 3, "activity": "Fill hole every 5 stands. Record volumes.", "parallel": "Compare fill volume with theoretical.", "caution": "Any discrepancy: stop and investigate."},
                    {"step_number": 4, "activity": "Pull past casing shoe. Record P/U weight.", "parallel": "", "caution": ""},
                    {"step_number": 5, "activity": "Continue POOH to surface.", "parallel": "", "caution": ""},
                    {"step_number": 6, "activity": "L/D BHA. Inspect bit.", "parallel": "Record bit dull grade.", "caution": ""},
                ]
            },
        ]

    def save_cost_record(self, data: dict):
        session = self.create_session()
        try:
            if data.get("id"):
                record = session.query(CostRecord).filter(
                    CostRecord.id == data["id"]
                ).first()
                if record:
                    for k, v in data.items():
                        if k != "id" and hasattr(record, k):
                            setattr(record, k, v)
                    record.updated_at = _now_utc()
                    record_id = record.id
                else:
                    return None
            else:
                valid = {c.name for c in CostRecord.__table__.columns}
                filtered = {k: v for k, v in data.items() if k in valid}
                record = CostRecord(**filtered)
                session.add(record)
                session.flush()
                record_id = record.id
            session.commit()
            return record_id
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving cost: {e}")
            return None
        finally:
            session.close()

    def get_cost_records(self, well_id: int, category: str = None):
        session = self.create_session()
        try:
            query = session.query(CostRecord).filter(
                CostRecord.well_id == well_id
            )
            if category:
                query = query.filter(CostRecord.category == category)
            records = query.order_by(CostRecord.cost_date.desc()).all()
            return [{col.name: getattr(r, col.name) for col in CostRecord.__table__.columns} for r in records]
        except Exception as e:
            logger.error(f"Error getting costs: {e}")
            return []
        finally:
            session.close()

    def get_cost_summary(self, well_id: int):
        session = self.create_session()
        try:
            from sqlalchemy import func
            records = session.query(
                CostRecord.category,
                func.sum(CostRecord.planned_cost).label('planned'),
                func.sum(CostRecord.actual_cost).label('actual'),
            ).filter(
                CostRecord.well_id == well_id
            ).group_by(CostRecord.category).all()
            return [{
                "category": r.category,
                "planned": r.planned or 0,
                "actual": r.actual or 0,
                "variance": (r.planned or 0) - (r.actual or 0),
            } for r in records]
        except Exception as e:
            logger.error(f"Cost summary error: {e}")
            return []
        finally:
            session.close()
            
    def log_audit(self, action, entity_type="", entity_id=None,
                  entity_name="", details="", user_id=None, username=""):
        session = self.create_session()
        try:
            log = AuditLog(
                user_id=user_id,
                username=username,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                details=details[:500] if details else "",
                timestamp=_now_utc()
            )
            session.add(log)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Audit log error: {e}")
        finally:
            session.close()

    def get_audit_logs(self, entity_type=None, entity_id=None,
                       user_id=None, limit=100):
        session = self.create_session()
        try:
            query = session.query(AuditLog)
            if entity_type:
                query = query.filter(AuditLog.entity_type == entity_type)
            if entity_id:
                query = query.filter(AuditLog.entity_id == entity_id)
            if user_id:
                query = query.filter(AuditLog.user_id == user_id)
            logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
            return [{col.name: getattr(l, col.name) for col in AuditLog.__table__.columns} for l in logs]
        except Exception as e:
            logger.error(f"Get audit logs error: {e}")
            return []
        finally:
            session.close()

    def auto_backup(self, backup_dir=None):
        """Backup خودکار دیتابیس"""
        import shutil
        import os

        if backup_dir is None:
            base_dir = Path(__file__).resolve().parent.parent
            backup_dir = str(base_dir / "backups")

        os.makedirs(backup_dir, exist_ok=True)

        if not os.path.exists(self.db_path):
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(
            backup_dir, f"drillmaster_backup_{timestamp}.db"
        )

        try:
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"Auto-backup created: {backup_path}")

            backups = sorted([
                f for f in os.listdir(backup_dir)
                if f.startswith("drillmaster_backup_") and f.endswith(".db")
            ])
            while len(backups) > 10:
                old = os.path.join(backup_dir, backups.pop(0))
                os.remove(old)
                logger.info(f"Old backup removed: {old}")

            return backup_path
        except Exception as e:
            logger.error(f"Auto-backup error: {e}")
            return None
            
    def search_all(self, query_text: str, well_id: int = None, limit: int = 50) -> list:
        if not query_text or len(query_text) < 2:
            return []

        session = self.create_session()
        results = []

        def escape_like(text: str) -> str:
            return (
                text
                .replace('\\', '\\\\')
                .replace('%', '\\%')
                .replace('_', '\\_')
            )

        escaped = escape_like(query_text)
        q = f"%{escaped}%"

        try:
            # Wells
            wells = session.query(Well).filter(
                (Well.name.ilike(q)) |
                (Well.code.ilike(q)) |
                (Well.field_name.ilike(q)) |
                (Well.rig_name.ilike(q)) |
                (Well.operator.ilike(q))
            ).limit(10).all()
            
            for w in wells:
                results.append({
                    "type": "well",
                    "id": w.id,
                    "title": w.name,
                    "subtitle": f"Code: {w.code} | Field: {w.field_name}",
                    "icon": "🛢️",
                })

            dr_query = session.query(DailyReport).filter(
                DailyReport.summary.ilike(q)
            )
            if well_id:
                dr_query = dr_query.filter(DailyReport.well_id == well_id)
            reports = dr_query.limit(10).all() 
            for r in reports:
                results.append({
                    "type": "report",
                    "id": r.id,
                    "title": f"Report #{r.report_number} - {r.report_date}",
                    "subtitle": (r.summary or "")[:100],
                    "icon": "📅",
                })

            # Time Logs
            logs = session.query(TimeLog24H).filter(
                TimeLog24H.activity_description.ilike(q)
            ).limit(10).all()
            for l in logs:
                results.append({
                    "type": "timelog",
                    "id": l.id,
                    "title": f"{l.main_code or ''} - {l.time_from}",
                    "subtitle": (l.activity_description or "")[:100],
                    "icon": "🕐",
                })

        except Exception as e:
            logger.error(f"Search error: {e}")
        finally:
            session.close()

        return results[:limit]
        