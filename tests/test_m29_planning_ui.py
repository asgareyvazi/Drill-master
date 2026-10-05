"""One isolated offscreen process exercises the actual W10/dialog consumers."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_planning_mutations_null_charts_and_active_revision():
    script = textwrap.dedent("""
        import sys
        sys.path.insert(0, 'tests')
        from datetime import date, time
        from PySide6.QtWidgets import QApplication, QTableWidgetItem, QMessageBox, QLabel
        from PySide6.QtCore import Qt
        from core.database import BulkMaterials, DailyReport, TimeLog24H, WellPlan, PlannedActivity, BitReport, Section
        from core.permissions import permissions
        from test_cost_truth_boundary import memory_manager
        from tabs.w10_Planning_Widget import MaterialInventoryTab, WellPlanTab, CodeManagementTab, DrillingParamsTab
        from dialogs.planning_dialog import WellPlanDialog, AddPlanActivityDialog
        app = QApplication([])
        QMessageBox.information = lambda *a, **k: QMessageBox.Ok
        QMessageBox.critical = lambda *a, **k: QMessageBox.Ok
        QMessageBox.question = lambda *a, **k: QMessageBox.Yes
        permissions.set_user({'role':'engineer'})
        db, wid = memory_manager()
        with db.session_scope() as s:
            section = Section(well_id=wid, name='S')
            s.add(section); s.flush(); sid=section.id
            report = DailyReport(well_id=wid, section_id=sid, report_date=date(2026,1,1), depth_2400=None)
            s.add(report); s.flush(); rid=report.id
            s.add(TimeLog24H(report_id=rid,time_from=time(0),time_to=time(1),duration=None,is_npt=True))
            s.add(BulkMaterials(well_id=wid, report_id=rid,section_id=sid,material_name='Barite',unit='lb',initial_stock=123,report_date=date(2026,1,1)))
        tab=MaterialInventoryTab(db)
        tab.set_current_well(wid); tab.set_current_report(rid); tab.set_current_section(sid)
        tab.material_table.setRowCount(2)
        for col,value in enumerate(['Barite','kg','','0','0']):
            tab.material_table.setItem(1,col,QTableWidgetItem(value))
        assert tab.save_material_row(1) is True
        assert tab.material_table.item(1,5).text()=='—'
        selected=tab.material_table.item(1,0).data(Qt.ItemDataRole.UserRole)
        with db.session_scope() as s:
            rows=s.query(BulkMaterials).all()
            assert len(rows)==2
            row=s.get(BulkMaterials,selected)
            assert row.initial_stock is row.current_stock is None and row.received==row.used==0
        permissions.set_user({'role':'viewer'})
        tab.material_table.item(1,2).setText('9')
        assert tab.save_material_row(1) is False
        with db.session_scope() as s: assert s.get(BulkMaterials,selected).initial_stock is None
        permissions.set_user({'role':'supervisor'})
        def broken_chart(): raise RuntimeError('Injected renderer failure after commit')
        tab.update_chart=broken_chart
        tab.material_table.selectRow(1)
        assert tab.remove_material() is True
        assert 'DELETED — display refresh failed' in tab.status_label.text()
        with db.session_scope() as s:
            rows=s.query(BulkMaterials).all()
            assert len(rows)==1 and rows[0].unit=='lb' and rows[0].initial_stock==123

        dialog=WellPlanDialog(db,wid)
        assert dialog.final_depth.value()==-1
        dialog.activities=[dict(activity='Unknown target',start='2026-01-01 00:00',end='2026-01-02 00:00',section_id=sid)]
        dialog._refresh_table(); dialog._draw_timeline()
        assert isinstance(dialog.timeline_widget.layout().itemAt(0).widget(),QLabel)
        assert dialog.save_plan() is True
        with db.session_scope() as s:
            activity=s.query(PlannedActivity).one()
            assert activity.section_id==sid
            assert activity.planned_depth_to is activity.planned_duration_hours is None
            first=s.query(WellPlan).one().id
        dialog.activities=[dict(activity='Invalid',start='bad',end='2026-01-02 00:00')]
        assert dialog.save_plan() is False
        with db.session_scope() as s:
            assert s.query(WellPlan).count()==1 and s.get(WellPlan,first).is_active
        dialog.activities=[dict(activity='Explicit zero',start='2026-01-01 00:00',end='2026-01-02 00:00',depth_from=0,depth_to=0,duration_hrs=0)]
        assert dialog.save_plan() is True
        with db.session_scope() as s:
            assert s.query(WellPlan).filter_by(is_active=True).count()==1
            assert s.get(WellPlan,first).is_active is False
        wp=WellPlanTab(db)
        wp.set_current_well(wid)
        assert len(wp.plan_activities)==1 and wp.plan_activities[0]['activity_name']=='Explicit zero'
        assert wp.fact_depths==[None] and wp.plan_final_value.text()=='0.0 m'
        assert wp.final_depth_value.text()=='— m'
        wp.set_current_section(sid)
        assert wp.plan_activities==[]
        edit=AddPlanActivityDialog(None,db,wid,[],dict(activity='Untouched',depth_to=0,duration_hrs=None))
        assert edit.depth_from.value()==-1 and edit.depth_to.value()==0 and edit.duration.value()==-1

        import tabs.w10_Planning_Widget as planning_module
        from tabs.w10_Planning_Widget import MudParamsTab
        mud_tab=MudParamsTab(db)
        assert mud_tab.data_table.horizontalHeaderItem(1).text()=='MW (PCF)'
        assert mud_tab.param_combo.currentText()=='Mud Sample MW (PCF)'
        assert mud_tab.data_table.horizontalHeaderItem(0).text()=='Depth (m)'
        mud_tab.data_table.setRowCount(1); mud_tab.mud_data=[{'depth': 123}]
        mud_tab.set_current_well(None)
        assert mud_tab.data_table.rowCount()==0 and mud_tab.mud_data==[]
        codes=CodeManagementTab(db)
        codes.set_current_well(wid); codes.set_current_report(rid)
        assert codes.code_table.rowCount()==1 and codes.code_table.item(0,5).text()=='—'
        assert codes.total_hours.text()=='— hrs'
        assert codes.status_summary_table.item(0,1).text()=='— days'
        original_subplots=planning_module.plt.subplots
        def broken_chart(*args, **kwargs):
            raise RuntimeError('injected chart renderer failure')
        planning_module.plt.subplots=broken_chart
        try:
            codes._draw_main_code_chart({'Drilling': 1})
            assert any('FAILED' in label.text() for label in codes.main_code_chart.findChildren(QLabel))
        finally:
            planning_module.plt.subplots=original_subplots
        with db.session_scope() as s:
            s.add(BitReport(well_id=wid,report_id=rid,report_date=date(2026,1,1),bit_records_json=[{
                'Bit No':'1','Depth Out (m)':0,'ROP (m/hr)':0,'WOB Min (klb)':10}]))
        drilling=DrillingParamsTab(db)
        drilling.set_current_well(wid)
        assert drilling.rop_data==[dict(depth=0,rop=0)]
        assert drilling.bit_params['1']['WOB (klb)'] is None
        assert drilling.bit_params['1']['ROP (m/hr)']==0
        with db.session_scope() as s:
            s.add(BitReport(well_id=wid,report_date=date(2026,1,1),bit_records_json=[]))
        drilling.load_data()
        assert 'Ambiguous' in drilling.status_label.text() and drilling.rop_table.rowCount()==0
        from tabs.w6_Trajectory_Widget import TripSheetTab
        from core.database import TripSheetEntry
        trip=TripSheetTab(db)
        trip.set_current_well(wid); trip.load_for_report(rid)
        trip.add_row()
        assert trip.trip_table.item(0,1).text().count(':')==1
        assert trip.trip_table.item(0,3).text()==''
        trip.trip_table.item(0,2).setText('Trip')
        trip.trip_table.item(0,1).setText('bad')
        assert trip.save_data() is False
        trip.trip_table.item(0,1).setText('01:00')
        assert trip.save_data() is True
        with db.session_scope() as session:
            row=session.query(TripSheetEntry).filter_by(report_id=rid).one()
            assert row.depth is row.duration is None and row.activity=='Trip'
        trip.calculate_cumulative()
        assert trip.trip_table.item(0,4).text()=='—'
        from tabs.w2_Daily_Report import DailyReportWidget
        from dialogs.hierarchy_dialogs import NewSectionDialog
        ddr=DailyReportWidget(db)
        ddr.current_well_id=wid; ddr.current_section_id=sid
        ddr.current_well=db.get_well_by_id(wid)
        ddr.load_report_by_id(rid)
        assert ddr.depth_2400.value()==-1
        assert ddr._depth_gain() is None
        assert "Depth @ 24:00:</strong> — m" in ddr.create_print_html()
        ddr.depth_2400.setValue(0)
        assert ddr._collect_report_data(wid,sid)['depth_2400']==0
        permissions.set_user({'role':'viewer'})
        assert ddr.save_report() is False
        permissions.set_user({'role':'engineer'})
        section_dialog=NewSectionDialog(db, None, wid)
        section_dialog.name_edit.setText('Unknown duration')
        section_dialog.depth_to_spin.setValue(100)
        assert section_dialog.planned_days_spin.value()==-1
        section_dialog.create_section()
        with db.session_scope() as session:
            saved=session.get(Section,section_dialog.created_id)
            assert saved.planned_days is saved.planned_rop is None
        db.close()
        print('M29_UI_OK')
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "M29_UI_OK" in result.stdout
