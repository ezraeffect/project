"""
WTVB01-485 Vibration Sensor Monitoring - GUI Visualization
PyQt5 기반 탭 방식 레이아웃으로 시계열 차트를 표시
"""

import sys
import time
import csv
import serial
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from collections import deque
import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStatusBar, QComboBox, QSpinBox, QGridLayout, QGroupBox, QTabWidget, QFrame,
    QTableWidget, QTableWidgetItem, QFileDialog, QDoubleSpinBox, QMessageBox
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


class AlertIndicator(QWidget):
    """시각적 경고 표시기 (큰 원형 LED 스타일)"""
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.status = 'normal'
        self.blink_state = True
        
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        
        # 상태 원형 표시
        self.status_circle = QLabel("●")
        self.status_circle.setAlignment(Qt.AlignCenter)
        self.status_circle.setStyleSheet("font-size: 60px; color: #4ECDC4;")
        
        # 제목
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFFFFF;")
        
        # 값 표시
        self.value_label = QLabel("0.00")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #FFFFFF;")
        
        # 임계값 표시
        self.threshold_label = QLabel("Warn: - / Crit: -")
        self.threshold_label.setAlignment(Qt.AlignCenter)
        self.threshold_label.setStyleSheet("font-size: 10px; color: #AAAAAA;")
        
        layout.addWidget(self.status_circle)
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.threshold_label)
        
        self.setLayout(layout)
        
        # 깜빡임 타이머
        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self._on_blink)
        
    def set_status(self, status: str, value: float, warn_thr: float, crit_thr: float) -> None:
        """상태 업데이트"""
        self.status = status
        self.value_label.setText(f"{value:.3f}")
        self.threshold_label.setText(f"Warn: {warn_thr:.2f} / Crit: {crit_thr:.2f}")
        
        colors = {
            'normal': '#4ECDC4',
            'warning': '#FFA500', 
            'anomaly': '#FF6B6B'
        }
        color = colors.get(status, '#CCCCCC')
        
        if status == 'anomaly':
            # 위험 상태: 깜빡임 시작
            if not self.blink_timer.isActive():
                self.blink_timer.start(300)
        elif status == 'warning':
            # 경고 상태: 느린 깜빡임
            self.blink_timer.stop()
            self.status_circle.setStyleSheet(f"font-size: 60px; color: {color};")
        else:
            # 정상 상태
            self.blink_timer.stop()
            self.status_circle.setStyleSheet(f"font-size: 60px; color: {color};")
    
    def _on_blink(self) -> None:
        """깜빡임 효과"""
        self.blink_state = not self.blink_state
        if self.blink_state:
            self.status_circle.setStyleSheet("font-size: 60px; color: #FF6B6B;")
        else:
            self.status_circle.setStyleSheet("font-size: 60px; color: #440000;")


class RMSTrendChart(QWidget):
    """RMS 트렌드 차트 (임계선 포함)"""
    
    def __init__(self, title: str, parent=None, max_points: int = 200):
        super().__init__(parent)
        self.max_points = max_points
        self.times = deque(maxlen=max_points)
        
        # 데이터 시리즈
        self.series_x = QLineSeries()
        self.series_y = QLineSeries()
        self.series_z = QLineSeries()
        self.series_x.setName("X")
        self.series_y.setName("Y")
        self.series_z.setName("Z")
        self.series_x.setColor(QColor("#FF6B6B"))
        self.series_y.setColor(QColor("#4ECDC4"))
        self.series_z.setColor(QColor("#FFE66D"))
        
        # 임계선
        self.warn_line = QLineSeries()
        self.crit_line = QLineSeries()
        warn_pen = QPen(QColor("#FFA500"))
        warn_pen.setWidth(2)
        warn_pen.setStyle(Qt.DashLine)
        crit_pen = QPen(QColor("#FF0000"))
        crit_pen.setWidth(2)
        crit_pen.setStyle(Qt.DashLine)
        self.warn_line.setPen(warn_pen)
        self.crit_line.setPen(crit_pen)
        
        # 차트 설정
        self.chart = QChart()
        self.chart.addSeries(self.series_x)
        self.chart.addSeries(self.series_y)
        self.chart.addSeries(self.series_z)
        self.chart.addSeries(self.warn_line)
        self.chart.addSeries(self.crit_line)
        
        self.x_axis = QDateTimeAxis()
        self.x_axis.setFormat("hh:mm:ss")
        self.x_axis.setTitleText("Time")
        self.y_axis = QValueAxis()
        self.y_axis.setTitleText("RMS")
        
        self.chart.addAxis(self.x_axis, Qt.AlignBottom)
        self.chart.addAxis(self.y_axis, Qt.AlignLeft)
        
        for s in [self.series_x, self.series_y, self.series_z, self.warn_line, self.crit_line]:
            s.attachAxis(self.x_axis)
            s.attachAxis(self.y_axis)
        
        self.chart.setBackgroundBrush(QColor("#2B2B2B"))
        self.chart.setTitle(title)
        self.chart.setTitleBrush(QColor("#FFFFFF"))
        
        self.chart_view = QChartView(self.chart)
        layout = QVBoxLayout()
        layout.addWidget(self.chart_view)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        
        self.warn_threshold = 0
        self.crit_threshold = 0
        
    def update_data(self, timestamp: float, rms_x: float, rms_y: float, rms_z: float,
                    warn_thr: float = 0, crit_thr: float = 0) -> None:
        """데이터 업데이트"""
        ts_ms = int(timestamp * 1000)
        self.times.append(ts_ms)
        self.warn_threshold = warn_thr
        self.crit_threshold = crit_thr
        
        self.series_x.append(ts_ms, rms_x)
        self.series_y.append(ts_ms, rms_y)
        self.series_z.append(ts_ms, rms_z)
        
        # 포인트 수 제한
        for s in [self.series_x, self.series_y, self.series_z]:
            if s.count() > self.max_points:
                s.removePoints(0, s.count() - self.max_points)
        
        # 임계선 업데이트
        if len(self.times) >= 2:
            self.warn_line.clear()
            self.crit_line.clear()
            self.warn_line.append(self.times[0], warn_thr)
            self.warn_line.append(self.times[-1], warn_thr)
            self.crit_line.append(self.times[0], crit_thr)
            self.crit_line.append(self.times[-1], crit_thr)
        
        # 축 범위 조정
        if self.times:
            start_time = QDateTime.fromMSecsSinceEpoch(self.times[0])
            end_time = QDateTime.fromMSecsSinceEpoch(self.times[-1])
            self.x_axis.setRange(start_time, end_time)
            
            all_vals = [rms_x, rms_y, rms_z, warn_thr, crit_thr]
            if self.series_x.count() > 0:
                all_vals.extend([p.y() for p in self.series_x.pointsVector()])
            max_val = max(all_vals) if all_vals else 1.0
            min_val = min(0, min(all_vals)) if all_vals else 0
            margin = (max_val - min_val) * 0.1 if max_val > min_val else 1.0
            self.y_axis.setRange(min_val, max_val + margin)
    
    def clear(self) -> None:
        self.series_x.clear()
        self.series_y.clear()
        self.series_z.clear()
        self.warn_line.clear()
        self.crit_line.clear()
        self.times.clear()


class AxisStatusWidget(QWidget):
    """단일 축 상태 표시 위젯"""
    
    def __init__(self, axis_name: str, parent=None):
        super().__init__(parent)
        self.axis_name = axis_name
        
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 축 이름
        name_label = QLabel(f"{axis_name.upper()}")
        name_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #FFFFFF; min-width: 30px;")
        
        # 상태 표시
        self.status_label = QLabel("●")
        self.status_label.setStyleSheet("font-size: 20px; color: #4ECDC4;")
        
        # RMS 값
        self.rms_label = QLabel("RMS: 0.000")
        self.rms_label.setStyleSheet("color: #FFFFFF; min-width: 100px;")
        
        # Peak 값
        self.peak_label = QLabel("Peak: 0.000")
        self.peak_label.setStyleSheet("color: #FFFFFF; min-width: 100px;")
        
        # Crest Factor
        self.crest_label = QLabel("CF: 0.000")
        self.crest_label.setStyleSheet("color: #FFFFFF; min-width: 80px;")
        
        # 상태 텍스트
        self.status_text = QLabel("정상")
        self.status_text.setStyleSheet("font-weight: bold; color: #4ECDC4; min-width: 50px;")
        
        layout.addWidget(name_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.rms_label)
        layout.addWidget(self.peak_label)
        layout.addWidget(self.crest_label)
        layout.addWidget(self.status_text)
        layout.addStretch()
        
        self.setLayout(layout)
        
    def update_status(self, status: str, rms: float, peak: float, crest: float) -> None:
        """상태 업데이트"""
        colors = {
            'normal': '#4ECDC4',
            'warning': '#FFA500',
            'anomaly': '#FF6B6B'
        }
        texts = {
            'normal': '정상',
            'warning': '경고',
            'anomaly': '위험'
        }
        
        color = colors.get(status, '#CCCCCC')
        text = texts.get(status, status)
        
        self.status_label.setStyleSheet(f"font-size: 20px; color: {color};")
        self.status_text.setText(text)
        self.status_text.setStyleSheet(f"font-weight: bold; color: {color}; min-width: 50px;")
        
        self.rms_label.setText(f"RMS: {rms:.3f}")
        self.peak_label.setText(f"Peak: {peak:.3f}")
        self.crest_label.setText(f"CF: {crest:.2f}")


class ArduinoControlPanel(QWidget):
    """아두이노 제어 및 합성 Velocity 표시 패널"""
    
    # 상태 코드 정의
    STATUS_DISCONNECTED = 0  # 미연결
    STATUS_NORMAL = 1        # 정상
    STATUS_WARNING = 2       # 경고
    STATUS_ANOMALY = 3       # 위험
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 아두이노 시리얼 연결
        self.arduino_serial: Optional[serial.Serial] = None
        self.is_arduino_connected = False
        
        # 전송 타이머
        self.send_timer = QTimer()
        self.send_timer.timeout.connect(self._on_send_timer)
        self.send_count = 0
        
        # 현재 데이터 저장 (전송용)
        self.current_velocity = 0.0
        self.current_status = self.STATUS_DISCONNECTED
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        
        # ===== 합성 Velocity 표시 영역 =====
        velocity_frame = QFrame()
        velocity_frame.setFrameShape(QFrame.Box)
        velocity_frame.setStyleSheet("background-color: #1E1E1E; border: 2px solid #4ECDC4; border-radius: 12px;")
        velocity_layout = QVBoxLayout(velocity_frame)
        velocity_layout.setContentsMargins(20, 20, 20, 20)
        
        # 제목
        title_label = QLabel("합성 Velocity (V_total)")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #4ECDC4; border: none;")
        velocity_layout.addWidget(title_label)
        
        # 계산식 표시
        formula_label = QLabel("V_total = √(Vx² + Vy² + Vz²)")
        formula_label.setAlignment(Qt.AlignCenter)
        formula_label.setStyleSheet("font-size: 12px; color: #AAAAAA; border: none;")
        velocity_layout.addWidget(formula_label)
        
        # 합성 Velocity 값 (큰 글씨)
        self.total_velocity_label = QLabel("0.000")
        self.total_velocity_label.setAlignment(Qt.AlignCenter)
        self.total_velocity_label.setStyleSheet("font-size: 72px; font-weight: bold; color: #4ECDC4; border: none;")
        velocity_layout.addWidget(self.total_velocity_label)
        
        # 단위
        unit_label = QLabel("mm/s")
        unit_label.setAlignment(Qt.AlignCenter)
        unit_label.setStyleSheet("font-size: 24px; color: #FFFFFF; border: none;")
        velocity_layout.addWidget(unit_label)
        
        main_layout.addWidget(velocity_frame)
        
        # ===== 개별 축 값 표시 =====
        axis_frame = QGroupBox("개별 축 Velocity")
        axis_layout = QHBoxLayout(axis_frame)
        
        # X축
        vx_layout = QVBoxLayout()
        vx_title = QLabel("Vx")
        vx_title.setAlignment(Qt.AlignCenter)
        vx_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #FF6B6B;")
        self.vx_label = QLabel("0.000")
        self.vx_label.setAlignment(Qt.AlignCenter)
        self.vx_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #FF6B6B;")
        vx_unit = QLabel("mm/s")
        vx_unit.setAlignment(Qt.AlignCenter)
        vx_unit.setStyleSheet("font-size: 12px; color: #AAAAAA;")
        vx_layout.addWidget(vx_title)
        vx_layout.addWidget(self.vx_label)
        vx_layout.addWidget(vx_unit)
        
        # Y축
        vy_layout = QVBoxLayout()
        vy_title = QLabel("Vy")
        vy_title.setAlignment(Qt.AlignCenter)
        vy_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #4ECDC4;")
        self.vy_label = QLabel("0.000")
        self.vy_label.setAlignment(Qt.AlignCenter)
        self.vy_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #4ECDC4;")
        vy_unit = QLabel("mm/s")
        vy_unit.setAlignment(Qt.AlignCenter)
        vy_unit.setStyleSheet("font-size: 12px; color: #AAAAAA;")
        vy_layout.addWidget(vy_title)
        vy_layout.addWidget(self.vy_label)
        vy_layout.addWidget(vy_unit)
        
        # Z축
        vz_layout = QVBoxLayout()
        vz_title = QLabel("Vz")
        vz_title.setAlignment(Qt.AlignCenter)
        vz_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFE66D;")
        self.vz_label = QLabel("0.000")
        self.vz_label.setAlignment(Qt.AlignCenter)
        self.vz_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #FFE66D;")
        vz_unit = QLabel("mm/s")
        vz_unit.setAlignment(Qt.AlignCenter)
        vz_unit.setStyleSheet("font-size: 12px; color: #AAAAAA;")
        vz_layout.addWidget(vz_title)
        vz_layout.addWidget(self.vz_label)
        vz_layout.addWidget(vz_unit)
        
        axis_layout.addLayout(vx_layout)
        axis_layout.addLayout(vy_layout)
        axis_layout.addLayout(vz_layout)
        
        main_layout.addWidget(axis_frame)
        
        # ===== 아두이노 연결 설정 =====
        arduino_frame = QGroupBox("아두이노 연결")
        arduino_layout = QVBoxLayout(arduino_frame)
        
        # 포트 선택
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("COM Port:"))
        self.arduino_port_combo = QComboBox()
        self.arduino_port_combo.addItems(get_available_ports())
        self.arduino_port_combo.setMinimumWidth(100)
        port_layout.addWidget(self.arduino_port_combo)
        
        port_layout.addWidget(QLabel("Baud:"))
        self.arduino_baud_combo = QComboBox()
        self.arduino_baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.arduino_baud_combo.setCurrentText("9600")
        port_layout.addWidget(self.arduino_baud_combo)
        
        self.arduino_refresh_btn = QPushButton("🔄")
        self.arduino_refresh_btn.setMaximumWidth(40)
        self.arduino_refresh_btn.setToolTip("포트 새로고침")
        self.arduino_refresh_btn.clicked.connect(self._refresh_arduino_ports)
        port_layout.addWidget(self.arduino_refresh_btn)
        
        self.arduino_connect_btn = QPushButton("연결")
        self.arduino_connect_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.arduino_connect_btn.clicked.connect(self._on_arduino_connect_clicked)
        port_layout.addWidget(self.arduino_connect_btn)
        
        self.arduino_disconnect_btn = QPushButton("해제")
        self.arduino_disconnect_btn.setStyleSheet("background-color: #F44336; color: white; font-weight: bold;")
        self.arduino_disconnect_btn.setEnabled(False)
        self.arduino_disconnect_btn.clicked.connect(self._on_arduino_disconnect_clicked)
        port_layout.addWidget(self.arduino_disconnect_btn)
        
        arduino_layout.addLayout(port_layout)
        
        # 전송 설정
        send_layout = QHBoxLayout()
        send_layout.addWidget(QLabel("전송 주기:"))
        self.send_interval_spin = QSpinBox()
        self.send_interval_spin.setRange(100, 5000)
        self.send_interval_spin.setValue(1000)
        self.send_interval_spin.setSuffix(" ms")
        send_layout.addWidget(self.send_interval_spin)
        
        self.start_send_btn = QPushButton("▶ 전송 시작")
        self.start_send_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.start_send_btn.setEnabled(False)
        self.start_send_btn.clicked.connect(self._on_start_send_clicked)
        send_layout.addWidget(self.start_send_btn)
        
        self.stop_send_btn = QPushButton("⏹ 전송 중지")
        self.stop_send_btn.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        self.stop_send_btn.setEnabled(False)
        self.stop_send_btn.clicked.connect(self._on_stop_send_clicked)
        send_layout.addWidget(self.stop_send_btn)
        
        arduino_layout.addLayout(send_layout)
        
        # 상태 표시
        status_layout = QHBoxLayout()
        self.arduino_status_indicator = QLabel("●")
        self.arduino_status_indicator.setStyleSheet("font-size: 16px; color: #FF6B6B;")
        status_layout.addWidget(self.arduino_status_indicator)
        
        self.arduino_status_label = QLabel("미연결")
        self.arduino_status_label.setStyleSheet("color: #AAAAAA; font-weight: bold;")
        status_layout.addWidget(self.arduino_status_label)
        
        status_layout.addStretch()
        
        status_layout.addWidget(QLabel("전송 횟수:"))
        self.send_count_label = QLabel("0")
        self.send_count_label.setStyleSheet("color: #4ECDC4; font-weight: bold;")
        status_layout.addWidget(self.send_count_label)
        
        arduino_layout.addLayout(status_layout)
        
        # 로그 표시
        log_layout = QVBoxLayout()
        log_layout.addWidget(QLabel("전송 로그:"))
        self.log_text = QTableWidget(0, 2)
        self.log_text.setHorizontalHeaderLabels(["시간", "데이터"])
        self.log_text.horizontalHeader().setStretchLastSection(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)
        
        arduino_layout.addLayout(log_layout)
        
        main_layout.addWidget(arduino_frame)
        main_layout.addStretch()
        
        self.setLayout(main_layout)
    
    def _refresh_arduino_ports(self) -> None:
        """아두이노 포트 새로고침"""
        current = self.arduino_port_combo.currentText()
        self.arduino_port_combo.clear()
        self.arduino_port_combo.addItems(get_available_ports())
        idx = self.arduino_port_combo.findText(current)
        if idx >= 0:
            self.arduino_port_combo.setCurrentIndex(idx)
    
    def _on_arduino_connect_clicked(self) -> None:
        """아두이노 연결"""
        port = self.arduino_port_combo.currentText()
        baudrate = int(self.arduino_baud_combo.currentText())
        
        if not port:
            QMessageBox.warning(self, "연결 오류", "COM 포트를 선택하세요.")
            return
        
        try:
            self.arduino_serial = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=1.0
            )
            self.is_arduino_connected = True
            
            # UI 업데이트
            self.arduino_connect_btn.setEnabled(False)
            self.arduino_disconnect_btn.setEnabled(True)
            self.start_send_btn.setEnabled(True)
            self.arduino_port_combo.setEnabled(False)
            self.arduino_baud_combo.setEnabled(False)
            
            self.arduino_status_indicator.setStyleSheet("font-size: 16px; color: #4ECDC4;")
            self.arduino_status_label.setText(f"연결됨 ({port} @ {baudrate}bps)")
            self.arduino_status_label.setStyleSheet("color: #4ECDC4; font-weight: bold;")
            
            self._add_log("시스템", f"아두이노 연결됨: {port}")
            
        except serial.SerialException as e:
            QMessageBox.critical(self, "연결 실패", f"아두이노 연결에 실패했습니다.\n\n오류: {str(e)}")
    
    def _on_arduino_disconnect_clicked(self) -> None:
        """아두이노 연결 해제"""
        # 전송 중지
        if self.send_timer.isActive():
            self.send_timer.stop()
        
        # 시리얼 닫기
        if self.arduino_serial and self.arduino_serial.is_open:
            self.arduino_serial.close()
        
        self.arduino_serial = None
        self.is_arduino_connected = False
        
        # UI 업데이트
        self.arduino_connect_btn.setEnabled(True)
        self.arduino_disconnect_btn.setEnabled(False)
        self.start_send_btn.setEnabled(False)
        self.stop_send_btn.setEnabled(False)
        self.arduino_port_combo.setEnabled(True)
        self.arduino_baud_combo.setEnabled(True)
        
        self.arduino_status_indicator.setStyleSheet("font-size: 16px; color: #FF6B6B;")
        self.arduino_status_label.setText("미연결")
        self.arduino_status_label.setStyleSheet("color: #AAAAAA; font-weight: bold;")
        
        self._add_log("시스템", "아두이노 연결 해제됨")
    
    def _on_start_send_clicked(self) -> None:
        """전송 시작"""
        interval = self.send_interval_spin.value()
        self.send_timer.start(interval)
        self.send_count = 0
        self.send_count_label.setText("0")
        
        self.start_send_btn.setEnabled(False)
        self.stop_send_btn.setEnabled(True)
        self.send_interval_spin.setEnabled(False)
        
        self._add_log("시스템", f"전송 시작 (주기: {interval}ms)")
    
    def _on_stop_send_clicked(self) -> None:
        """전송 중지"""
        self.send_timer.stop()
        
        self.start_send_btn.setEnabled(True)
        self.stop_send_btn.setEnabled(False)
        self.send_interval_spin.setEnabled(True)
        
        self._add_log("시스템", f"전송 중지 (총 {self.send_count}회 전송)")
    
    def _on_send_timer(self) -> None:
        """타이머에 의한 주기적 전송 - 프로토콜: <V:값,S:상태>\n"""
        if not self.is_arduino_connected or not self.arduino_serial:
            return
        
        try:
            # 프로토콜 포맷: <V:0.000,S:0>\n
            message = f"<V:{self.current_velocity:.3f},S:{self.current_status}>\n"
            self.arduino_serial.write(message.encode('utf-8'))
            
            self.send_count += 1
            self.send_count_label.setText(str(self.send_count))
            
            # 상태 텍스트 변환
            status_text = {
                0: '미연결',
                1: '정상',
                2: '경고',
                3: '위험'
            }.get(self.current_status, '알수없음')
            
            self._add_log("TX", f"V={self.current_velocity:.3f}, S={self.current_status}({status_text})")
            
        except serial.SerialException as e:
            self._add_log("오류", f"전송 실패: {str(e)}")
            self._on_stop_send_clicked()
    
    def _add_log(self, prefix: str, message: str) -> None:
        """로그 추가"""
        row = self.log_text.rowCount()
        self.log_text.insertRow(row)
        
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        time_item = QTableWidgetItem(timestamp)
        time_item.setForeground(QColor("#AAAAAA"))
        
        # 메시지 색상 설정
        msg_item = QTableWidgetItem(f"[{prefix}] {message}")
        if prefix == "TX":
            msg_item.setForeground(QColor("#4ECDC4"))
        elif prefix == "오류":
            msg_item.setForeground(QColor("#FF6B6B"))
        elif prefix == "시스템":
            msg_item.setForeground(QColor("#FFE66D"))
        
        self.log_text.setItem(row, 0, time_item)
        self.log_text.setItem(row, 1, msg_item)
        self.log_text.scrollToBottom()
        
        # 최대 50개 유지
        while self.log_text.rowCount() > 50:
            self.log_text.removeRow(0)
    
    def send_data(self, data: str) -> bool:
        """데이터 전송 (외부에서 호출 가능)"""
        if not self.is_arduino_connected or not self.arduino_serial:
            return False
        
        try:
            self.arduino_serial.write(data.encode('utf-8'))
            self._add_log("TX", data.strip())
            return True
        except serial.SerialException:
            return False
    
    def close_connection(self) -> None:
        """연결 종료 (윈도우 닫힐 때 호출)"""
        if self.send_timer.isActive():
            self.send_timer.stop()
        if self.arduino_serial and self.arduino_serial.is_open:
            self.arduino_serial.close()
    
    def update_velocity(self, vx: float, vy: float, vz: float) -> None:
        """개별 축 및 합성 Velocity 값 업데이트"""
        # 개별 축 값 표시
        self.vx_label.setText(f"{vx:.3f}")
        self.vy_label.setText(f"{vy:.3f}")
        self.vz_label.setText(f"{vz:.3f}")
        
        # 합성 Velocity 계산: V_total = sqrt(Vx² + Vy² + Vz²)
        v_total = np.sqrt(vx**2 + vy**2 + vz**2)
        self.total_velocity_label.setText(f"{v_total:.3f}")
        
        # 전송용 값 저장
        self.current_velocity = v_total
        
        return v_total
    
    def update_status(self, status: str) -> None:
        """대시보드 상태 업데이트 (전송용)
        
        Args:
            status: 'disconnected', 'normal', 'warning', 'anomaly' 중 하나
        """
        status_map = {
            'disconnected': self.STATUS_DISCONNECTED,
            'normal': self.STATUS_NORMAL,
            'warning': self.STATUS_WARNING,
            'anomaly': self.STATUS_ANOMALY
        }
        self.current_status = status_map.get(status, self.STATUS_DISCONNECTED)
    
    def get_total_velocity(self, vx: float, vy: float, vz: float) -> float:
        """합성 Velocity 계산만 수행"""
        return np.sqrt(vx**2 + vy**2 + vz**2)


class DashboardPanel(QWidget):
    """새로운 이상 진동 감지 대시보드 (FFT 없이 시간 도메인 기반)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        
        # ===== 상단: 전체 상태 표시 =====
        top_frame = QFrame()
        top_frame.setFrameShape(QFrame.Box)
        top_frame.setStyleSheet("background-color: #1E1E1E; border: 2px solid #3C3C3C; border-radius: 8px;")
        top_frame.setMaximumHeight(100)
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(10, 5, 10, 5)
        
        # 전체 상태 LED
        self.main_status_circle = QLabel("●")
        self.main_status_circle.setAlignment(Qt.AlignCenter)
        self.main_status_circle.setStyleSheet("font-size: 50px; color: #CCCCCC;")
        
        # 상태 텍스트
        status_text_layout = QVBoxLayout()
        status_text_layout.setSpacing(2)
        self.main_status_text = QLabel("미연결")
        self.main_status_text.setStyleSheet("font-size: 22px; font-weight: bold; color: #CCCCCC;")
        self.main_status_desc = QLabel("센서 연결 대기 중...")
        self.main_status_desc.setStyleSheet("font-size: 11px; color: #AAAAAA;")
        status_text_layout.addWidget(self.main_status_text)
        status_text_layout.addWidget(self.main_status_desc)
        
        # 운영 정보
        info_layout = QVBoxLayout()
        self.motor_id_label = QLabel("모터 ID: -")
        self.last_update_label = QLabel("최종 측정: -")
        self.uptime_label = QLabel("가동 시간: -")
        self.sample_count_label = QLabel("샘플 수: 0")
        for lbl in [self.motor_id_label, self.last_update_label, self.uptime_label, self.sample_count_label]:
            lbl.setStyleSheet("color: #AAAAAA; font-size: 12px;")
            info_layout.addWidget(lbl)
        
        top_layout.addWidget(self.main_status_circle)
        top_layout.addLayout(status_text_layout)
        top_layout.addStretch()
        top_layout.addLayout(info_layout)
        
        # ===== 3축 지표 표시기 =====
        indicators_frame = QFrame()
        indicators_frame.setStyleSheet("background-color: #252525; border-radius: 8px;")
        indicators_frame.setMaximumHeight(120)
        indicators_layout = QHBoxLayout(indicators_frame)
        indicators_layout.setContentsMargins(5, 5, 5, 5)
        
        self.alert_vx = AlertIndicator("Velocity X (mm/s)")
        self.alert_vy = AlertIndicator("Velocity Y (mm/s)")
        self.alert_vz = AlertIndicator("Velocity Z (mm/s)")
        
        indicators_layout.addWidget(self.alert_vx)
        indicators_layout.addWidget(self.alert_vy)
        indicators_layout.addWidget(self.alert_vz)
        
        # ===== 각 축 상세 상태 =====
        status_frame = QGroupBox("축별 상세 상태")
        status_frame.setMaximumHeight(110)
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(5, 5, 5, 5)
        status_layout.setSpacing(2)
        
        self.axis_vx = AxisStatusWidget("vx")
        self.axis_vy = AxisStatusWidget("vy")
        self.axis_vz = AxisStatusWidget("vz")
        
        status_layout.addWidget(self.axis_vx)
        status_layout.addWidget(self.axis_vy)
        status_layout.addWidget(self.axis_vz)
        
        # ===== RMS 트렌드 차트 =====
        self.rms_trend = RMSTrendChart("Velocity RMS Trend")
        self.rms_trend.setMinimumHeight(180)
        
        # ===== 하단: 설정 및 이벤트 로그 =====
        bottom_layout = QHBoxLayout()
        
        # 베이스라인 설정
        baseline_frame = QGroupBox("베이스라인 설정")
        baseline_layout = QVBoxLayout(baseline_frame)
        
        dur_layout = QHBoxLayout()
        dur_layout.addWidget(QLabel("수집 시간:"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(5, 120)
        self.duration_spin.setValue(15)
        self.duration_spin.setSuffix(" 초")
        dur_layout.addWidget(self.duration_spin)
        
        self.compute_baseline_button = QPushButton("🔄 베이스라인 계산")
        self.compute_baseline_button.setStyleSheet(
            "background-color: #4ECDC4; color: #000; font-weight: bold; padding: 8px; border-radius: 4px;"
        )
        
        self.baseline_label = QLabel("상태: 미계산")
        self.baseline_label.setStyleSheet("color: #FFA500;")
        
        baseline_layout.addLayout(dur_layout)
        baseline_layout.addWidget(self.compute_baseline_button)
        baseline_layout.addWidget(self.baseline_label)
        
        # 임계값 설정
        threshold_frame = QGroupBox("임계값 설정 (배수)")
        threshold_layout = QGridLayout(threshold_frame)
        
        threshold_layout.addWidget(QLabel("경고 배수:"), 0, 0)
        self.warn_factor_spin = QDoubleSpinBox()
        self.warn_factor_spin.setRange(1.0, 5.0)
        self.warn_factor_spin.setValue(1.3)
        self.warn_factor_spin.setSingleStep(0.1)
        threshold_layout.addWidget(self.warn_factor_spin, 0, 1)
        
        threshold_layout.addWidget(QLabel("위험 배수:"), 1, 0)
        self.crit_factor_spin = QDoubleSpinBox()
        self.crit_factor_spin.setRange(1.0, 10.0)
        self.crit_factor_spin.setValue(1.6)
        self.crit_factor_spin.setSingleStep(0.1)
        threshold_layout.addWidget(self.crit_factor_spin, 1, 1)
        
        self.apply_thr_button = QPushButton("✓ 임계값 적용")
        self.apply_thr_button.setStyleSheet(
            "background-color: #5C6BC0; color: #FFF; font-weight: bold; padding: 6px; border-radius: 4px;"
        )
        threshold_layout.addWidget(self.apply_thr_button, 2, 0, 1, 2)
        
        # 현재 임계값 표시
        self.current_warn_label = QLabel("경고 임계값: -")
        self.current_crit_label = QLabel("위험 임계값: -")
        self.current_warn_label.setStyleSheet("color: #FFA500; font-size: 10px;")
        self.current_crit_label.setStyleSheet("color: #FF6B6B; font-size: 10px;")
        threshold_layout.addWidget(self.current_warn_label, 3, 0, 1, 2)
        threshold_layout.addWidget(self.current_crit_label, 4, 0, 1, 2)
        
        # 이벤트 로그
        log_frame = QGroupBox("이벤트 로그")
        log_layout = QVBoxLayout(log_frame)
        
        self.event_table = QTableWidget(0, 5)
        self.event_table.setHorizontalHeaderLabels(["시간", "축", "지표", "값", "상태"])
        self.event_table.horizontalHeader().setStretchLastSection(True)
        self.event_table.setMaximumHeight(100)
        
        btn_layout = QHBoxLayout()
        self.export_events_button = QPushButton("📥 이벤트 Export")
        self.export_raw_button = QPushButton("📥 원시데이터 Export")
        self.clear_events_button = QPushButton("🗑 로그 초기화")
        btn_layout.addWidget(self.export_events_button)
        btn_layout.addWidget(self.export_raw_button)
        btn_layout.addWidget(self.clear_events_button)
        
        log_layout.addWidget(self.event_table)
        log_layout.addLayout(btn_layout)
        
        bottom_layout.addWidget(baseline_frame)
        bottom_layout.addWidget(threshold_frame)
        bottom_layout.addWidget(log_frame, 2)
        
        # ===== 메인 레이아웃 조합 =====
        main_layout.addWidget(top_frame)
        main_layout.addWidget(indicators_frame)
        main_layout.addWidget(status_frame)
        main_layout.addWidget(self.rms_trend, 3)
        main_layout.addLayout(bottom_layout)
        
        self.setLayout(main_layout)
        
        # 깜빡임 타이머 (전체 상태)
        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self._on_main_blink)
        self.blink_state = True
        self.current_severity = 'disconnected'

    def _on_main_blink(self) -> None:
        """메인 상태 깜빡임"""
        self.blink_state = not self.blink_state
        if self.current_severity == 'anomaly':
            if self.blink_state:
                self.main_status_circle.setStyleSheet("font-size: 50px; color: #FF6B6B;")
            else:
                self.main_status_circle.setStyleSheet("font-size: 50px; color: #440000;")
    
    def set_status(self, level: str) -> None:
        """전체 상태 설정"""
        self.current_severity = level
        colors = {
            'normal': '#4ECDC4',
            'warning': '#FFA500',
            'anomaly': '#FF6B6B',
            'disconnected': '#CCCCCC'
        }
        texts = {
            'normal': '정상',
            'warning': '경고',
            'anomaly': '⚠️ 위험',
            'disconnected': '미연결'
        }
        descs = {
            'normal': '모든 진동 지표가 정상 범위 내에 있습니다.',
            'warning': '일부 지표가 경고 수준입니다. 모니터링을 강화하세요.',
            'anomaly': '이상 진동이 감지되었습니다! 즉시 점검이 필요합니다.',
            'disconnected': '센서 연결 대기 중...'
        }
        
        color = colors.get(level, '#CCCCCC')
        self.main_status_text.setText(texts.get(level, level))
        self.main_status_text.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {color};")
        self.main_status_desc.setText(descs.get(level, ''))
        
        if level == 'anomaly':
            if not self.blink_timer.isActive():
                self.blink_timer.start(300)
        else:
            self.blink_timer.stop()
            self.main_status_circle.setStyleSheet(f"font-size: 50px; color: {color};")
    
    def set_info(self, motor_id: str, last_ts: str, uptime: str) -> None:
        """운영 정보 설정"""
        self.motor_id_label.setText(f"모터 ID: {motor_id}")
        self.last_update_label.setText(f"최종 측정: {last_ts}")
        self.uptime_label.setText(f"가동 시간: {uptime}")
    
    def set_sample_count(self, count: int) -> None:
        """샘플 수 표시"""
        self.sample_count_label.setText(f"샘플 수: {count}")
    
    def set_baseline_info(self, text: str, success: bool = True) -> None:
        """베이스라인 상태 표시"""
        color = "#4ECDC4" if success else "#FFA500"
        self.baseline_label.setText(f"상태: {text}")
        self.baseline_label.setStyleSheet(f"color: {color};")
    
    def set_threshold_display(self, warn: float, crit: float) -> None:
        """현재 임계값 표시"""
        self.current_warn_label.setText(f"경고 임계값: {warn:.3f}")
        self.current_crit_label.setText(f"위험 임계값: {crit:.3f}")
    
    def update_axis_indicators(self, vx_data: dict, vy_data: dict, vz_data: dict) -> None:
        """3축 지표 업데이트"""
        for alert, data in [(self.alert_vx, vx_data), (self.alert_vy, vy_data), (self.alert_vz, vz_data)]:
            alert.set_status(
                data.get('status', 'normal'),
                data.get('rms', 0),
                data.get('warn', 0),
                data.get('crit', 0)
            )
        
        for axis_widget, data in [(self.axis_vx, vx_data), (self.axis_vy, vy_data), (self.axis_vz, vz_data)]:
            axis_widget.update_status(
                data.get('status', 'normal'),
                data.get('rms', 0),
                data.get('peak', 0),
                data.get('crest', 0)
            )
    
    def add_event(self, timestamp: str, axis: str, metric: str, value: float, level: str) -> None:
        """이벤트 로그 추가"""
        row = self.event_table.rowCount()
        self.event_table.insertRow(row)
        
        level_colors = {'정상': '#4ECDC4', '경고': '#FFA500', '위험': '#FF6B6B'}
        
        for col, val in enumerate([timestamp, axis, metric, f"{value:.4f}", level]):
            item = QTableWidgetItem(str(val))
            if col == 4:  # 상태 컬럼
                item.setForeground(QColor(level_colors.get(level, '#FFFFFF')))
            self.event_table.setItem(row, col, item)
        
        self.event_table.scrollToBottom()
        
        # 최대 100개 유지
        while self.event_table.rowCount() > 100:
            self.event_table.removeRow(0)
    
    def clear_events(self) -> None:
        """이벤트 로그 초기화"""
        self.event_table.setRowCount(0)
    
    def clear_trend(self) -> None:
        """트렌드 차트 초기화"""
        self.rms_trend.clear()


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
        self.last_event_state = {'vx': 'normal', 'vy': 'normal', 'vz': 'normal'}  # Velocity 축 기반 이벤트 추적

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

        # 아두이노 제어 탭 추가
        self.arduino_panel = ArduinoControlPanel()
        self.tab_widget.addTab(self.arduino_panel, "Arduino Control")

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
        self.dashboard_panel.clear_events_button.clicked.connect(self._on_clear_events_clicked)

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
    def _compute_rms(values: List[float]) -> float:
        """RMS (Root Mean Square) 계산"""
        if not values:
            return 0.0
        arr = np.array(values)
        return float(np.sqrt(np.mean(arr ** 2)))

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
                QMessageBox.critical(
                    self, 
                    "연결 실패", 
                    f"COM 포트 연결에 실패했습니다.\n\n"
                    f"포트: {port}\n"
                    f"가능한 원인:\n"
                    f"• 포트가 다른 프로그램에서 사용 중\n"
                    f"• 센서가 연결되지 않음\n"
                    f"• 잘못된 포트 선택"
                )
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
                QMessageBox.warning(
                    self,
                    "데이터 수집 실패",
                    "데이터 수집을 시작할 수 없습니다.\n\n"
                    "센서 연결 상태를 확인하세요."
                )
        
        except Exception as e:
            self.statusBar.showMessage(f"Connection error: {str(e)}")
            QMessageBox.critical(
                self,
                "연결 오류",
                f"센서 연결 중 오류가 발생했습니다.\n\n오류: {str(e)}"
            )
    
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
        self.dashboard_panel.set_baseline_info("미계산", success=False)
        self.dashboard_panel.clear_trend()
        self.last_event_state = {'vx': 'normal', 'vy': 'normal', 'vz': 'normal'}
    
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
        """최근 창 데이터로 베이스라인 계산 (Velocity 기반)"""
        if not self.collector or not self.collector.is_running:
            self.statusBar.showMessage("센서 연결 후 베이스라인을 계산하세요")
            QMessageBox.warning(
                self,
                "베이스라인 계산 불가",
                "센서가 연결되지 않았습니다.\n\n"
                "먼저 센서를 연결한 후 베이스라인을 계산하세요."
            )
            return

        duration = self.dashboard_panel.duration_spin.value()
        data_list = self.collector.get_data_by_time_range(duration)
        if len(data_list) < 30:
            self.statusBar.showMessage(f"데이터 부족 (필요: 30개 이상, 현재: {len(data_list)}개)")
            QMessageBox.warning(
                self,
                "데이터 부족",
                f"베이스라인 계산을 위한 데이터가 부족합니다.\n\n"
                f"필요: 30개 이상\n"
                f"현재: {len(data_list)}개\n\n"
                f"설정된 시간({duration}초) 동안 더 많은 데이터를 수집하거나,\n"
                f"수집 시간을 늘려주세요."
            )
            return

        buffer = DataBuffer(max_size=len(data_list) + 10)
        for item in data_list:
            buffer.add(item)

        calc = BaselineCalculator()
        if not calc.calculate_baseline(buffer):
            self.statusBar.showMessage("베이스라인 계산 실패")
            self.dashboard_panel.set_baseline_info("계산 실패", success=False)
            
            # 데이터 분석하여 문제 진단
            vx_vals = [d.vx for d in data_list]
            vy_vals = [d.vy for d in data_list]
            vz_vals = [d.vz for d in data_list]
            
            # 모든 값이 0인지 확인
            all_zero_x = all(v == 0 for v in vx_vals)
            all_zero_y = all(v == 0 for v in vy_vals)
            all_zero_z = all(v == 0 for v in vz_vals)
            
            problem_axes = []
            if all_zero_x:
                problem_axes.append("X축")
            if all_zero_y:
                problem_axes.append("Y축")
            if all_zero_z:
                problem_axes.append("Z축")
            
            if problem_axes:
                axes_str = ", ".join(problem_axes)
                QMessageBox.critical(
                    self,
                    "베이스라인 계산 실패",
                    f"베이스라인 계산에 실패했습니다.\n\n"
                    f"문제 감지: {axes_str}의 모든 값이 0입니다.\n\n"
                    f"가능한 원인:\n"
                    f"• 센서가 제대로 장착되지 않음\n"
                    f"• 센서 축 설정 문제\n"
                    f"• 통신 오류로 인한 데이터 손실"
                )
            else:
                QMessageBox.critical(
                    self,
                    "베이스라인 계산 실패",
                    "베이스라인 계산에 실패했습니다.\n\n"
                    "데이터의 변동이 너무 적거나,\n"
                    "유효하지 않은 데이터가 포함되어 있습니다."
                )
            return

        calc.save_baseline()
        self.baseline_calculator = calc
        
        # 경고/위험 배수 가져오기
        warn_factor = self.dashboard_panel.warn_factor_spin.value()
        crit_factor = self.dashboard_panel.crit_factor_spin.value()
        
        self.anomaly_detector = AnomalyDetector(
            self.baseline_calculator,
            warning_rms_factor=warn_factor,
            critical_rms_factor=crit_factor
        )
        self.anomaly_detector.calculate_thresholds()
        
        # Velocity 기반 임계값 표시
        thr_vx = self.anomaly_detector.thresholds.get('vx', {})
        warn_val = thr_vx.get('warning', 0.0)
        crit_val = thr_vx.get('critical', 0.0)
        
        self.dashboard_panel.set_baseline_info(f"{len(data_list)}개 샘플로 계산 완료", success=True)
        self.dashboard_panel.set_threshold_display(warn_val, crit_val)
        self.statusBar.showMessage(f"베이스라인 계산 완료 - 경고: {warn_val:.3f}, 위험: {crit_val:.3f}")
    
    def _on_error(self, error_msg: str) -> None:
        """에러 콜백 - 상태바에 표시 (터미널 출력 대신)"""
        self.statusBar.showMessage(f"오류: {error_msg}")
    
    def _on_connection_lost(self) -> None:
        """연결 끊김 콜백"""
        self._on_disconnect_clicked()
        self.statusBar.showMessage("Connection lost")
        QMessageBox.warning(
            self,
            "연결 끊김",
            "센서와의 연결이 끊어졌습니다.\n\n"
            "케이블 연결 상태를 확인하고 다시 연결하세요."
        )

    def _on_apply_thresholds_clicked(self) -> None:
        """사용자 지정 임계값 배수 적용 (Velocity 기반)"""
        if not self.baseline_calculator:
            self.statusBar.showMessage("먼저 베이스라인을 계산하세요")
            QMessageBox.warning(
                self,
                "임계값 적용 불가",
                "베이스라인이 계산되지 않았습니다.\n\n"
                "먼저 베이스라인을 계산한 후 임계값을 적용하세요."
            )
            return
        
        warn_factor = self.dashboard_panel.warn_factor_spin.value()
        crit_factor = self.dashboard_panel.crit_factor_spin.value()
        
        # 새 배수로 AnomalyDetector 재생성
        self.anomaly_detector = AnomalyDetector(
            self.baseline_calculator,
            warning_rms_factor=warn_factor,
            critical_rms_factor=crit_factor
        )
        self.anomaly_detector.calculate_thresholds()
        
        # 임계값 표시 업데이트
        thr_vx = self.anomaly_detector.thresholds.get('vx', {})
        warn_val = thr_vx.get('warning', 0.0)
        crit_val = thr_vx.get('critical', 0.0)
        
        self.dashboard_panel.set_threshold_display(warn_val, crit_val)
        self.statusBar.showMessage(f"임계값 적용 완료 - 경고: {warn_val:.3f}, 위험: {crit_val:.3f}")
    
    def _on_clear_events_clicked(self) -> None:
        """이벤트 로그 초기화"""
        self.dashboard_panel.clear_events()
        self.statusBar.showMessage("이벤트 로그가 초기화되었습니다")

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
    
    @staticmethod
    def _compute_peak(values: List[float]) -> float:
        """Peak 값 계산 (최대 절대값)"""
        if not values:
            return 0.0
        return float(max(abs(v) for v in values))
    
    @staticmethod
    def _compute_crest_factor(rms: float, peak: float) -> float:
        """Crest Factor 계산 (Peak / RMS)"""
        if rms <= 0:
            return 0.0
        return peak / rms
    
    def _on_update_timer(self) -> None:
        """주기적 업데이트 (타이머) - Velocity 기반 이상 감지"""
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

            # 아두이노 패널 업데이트 - 합성 Velocity 계산
            self.arduino_panel.update_velocity(latest_data.vx, latest_data.vy, latest_data.vz)

            # 윈도우 데이터 (최근 5초)
            window_data = self.collector.get_data_by_time_range(5.0)
            vx_vals = [d.vx for d in window_data]
            vy_vals = [d.vy for d in window_data]
            vz_vals = [d.vz for d in window_data]

            # RMS, Peak, Crest Factor 계산 (FFT 없이 시간 도메인만)
            rms_vx = self._compute_rms(vx_vals)
            rms_vy = self._compute_rms(vy_vals)
            rms_vz = self._compute_rms(vz_vals)
            
            peak_vx = self._compute_peak(vx_vals)
            peak_vy = self._compute_peak(vy_vals)
            peak_vz = self._compute_peak(vz_vals)
            
            crest_vx = self._compute_crest_factor(rms_vx, peak_vx)
            crest_vy = self._compute_crest_factor(rms_vy, peak_vy)
            crest_vz = self._compute_crest_factor(rms_vz, peak_vz)

            # 임계값 가져오기
            thr_vx = self.anomaly_detector.thresholds.get('vx', {}) if self.anomaly_detector else {}
            thr_vy = self.anomaly_detector.thresholds.get('vy', {}) if self.anomaly_detector else {}
            thr_vz = self.anomaly_detector.thresholds.get('vz', {}) if self.anomaly_detector else {}
            
            warn_vx = thr_vx.get('warning', 0.0)
            crit_vx = thr_vx.get('critical', 0.0)
            warn_vy = thr_vy.get('warning', 0.0)
            crit_vy = thr_vy.get('critical', 0.0)
            warn_vz = thr_vz.get('warning', 0.0)
            crit_vz = thr_vz.get('critical', 0.0)

            # 각 축 상태 판정 (RMS 기반)
            def get_status(rms: float, warn: float, crit: float) -> str:
                if crit > 0 and rms > crit:
                    return 'anomaly'
                elif warn > 0 and rms > warn:
                    return 'warning'
                return 'normal'
            
            status_vx = get_status(rms_vx, warn_vx, crit_vx)
            status_vy = get_status(rms_vy, warn_vy, crit_vy)
            status_vz = get_status(rms_vz, warn_vz, crit_vz)

            # 대시보드 업데이트 - 3축 지표
            vx_data = {'status': status_vx, 'rms': rms_vx, 'peak': peak_vx, 'crest': crest_vx, 'warn': warn_vx, 'crit': crit_vx}
            vy_data = {'status': status_vy, 'rms': rms_vy, 'peak': peak_vy, 'crest': crest_vy, 'warn': warn_vy, 'crit': crit_vy}
            vz_data = {'status': status_vz, 'rms': rms_vz, 'peak': peak_vz, 'crest': crest_vz, 'warn': warn_vz, 'crit': crit_vz}
            
            self.dashboard_panel.update_axis_indicators(vx_data, vy_data, vz_data)
            
            # RMS 트렌드 차트 업데이트
            self.dashboard_panel.rms_trend.update_data(ts, rms_vx, rms_vy, rms_vz, warn_vx, crit_vx)
            
            # 전체 상태 결정
            severity = 'normal'
            if status_vx == 'anomaly' or status_vy == 'anomaly' or status_vz == 'anomaly':
                severity = 'anomaly'
            elif status_vx == 'warning' or status_vy == 'warning' or status_vz == 'warning':
                severity = 'warning'
            
            # 아두이노 패널에 상태 업데이트 (전송용)
            self.arduino_panel.update_status(severity)
            
            # 이벤트 로그 (상태 변화 시 기록)
            for axis, status, rms_val in [('vx', status_vx, rms_vx), ('vy', status_vy, rms_vy), ('vz', status_vz, rms_vz)]:
                if status != 'normal' and self.last_event_state.get(axis) != status:
                    ts_str = datetime.fromtimestamp(latest_data.timestamp).strftime("%Y-%m-%d %H:%M:%S")
                    level_text = '위험' if status == 'anomaly' else '경고'
                    self.dashboard_panel.add_event(ts_str, axis.upper(), "RMS", rms_val, level_text)
                self.last_event_state[axis] = status
            
            # Anomaly 패널 업데이트 (기존 호환성)
            if self.anomaly_detector and self.anomaly_detector.thresholds:
                window_for_anomaly = self.collector.get_all_data()
                anomaly_results = self.anomaly_detector.detect_anomaly(latest_data, window_for_anomaly)
                for axis in ['ax', 'ay', 'az']:
                    if axis in anomaly_results and axis in self.anomaly_detector.thresholds:
                        self.anomaly_panel.update_row(axis, anomaly_results[axis], self.anomaly_detector.thresholds[axis])
            
            self.dashboard_panel.set_status(severity if self.sensor and self.sensor.is_connected else 'disconnected')

            # 운영 정보 업데이트
            stats = self.collector.get_statistics()
            uptime_str = self._format_uptime(stats.get('elapsed_time', 0.0))
            last_ts_str = datetime.fromtimestamp(latest_data.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            motor_id = str(self.comm_panel.slave_id_spin.value())
            self.dashboard_panel.set_info(motor_id, last_ts_str, uptime_str)
            self.dashboard_panel.set_sample_count(self.collector.buffer.size())
    
    def closeEvent(self, event) -> None:
        """윈도우 종료 이벤트"""
        # 아두이노 연결 종료
        if hasattr(self, 'arduino_panel'):
            self.arduino_panel.close_connection()
        
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
