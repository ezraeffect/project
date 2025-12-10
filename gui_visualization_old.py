"""
WTVB01-485 Vibration Sensor Monitoring - GUI Visualization
PyQt5 기반 탭 방식 레이아웃으로 시계열 차트를 표시
"""

import sys
import time
import csv
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from collections import deque
import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStatusBar, QComboBox, QSpinBox, QGridLayout, QGroupBox, QTabWidget, QFrame,
    QTableWidget, QTableWidgetItem, QFileDialog, QDoubleSpinBox
)
from PyQt5.QtCore import Qt, QTimer, QDateTime
from PyQt5.QtGui import QColor, QPen, QFont
from PyQt5.QtChart import QChart, QChartView, QLineSeries, QValueAxis, QDateTimeAxis, QBarSeries, QBarSet

from data_collector import DataCollector, MultiAxisAnalyzer, DataBuffer
from sensor_communication import WTVBSensor, get_available_ports
from anomaly_detection import BaselineCalculator, AnomalyDetector


class TriAxisChart(QWidget):
    """3축 데이터를 한 차트에 표시하는 탭 전용 위젯"""

    def __init__(self, title: str, y_label: str, max_points: int = 200,
                 y_range: Optional[tuple] = None, parent=None):
        super().__init__(parent)
        self.title = title
        self.y_label = y_label
        self.max_points = max_points
        self.y_range = y_range

        # 3개의 데이터 시리즈 (X, Y, Z)
        self.series_x = QLineSeries()
        self.series_y = QLineSeries()
        self.series_z = QLineSeries()

        self.series_x.setName("X")
        self.series_y.setName("Y")
        self.series_z.setName("Z")

        # 색상 설정
        self.series_x.setColor(QColor("#FF6B6B"))  # 빨강
        self.series_y.setColor(QColor("#4ECDC4"))  # 청록
        self.series_z.setColor(QColor("#FFE66D"))  # 노랑

        self.series_x.setUseOpenGL(True)
        self.series_y.setUseOpenGL(True)
        self.series_z.setUseOpenGL(True)

        # 차트 생성
        self.chart = QChart()
        self.chart.addSeries(self.series_x)
        self.chart.addSeries(self.series_y)
        self.chart.addSeries(self.series_z)

        # 축
        self.x_axis = QDateTimeAxis()
        self.x_axis.setFormat("hh:mm:ss")
        self.x_axis.setTitleText("Time")
        self.x_axis.setTickCount(6)
        self.y_axis = QValueAxis()
        self.y_axis.setTitleText(self.y_label)
        if self.y_range:
            self.y_axis.setRange(self.y_range[0], self.y_range[1])
        else:
            self.y_axis.setRange(-50, 50)

        axis_pen = QPen(QColor("#9BC5FF"))
        axis_pen.setWidth(2)
        self.x_axis.setLinePen(axis_pen)
        self.y_axis.setLinePen(axis_pen)
        self.x_axis.setLabelsBrush(QColor("#E8F1FF"))
        self.y_axis.setLabelsBrush(QColor("#E8F1FF"))
        self.x_axis.setTitleBrush(QColor("#E8F1FF"))
        self.y_axis.setTitleBrush(QColor("#E8F1FF"))
        self.x_axis.setGridLineColor(QColor("#3C4C65"))
        self.y_axis.setGridLineColor(QColor("#3C4C65"))

        self.chart.addAxis(self.x_axis, Qt.AlignBottom)
        self.chart.addAxis(self.y_axis, Qt.AlignLeft)

        for series in [self.series_x, self.series_y, self.series_z]:
            series.attachAxis(self.x_axis)
            series.attachAxis(self.y_axis)

        self.chart.setBackgroundBrush(QColor("#2B2B2B"))
        self.chart.setTitleBrush(QColor("#FFFFFF"))
        self.chart.setTitle(title)

        # 차트 뷰
        self.chart_view = QChartView(self.chart)

        layout = QVBoxLayout()
        layout.addWidget(self.chart_view)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # 데이터 버퍼
        self.data_x = deque(maxlen=self.max_points)
        self.data_y = deque(maxlen=self.max_points)
        self.data_z = deque(maxlen=self.max_points)
        self.timestamps = deque(maxlen=self.max_points)


    def update_data(self, x: float, y: float, z: float, timestamp: Optional[float] = None) -> None:
        """데이터 업데이트 (timestamp는 초 단위 Unix 시간)"""
        ts = timestamp if timestamp is not None else time.time()
        ts_ms = int(ts * 1000)

        self.data_x.append(x)
        self.data_y.append(y)
        self.data_z.append(z)
        self.timestamps.append(ts_ms)

        # 시리즈 업데이트
        self.series_x.clear()
        self.series_y.clear()
        self.series_z.clear()

        for t_ms, vx, vy, vz in zip(self.timestamps, self.data_x, self.data_y, self.data_z):
            self.series_x.append(t_ms, vx)
            self.series_y.append(t_ms, vy)
            self.series_z.append(t_ms, vz)


        # 축 범위 자동 조정
        if len(self.timestamps) > 0:
            if len(self.timestamps) == 1:
                single_time = self.timestamps[0]
                start_time = QDateTime.fromMSecsSinceEpoch(single_time - 2000)
                end_time = QDateTime.fromMSecsSinceEpoch(single_time + 2000)
            else:
                start_time = QDateTime.fromMSecsSinceEpoch(self.timestamps[0])
                end_time = QDateTime.fromMSecsSinceEpoch(self.timestamps[-1])
            self.x_axis.setRange(start_time, end_time)

        if len(self.data_x) > 0:
            all_values = list(self.data_x) + list(self.data_y) + list(self.data_z)
            max_val = max(all_values) if all_values else 50
            min_val = min(all_values) if all_values else -50
            margin = (max_val - min_val) * 0.15 if max_val > min_val else 10
            self.y_axis.setRange(min_val - margin, max_val + margin)

    def clear(self) -> None:
        """그래프 초기화"""
        self.data_x.clear()
        self.data_y.clear()
        self.data_z.clear()
        self.timestamps.clear()
        self.series_x.clear()
        self.series_y.clear()
        self.series_z.clear()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # 기본 정렬 사용; 추가 작업 없음


class CommunicationPanel(QWidget):
    """통신 설정 및 상태 표시 패널"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        layout = QHBoxLayout()
        
        # 1. 통신 설정 (좌측)
        settings_group = QGroupBox("Communication Settings")
        settings_layout = QHBoxLayout()
        
        settings_layout.addWidget(QLabel("COM Port:"))
        self.port_combo = QComboBox()
        self.port_combo.addItems(get_available_ports())
        settings_layout.addWidget(self.port_combo)
        
        settings_layout.addWidget(QLabel("Baud Rate:"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["4800", "9600", "19200", "38400", "57600", "115200", "230400"])
        self.baud_combo.setCurrentText("9600")
        settings_layout.addWidget(self.baud_combo)
        
        settings_layout.addWidget(QLabel("Slave ID:"))
        self.slave_id_spin = QSpinBox()
        self.slave_id_spin.setRange(0x00, 0x7F)
        self.slave_id_spin.setValue(0x50)
        settings_layout.addWidget(self.slave_id_spin)
        
        # 버튼
        self.connect_button = QPushButton("Connect")
        self.connect_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        settings_layout.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False)
        self.disconnect_button.setStyleSheet("background-color: #F44336; color: white; font-weight: bold;")
        settings_layout.addWidget(self.disconnect_button)
        
        self.refresh_button = QPushButton("Refresh Ports")
        settings_layout.addWidget(self.refresh_button)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # 2. 상태 표시 (우측)
        status_group = QGroupBox("Connection Status")
        status_layout = QGridLayout()
        
        self.connection_status_label = QLabel("●")
        self.connection_status_label.setStyleSheet("color: #FF6B6B; font-size: 14pt;")
        status_layout.addWidget(QLabel("Status:"), 0, 0)
        status_layout.addWidget(self.connection_status_label, 0, 1)
        
        self.receive_status_label = QLabel("Idle")
        status_layout.addWidget(QLabel("Receive:"), 1, 0)
        status_layout.addWidget(self.receive_status_label, 1, 1)
        
        self.packet_count_label = QLabel("0")
        status_layout.addWidget(QLabel("Packets:"), 2, 0)
        status_layout.addWidget(self.packet_count_label, 2, 1)
        
        self.elapsed_time_label = QLabel("00:00:00")
        status_layout.addWidget(QLabel("Elapsed:"), 3, 0)
        status_layout.addWidget(self.elapsed_time_label, 3, 1)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        self.setLayout(layout)
        
        # 타이머
        self.elapsed_timer = QTimer()
        self.elapsed_timer.timeout.connect(self._update_elapsed_time)
        self.start_time = None
        self.packet_count = 0
        
    def set_connected(self, connected: bool, port: str = "", baudrate: int = 0) -> None:
        """연결 상태 업데이트"""
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.port_combo.setEnabled(not connected)
        self.baud_combo.setEnabled(not connected)
        self.slave_id_spin.setEnabled(not connected)
        
        if connected:
            self.connection_status_label.setText("●")
            self.connection_status_label.setStyleSheet("color: #4CAF50; font-size: 14pt;")
            self.start_time = datetime.now()
            self.elapsed_timer.start(1000)
            self.packet_count = 0
        else:
            self.connection_status_label.setText("●")
            self.connection_status_label.setStyleSheet("color: #FF6B6B; font-size: 14pt;")
            self.elapsed_timer.stop()
            self.start_time = None
            self.elapsed_time_label.setText("00:00:00")
    
    def update_receive_status(self, receiving: bool) -> None:
        """수신 상태 업데이트"""
        if receiving:
            self.receive_status_label.setText("Receiving")
            self.receive_status_label.setStyleSheet("color: #4ECDC4;")
            self.packet_count += 1
            self.packet_count_label.setText(str(self.packet_count))
        else:
            self.receive_status_label.setText("Idle")
            self.receive_status_label.setStyleSheet("color: #FFD700;")
    
    def _update_elapsed_time(self) -> None:
        """경과 시간 업데이트"""
        if self.start_time:
            elapsed = datetime.now() - self.start_time
            hours = elapsed.seconds // 3600
            minutes = (elapsed.seconds % 3600) // 60
            seconds = elapsed.seconds % 60
            self.elapsed_time_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")


class SensorInfoPanel(QWidget):
    """센서 정보 표시 패널"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # 3x5 그리드 레이아웃
        grid = QGridLayout()
        grid.setSpacing(20)
        
        # 센서 정보 레이블 딕셔너리
        self.info_labels = {}
        
        # 행 1: 가속도
        self._add_info_item(grid, 0, 0, "Acceleration X", "ax_value", "g")
        self._add_info_item(grid, 0, 1, "Acceleration Y", "ay_value", "g")
        self._add_info_item(grid, 0, 2, "Acceleration Z", "az_value", "g")
        
        # 행 2: 가속도 진폭
        self._add_info_item(grid, 1, 0, "X acceleration amplitude", "ax_amp_value", "g")
        self._add_info_item(grid, 1, 1, "Y acceleration amplitude", "ay_amp_value", "g")
        self._add_info_item(grid, 1, 2, "Z acceleration amplitude", "az_amp_value", "g")
        
        # 행 3: 속도 진폭
        self._add_info_item(grid, 2, 0, "X velocity amplitude", "vx_value", "mm/s")
        self._add_info_item(grid, 2, 1, "Y velocity amplitude", "vy_value", "mm/s")
        self._add_info_item(grid, 2, 2, "Z velocity amplitude", "vz_value", "mm/s")
        
        # 행 4: 변위 진폭
        self._add_info_item(grid, 3, 0, "X displacement amplitude", "dx_value", "μm")
        self._add_info_item(grid, 3, 1, "Y displacement amplitude", "dy_value", "μm")
        self._add_info_item(grid, 3, 2, "Z displacement amplitude", "dz_value", "μm")
        
        # 행 5: 주파수 진동
        self._add_info_item(grid, 4, 0, "X frequency vibration frequency", "hx_value", "Hz")
        self._add_info_item(grid, 4, 1, "Y frequency vibration frequency", "hy_value", "Hz")
        self._add_info_item(grid, 4, 2, "Z frequency vibration frequency", "hz_value", "Hz")
        
        # 행 6: 칩 시간, 온도, 버전
        self._add_info_item(grid, 5, 0, "Chip Time", "time_value", "")
        self._add_info_item(grid, 5, 1, "Temperature", "temp_value", "°C")
        self._add_info_item(grid, 5, 2, "Version number", "version_value", "")
        
        main_layout.addLayout(grid)
        main_layout.addStretch()
        self.setLayout(main_layout)
    
    def _add_info_item(self, grid: QGridLayout, row: int, col: int, label_text: str, key: str, unit: str) -> None:
        """정보 항목 추가"""
        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setStyleSheet("background-color: #1E1E1E; border: 1px solid #3C3C3C; border-radius: 4px;")
        
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        
        # 값 레이블
        value_label = QLabel("0.0" + unit)
        value_label.setAlignment(Qt.AlignCenter)
        value_font = QFont()
        value_font.setPointSize(18)
        value_font.setBold(True)
        value_label.setFont(value_font)
        value_label.setStyleSheet("color: #FFA500;")
        
        # 설명 레이블
        desc_label = QLabel(label_text)
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        desc_font = QFont()
        desc_font.setPointSize(9)
        desc_label.setFont(desc_font)
        desc_label.setStyleSheet("color: #CCCCCC;")
        
        layout.addWidget(value_label)
        layout.addWidget(desc_label)
        frame.setLayout(layout)
        
        grid.addWidget(frame, row, col)
        self.info_labels[key] = (value_label, unit)
    
    def update_info(self, data, ax_amp: float = 0.0, ay_amp: float = 0.0, az_amp: float = 0.0) -> None:
        """센서 데이터로 정보 업데이트"""
        if not data:
            return
        
        # 가속도
        self._update_value("ax_value", data.ax)
        self._update_value("ay_value", data.ay)
        self._update_value("az_value", data.az)
        
        # 가속도 진폭 (계산된 값)
        self._update_value("ax_amp_value", ax_amp)
        self._update_value("ay_amp_value", ay_amp)
        self._update_value("az_amp_value", az_amp)
        
        # 속도
        self._update_value("vx_value", data.vx)
        self._update_value("vy_value", data.vy)
        self._update_value("vz_value", data.vz)
        
        # 변위
        self._update_value("dx_value", data.dx, decimals=0)
        self._update_value("dy_value", data.dy, decimals=0)
        self._update_value("dz_value", data.dz, decimals=0)
        
        # 주파수
        self._update_value("hx_value", data.hx, decimals=1)
        self._update_value("hy_value", data.hy, decimals=1)
        self._update_value("hz_value", data.hz, decimals=1)
        
        # 시간
        time_str = datetime.fromtimestamp(data.timestamp).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.info_labels["time_value"][0].setText(time_str)
        
        # 온도
        self._update_value("temp_value", data.temp, decimals=2)
        
        # 버전 (임시)
        self.info_labels["version_value"][0].setText("10210.1.22")
    
    def _update_value(self, key: str, value: float, decimals: int = 4) -> None:
        """값 업데이트"""
        if key in self.info_labels:
            label, unit = self.info_labels[key]
            formatted = f"{value:.{decimals}f}{unit}"
            label.setText(formatted)


class AnomalyPanel(QWidget):
    """가속도 이상 지표 표시 및 베이스라인 관리 패널"""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout()
        control_layout = QHBoxLayout()

        # Baseline 계산 UI는 Dashboard 탭으로 이동
        control_layout.addStretch()

        layout.addLayout(control_layout)

        # 상태 테이블 구성 (가속도 축 위주)
        headers = [
            "Axis", "Status", "RMS", "Warn", "Crit",
            "Kurtosis", "K-Warn", "K-Crit",
            "HF Energy", "HF-Warn", "HF-Crit"
        ]
        header_layout = QHBoxLayout()
        for text in headers:
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #E8F1FF; font-weight: bold;")
            lbl.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(lbl)
        layout.addLayout(header_layout)

        self.rows = {}
        axes = ["ax", "ay", "az"]
        for axis in axes:
            row_layout = QHBoxLayout()
            axis_label = QLabel(axis.upper())
            axis_label.setAlignment(Qt.AlignCenter)
            axis_label.setStyleSheet("color: #FFFFFF; font-weight: bold;")
            row_layout.addWidget(axis_label)

            status_label = QLabel("–")
            status_label.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(status_label)

            fields = ["rms", "warn", "crit", "kurt", "k_warn", "k_crit", "hf", "hf_warn", "hf_crit"]
            cell_map = {"status": status_label}
            for f in fields:
                lbl = QLabel("0")
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet("color: #CCCCCC;")
                row_layout.addWidget(lbl)
                cell_map[f] = lbl

            self.rows[axis] = cell_map
            layout.addLayout(row_layout)

        layout.addStretch()
        self.setLayout(layout)

    def reset(self) -> None:
        for cells in self.rows.values():
            cells["status"].setText("–")
            for key, lbl in cells.items():
                if key == "status":
                    continue
                lbl.setText("0")
                lbl.setStyleSheet("color: #CCCCCC;")

    def update_row(self, axis: str, result: Dict, thresholds: Dict) -> None:
        if axis not in self.rows:
            return
        cells = self.rows[axis]
        status = result.get('status', 'normal')
        status_color = {
            'normal': '#4ECDC4',
            'warning': '#FFA500',
            'anomaly': '#FF6B6B'
        }.get(status, '#CCCCCC')
        cells['status'].setText(status.upper())
        cells['status'].setStyleSheet(f"color: {status_color}; font-weight: bold;")

        metrics = result.get('metrics', {})
        rms_val = metrics.get('rms', result.get('current_value', 0.0))
        cells['rms'].setText(f"{rms_val:.3f}")
        cells['warn'].setText(f"{thresholds.get('warning', 0):.3f}")
        cells['crit'].setText(f"{thresholds.get('critical', 0):.3f}")

        kurt = metrics.get('kurtosis', 0.0)
        cells['kurt'].setText(f"{kurt:.3f}")
        cells['k_warn'].setText(f"{thresholds.get('kurtosis_warning', 0):.3f}")
        cells['k_crit'].setText(f"{thresholds.get('kurtosis_critical', 0):.3f}")

        hf = metrics.get('hf_energy', 0.0)
        cells['hf'].setText(f"{hf:.3f}")
        cells['hf_warn'].setText(f"{thresholds.get('hf_warning', 0):.3f}")
        cells['hf_crit'].setText(f"{thresholds.get('hf_critical', 0):.3f}")


class FeatureTrendChart(QWidget):
    """특징 지표 트렌드 (RMS, Kurtosis, HF 에너지)"""

    def __init__(self, parent=None, max_points: int = 300):
        super().__init__(parent)
        self.max_points = max_points
        self.times = deque(maxlen=max_points)
        self.series_rms = QLineSeries(name="Velocity RMS")
        self.series_kurt = QLineSeries(name="Accel Kurtosis")
        self.series_hf = QLineSeries(name="HF Energy")
        self.warn_rms = QLineSeries(name="Warn RMS")
        self.crit_rms = QLineSeries(name="Crit RMS")
        self.warn_kurt = QLineSeries(name="Warn Kurt")
        self.crit_kurt = QLineSeries(name="Crit Kurt")
        self.warn_hf = QLineSeries(name="Warn HF")
        self.crit_hf = QLineSeries(name="Crit HF")

        # 색상 설정
        self.series_rms.setColor(QColor("#4ECDC4"))
        self.series_kurt.setColor(QColor("#FFD166"))
        self.series_hf.setColor(QColor("#9B7BF8"))
        for s, color in [
            (self.warn_rms, "#FFA500"), (self.crit_rms, "#FF6B6B"),
            (self.warn_kurt, "#FFA500"), (self.crit_kurt, "#FF6B6B"),
            (self.warn_hf, "#FFA500"), (self.crit_hf, "#FF6B6B")
        ]:
            pen = QPen(QColor(color))
            pen.setWidth(1)
            s.setPen(pen)

        self.chart = QChart()
        for s in [self.series_rms, self.series_kurt, self.series_hf,
                  self.warn_rms, self.crit_rms, self.warn_kurt, self.crit_kurt,
                  self.warn_hf, self.crit_hf]:
            self.chart.addSeries(s)

        self.x_axis = QDateTimeAxis()
        self.x_axis.setFormat("hh:mm:ss")
        self.x_axis.setTitleText("Time")
        self.y_axis = QValueAxis()
        self.y_axis.setTitleText("Value")
        self.y_axis.setRange(0, 1)

        self.chart.addAxis(self.x_axis, Qt.AlignBottom)
        self.chart.addAxis(self.y_axis, Qt.AlignLeft)
        for s in self.chart.series():
            s.attachAxis(self.x_axis)
            s.attachAxis(self.y_axis)

        self.chart.setBackgroundBrush(QColor("#2B2B2B"))
        self.chart.setTitle("Feature Trends")
        self.chart_view = QChartView(self.chart)

        layout = QVBoxLayout()
        layout.addWidget(self.chart_view)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def update_points(self, timestamp: float, rms: float, kurt: float, hf: float,
                      thresholds: Optional[Dict] = None) -> None:
        ts_ms = int(timestamp * 1000)
        self.series_rms.append(ts_ms, rms)
        self.series_kurt.append(ts_ms, kurt)
        self.series_hf.append(ts_ms, hf)
        self.times.append(ts_ms)

        # Trim series to max_points
        if self.series_rms.count() > self.max_points:
            for s in [self.series_rms, self.series_kurt, self.series_hf,
                      self.warn_rms, self.crit_rms, self.warn_kurt, self.crit_kurt,
                      self.warn_hf, self.crit_hf]:
                s.removePoints(0, s.count() - self.max_points)

        # Threshold lines
        def _set_line(series: QLineSeries, value: float):
            series.clear()
            if not self.times:
                return
            series.append(self.times[0], value)
            series.append(self.times[-1], value)

        if thresholds:
            _set_line(self.warn_rms, thresholds.get('rms_warning', 0))
            _set_line(self.crit_rms, thresholds.get('rms_critical', 0))
            _set_line(self.warn_kurt, thresholds.get('kurtosis_warning', 0))
            _set_line(self.crit_kurt, thresholds.get('kurtosis_critical', 0))
            _set_line(self.warn_hf, thresholds.get('hf_warning', 0))
            _set_line(self.crit_hf, thresholds.get('hf_critical', 0))

        # Axes range auto-fit
        if self.times:
            start_time = QDateTime.fromMSecsSinceEpoch(self.times[0])
            end_time = QDateTime.fromMSecsSinceEpoch(self.times[-1])
            self.x_axis.setRange(start_time, end_time)

        all_vals = [p.y() for s in [self.series_rms, self.series_kurt, self.series_hf] for p in s.pointsVector()]
        all_vals += [p.y() for s in [self.warn_rms, self.crit_rms, self.warn_kurt, self.crit_kurt, self.warn_hf, self.crit_hf] for p in s.pointsVector()]
        if all_vals:
            v_min = min(all_vals)
            v_max = max(all_vals)
            margin = (v_max - v_min) * 0.2 if v_max > v_min else 1.0
            self.y_axis.setRange(v_min - margin, v_max + margin)


class FFTViewerWidget(QWidget):
    """FFT 스펙트럼 뷰어"""

    def __init__(self, parent=None, max_freq: float = 8000.0):
        super().__init__(parent)
        self.max_freq = max_freq
        self.series = QLineSeries(name="Spectrum")
        self.series.setColor(QColor("#4ECDC4"))
        self.chart = QChart()
        self.chart.addSeries(self.series)
        self.x_axis = QValueAxis()
        self.x_axis.setTitleText("Frequency (Hz)")
        self.y_axis = QValueAxis()
        self.y_axis.setTitleText("Amplitude")
        self.chart.addAxis(self.x_axis, Qt.AlignBottom)
        self.chart.addAxis(self.y_axis, Qt.AlignLeft)
        self.series.attachAxis(self.x_axis)
        self.series.attachAxis(self.y_axis)
        self.chart.setBackgroundBrush(QColor("#2B2B2B"))
        self.chart.setTitle("FFT Spectrum (Accel X)")
        self.chart_view = QChartView(self.chart)
        layout = QVBoxLayout()
        layout.addWidget(self.chart_view)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def update_spectrum(self, values: List[float], sample_rate: float) -> None:
        self.series.clear()
        if not values or sample_rate <= 0:
            return
        arr = np.array(values)
        n = len(arr)
        if n < 8:
            return
        fft = np.fft.rfft(arr - np.mean(arr))
        freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
        mask = freqs <= self.max_freq
        freqs = freqs[mask]
        mags = np.abs(fft[mask])
        for f, m in zip(freqs, mags):
            self.series.append(float(f), float(m))
        if len(freqs) > 1:
            self.x_axis.setRange(0, min(self.max_freq, float(freqs[-1])))
        if len(mags) > 0:
            self.y_axis.setRange(0, float(max(mags)) * 1.2)


class BarLevelWidget(QWidget):
    """3축 RMS 레벨 표시"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.series = QBarSeries()
        self.bar_set = QBarSet("RMS")
        self.series.append(self.bar_set)

        self.chart = QChart()
        self.chart.addSeries(self.series)
        self.x_axis = QValueAxis()
        self.x_axis.setRange(0, 3)
        self.x_axis.setTickCount(3)
        self.x_axis.setLabelFormat("%.0f")
        self.y_axis = QValueAxis()
        self.y_axis.setTitleText("RMS")
        self.chart.addAxis(self.x_axis, Qt.AlignBottom)
        self.chart.addAxis(self.y_axis, Qt.AlignLeft)
        self.series.attachAxis(self.x_axis)
        self.series.attachAxis(self.y_axis)
        self.chart.setTitle("3-Axis RMS")
        self.chart.setBackgroundBrush(QColor("#2B2B2B"))
        self.chart.legend().hide()
        self.chart_view = QChartView(self.chart)

        layout = QVBoxLayout()
        layout.addWidget(self.chart_view)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def update_levels(self, rms_vals: Tuple[float, float, float], warn: float, crit: float) -> None:
        vx, vy, vz = rms_vals
        self.bar_set.remove(0, self.bar_set.count())
        for v in [vx, vy, vz]:
            self.bar_set.append(float(v))
        max_val = max(vx, vy, vz, warn, crit, 1e-6)
        self.y_axis.setRange(0, max_val * 1.2)
        # 색상은 최대 레벨에 따라 결정
        level = 'normal'
        if max(vx, vy, vz) > crit:
            level = 'anomaly'
        elif max(vx, vy, vz) > warn:
            level = 'warning'
        color = {'normal': '#4ECDC4', 'warning': '#FFA500', 'anomaly': '#FF6B6B'}[level]
        self.bar_set.setColor(QColor(color))


class WaveformWidget(QWidget):
    """가속도 파형 표시"""

    def __init__(self, parent=None, max_points: int = 512):
        super().__init__(parent)
        self.max_points = max_points
        self.series = QLineSeries(name="Accel X")
        self.series.setColor(QColor("#9BC5FF"))
        self.chart = QChart()
        self.chart.addSeries(self.series)
        self.x_axis = QValueAxis()
        self.x_axis.setTitleText("Samples")
        self.y_axis = QValueAxis()
        self.y_axis.setTitleText("g")
        self.chart.addAxis(self.x_axis, Qt.AlignBottom)
        self.chart.addAxis(self.y_axis, Qt.AlignLeft)
        self.series.attachAxis(self.x_axis)
        self.series.attachAxis(self.y_axis)
        self.chart.setTitle("Acceleration Waveform (X)")
        self.chart.setBackgroundBrush(QColor("#2B2B2B"))
        self.chart_view = QChartView(self.chart)
        layout = QVBoxLayout()
        layout.addWidget(self.chart_view)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def update_waveform(self, values: List[float]) -> None:
        self.series.clear()
        if not values:
            return
        if len(values) > self.max_points:
            values = values[-self.max_points:]
        for idx, val in enumerate(values):
            self.series.append(idx, float(val))
        if values:
            vmin, vmax = min(values), max(values)
            margin = (vmax - vmin) * 0.2 if vmax > vmin else 0.5
            self.x_axis.setRange(0, len(values))
            self.y_axis.setRange(vmin - margin, vmax + margin)


class DashboardPanel(QWidget):
    """이상 진동 감지 대시보드"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status_label = QLabel("상태: 미연결")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #CCCCCC;")

        self.info_label = QLabel("모터 ID: -, 최종 측정: -, 가동 시간: -")
        self.info_label.setStyleSheet("color: #AAAAAA;")

        self.trend_chart = FeatureTrendChart()
        self.fft_viewer = FFTViewerWidget()
        self.bar_levels = BarLevelWidget()
        self.waveform = WaveformWidget()

        # 베이스라인 계산
        self.baseline_label = QLabel("Baseline: not computed")
        self.baseline_label.setStyleSheet("color: #CCCCCC;")
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(5, 120)
        self.duration_spin.setValue(15)
        self.duration_spin.setSuffix(" s")
        self.compute_baseline_button = QPushButton("베이스라인 계산 (최근 구간)")
        self.compute_baseline_button.setStyleSheet("background-color: #4ECDC4; color: #000; font-weight: bold;")

        # 임계값 설정
        self.rms_warn = QDoubleSpinBox()
        self.rms_warn.setRange(0, 1e6)
        self.rms_warn.setDecimals(4)
        self.rms_crit = QDoubleSpinBox()
        self.rms_crit.setRange(0, 1e6)
        self.rms_crit.setDecimals(4)
        self.kurt_warn = QDoubleSpinBox(); self.kurt_warn.setRange(0, 1e6)
        self.kurt_crit = QDoubleSpinBox(); self.kurt_crit.setRange(0, 1e6)
        self.hf_warn = QDoubleSpinBox(); self.hf_warn.setRange(0, 1e12)
        self.hf_crit = QDoubleSpinBox(); self.hf_crit.setRange(0, 1e12)
        for box in [self.rms_warn, self.rms_crit, self.kurt_warn, self.kurt_crit, self.hf_warn, self.hf_crit]:
            box.setSingleStep(0.1)
        self.apply_thr_button = QPushButton("임계값 적용")

        thr_layout = QGridLayout()
        thr_layout.addWidget(QLabel("RMS 경고"), 0, 0); thr_layout.addWidget(self.rms_warn, 0, 1)
        thr_layout.addWidget(QLabel("RMS 위험"), 0, 2); thr_layout.addWidget(self.rms_crit, 0, 3)
        thr_layout.addWidget(QLabel("Kurt 경고"), 1, 0); thr_layout.addWidget(self.kurt_warn, 1, 1)
        thr_layout.addWidget(QLabel("Kurt 위험"), 1, 2); thr_layout.addWidget(self.kurt_crit, 1, 3)
        thr_layout.addWidget(QLabel("HF 경고"), 2, 0); thr_layout.addWidget(self.hf_warn, 2, 1)
        thr_layout.addWidget(QLabel("HF 위험"), 2, 2); thr_layout.addWidget(self.hf_crit, 2, 3)
        thr_layout.addWidget(self.apply_thr_button, 3, 0, 1, 4)
        thr_frame = QGroupBox("임계값 설정")
        thr_frame.setLayout(thr_layout)

        # 베이스라인 설정
        baseline_layout = QHBoxLayout()
        baseline_layout.addWidget(QLabel("윈도우"))
        baseline_layout.addWidget(self.duration_spin)
        baseline_layout.addWidget(self.compute_baseline_button)
        baseline_layout.addStretch()
        baseline_layout.addWidget(self.baseline_label)
        baseline_frame = QGroupBox("베이스라인")
        baseline_frame.setLayout(baseline_layout)

        # 이벤트 로그 테이블
        self.event_table = QTableWidget(0, 4)
        self.event_table.setHorizontalHeaderLabels(["시간", "지표", "값", "수준"])
        self.event_table.horizontalHeader().setStretchLastSection(True)
        self.export_events_button = QPushButton("이벤트 로그 Export")
        self.export_raw_button = QPushButton("원시 데이터 Export")

        # 레이아웃 구성
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.status_label)
        top_layout.addWidget(self.info_label)
        top_layout.addStretch()

        row1 = QHBoxLayout()
        row1.addWidget(self.trend_chart, 3)
        row1.addWidget(self.bar_levels, 1)

        row2 = QHBoxLayout()
        row2.addWidget(self.fft_viewer, 2)
        row2.addWidget(self.waveform, 2)

        log_layout = QVBoxLayout()
        log_layout.addWidget(self.event_table)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.export_events_button)
        btn_layout.addWidget(self.export_raw_button)
        btn_layout.addStretch()
        log_layout.addLayout(btn_layout)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(baseline_frame, 1)
        bottom_layout.addWidget(thr_frame, 1)
        bottom_layout.addLayout(log_layout, 2)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addLayout(row1)
        main_layout.addLayout(row2)
        main_layout.addLayout(bottom_layout)
        self.setLayout(main_layout)

    def set_status(self, level: str) -> None:
        color = {'normal': '#4ECDC4', 'warning': '#FFA500', 'anomaly': '#FF6B6B', 'disconnected': '#CCCCCC'}.get(level, '#CCCCCC')
        text = {'normal': '정상', 'warning': '경고', 'anomaly': '위험', 'disconnected': '미연결'}.get(level, level)
        self.status_label.setText(f"상태: {text}")
        self.status_label.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {color};")

    def set_info(self, motor_id: str, last_ts: str, uptime: str) -> None:
        self.info_label.setText(f"모터 ID: {motor_id}, 최종 측정: {last_ts}, 가동 시간: {uptime}")

    def set_baseline_info(self, text: str) -> None:
        self.baseline_label.setText(text)

    def add_event(self, timestamp: str, metric: str, value: float, level: str) -> None:
        row = self.event_table.rowCount()
        self.event_table.insertRow(row)
        for col, val in enumerate([timestamp, metric, f"{value:.4f}", level]):
            item = QTableWidgetItem(str(val))
            self.event_table.setItem(row, col, item)
        self.event_table.scrollToBottom()

    def set_threshold_inputs(self, rms_warn: float, rms_crit: float, kurt_warn: float,
                              kurt_crit: float, hf_warn: float, hf_crit: float) -> None:
        self.rms_warn.setValue(rms_warn)
        self.rms_crit.setValue(rms_crit)
        self.kurt_warn.setValue(kurt_warn)
        self.kurt_crit.setValue(kurt_crit)
        self.hf_warn.setValue(hf_warn)
        self.hf_crit.setValue(hf_crit)


class VisualizationWindow(QMainWindow):
    """메인 윈도우 (탭 방식)"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("WTVB01-485 Vibration Sensor Monitoring")
        self.setGeometry(100, 100, 1600, 900)

        # 센서 및 수집기
        self.sensor: Optional[WTVBSensor] = None
        self.collector: Optional[DataCollector] = None
        self.analyzer: Optional[MultiAxisAnalyzer] = None
        self.baseline_calculator: Optional[BaselineCalculator] = None
        self.anomaly_detector: Optional[AnomalyDetector] = None
        self.last_event_state = {'ax': 'normal', 'ay': 'normal', 'az': 'normal'}

        # 메인 레이아웃
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        # 통신 패널
        self.comm_panel = CommunicationPanel()
        main_layout.addWidget(self.comm_panel)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 탭 위젯
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # 차트 위젯
        self.chart_widgets: Dict[str, TriAxisChart] = {}

        # 대시보드 탭
        self.dashboard_panel = DashboardPanel()
        self.tab_widget.addTab(self.dashboard_panel, "Dashboard")

        # 차트 구성 (ID, 탭 제목, Y축 라벨)
        self.charts_config = [
            ("Velocity", "Velocity", "Vibration Velocity (mm/s)", None),
            ("Displacement", "Displacement", "Vibration Displacement (μm)", None),
            ("Frequency", "Frequency", "Vibration Frequency (Hz)", None),
            ("Acceleration", "Acceleration", "Acceleration (g)", None),
            ("Temperature", "Temperature", "Temperature (°C)", (0, 120)),
        ]

        # 탭 생성
        for chart_id, tab_title, y_label, y_range in self.charts_config:
            self._create_tab_chart(chart_id, tab_title, y_label, y_range)
        
        # 센서 정보 탭 추가
        self.sensor_info_panel = SensorInfoPanel()
        self.tab_widget.addTab(self.sensor_info_panel, "Sensor Info")

        # 이상 감지 탭 추가
        self.anomaly_panel = AnomalyPanel()
        self.tab_widget.addTab(self.anomaly_panel, "Anomaly")

        # 상태바
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")

        # 타이머
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._on_update_timer)
        self.update_timer.start(100)  # 100ms마다 업데이트

        # 신호 연결
        self.comm_panel.connect_button.clicked.connect(self._on_connect_clicked)
        self.comm_panel.disconnect_button.clicked.connect(self._on_disconnect_clicked)
        self.comm_panel.refresh_button.clicked.connect(self._on_refresh_ports_clicked)
        self.dashboard_panel.compute_baseline_button.clicked.connect(self._on_compute_baseline_clicked)
        self.dashboard_panel.apply_thr_button.clicked.connect(self._on_apply_thresholds_clicked)
        self.dashboard_panel.export_events_button.clicked.connect(self._on_export_events_clicked)
        self.dashboard_panel.export_raw_button.clicked.connect(self._on_export_raw_clicked)

        # 다크 테마
        self._apply_dark_theme()

    def _create_tab_chart(self, chart_id: str, tab_title: str, y_label: str, y_range: Optional[tuple]) -> None:
        """탭 차트 생성"""
        chart = TriAxisChart(tab_title, y_label, max_points=200, y_range=y_range)
        self.chart_widgets[chart_id] = chart
        self.tab_widget.addTab(chart, tab_title)
    
    def _apply_dark_theme(self) -> None:
        """다크 테마 적용"""
        app = QApplication.instance()
        app.setStyle('Fusion')
        
        palette = app.palette()
        palette.setColor(palette.Window, QColor(53, 53, 53))
        palette.setColor(palette.WindowText, QColor(255, 255, 255))
        palette.setColor(palette.Base, QColor(25, 25, 25))
        palette.setColor(palette.AlternateBase, QColor(53, 53, 53))
        palette.setColor(palette.ToolTipBase, QColor(255, 255, 255))
        palette.setColor(palette.ToolTipText, QColor(255, 255, 255))
        palette.setColor(palette.Text, QColor(255, 255, 255))
        palette.setColor(palette.Button, QColor(53, 53, 53))
        palette.setColor(palette.ButtonText, QColor(255, 255, 255))
        palette.setColor(palette.BrightText, QColor(255, 0, 0))
        palette.setColor(palette.Link, QColor(42, 130, 218))
        palette.setColor(palette.Highlight, QColor(42, 130, 218))
        palette.setColor(palette.HighlightedText, QColor(0, 0, 0))
        app.setPalette(palette)

    @staticmethod
    def _estimate_sample_rate(data_list: List) -> float:
        if not data_list or len(data_list) < 2:
            return 0.0
        t0 = data_list[0].timestamp
        t1 = data_list[-1].timestamp
        if t1 <= t0:
            return 0.0
        return (len(data_list) - 1) / (t1 - t0)

    @staticmethod
    def _compute_rms(values: List[float]) -> float:
        if not values:
            return 0.0
        arr = np.array(values)
        return float(np.sqrt(np.mean(arr ** 2)))

    @staticmethod
    def _compute_kurtosis(values: List[float]) -> float:
        if not values:
            return 0.0
        arr = np.array(values)
        mean = np.mean(arr)
        variance = np.var(arr)
        if variance == 0:
            return 0.0
        return float(np.mean((arr - mean) ** 4) / (variance ** 2))

    @staticmethod
    def _high_freq_energy(values: List[float], sample_rate: float, fmin: float = 2000.0) -> float:
        if not values or sample_rate <= 0 or sample_rate < 2 * fmin:
            return 0.0
        arr = np.array(values)
        n = len(arr)
        if n < 8:
            return 0.0
        fft = np.fft.rfft(arr - np.mean(arr))
        freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
        mask = freqs >= fmin
        if not np.any(mask):
            return 0.0
        energy = np.sum(np.abs(fft[mask]) ** 2) / n
        return float(energy)

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        if seconds <= 0:
            return "-"
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    
    def _on_connect_clicked(self) -> None:
        """연결 버튼 클릭"""
        port = self.comm_panel.port_combo.currentText()
        baudrate = int(self.comm_panel.baud_combo.currentText())
        slave_id = self.comm_panel.slave_id_spin.value()
        
        if not port:
            self.statusBar.showMessage("Please select a COM port")
            return
        
        try:
            self.sensor = WTVBSensor(port=port, baudrate=baudrate, slave_id=slave_id)
            
            if not self.sensor.connect():
                self.statusBar.showMessage(f"Failed to connect to {port}")
                return
            
            self.collector = DataCollector(self.sensor, buffer_size=1000, collection_interval=0.05)
            self.analyzer = MultiAxisAnalyzer(self.collector.buffer)
            
            self.collector.on_data_received = self._on_data_received
            self.collector.on_error = self._on_error
            self.collector.on_connection_lost = self._on_connection_lost
            
            if self.collector.start():
                self.comm_panel.set_connected(True, port, baudrate)
                self.statusBar.showMessage(f"Connected to {port} at {baudrate} bps")
            else:
                self.statusBar.showMessage("Failed to start data collection")
        
        except Exception as e:
            self.statusBar.showMessage(f"Connection error: {str(e)}")
    
    def _on_disconnect_clicked(self) -> None:
        """연결 해제 버튼 클릭"""
        if self.collector:
            self.collector.stop()
        
        if self.sensor:
            self.sensor.disconnect()
        
        self.comm_panel.set_connected(False)
        self.statusBar.showMessage("Disconnected")
        
        # 그래프 초기화
        for chart in self.chart_widgets.values():
            chart.clear()

        # 이상 감지 상태 초기화
        self.baseline_calculator = None
        self.anomaly_detector = None
        self.anomaly_panel.reset()
        self.dashboard_panel.set_status('disconnected')
        self.dashboard_panel.set_baseline_info("Baseline: not computed")
    
    def _on_refresh_ports_clicked(self) -> None:
        """포트 새로고침"""
        current_port = self.comm_panel.port_combo.currentText()
        self.comm_panel.port_combo.clear()
        self.comm_panel.port_combo.addItems(get_available_ports())
        
        index = self.comm_panel.port_combo.findText(current_port)
        if index >= 0:
            self.comm_panel.port_combo.setCurrentIndex(index)
    
    def _on_data_received(self, data) -> None:
        """데이터 수신 콜백"""
        pass

    def _on_compute_baseline_clicked(self) -> None:
        """최근 창 데이터로 베이스라인 계산"""
        if not self.collector or not self.collector.is_running:
            self.statusBar.showMessage("Connect sensor before computing baseline")
            return

        duration = self.dashboard_panel.duration_spin.value()
        data_list = self.collector.get_data_by_time_range(duration)
        if len(data_list) < 30:
            self.statusBar.showMessage(f"Not enough data for baseline (need >=30, have {len(data_list)})")
            return

        buffer = DataBuffer(max_size=len(data_list) + 10)
        for item in data_list:
            buffer.add(item)

        calc = BaselineCalculator()
        if not calc.calculate_baseline(buffer):
            self.statusBar.showMessage("Baseline calculation failed")
            return

        calc.save_baseline()
        self.baseline_calculator = calc
        self.anomaly_detector = AnomalyDetector(self.baseline_calculator)
        self.anomaly_detector.calculate_thresholds()
        self.dashboard_panel.set_baseline_info(f"Baseline: {len(data_list)} samples")
        thr_ax = self.anomaly_detector.thresholds.get('ax', {})
        self.dashboard_panel.set_threshold_inputs(
            thr_ax.get('warning', 0.0),
            thr_ax.get('critical', 0.0),
            thr_ax.get('kurtosis_warning', 0.0),
            thr_ax.get('kurtosis_critical', 0.0),
            thr_ax.get('hf_warning', 0.0),
            thr_ax.get('hf_critical', 0.0),
        )
        self.statusBar.showMessage("Baseline computed and thresholds ready")
    
    def _on_error(self, error_msg: str) -> None:
        """에러 콜백"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {error_msg}")
    
    def _on_connection_lost(self) -> None:
        """연결 끊김 콜백"""
        self._on_disconnect_clicked()
        self.statusBar.showMessage("Connection lost")

    def _on_apply_thresholds_clicked(self) -> None:
        if not self.anomaly_detector or not self.anomaly_detector.thresholds:
            self.statusBar.showMessage("Baseline/thresholds not ready")
            return
        rms_w = self.dashboard_panel.rms_warn.value()
        rms_c = self.dashboard_panel.rms_crit.value()
        k_w = self.dashboard_panel.kurt_warn.value()
        k_c = self.dashboard_panel.kurt_crit.value()
        hf_w = self.dashboard_panel.hf_warn.value()
        hf_c = self.dashboard_panel.hf_crit.value()
        for axis in ['ax', 'ay', 'az']:
            thr = self.anomaly_detector.thresholds.get(axis, {})
            thr['warning'] = rms_w
            thr['critical'] = rms_c
            thr['kurtosis_warning'] = k_w
            thr['kurtosis_critical'] = k_c
            thr['hf_warning'] = hf_w
            thr['hf_critical'] = hf_c
            thr['method'] = 'rms_factor'
            self.anomaly_detector.thresholds[axis] = thr
        self.statusBar.showMessage("Custom thresholds applied")

    def _on_export_events_clicked(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Events", "events.csv", "CSV Files (*.csv)")
        if not path:
            return
        table = self.dashboard_panel.event_table
        headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for row in range(table.rowCount()):
                writer.writerow([
                    table.item(row, col).text() if table.item(row, col) else ""
                    for col in range(table.columnCount())
                ])
        self.statusBar.showMessage(f"Events exported to {path}")

    def _on_export_raw_clicked(self) -> None:
        if not self.collector:
            self.statusBar.showMessage("No data to export")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Raw Data", "raw_data.csv", "CSV Files (*.csv)")
        if not path:
            return
        data_dicts = self.collector.buffer.to_dict_list()
        if not data_dicts:
            self.statusBar.showMessage("Buffer empty; nothing exported")
            return
        keys = list(data_dicts[0].keys())
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data_dicts)
        self.statusBar.showMessage(f"Raw data exported to {path}")
    
    def _on_update_timer(self) -> None:
        """주기적 업데이트 (타이머)"""
        if not self.collector or not self.sensor or not self.sensor.is_connected:
            return
        
        latest_data = self.collector.get_latest_data()
        if latest_data:
            self.comm_panel.update_receive_status(True)
            
            # 각 그래프 업데이트
            ts = getattr(latest_data, "timestamp", time.time())
            self.chart_widgets["Velocity"].update_data(latest_data.vx, latest_data.vy, latest_data.vz, ts)
            self.chart_widgets["Displacement"].update_data(latest_data.dx, latest_data.dy, latest_data.dz, ts)
            self.chart_widgets["Frequency"].update_data(latest_data.hx, latest_data.hy, latest_data.hz, ts)
            self.chart_widgets["Acceleration"].update_data(latest_data.ax, latest_data.ay, latest_data.az, ts)
            self.chart_widgets["Temperature"].update_data(latest_data.temp, latest_data.temp, latest_data.temp, ts)
            
            # 센서 정보 패널 업데이트 (가속도 진폭 계산)
            ax_amp, ay_amp, az_amp = self.collector.get_acceleration_amplitudes()
            self.sensor_info_panel.update_info(latest_data, ax_amp, ay_amp, az_amp)

            # 특징 계산용 윈도우 데이터
            window_data = self.collector.get_data_by_time_range(5.0)
            sample_rate = self._estimate_sample_rate(window_data)
            vx_vals = [d.vx for d in window_data]
            vy_vals = [d.vy for d in window_data]
            vz_vals = [d.vz for d in window_data]
            ax_vals = [d.ax for d in window_data]

            rms_vx = self._compute_rms(vx_vals)
            rms_vy = self._compute_rms(vy_vals)
            rms_vz = self._compute_rms(vz_vals)
            rms_velocity = (rms_vx + rms_vy + rms_vz) / 3.0 if window_data else 0.0
            kurt_ax = self._compute_kurtosis(ax_vals)
            hf_energy = self._high_freq_energy(ax_vals, sample_rate)

            # 임계값 참조
            thr_vx = self.anomaly_detector.thresholds.get('vx', {}) if self.anomaly_detector else {}
            thr_ax = self.anomaly_detector.thresholds.get('ax', {}) if self.anomaly_detector else {}
            trend_thr = {
                'rms_warning': thr_vx.get('warning', 0.0),
                'rms_critical': thr_vx.get('critical', 0.0),
                'kurtosis_warning': thr_ax.get('kurtosis_warning', 0.0),
                'kurtosis_critical': thr_ax.get('kurtosis_critical', 0.0),
                'hf_warning': thr_ax.get('hf_warning', 0.0),
                'hf_critical': thr_ax.get('hf_critical', 0.0),
            }

            now_ts = time.time()
            self.dashboard_panel.trend_chart.update_points(now_ts, rms_velocity, kurt_ax, hf_energy, trend_thr)
            self.dashboard_panel.bar_levels.update_levels((rms_vx, rms_vy, rms_vz), trend_thr['rms_warning'], trend_thr['rms_critical'])
            self.dashboard_panel.waveform.update_waveform(ax_vals)
            self.dashboard_panel.fft_viewer.update_spectrum(ax_vals, sample_rate)

            # 이상 감지 업데이트
            severity = 'normal'
            if self.anomaly_detector and self.anomaly_detector.thresholds:
                window_for_anomaly = self.collector.get_all_data()
                anomaly_results = self.anomaly_detector.detect_anomaly(latest_data, window_for_anomaly)
                for axis in ['ax', 'ay', 'az']:
                    if not anomaly_results:
                        break
                    if axis in anomaly_results and axis in self.anomaly_detector.thresholds:
                        self.anomaly_panel.update_row(axis, anomaly_results[axis], self.anomaly_detector.thresholds[axis])
                        state = anomaly_results[axis]['status']
                        if state == 'anomaly':
                            severity = 'anomaly'
                        elif state == 'warning' and severity != 'anomaly':
                            severity = 'warning'
                        # 이벤트 로그 (상태 변화 시 기록)
                        if state != 'normal' and self.last_event_state.get(axis) != state:
                            ts_str = datetime.fromtimestamp(latest_data.timestamp).strftime("%Y-%m-%d %H:%M:%S")
                            metric_val = anomaly_results[axis].get('current_value', 0.0)
                            level_text = '위험' if state == 'anomaly' else '경고'
                            self.dashboard_panel.add_event(ts_str, axis.upper(), metric_val, level_text)
                        self.last_event_state[axis] = state
            else:
                self.last_event_state = {'ax': 'normal', 'ay': 'normal', 'az': 'normal'}

            self.dashboard_panel.set_status(severity if self.sensor and self.sensor.is_connected else 'disconnected')

            # 운영 정보 업데이트
            stats = self.collector.get_statistics()
            uptime_str = self._format_uptime(stats.get('elapsed_time', 0.0))
            last_ts_str = datetime.fromtimestamp(latest_data.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            motor_id = str(self.comm_panel.slave_id_spin.value())
            self.dashboard_panel.set_info(motor_id, last_ts_str, uptime_str)
    
    def closeEvent(self, event) -> None:
        """윈도우 종료 이벤트"""
        if self.collector:
            self.collector.stop()
        if self.sensor:
            self.sensor.disconnect()
        event.accept()


def main():
    """메인 함수"""
    app = QApplication(sys.argv)
    
    window = VisualizationWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
