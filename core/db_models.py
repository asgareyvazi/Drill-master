"""
Database ORM Models — extracted from database.py for maintainability.

All SQLAlchemy model classes are defined here. database.py imports them
for backward compatibility:
    from core.database import Well, DailyReport, ...
"""
import logging
from datetime import datetime, date, timezone

from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime,
    Boolean, ForeignKey, JSON, Text, Time,
)
from sqlalchemy.orm import relationship, declarative_base, backref

logger = logging.getLogger(__name__)

Base = declarative_base()

def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

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
