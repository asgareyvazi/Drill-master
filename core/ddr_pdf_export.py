# core/ddr_pdf_export.py
"""
Professional DDR PDF Export
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DDRPDFExporter:
    """اکسپورت حرفه‌ای DDR به PDF"""

    def __init__(self, db_manager):
        self.db = db_manager

    def export(self, report_id: int, filename: str) -> bool:
        try:
            report = self.db.get_daily_report_by_id(report_id)
            if not report:
                return False

            well = self.db.get_well_by_id(report.get('well_id')) or {}
            params = self.db.get_drilling_parameters(report_id=report_id)
            mud = self.db.get_mud_report(report_id=report_id)

            # Time logs
            session = self.db.create_session()
            from core.database import TimeLog24H
            logs = session.query(TimeLog24H).filter(
                TimeLog24H.report_id == report_id
            ).order_by(TimeLog24H.time_from).all()
            session.close()

            html = self._build_html(report, well, logs, params, mud)

            # PDF via QTextDocument
            from PySide6.QtGui import QTextDocument
            from PySide6.QtPrintSupport import QPrinter

            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(filename)
            printer.setPageSize(QPrinter.A4)

            doc = QTextDocument()
            doc.setHtml(html)
            doc.print_(printer)
            return True

        except Exception as e:
            logger.error(f"DDR PDF error: {e}")
            return False

    def _build_html(self, report, well, logs, params, mud):
        wn = well.get('name', 'Unknown')
        rn = well.get('rig_name', '')
        op = well.get('operator', '')
        field = well.get('field_name', '')
        rd = report.get('report_date', '')
        rno = report.get('report_number', '')
        rig_day = report.get('rig_day', '')
        d0 = report.get('depth_0000', 0) or 0
        d6 = report.get('depth_0600', 0) or 0
        d24 = report.get('depth_2400', 0) or 0
        summary = report.get('summary', '') or ''

        total_hrs = sum(l.duration or 0 for l in logs)
        npt_hrs = sum(l.duration or 0 for l in logs if l.is_npt)
        pt_hrs = total_hrs - npt_hrs

        html = f"""<html><head><style>
        body {{ font-family: Arial; font-size: 10pt; margin: 15px; color: #2c3e50; }}
        h1 {{ color: #2c3e50; font-size: 15pt; text-align: center; border-bottom: 3px solid #3498db; }}
        h2 {{ color: #2980b9; font-size: 12pt; margin-top: 12px; border-bottom: 1px solid #bdc3c7; }}
        .ht {{ width: 100%; border-collapse: collapse; margin: 8px 0; }}
        .ht td, .ht th {{ padding: 4px 6px; border: 1px solid #bdc3c7; font-size: 9pt; }}
        .ht th {{ background: #3498db; color: white; }}
        .tt {{ width: 100%; border-collapse: collapse; font-size: 8pt; }}
        .tt td, .tt th {{ padding: 3px 4px; border: 1px solid #bdc3c7; }}
        .tt th {{ background: #2c3e50; color: white; }}
        .npt {{ background: #fadbd8; }}
        .sum {{ padding: 8px; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; }}
        </style></head><body>
        <h1>📋 DAILY DRILLING REPORT</h1>
        <table class="ht">
        <tr><th>Well</th><td>{wn}</td><th>Rig</th><td>{rn}</td><th>Report #</th><td>{rno}</td></tr>
        <tr><th>Operator</th><td>{op}</td><th>Field</th><td>{field}</td><th>Rig Day</th><td>{rig_day}</td></tr>
        <tr><th>Date</th><td>{rd}</td><th>Status</th><td>{report.get('status','')}</td><th></th><td></td></tr>
        </table>
        <h2>📏 Depth Summary</h2>
        <table class="ht">
        <tr><th>@ 00:00</th><td>{d0:.1f} m</td><th>@ 06:00</th><td>{d6:.1f} m</td>
        <th>@ 24:00</th><td>{d24:.1f} m</td><th>Progress</th><td>{d24-d0:.1f} m</td></tr>
        </table>"""

        if params:
            html += f"""<h2>⚙️ Drilling Parameters</h2>
            <table class="ht">
            <tr><th>Bit #</th><td>{params.get('bit_no','')}</td><th>Size</th><td>{params.get('bit_size','')}"</td>
            <th>Type</th><td>{params.get('bit_type','')}</td><th>ROP</th><td>{params.get('avg_rop',0):.1f} m/hr</td></tr>
            <tr><th>WOB</th><td>{params.get('wob_min',0)}-{params.get('wob_max',0)} klb</td>
            <th>RPM</th><td>{params.get('rpm_min',0)}-{params.get('rpm_max',0)}</td>
            <th>TQ</th><td>{params.get('torque_min',0)}-{params.get('torque_max',0)}</td>
            <th>SPP</th><td>{params.get('pump_pressure_min',0)}-{params.get('pump_pressure_max',0)} psi</td></tr>
            </table>"""

        if mud:
            html += f"""<h2>🧪 Mud Properties</h2>
            <table class="ht">
            <tr><th>Type</th><td>{mud.get('mud_type','')}</td><th>MW</th><td>{mud.get('mw',0):.1f} pcf</td>
            <th>PV</th><td>{mud.get('pv',0):.1f}</td><th>YP</th><td>{mud.get('yp',0):.1f}</td></tr>
            <tr><th>Gel 10s/10m</th><td>{mud.get('gel_10s',0):.1f}/{mud.get('gel_10m',0):.1f}</td>
            <th>FL</th><td>{mud.get('fl',0):.1f}</td><th>pH</th><td>{mud.get('ph',0):.1f}</td>
            <th>Cl-</th><td>{mud.get('chloride',0):.0f}</td></tr>
            </table>"""

        html += """<h2>🕒 24-Hour Operations</h2>
        <table class="tt">
        <tr><th>From</th><th>To</th><th>Hrs</th><th>Phase</th><th>Code</th><th>NPT</th><th>Description</th></tr>"""

        for log in logs:
            tf = log.time_from.strftime("%H:%M") if log.time_from else ""
            tt = log.time_to.strftime("%H:%M") if log.time_to else ""
            cls = 'npt' if log.is_npt else ''
            html += f"""<tr class="{cls}"><td>{tf}</td><td>{tt}</td><td>{log.duration or 0:.2f}</td>
            <td>{log.main_phase or ''}</td><td>{log.main_code or ''}</td>
            <td>{'⚠️' if log.is_npt else ''}</td><td>{log.activity_description or ''}</td></tr>"""

        html += f"""</table>
        <h2>📊 Time Analysis</h2>
        <table class="ht">
        <tr><th>Total Hours</th><td>{total_hrs:.1f}</td>
        <th>Productive</th><td>{pt_hrs:.1f} ({pt_hrs/max(total_hrs,1)*100:.0f}%)</td>
        <th>NPT</th><td>{npt_hrs:.1f} ({npt_hrs/max(total_hrs,1)*100:.0f}%)</td></tr>
        </table>"""

        if summary:
            html += f'<h2>📝 Summary</h2><div class="sum">{summary.replace(chr(10),"<br>")}</div>'

        html += f'<hr><p style="color:#999;font-size:8pt;text-align:center;">DrillMaster | {datetime.now().strftime("%Y-%m-%d %H:%M")}</p></body></html>'
        return html