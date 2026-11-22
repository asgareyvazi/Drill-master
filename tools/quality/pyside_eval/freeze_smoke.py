"""M324 frozen-build smoke: the Qt modules DrillMaster imports, inside a PyInstaller one-folder bundle."""
import sys
import PySide6
import shiboken6
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtNetwork import QNetworkAccessManager
from PySide6.QtCharts import QChart, QChartView, QLineSeries


class Emitter(QObject):
    fired = Signal(int)


app = QApplication(sys.argv)
win = QMainWindow()
series = QLineSeries()
series.append(0, 0)
series.append(1, 2)
chart = QChart()
chart.addSeries(series)
win.setCentralWidget(QChartView(chart))
printer = QPrinter()
svg = QSvgRenderer(b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"/>')
net = QNetworkAccessManager()
got = []
e = Emitter()
e.fired.connect(got.append)
e.fired.emit(7)
win.show()
QTimer.singleShot(50, app.quit)
app.exec()
print(f"FROZEN={getattr(sys, 'frozen', False)} PySide6={PySide6.__version__} shiboken6={shiboken6.__version__} "
      f"platform={app.platformName()} svg_valid={svg.isValid()} signal={got} chart_series={len(chart.series())}")
