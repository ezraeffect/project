"""
PyQt5 기반 실시간 데이터 시각화 GUI
센서 데이터를 실시간 그래프로 표시
"""

import sys
import time
from typing import Optional, List
from datetime import datetime
from collections import deque

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QStatusBar,
    QComboBox, QSpinBox, QGridLayout, QGroupBox, QFrame,
    QDoubleSpinBox, QMessageBox, QTextEdit
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread, QDateTime, QPointF
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtChart import QChart, QChartView, QLineSeries, QDateTimeAxis, QValueAxis

from data_collector import DataCollector, MultiAxisAnalyzer
from sensor_communication import WTVBSensor, get_available_ports
from anomaly_detection import BaselineCalculator, AnomalyDetector


class ChartManager:
    """차트 생성 및 관리 클래스"""
    
    @staticmethod
    def create_chart(title: str, y_label: str = "Value") -> tuple:
        """차트 생성 (타이틀/범례 숨김)"""
        chart = QChart()
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.setBackgroundBrush(QColor("#f5f5f5"))
        chart.legend().hide()  # 범례 숨김
        chart.setTitle("")     # 타이틀 미표시
        
        chart_view = QChartView(chart)
        
        return chart, chart_view
    
    @staticmethod
    def add_axis(chart: QChart, x_max: int = 100, y_max: int = 100):
        """축 추가"""
        x_axis = QValueAxis()
        x_axis.setRange(0, x_max)
        x_axis.setLabelFormat("%d")
        
        y_axis = QValueAxis()
        y_axis.setRange(0, y_max)
        
        chart.addAxis(x_axis, Qt.AlignBottom)
        chart.addAxis(y_axis, Qt.AlignLeft)
        
        return x_axis, y_axis
    
    @staticmethod
    def create_series(name: str, color: str = "#1f77b4") -> QLineSeries:
        """데이터 시리즈 생성"""
        series = QLineSeries()
        series.setName(name)
        series.setColor(QColor(color))
        series.setUseOpenGL(True)
        return series


class GraphWidget(QWidget):
    """단일 센서 데이터 그래프 위젯"""
    
    def __init__(self, title: str, y_label: str = "Value", parent=None):
        """
        그래프 위젯 초기화
        
        Args:
            title: 그래프 제목
            y_label: Y축 레이블
            parent: 부모 위젯
        """
        super().__init__(parent)
        
        self.title = title
        self.y_label = y_label
        self.max_points = 100  # 표시할 최대 포인트 수
        self.data_buffer = deque(maxlen=self.max_points)
        
        layout = QVBoxLayout()
        
        # 차트 생성
        self.chart, self.chart_view = ChartManager.create_chart(title, y_label)
        
        # 데이터 시리즈
        self.series = ChartManager.create_series(y_label)
        self.chart.addSeries(self.series)
        
        # 축
        self.x_axis, self.y_axis = ChartManager.add_axis(self.chart, 100, 100)
        self.series.attachAxis(self.x_axis)
        self.series.attachAxis(self.y_axis)
        
        layout.addWidget(self.chart_view)
        
        # 현재값 표시
        value_layout = QHBoxLayout()
        value_layout.addWidget(QLabel("Current Value:"))
        self.current_value_label = QLabel("0.00")
        self.current_value_label.setStyleSheet("font-weight: bold; color: #1f77b4; font-size: 12pt;")
        value_layout.addWidget(self.current_value_label)
        value_layout.addStretch()
        layout.addLayout(value_layout)
        
        self.setLayout(layout)
    
    def update_data(self, value: float) -> None:
        """
        새로운 데이터로 그래프 업데이트
        
        Args:
            value: 새로운 값
        """
        # 데이터 버퍼에 추가
        self.data_buffer.append(value)
        
        # 시리즈 업데이트
        self.series.clear()
        for i, v in enumerate(self.data_buffer):
            self.series.append(i, v)
        
        # 축 범위 업데이트
        self.x_axis.setRange(0, max(1, len(self.data_buffer) - 1))
        
        # Y축 범위 동적 조정
        if len(self.data_buffer) > 0:
            max_val = max(self.data_buffer) if self.data_buffer else 1
            min_val = min(self.data_buffer) if self.data_buffer else 0
            margin = (max_val - min_val) * 0.1 if max_val > min_val else 10
            self.y_axis.setRange(max(0, min_val - margin), max_val + margin)
        
        # 현재값 표시
        self.current_value_label.setText(f"{value:.2f}")
    
    def clear_data(self) -> None:
        """그래프 데이터 초기화"""
        self.data_buffer.clear()
        self.series.clear()
        self.current_value_label.setText("0.00")


class TriAxisGraphWidget(QWidget):
    """3축 센서 데이터 그래프 위젯 (3개 그래프 동시 표시)"""
    
    def __init__(self, title: str, y_label: str = "Value", parent=None):
        """
        3축 그래프 위젯 초기화
        
        Args:
            title: 위젯 제목
            y_label: Y축 레이블
            parent: 부모 위젯
        """
        super().__init__(parent)
        
        self.title = title
        self.y_label = y_label
        
        layout = QGridLayout()
        
        # 3개의 그래프 생성
        self.graph_x = GraphWidget(f"{title} - X Axis")
        self.graph_y = GraphWidget(f"{title} - Y Axis")
        self.graph_z = GraphWidget(f"{title} - Z Axis")
        
        # 그리드에 배치
        layout.addWidget(self.graph_x, 0, 0)
        layout.addWidget(self.graph_y, 0, 1)
        layout.addWidget(self.graph_z, 0, 2)
        
        self.setLayout(layout)
    
    def update_data(self, x: float, y: float, z: float) -> None:
        """3축 데이터 업데이트"""
        self.graph_x.update_data(x)
        self.graph_y.update_data(y)
        self.graph_z.update_data(z)
    
    def clear_data(self) -> None:
        """모든 그래프 초기화"""
        self.graph_x.clear_data()
        self.graph_y.clear_data()
        self.graph_z.clear_data()


class AnomalyDetectionWidget(QWidget):
    """이상 진동 감지 탭"""
    
    def __init__(self, parent=None):
        """이상 진동 감지 위젯 초기화"""
        super().__init__(parent)
        
        layout = QVBoxLayout()
        
        # Baseline 수집 섹션
        baseline_group = QGroupBox("Baseline Collection")
        baseline_layout = QVBoxLayout()
        
        # 설명
        desc_label = QLabel("Step 1: Collect baseline data from normal operation state")
        baseline_layout.addWidget(desc_label)
        
        # 수집 시간 설정
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Collection Duration (seconds):"))
        self.baseline_duration_spin = QSpinBox()
        self.baseline_duration_spin.setRange(10, 300)
        self.baseline_duration_spin.setValue(60)
        time_layout.addWidget(self.baseline_duration_spin)
        time_layout.addStretch()
        baseline_layout.addLayout(time_layout)
        
        # 수집 상태 표시
        self.baseline_status_label = QLabel("Status: Not started")
        self.baseline_status_label.setStyleSheet("color: gray;")
        baseline_layout.addWidget(self.baseline_status_label)
        
        # 수집 진행도
        self.baseline_progress_label = QLabel("0 / 60 seconds")
        baseline_layout.addWidget(self.baseline_progress_label)
        
        # 수집 데이터 카운트
        self.baseline_count_label = QLabel("Data Points: 0")
        baseline_layout.addWidget(self.baseline_count_label)
        
        # 수집 버튼
        button_layout = QHBoxLayout()
        self.start_baseline_button = QPushButton("Start Baseline Collection")
        self.start_baseline_button.clicked.connect(self._on_start_baseline)
        button_layout.addWidget(self.start_baseline_button)
        
        self.stop_baseline_button = QPushButton("Stop & Save Baseline")
        self.stop_baseline_button.setEnabled(False)
        self.stop_baseline_button.clicked.connect(self._on_stop_baseline)
        button_layout.addWidget(self.stop_baseline_button)
        
        button_layout.addStretch()
        baseline_layout.addLayout(button_layout)
        baseline_group.setLayout(baseline_layout)
        layout.addWidget(baseline_group)
        
        # 실시간 그래프 섹션
        graph_group = QGroupBox("Real-time Data Visualization")
        graph_layout = QHBoxLayout()
        
        # 3축 속도 그래프
        self.baseline_velocity_graph = TriAxisGraphWidget("Vibration Velocity (mm/s)")
        graph_layout.addWidget(self.baseline_velocity_graph)
        
        # 3축 변위 그래프
        self.baseline_displacement_graph = TriAxisGraphWidget("Vibration Displacement (um)")
        graph_layout.addWidget(self.baseline_displacement_graph)
        
        graph_group.setLayout(graph_layout)
        layout.addWidget(graph_group)
        
        # 통계 테이블 섹션
        stats_group = QGroupBox("Real-time Statistics")
        stats_layout = QVBoxLayout()
        
        from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem
        self.baseline_stats_table = QTableWidget()
        self.baseline_stats_table.setColumnCount(7)
        self.baseline_stats_table.setHorizontalHeaderLabels(
            ["Axis", "Count", "Mean", "Std", "Min", "Max", "RMS"]
        )
        self.baseline_stats_table.setMaximumHeight(200)
        self.baseline_stats_table.setColumnWidth(0, 60)
        for i in range(1, 7):
            self.baseline_stats_table.setColumnWidth(i, 80)
        
        stats_layout.addWidget(self.baseline_stats_table)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # Threshold 설정 섹션
        threshold_group = QGroupBox("Threshold Configuration")
        threshold_layout = QVBoxLayout()
        
        # 설명
        desc_label2 = QLabel("Step 2: Calculate thresholds based on baseline data")
        threshold_layout.addWidget(desc_label2)
        
        # STD Multiplier 설정
        std_layout = QHBoxLayout()
        std_layout.addWidget(QLabel("Standard Deviation Multiplier:"))
        self.std_multiplier_spin = QSpinBox()
        self.std_multiplier_spin.setRange(1, 5)
        self.std_multiplier_spin.setValue(2)
        std_layout.addWidget(self.std_multiplier_spin)
        std_layout.addWidget(QLabel("(Higher = less sensitive)"))
        std_layout.addStretch()
        threshold_layout.addLayout(std_layout)
        
        # 임계값 계산 버튼
        calc_button = QPushButton("Calculate Thresholds")
        calc_button.clicked.connect(self._on_calculate_thresholds)
        threshold_layout.addWidget(calc_button)
        
        # 임계값 표시
        from PyQt5.QtWidgets import QTextEdit
        self.threshold_display = QTextEdit()
        self.threshold_display.setText("Thresholds not calculated yet")
        self.threshold_display.setReadOnly(True)
        self.threshold_display.setMaximumHeight(150)
        self.threshold_display.setStyleSheet(
            "QTextEdit { background-color: #2b2b2b; color: #ffffff; border: 1px solid #444444; padding: 5px; }"
        )
        threshold_layout.addWidget(self.threshold_display)
        
        threshold_group.setLayout(threshold_layout)
        layout.addWidget(threshold_group)
        
        # Baseline 정보 표시
        info_group = QGroupBox("Baseline Statistics")
        info_layout = QVBoxLayout()
        
        self.baseline_info_display = QTextEdit()
        self.baseline_info_display.setText("No baseline data loaded")
        self.baseline_info_display.setReadOnly(True)
        self.baseline_info_display.setMaximumHeight(200)
        self.baseline_info_display.setStyleSheet(
            "QTextEdit { background-color: #2b2b2b; color: #ffffff; border: 1px solid #444444; padding: 5px; }"
        )
        info_layout.addWidget(self.baseline_info_display)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        layout.addStretch()
        self.setLayout(layout)
        
        # 내부 변수
        self.baseline_calculator = None
        self.baseline_collection_active = False
        self.baseline_start_time = None
        self.baseline_collected_count = 0
    
    def _on_start_baseline(self):
        """Baseline 수집 시작"""
        if self.baseline_collection_active:
            return
        
        self.baseline_calculator = BaselineCalculator()
        self.baseline_collection_active = True
        self.baseline_start_time = time.time()
        self.baseline_collected_count = 0
        
        self.start_baseline_button.setEnabled(False)
        self.stop_baseline_button.setEnabled(True)
        self.baseline_status_label.setText("Status: Collecting...")
        self.baseline_status_label.setStyleSheet("color: orange;")
    
    def _on_stop_baseline(self):
        """Baseline 수집 종료 및 UI 업데이트 (플래그 변경 안 함)"""
        # 주의: baseline_collection_active 플래그는 VisualizationWindow._on_stop_baseline_collection()에서 변경됨
        self.start_baseline_button.setEnabled(True)
        self.stop_baseline_button.setEnabled(False)
        
        # 여기서는 GUI만 업데이트하고, 실제 저장은 VisualizationWindow에서 수행
        self.baseline_status_label.setText("Status: Baseline saved successfully")
        self.baseline_status_label.setStyleSheet("color: green;")
    
    def _on_calculate_thresholds(self):
        """임계값 계산"""
        # baseline_calculator가 없으면 파일에서 로드 시도
        if self.baseline_calculator is None:
            from anomaly_detection import BaselineCalculator
            self.baseline_calculator = BaselineCalculator()
            if not self.baseline_calculator.load_baseline():
                self.threshold_display.setPlainText("Error: No baseline data. Please collect baseline first.")
                return
        
        baseline = self.baseline_calculator.get_baseline()
        
        # baseline이 비어있는지 확인 (모든 축이 빈 dict인지 체크)
        is_empty = all(not v or len(v) == 0 for v in baseline.values())
        if not baseline or is_empty:
            self.threshold_display.setPlainText("Error: Baseline is empty. Please collect baseline data first.")
            return
        
        std_multiplier = self.std_multiplier_spin.value()
        
        # 임계값 계산
        thresholds_text = f"Thresholds calculated with Std Multiplier: {std_multiplier}\n\n"
        
        for axis, features in baseline.items():
            if features:
                mean = features.get('mean', 0)
                std = features.get('std', 0)
                warning = mean + std * std_multiplier
                critical = mean + std * (std_multiplier * 1.5)
                thresholds_text += f"{axis.upper()}: Mean={mean:.2f}, Std={std:.2f}\n"
                thresholds_text += f"  Warning: {warning:.2f}, Critical: {critical:.2f}\n\n"
        
        self.threshold_display.setPlainText(thresholds_text)
        
        # Parent window의 anomaly detector 초기화
        # QApplication의 activeWindow를 통해 parent 찾기
        from PyQt5.QtWidgets import QApplication
        window = QApplication.instance().activeWindow()
        if window and hasattr(window, 'setup_anomaly_detector'):
            print(f"DEBUG: Calling setup_anomaly_detector on window: {window}")
            window.setup_anomaly_detector()
        else:
            print(f"DEBUG: Window not found or doesn't have setup_anomaly_detector. window={window}")
    
    def update_baseline_status(self, duration_seconds: int, data_count: int = 0):
        """Baseline 수집 상태 업데이트"""
        if self.baseline_collection_active and self.baseline_start_time:
            elapsed = time.time() - self.baseline_start_time
            self.baseline_progress_label.setText(f"{elapsed:.0f} / {duration_seconds} seconds")
            self.baseline_count_label.setText(f"Data Points: {data_count}")
    
    def update_baseline_info(self, baseline: dict):
        """Baseline 정보 표시"""
        if not baseline or all(not v for v in baseline.values()):
            self.baseline_info_display.setPlainText("No baseline data")
            return
        
        info_text = "Baseline Statistics:\n"
        for axis, features in baseline.items():
            if features:
                rms = features.get('rms', 0)
                peak = features.get('peak', 0)
                mean = features.get('mean', 0)
                std = features.get('std', 0)
                info_text += f"\n{axis.upper()}:\n"
                info_text += f"  RMS: {rms:.4f}, Peak: {peak:.4f}\n"
                info_text += f"  Mean: {mean:.4f}, Std: {std:.4f}\n"
        
        self.baseline_info_display.setPlainText(info_text)
    
    def update_realtime_graphs(self, current_data):
        """실시간 그래프 업데이트"""
        if current_data:
            self.baseline_velocity_graph.update_data(current_data.vx, current_data.vy, current_data.vz)
            self.baseline_displacement_graph.update_data(current_data.dx, current_data.dy, current_data.dz)
    
    def update_statistics_table(self, stats: dict):
        """통계 테이블 업데이트"""
        from PyQt5.QtWidgets import QTableWidgetItem
        
        axes = ['vx', 'vy', 'vz', 'dx', 'dy', 'dz']
        self.baseline_stats_table.setRowCount(len(axes))
        
        for row, axis in enumerate(axes):
            if axis in stats and stats[axis]:
                data = stats[axis]
                count = data.get('count', 0)
                mean = data.get('mean', 0)
                std = data.get('std', 0)
                min_val = data.get('min', 0)
                max_val = data.get('max', 0)
                rms = data.get('rms', 0)
                
                # 테이블 셀 설정
                self.baseline_stats_table.setItem(row, 0, QTableWidgetItem(axis.upper()))
                self.baseline_stats_table.setItem(row, 1, QTableWidgetItem(str(count)))
                self.baseline_stats_table.setItem(row, 2, QTableWidgetItem(f"{mean:.4f}"))
                self.baseline_stats_table.setItem(row, 3, QTableWidgetItem(f"{std:.4f}"))
                self.baseline_stats_table.setItem(row, 4, QTableWidgetItem(f"{min_val:.4f}"))
                self.baseline_stats_table.setItem(row, 5, QTableWidgetItem(f"{max_val:.4f}"))
                self.baseline_stats_table.setItem(row, 6, QTableWidgetItem(f"{rms:.4f}"))


class RealtimeMonitoringWidget(QWidget):
    """실시간 이상 감지 모니터링 탭"""
    
    def __init__(self, parent=None):
        """실시간 모니터링 위젯 초기화"""
        super().__init__(parent)
        
        from PyQt5.QtWidgets import QTextEdit
        
        layout = QVBoxLayout()
        
        # 상태 표시 섹션
        status_group = QGroupBox("System Status")
        status_layout = QVBoxLayout()
        
        # 전체 상태 표시
        self.overall_status_label = QLabel("Status: Ready")
        self.overall_status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #00FF00;")
        status_layout.addWidget(self.overall_status_label)
        
        # 임계값 로드 상태 및 버튼
        threshold_layout = QHBoxLayout()
        self.threshold_loaded_label = QLabel("Threshold Status: Not loaded")
        self.threshold_loaded_label.setStyleSheet("color: #FF9500;")
        threshold_layout.addWidget(self.threshold_loaded_label)
        
        self.load_baseline_button = QPushButton("Load Baseline")
        self.load_baseline_button.setMaximumWidth(120)
        self.load_baseline_button.clicked.connect(self._on_load_baseline)
        threshold_layout.addWidget(self.load_baseline_button)
        
        threshold_layout.addStretch()
        status_layout.addLayout(threshold_layout)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # 축별 상태 섹션
        axes_group = QGroupBox("Axis Status")
        axes_layout = QHBoxLayout()
        
        # 속도 축별 상태
        velocity_group = QGroupBox("Velocity (mm/s)")
        velocity_layout = QVBoxLayout()
        self.velocity_status_labels = {}
        for axis in ['VX', 'VY', 'VZ']:
            label = QLabel(f"{axis}: - / -")
            label.setStyleSheet("background-color: #2b2b2b; padding: 8px; border-radius: 4px;")
            self.velocity_status_labels[axis] = label
            velocity_layout.addWidget(label)
        velocity_group.setLayout(velocity_layout)
        axes_layout.addWidget(velocity_group)
        
        # 변위 축별 상태
        displacement_group = QGroupBox("Displacement (um)")
        displacement_layout = QVBoxLayout()
        self.displacement_status_labels = {}
        for axis in ['DX', 'DY', 'DZ']:
            label = QLabel(f"{axis}: - / -")
            label.setStyleSheet("background-color: #2b2b2b; padding: 8px; border-radius: 4px;")
            self.displacement_status_labels[axis] = label
            displacement_layout.addWidget(label)
        displacement_group.setLayout(displacement_layout)
        axes_layout.addWidget(displacement_group)
        
        # 가속도 축별 상태
        acceleration_group = QGroupBox("Acceleration (g)")
        acceleration_layout = QVBoxLayout()
        self.acceleration_status_labels = {}
        for axis in ['AX', 'AY', 'AZ']:
            label = QLabel(f"{axis}: - / -")
            label.setStyleSheet("background-color: #2b2b2b; padding: 8px; border-radius: 4px;")
            self.acceleration_status_labels[axis] = label
            acceleration_layout.addWidget(label)
        acceleration_group.setLayout(acceleration_layout)
        axes_layout.addWidget(acceleration_group)
        
        axes_group.setLayout(axes_layout)
        layout.addWidget(axes_group)
        
        # 실시간 그래프 섹션
        graph_group = QGroupBox("Real-time Trends")
        graph_layout = QHBoxLayout()
        
        # 속도 그래프
        self.monitoring_velocity_graph = TriAxisGraphWidget("Velocity Trend (mm/s)")
        graph_layout.addWidget(self.monitoring_velocity_graph)
        
        # 변위 그래프
        self.monitoring_displacement_graph = TriAxisGraphWidget("Displacement Trend (um)")
        graph_layout.addWidget(self.monitoring_displacement_graph)
        
        graph_group.setLayout(graph_layout)
        layout.addWidget(graph_group)
        
        # 이상 감지 로그 섹션
        log_group = QGroupBox("Anomaly Events Log")
        log_layout = QVBoxLayout()
        
        self.anomaly_log = QTextEdit()
        self.anomaly_log.setReadOnly(True)
        self.anomaly_log.setMaximumHeight(150)
        self.anomaly_log.setStyleSheet(
            "QTextEdit { background-color: #2b2b2b; color: #ffffff; border: 1px solid #444444; padding: 5px; }"
        )
        log_layout.addWidget(self.anomaly_log)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        # 내부 변수
        self.baseline_calculator = None
        self.anomaly_detector = None
        self.anomaly_count = 0
        self.warning_count = 0
        self.critical_count = 0
        
        layout.addStretch()
        self.setLayout(layout)
    
    def update_threshold_status(self, loaded: bool):
        """임계값 로드 상태 업데이트"""
        if loaded:
            self.threshold_loaded_label.setText("Threshold Status: ✓ Loaded")
            self.threshold_loaded_label.setStyleSheet("color: #00FF00;")
        else:
            self.threshold_loaded_label.setText("Threshold Status: ✗ Not loaded")
            self.threshold_loaded_label.setStyleSheet("color: #FF0000;")
    
    def update_monitoring_status(self, current_data, anomaly_status: dict):
        """모니터링 상태 업데이트"""
        if not current_data or not anomaly_status:
            return
        
        # 속도 축별 상태 업데이트
        velocity_axes = {
            'VX': ('vx', current_data.vx),
            'VY': ('vy', current_data.vy),
            'VZ': ('vz', current_data.vz)
        }
        
        for display_name, (key, value) in velocity_axes.items():
            status = anomaly_status.get(key, {})
            state = status.get('state', 'NORMAL')
            threshold = status.get('threshold', 0)
            
            # 상태에 따른 색상 설정
            if state == 'CRITICAL':
                color = "#FF0000"  # 빨강
                state_text = "🔴 CRITICAL"
            elif state == 'WARNING':
                color = "#FF9500"  # 주황
                state_text = "🟠 WARNING"
            else:
                color = "#00FF00"  # 초록
                state_text = "🟢 NORMAL"
            
            self.velocity_status_labels[display_name].setText(
                f"{display_name}: {value:.2f} / {threshold:.2f} [{state_text}]"
            )
            self.velocity_status_labels[display_name].setStyleSheet(
                f"background-color: #2b2b2b; color: {color}; padding: 8px; border-radius: 4px; font-weight: bold;"
            )
        
        # 변위 축별 상태 업데이트
        displacement_axes = {
            'DX': ('dx', current_data.dx),
            'DY': ('dy', current_data.dy),
            'DZ': ('dz', current_data.dz)
        }
        
        for display_name, (key, value) in displacement_axes.items():
            status = anomaly_status.get(key, {})
            state = status.get('state', 'NORMAL')
            threshold = status.get('threshold', 0)
            
            if state == 'CRITICAL':
                color = "#FF0000"
                state_text = "🔴 CRITICAL"
            elif state == 'WARNING':
                color = "#FF9500"
                state_text = "🟠 WARNING"
            else:
                color = "#00FF00"
                state_text = "🟢 NORMAL"
            
            self.displacement_status_labels[display_name].setText(
                f"{display_name}: {value:.2f} / {threshold:.2f} [{state_text}]"
            )
            self.displacement_status_labels[display_name].setStyleSheet(
                f"background-color: #2b2b2b; color: {color}; padding: 8px; border-radius: 4px; font-weight: bold;"
            )
        
        # 가속도 축별 상태 업데이트
        acceleration_axes = {
            'AX': ('ax', current_data.ax),
            'AY': ('ay', current_data.ay),
            'AZ': ('az', current_data.az)
        }
        
        for display_name, (key, value) in acceleration_axes.items():
            status = anomaly_status.get(key, {})
            state = status.get('state', 'NORMAL')
            threshold = status.get('threshold', 0)
            
            if state == 'CRITICAL':
                color = "#FF0000"
                state_text = "🔴 CRITICAL"
            elif state == 'WARNING':
                color = "#FF9500"
                state_text = "🟠 WARNING"
            else:
                color = "#00FF00"
                state_text = "🟢 NORMAL"
            
            self.acceleration_status_labels[display_name].setText(
                f"{display_name}: {value:.4f} / {threshold:.4f} [{state_text}]"
            )
            self.acceleration_status_labels[display_name].setStyleSheet(
                f"background-color: #2b2b2b; color: {color}; padding: 8px; border-radius: 4px; font-weight: bold;"
            )
        
        # 전체 상태 업데이트
        critical_axes = [k for k, v in anomaly_status.items() if v.get('state') == 'CRITICAL']
        warning_axes = [k for k, v in anomaly_status.items() if v.get('state') == 'WARNING']
        
        if critical_axes:
            self.overall_status_label.setText(f"Status: 🔴 CRITICAL ({len(critical_axes)} axis)")
            self.overall_status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #FF0000;")
        elif warning_axes:
            self.overall_status_label.setText(f"Status: 🟠 WARNING ({len(warning_axes)} axis)")
            self.overall_status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #FF9500;")
        else:
            self.overall_status_label.setText("Status: 🟢 NORMAL")
            self.overall_status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #00FF00;")
        
        # 그래프 업데이트
        self.monitoring_velocity_graph.update_data(current_data.vx, current_data.vy, current_data.vz)
        self.monitoring_displacement_graph.update_data(current_data.dx, current_data.dy, current_data.dz)
    
    def add_anomaly_event(self, timestamp: str, axis: str, state: str, value: float, threshold: float):
        """이상 감지 이벤트 로그 추가"""
        event_text = f"[{timestamp}] {axis}: {state} (Value: {value:.4f}, Threshold: {threshold:.4f})\n"
        self.anomaly_log.insertPlainText(event_text)
        
        # 스크롤을 맨 위로 이동 (최신 이벤트가 위에 보이도록)
        cursor = self.anomaly_log.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self.anomaly_log.setTextCursor(cursor)
    
    def _on_load_baseline(self):
        """저장된 baseline.json 파일 로드"""
        from anomaly_detection import BaselineCalculator
        
        baseline_calc = BaselineCalculator()
        if baseline_calc.load_baseline():
            # Parent window의 baseline_calculator 업데이트
            from PyQt5.QtWidgets import QApplication
            window = QApplication.instance().activeWindow()
            if window and hasattr(window, 'baseline_calculator'):
                window.baseline_calculator = baseline_calc
                window.anomaly_widget.baseline_calculator = baseline_calc
                
                # AnomalyDetector 초기화
                if hasattr(window, 'setup_anomaly_detector'):
                    window.setup_anomaly_detector()
                
                self.update_threshold_status(True)
                print(f"DEBUG: Baseline loaded successfully")
        else:
            print(f"DEBUG: Failed to load baseline.json")


class SensorConfigWidget(QWidget):
    """센서 설정 탭"""
    
    def __init__(self, parent=None):
        """센서 설정 위젯 초기화"""
        super().__init__(parent)
        
        layout = QVBoxLayout()
        
        # 1. 통신 설정 섹션
        comm_group = QGroupBox("Communication Settings")
        comm_layout = QVBoxLayout()
        
        # Baud Rate 설정
        baud_hlayout = QHBoxLayout()
        baud_hlayout.addWidget(QLabel("Baud Rate:"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["4800", "9600", "19200", "38400", "57600", "115200", "230400"])
        self.baud_combo.setCurrentText("9600")
        baud_hlayout.addWidget(self.baud_combo)
        
        self.baud_write_button = QPushButton("Write Baud Rate")
        self.baud_write_button.clicked.connect(self._on_write_baud_rate)
        baud_hlayout.addWidget(self.baud_write_button)
        baud_hlayout.addStretch()
        comm_layout.addLayout(baud_hlayout)
        
        # Device Address 설정
        addr_hlayout = QHBoxLayout()
        addr_hlayout.addWidget(QLabel("Device Address (Modbus ID):"))
        self.device_addr_spin = QSpinBox()
        self.device_addr_spin.setRange(0x00, 0x7F)
        self.device_addr_spin.setValue(0x50)
        self.device_addr_spin.setDisplayIntegerBase(16)
        addr_hlayout.addWidget(self.device_addr_spin)
        
        self.device_addr_write_button = QPushButton("Write Device Address")
        self.device_addr_write_button.clicked.connect(self._on_write_device_address)
        addr_hlayout.addWidget(self.device_addr_write_button)
        addr_hlayout.addStretch()
        comm_layout.addLayout(addr_hlayout)
        
        comm_group.setLayout(comm_layout)
        layout.addWidget(comm_group)
        
        # 2. 필터 설정 섹션
        filter_group = QGroupBox("Filter Settings")
        filter_layout = QVBoxLayout()
        
        # Cutoff Frequency 설정
        cutoff_hlayout = QHBoxLayout()
        cutoff_hlayout.addWidget(QLabel("Cutoff Frequency (Hz):"))
        self.cutoff_spin = QDoubleSpinBox()
        self.cutoff_spin.setRange(0.0, 200.0)
        self.cutoff_spin.setValue(10.0)
        self.cutoff_spin.setDecimals(2)
        self.cutoff_spin.setSingleStep(0.1)
        cutoff_hlayout.addWidget(self.cutoff_spin)
        
        self.cutoff_write_button = QPushButton("Write Cutoff Frequency")
        self.cutoff_write_button.clicked.connect(self._on_write_cutoff_frequency)
        cutoff_hlayout.addWidget(self.cutoff_write_button)
        cutoff_hlayout.addStretch()
        filter_layout.addLayout(cutoff_hlayout)
        
        # Detection Period (Sample Frequency) 설정
        sample_hlayout = QHBoxLayout()
        sample_hlayout.addWidget(QLabel("Detection Period (Hz):"))
        self.sample_freq_spin = QSpinBox()
        self.sample_freq_spin.setRange(1, 200)
        self.sample_freq_spin.setValue(100)
        sample_hlayout.addWidget(self.sample_freq_spin)
        
        self.sample_freq_write_button = QPushButton("Write Detection Period")
        self.sample_freq_write_button.clicked.connect(self._on_write_sample_frequency)
        sample_hlayout.addWidget(self.sample_freq_write_button)
        sample_hlayout.addStretch()
        filter_layout.addLayout(sample_hlayout)
        
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)
        
        # 3. 시간 설정 섹션
        time_group = QGroupBox("Chip Time Settings")
        time_layout = QVBoxLayout()
        
        time_input_layout = QHBoxLayout()
        time_input_layout.addWidget(QLabel("Set Date & Time:"))
        
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2000, 2099)
        self.year_spin.setValue(2024)
        time_input_layout.addWidget(QLabel("Year:"))
        time_input_layout.addWidget(self.year_spin)
        
        self.month_spin = QSpinBox()
        self.month_spin.setRange(1, 12)
        self.month_spin.setValue(12)
        time_input_layout.addWidget(QLabel("Month:"))
        time_input_layout.addWidget(self.month_spin)
        
        self.day_spin = QSpinBox()
        self.day_spin.setRange(1, 31)
        self.day_spin.setValue(1)
        time_input_layout.addWidget(QLabel("Day:"))
        time_input_layout.addWidget(self.day_spin)
        
        self.hour_spin = QSpinBox()
        self.hour_spin.setRange(0, 23)
        self.hour_spin.setValue(0)
        time_input_layout.addWidget(QLabel("Hour:"))
        time_input_layout.addWidget(self.hour_spin)
        
        self.minute_spin = QSpinBox()
        self.minute_spin.setRange(0, 59)
        self.minute_spin.setValue(0)
        time_input_layout.addWidget(QLabel("Minute:"))
        time_input_layout.addWidget(self.minute_spin)
        
        self.second_spin = QSpinBox()
        self.second_spin.setRange(0, 59)
        self.second_spin.setValue(0)
        time_input_layout.addWidget(QLabel("Second:"))
        time_input_layout.addWidget(self.second_spin)
        
        time_input_layout.addStretch()
        time_layout.addLayout(time_input_layout)
        
        self.time_write_button = QPushButton("Write Chip Time")
        self.time_write_button.clicked.connect(self._on_write_chip_time)
        time_layout.addWidget(self.time_write_button)
        
        time_group.setLayout(time_layout)
        layout.addWidget(time_group)
        
        # 4. 모드 설정 섹션
        mode_group = QGroupBox("Mode Settings")
        mode_layout = QVBoxLayout()
        
        high_speed_hlayout = QHBoxLayout()
        high_speed_hlayout.addWidget(QLabel("High-Speed Mode (1000Hz, displacement only):"))
        
        self.highspeed_button = QPushButton("Enter High-Speed Mode")
        self.highspeed_button.setStyleSheet("background-color: #FF9500; color: white; font-weight: bold;")
        self.highspeed_button.clicked.connect(self._on_enter_highspeed_mode)
        high_speed_hlayout.addWidget(self.highspeed_button)
        
        high_speed_hlayout.addStretch()
        mode_layout.addLayout(high_speed_hlayout)
        
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)
        
        # 5. 유지보수 섹션
        maint_group = QGroupBox("Maintenance")
        maint_layout = QVBoxLayout()
        
        restart_hlayout = QHBoxLayout()
        self.restart_button = QPushButton("Restart Sensor")
        self.restart_button.setStyleSheet("background-color: #FF6347; color: white;")
        self.restart_button.clicked.connect(self._on_restart_sensor)
        restart_hlayout.addWidget(self.restart_button)
        
        self.factory_reset_button = QPushButton("Factory Reset")
        self.factory_reset_button.setStyleSheet("background-color: #DC143C; color: white; font-weight: bold;")
        self.factory_reset_button.clicked.connect(self._on_factory_reset)
        restart_hlayout.addWidget(self.factory_reset_button)
        
        restart_hlayout.addStretch()
        maint_layout.addLayout(restart_hlayout)
        
        maint_group.setLayout(maint_layout)
        layout.addWidget(maint_group)
        
        # 6. Raw Sensor Value 섹션
        raw_group = QGroupBox("Raw Sensor Values")
        raw_layout = QVBoxLayout()
        
        raw_button_layout = QHBoxLayout()
        self.read_raw_button = QPushButton("Read Raw Values")
        self.read_raw_button.setStyleSheet("background-color: #2196F3; color: white;")
        self.read_raw_button.clicked.connect(self._on_read_raw_values)
        raw_button_layout.addWidget(self.read_raw_button)
        
        self.read_all_registers_button = QPushButton("Read All Registers (0x00-0x70)")
        self.read_all_registers_button.setStyleSheet("background-color: #4CAF50; color: white;")
        self.read_all_registers_button.clicked.connect(self._on_read_all_registers)
        raw_button_layout.addWidget(self.read_all_registers_button)
        
        raw_button_layout.addStretch()
        raw_layout.addLayout(raw_button_layout)
        
        self.raw_values_display = QTextEdit()
        self.raw_values_display.setReadOnly(True)
        self.raw_values_display.setMaximumHeight(200)
        self.raw_values_display.setStyleSheet(
            "QTextEdit { background-color: #1a1a1a; color: #00FF00; border: 1px solid #444444; padding: 5px; font-family: 'Courier New'; font-size: 9pt; }"
        )
        self.raw_values_display.setPlainText("Ready to read raw values...")
        raw_layout.addWidget(self.raw_values_display)
        
        raw_group.setLayout(raw_layout)
        layout.addWidget(raw_group)
        
        # 7. 상태 표시 섹션
        status_group = QGroupBox("Configuration Status")
        status_layout = QVBoxLayout()
        
        self.config_status_display = QTextEdit()
        self.config_status_display.setReadOnly(True)
        self.config_status_display.setMaximumHeight(150)
        self.config_status_display.setStyleSheet(
            "QTextEdit { background-color: #2b2b2b; color: #ffffff; border: 1px solid #444444; padding: 5px; }"
        )
        self.config_status_display.setPlainText("Ready for configuration...")
        status_layout.addWidget(self.config_status_display)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        layout.addStretch()
        self.setLayout(layout)
        
        # 내부 변수
        self.sensor = None
    
    def set_sensor(self, sensor):
        """센서 객체 설정"""
        self.sensor = sensor
    
    def _log_status(self, message: str):
        """상태 메시지 기록"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        current = self.config_status_display.toPlainText()
        self.config_status_display.setPlainText(f"[{timestamp}] {message}\n{current}")
    
    def _on_write_baud_rate(self):
        """Baud Rate 쓰기"""
        if not self.sensor or not self.sensor.is_connected:
            self._log_status("❌ Sensor not connected")
            return
        
        baud_text = self.baud_combo.currentText()
        baud_map = {
            "4800": 0x01, "9600": 0x02, "19200": 0x03, "38400": 0x04,
            "57600": 0x05, "115200": 0x06, "230400": 0x07
        }
        baud_value = baud_map[baud_text]
        
        try:
            # Unlock
            self.sensor.write_register(0x0069, 0xB588)
            # Write Baud Rate
            self.sensor.write_register(0x04, baud_value)
            # Save
            self.sensor.write_register(0x0000, 0x0084)
            self._log_status(f"✓ Baud rate changed to {baud_text}. Sensor will restart at new baud rate.")
        except Exception as e:
            self._log_status(f"❌ Error: {str(e)}")
    
    def _on_write_device_address(self):
        """Device Address 쓰기"""
        if not self.sensor or not self.sensor.is_connected:
            self._log_status("❌ Sensor not connected")
            return
        
        device_addr = self.device_addr_spin.value()
        
        try:
            # Unlock
            self.sensor.write_register(0x0069, 0xB588)
            # Write Device Address
            self.sensor.write_register(0x1A, device_addr)
            # Save
            self.sensor.write_register(0x0000, 0x0084)
            self._log_status(f"✓ Device address changed to 0x{device_addr:02X}. Please restart connection.")
        except Exception as e:
            self._log_status(f"❌ Error: {str(e)}")
    
    def _on_write_cutoff_frequency(self):
        """Cutoff Frequency 쓰기"""
        if not self.sensor or not self.sensor.is_connected:
            self._log_status("❌ Sensor not connected")
            return
        
        cutoff_freq = self.cutoff_spin.value()
        freq_int = int(cutoff_freq)
        freq_frac = int((cutoff_freq - freq_int) * 100)
        
        try:
            # Unlock
            self.sensor.write_register(0x0069, 0xB588)
            # Write Cutoff Frequency Integer
            self.sensor.write_register(0x63, freq_int)
            # Write Cutoff Frequency Fraction
            self.sensor.write_register(0x64, freq_frac)
            # Save
            self.sensor.write_register(0x0000, 0x0084)
            self._log_status(f"✓ Cutoff frequency set to {cutoff_freq:.2f} Hz")
        except Exception as e:
            self._log_status(f"❌ Error: {str(e)}")
    
    def _on_write_sample_frequency(self):
        """Detection Period (Sample Frequency) 쓰기"""
        if not self.sensor or not self.sensor.is_connected:
            self._log_status("❌ Sensor not connected")
            return
        
        sample_freq = self.sample_freq_spin.value()
        
        try:
            # Unlock
            self.sensor.write_register(0x0069, 0xB588)
            # Write Sample Frequency
            self.sensor.write_register(0x65, sample_freq)
            # Save
            self.sensor.write_register(0x0000, 0x0084)
            self._log_status(f"✓ Detection period set to {sample_freq} Hz")
        except Exception as e:
            self._log_status(f"❌ Error: {str(e)}")
    
    def _on_write_chip_time(self):
        """Chip Time 쓰기"""
        if not self.sensor or not self.sensor.is_connected:
            self._log_status("❌ Sensor not connected")
            return
        
        year = self.year_spin.value() % 100  # 2024 -> 24
        month = self.month_spin.value()
        day = self.day_spin.value()
        hour = self.hour_spin.value()
        minute = self.minute_spin.value()
        second = self.second_spin.value()
        
        try:
            # Unlock
            self.sensor.write_register(0x0069, 0xB588)
            
            # Write YYMM (Year-Month)
            yymm_value = (month << 8) | year
            self.sensor.write_register(0x30, yymm_value)
            
            # Write DDHH (Day-Hour)
            ddhh_value = (hour << 8) | day
            self.sensor.write_register(0x31, ddhh_value)
            
            # Write MMSS (Minute-Second)
            mmss_value = (second << 8) | minute
            self.sensor.write_register(0x32, mmss_value)
            
            # Write MS (Millisecond = 0)
            self.sensor.write_register(0x33, 0x0000)
            
            # Save
            self.sensor.write_register(0x0000, 0x0084)
            
            datetime_str = f"{year:02d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
            self._log_status(f"✓ Chip time set to {datetime_str}")
        except Exception as e:
            self._log_status(f"❌ Error: {str(e)}")
    
    def _on_enter_highspeed_mode(self):
        """High-Speed Mode 진입"""
        if not self.sensor or not self.sensor.is_connected:
            self._log_status("❌ Sensor not connected")
            return
        
        try:
            # Unlock
            self.sensor.write_register(0x0069, 0xB588)
            # Enter High-Speed Mode
            self.sensor.write_register(0x62, 0x0001)
            
            self._log_status("✓ Entered High-Speed Mode (1000Hz, displacement only). Baud rate: 230400. Power off to exit.")
        except Exception as e:
            self._log_status(f"❌ Error: {str(e)}")
    
    def _on_restart_sensor(self):
        """센서 재시작"""
        if not self.sensor or not self.sensor.is_connected:
            self._log_status("❌ Sensor not connected")
            return
        
        try:
            # Unlock
            self.sensor.write_register(0x0069, 0xB588)
            # Restart
            self.sensor.write_register(0x0000, 0x00FF)
            
            self._log_status("✓ Sensor restarting...")
        except Exception as e:
            self._log_status(f"❌ Error: {str(e)}")
    
    def _on_read_raw_values(self):
        """센서의 현재 Raw 값 읽기"""
        if not self.sensor or not self.sensor.is_connected:
            self.raw_values_display.setPlainText("❌ Sensor not connected")
            return
        
        try:
            output = "=== CURRENT SENSOR RAW VALUES ===\n\n"
            
            # 가속도
            acc_data = self.sensor.modbus.read_registers(0x34, 3)
            if acc_data:
                ax = int.from_bytes(acc_data[0:2], 'big', signed=True) / 1000.0
                ay = int.from_bytes(acc_data[2:4], 'big', signed=True) / 1000.0
                az = int.from_bytes(acc_data[4:6], 'big', signed=True) / 1000.0
                output += f"Acceleration (g):\n  AX: {ax:.4f}\n  AY: {ay:.4f}\n  AZ: {az:.4f}\n\n"
            
            # 진동 속도
            vel_data = self.sensor.modbus.read_registers(0x3A, 3)
            if vel_data:
                vx = int.from_bytes(vel_data[0:2], 'big', signed=True) / 100.0
                vy = int.from_bytes(vel_data[2:4], 'big', signed=True) / 100.0
                vz = int.from_bytes(vel_data[4:6], 'big', signed=True) / 100.0
                output += f"Velocity (mm/s):\n  VX: {vx:.2f}\n  VY: {vy:.2f}\n  VZ: {vz:.2f}\n\n"
            
            # 온도
            temp_data = self.sensor.modbus.read_registers(0x40, 1)
            if temp_data:
                temp = int.from_bytes(temp_data[0:2], 'big', signed=True) / 100.0
                output += f"Temperature (°C): {temp:.2f}\n\n"
            
            # 진동 변위
            disp_data = self.sensor.modbus.read_registers(0x41, 3)
            if disp_data:
                dx = int.from_bytes(disp_data[0:2], 'big', signed=True)
                dy = int.from_bytes(disp_data[2:4], 'big', signed=True)
                dz = int.from_bytes(disp_data[4:6], 'big', signed=True)
                output += f"Displacement (um):\n  DX: {dx}\n  DY: {dy}\n  DZ: {dz}\n\n"
            
            # 진동 주파수
            freq_data = self.sensor.modbus.read_registers(0x44, 3)
            if freq_data:
                hx = int.from_bytes(freq_data[0:2], 'big', signed=False) / 100.0
                hy = int.from_bytes(freq_data[2:4], 'big', signed=False) / 100.0
                hz = int.from_bytes(freq_data[4:6], 'big', signed=False) / 100.0
                output += f"Frequency (Hz):\n  HX: {hx:.2f}\n  HY: {hy:.2f}\n  HZ: {hz:.2f}\n\n"
            
            self.raw_values_display.setPlainText(output)
            self._log_status("✓ Raw values read successfully")
        
        except Exception as e:
            error_msg = f"❌ Error reading raw values: {str(e)}"
            self.raw_values_display.setPlainText(error_msg)
            self._log_status(error_msg)
    
    def _on_read_all_registers(self):
        """모든 레지스터 값 읽기 (0x00-0x70)"""
        if not self.sensor or not self.sensor.is_connected:
            self.raw_values_display.setPlainText("❌ Sensor not connected")
            return
        
        try:
            output = "=== ALL REGISTERS (0x00-0x70) ===\n\n"
            
            # 레지스터를 16개씩 읽기
            for start_addr in range(0x00, 0x71, 16):
                end_addr = min(start_addr + 16, 0x71)
                count = end_addr - start_addr
                
                data = self.sensor.modbus.read_registers(start_addr, count)
                if data:
                    output += f"[{start_addr:#04x}-{end_addr-1:#04x}] "
                    for i in range(0, len(data), 2):
                        if i + 1 < len(data):
                            value = int.from_bytes(data[i:i+2], 'big', signed=False)
                            output += f"{value:#06x} "
                    output += "\n"
                else:
                    output += f"[{start_addr:#04x}-{end_addr-1:#04x}] (Failed to read)\n"
            
            self.raw_values_display.setPlainText(output)
            self._log_status("✓ All registers read successfully")
        
        except Exception as e:
            error_msg = f"❌ Error reading registers: {str(e)}"
            self.raw_values_display.setPlainText(error_msg)
            self._log_status(error_msg)
    
    def _on_factory_reset(self):
        """Factory Reset"""
        if not self.sensor or not self.sensor.is_connected:
            self._log_status("❌ Sensor not connected")
            return
        
        from PyQt5.QtWidgets import QMessageBox
        reply = QMessageBox.warning(
            self,
            "Factory Reset",
            "Are you sure you want to reset to factory settings? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # Unlock
                self.sensor.write_register(0x0069, 0xB588)
                # Factory Reset
                self.sensor.write_register(0x0000, 0x0001)
                
                self._log_status("✓ Factory reset initiated. Sensor will restart with default settings.")
            except Exception as e:
                self._log_status(f"❌ Error: {str(e)}")


class SerialMonitorWidget(QWidget):
    """시리얼 모니터 탭 (아두이노 IDE 스타일)"""
    
    def __init__(self, parent=None):
        """시리얼 모니터 위젯 초기화"""
        super().__init__(parent)
        
        layout = QVBoxLayout()
        
        # 컨트롤 패널
        control_layout = QHBoxLayout()
        
        # 데이터 형식 선택
        control_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["HEX", "DEC", "ASCII", "Mixed"])
        control_layout.addWidget(self.format_combo)
        
        # 시간 표시 여부
        self.show_timestamp_check = QComboBox()
        self.show_timestamp_check.addItems(["No timestamp", "With timestamp"])
        control_layout.addWidget(self.show_timestamp_check)
        
        # 버튼들
        self.start_monitor_button = QPushButton("Start Monitor")
        self.start_monitor_button.setStyleSheet("background-color: #4CAF50; color: white;")
        self.start_monitor_button.clicked.connect(self._on_start_monitor)
        control_layout.addWidget(self.start_monitor_button)
        
        self.stop_monitor_button = QPushButton("Stop Monitor")
        self.stop_monitor_button.setEnabled(False)
        self.stop_monitor_button.setStyleSheet("background-color: #F44336; color: white;")
        self.stop_monitor_button.clicked.connect(self._on_stop_monitor)
        control_layout.addWidget(self.stop_monitor_button)
        
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._on_clear)
        control_layout.addWidget(self.clear_button)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        # 시리얼 데이터 표시
        self.serial_display = QTextEdit()
        self.serial_display.setReadOnly(True)
        self.serial_display.setStyleSheet(
            "QTextEdit { background-color: #000000; color: #00FF00; border: 1px solid #00AA00; padding: 5px; font-family: 'Courier New'; font-size: 9pt; }"
        )
        self.serial_display.setPlainText("Waiting to start monitor...\n")
        layout.addWidget(self.serial_display)
        
        # 통계
        stats_layout = QHBoxLayout()
        stats_layout.addWidget(QLabel("Total Bytes:"))
        self.total_bytes_label = QLabel("0")
        stats_layout.addWidget(self.total_bytes_label)
        
        stats_layout.addWidget(QLabel("Data Rate:"))
        self.data_rate_label = QLabel("0 B/s")
        stats_layout.addWidget(self.data_rate_label)
        
        stats_layout.addStretch()
        layout.addLayout(stats_layout)
        
        self.setLayout(layout)
        
        # 내부 변수
        self.sensor = None
        self.monitoring = False
        self.total_bytes = 0
        self.monitor_timer = None
        self.last_byte_time = 0
        self.bytes_per_second = 0
        self.line_count = 0
        self.max_lines = 1000  # 최대 라인 수
    
    def set_sensor(self, sensor):
        """센서 객체 설정"""
        self.sensor = sensor
    
    def _on_start_monitor(self):
        """모니터링 시작"""
        if not self.sensor or not self.sensor.is_connected:
            self.serial_display.setPlainText("❌ Sensor not connected\n")
            return
        
        self.monitoring = True
        self.total_bytes = 0
        self.line_count = 0
        self.serial_display.clear()
        
        self.start_monitor_button.setEnabled(False)
        self.stop_monitor_button.setEnabled(True)
        
        self.serial_display.append("=== Serial Monitor Started ===")
        self.serial_display.append(f"Format: {self.format_combo.currentText()}\n")
        
        # 타이머 시작 (100ms 주기로 데이터 읽기)
        if not self.monitor_timer:
            self.monitor_timer = QTimer()
            self.monitor_timer.timeout.connect(self._on_monitor_update)
        
        self.monitor_timer.start(100)
    
    def _on_stop_monitor(self):
        """모니터링 중지"""
        self.monitoring = False
        if self.monitor_timer:
            self.monitor_timer.stop()
        
        self.start_monitor_button.setEnabled(True)
        self.stop_monitor_button.setEnabled(False)
        
        self.serial_display.append("\n=== Serial Monitor Stopped ===")
    
    def _on_clear(self):
        """화면 지우기"""
        self.serial_display.clear()
        self.line_count = 0
    
    def _on_monitor_update(self):
        """모니터링 업데이트"""
        if not self.sensor or not self.sensor.is_connected or not self.monitoring:
            return
        
        try:
            # 시리얼 포트에서 데이터 읽기
            if self.sensor.modbus.serial and self.sensor.modbus.serial.in_waiting > 0:
                raw_bytes = self.sensor.modbus.serial.read(self.sensor.modbus.serial.in_waiting)
                
                if raw_bytes:
                    current_time = datetime.now()
                    self.total_bytes += len(raw_bytes)
                    self.last_byte_time = time.time()
                    
                    # 데이터 형식 변환
                    formatted_data = self._format_data(raw_bytes, current_time)
                    
                    # 표시
                    cursor = self.serial_display.textCursor()
                    cursor.movePosition(cursor.End)
                    self.serial_display.setTextCursor(cursor)
                    self.serial_display.insertPlainText(formatted_data)
                    
                    self.line_count += formatted_data.count('\n')
                    
                    # 라인 수 제한
                    if self.line_count > self.max_lines:
                        self._trim_display()
                    
                    # 통계 업데이트
                    self._update_stats()
        
        except Exception as e:
            self.serial_display.append(f"❌ Error: {str(e)}")
    
    def _format_data(self, raw_bytes: bytes, timestamp: datetime) -> str:
        """데이터 형식 변환"""
        format_type = self.format_combo.currentText()
        show_timestamp = self.show_timestamp_check.currentText() == "With timestamp"
        
        result = ""
        
        if show_timestamp:
            result += f"[{timestamp.strftime('%H:%M:%S.%f')[:-3]}] "
        
        if format_type == "HEX":
            result += " ".join(f"{b:02X}" for b in raw_bytes)
        elif format_type == "DEC":
            result += " ".join(f"{b:03d}" for b in raw_bytes)
        elif format_type == "ASCII":
            result += raw_bytes.decode('latin-1', errors='replace')
        elif format_type == "Mixed":
            # HEX + ASCII 형식 (헥스덤프 형식)
            for i in range(0, len(raw_bytes), 16):
                chunk = raw_bytes[i:i+16]
                hex_part = " ".join(f"{b:02X}" for b in chunk)
                ascii_part = "".join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
                result += f"{i:04X}: {hex_part:<48} {ascii_part}\n"
                if show_timestamp and i == 0:
                    result = f"[{timestamp.strftime('%H:%M:%S.%f')[:-3]}] " + result
            return result
        
        result += "\n"
        return result
    
    def _update_stats(self):
        """통계 업데이트"""
        self.total_bytes_label.setText(str(self.total_bytes))
        
        # 데이터 속도 계산
        elapsed = time.time() - self.last_byte_time if self.last_byte_time > 0 else 1
        if elapsed < 1.0:
            self.bytes_per_second = int(len(self.serial_display.toPlainText()) / max(elapsed, 0.1))
        
        self.data_rate_label.setText(f"{self.bytes_per_second} B/s")
    
    def _trim_display(self):
        """표시 내용 정리 (라인 제한)"""
        doc = self.serial_display.document()
        block = doc.findBlockByLineNumber(self.max_lines // 2)
        
        if block.isValid():
            cursor = self.serial_display.textCursor()
            cursor.setPosition(0)
            cursor.setPosition(block.position(), cursor.KeepAnchor)
            cursor.removeSelectedText()
            self.line_count = self.max_lines // 2


class AnalyticsWidget(QWidget):
    """데이터 분석 및 통계 탭"""
    
    def __init__(self, parent=None):
        """분석 위젯 초기화"""
        super().__init__(parent)
        
        layout = QVBoxLayout()
        
        # 통계 정보 그룹
        stats_group = QGroupBox("Statistics Summary")
        stats_layout = QGridLayout()
        
        # 각 축별 현재값, 최대값, 최소값, 평균값
        labels = ["Velocity X", "Velocity Y", "Velocity Z", 
                  "Displacement X", "Displacement Y", "Displacement Z",
                  "Frequency X", "Frequency Y", "Frequency Z"]
        
        self.stat_labels = {}
        row = 0
        for label in labels:
            # 현재값
            stats_layout.addWidget(QLabel(f"{label} Current:"), row, 0)
            self.stat_labels[f"{label}_current"] = QLabel("0.00")
            stats_layout.addWidget(self.stat_labels[f"{label}_current"], row, 1)
            
            # 최대값
            stats_layout.addWidget(QLabel(f"  Max:"), row, 2)
            self.stat_labels[f"{label}_max"] = QLabel("0.00")
            stats_layout.addWidget(self.stat_labels[f"{label}_max"], row, 3)
            
            # 최소값
            stats_layout.addWidget(QLabel(f"  Min:"), row, 4)
            self.stat_labels[f"{label}_min"] = QLabel("0.00")
            stats_layout.addWidget(self.stat_labels[f"{label}_min"], row, 5)
            
            # 평균값
            stats_layout.addWidget(QLabel(f"  Avg:"), row, 6)
            self.stat_labels[f"{label}_avg"] = QLabel("0.00")
            stats_layout.addWidget(self.stat_labels[f"{label}_avg"], row, 7)
            
            row += 1
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # 온도 통계
        temp_group = QGroupBox("Temperature Statistics")
        temp_layout = QGridLayout()
        
        temp_layout.addWidget(QLabel("Current Temperature:"), 0, 0)
        self.temp_current_label = QLabel("0.00°C")
        temp_layout.addWidget(self.temp_current_label, 0, 1)
        
        temp_layout.addWidget(QLabel("Max Temperature:"), 0, 2)
        self.temp_max_label = QLabel("0.00°C")
        temp_layout.addWidget(self.temp_max_label, 0, 3)
        
        temp_layout.addWidget(QLabel("Min Temperature:"), 1, 0)
        self.temp_min_label = QLabel("0.00°C")
        temp_layout.addWidget(self.temp_min_label, 1, 1)
        
        temp_layout.addWidget(QLabel("Average Temperature:"), 1, 2)
        self.temp_avg_label = QLabel("0.00°C")
        temp_layout.addWidget(self.temp_avg_label, 1, 3)
        
        temp_group.setLayout(temp_layout)
        layout.addWidget(temp_group)
        
        # 수집 통계
        collection_group = QGroupBox("Data Collection Statistics")
        collection_layout = QGridLayout()
        
        collection_layout.addWidget(QLabel("Total Readings:"), 0, 0)
        self.total_readings_label = QLabel("0")
        collection_layout.addWidget(self.total_readings_label, 0, 1)
        
        collection_layout.addWidget(QLabel("Success Rate:"), 0, 2)
        self.collection_success_rate_label = QLabel("0%")
        collection_layout.addWidget(self.collection_success_rate_label, 0, 3)
        
        collection_layout.addWidget(QLabel("Total Errors:"), 1, 0)
        self.total_errors_label = QLabel("0")
        collection_layout.addWidget(self.total_errors_label, 1, 1)
        
        collection_layout.addWidget(QLabel("Elapsed Time:"), 1, 2)
        self.elapsed_time_label = QLabel("0h 0m 0s")
        collection_layout.addWidget(self.elapsed_time_label, 1, 3)
        
        collection_group.setLayout(collection_layout)
        layout.addWidget(collection_group)
        
        # 알람 통계
        alarm_group = QGroupBox("Alarm Statistics")
        alarm_layout = QGridLayout()
        
        alarm_layout.addWidget(QLabel("Total Alarms:"), 0, 0)
        self.total_alarms_label = QLabel("0")
        alarm_layout.addWidget(self.total_alarms_label, 0, 1)
        
        alarm_layout.addWidget(QLabel("Warning Count:"), 0, 2)
        self.warning_count_label = QLabel("0")
        alarm_layout.addWidget(self.warning_count_label, 0, 3)
        
        alarm_layout.addWidget(QLabel("Critical Count:"), 1, 0)
        self.critical_count_label = QLabel("0")
        alarm_layout.addWidget(self.critical_count_label, 1, 1)
        
        alarm_layout.addWidget(QLabel("Last Alarm:"), 1, 2)
        self.last_alarm_label = QLabel("N/A")
        alarm_layout.addWidget(self.last_alarm_label, 1, 3)
        
        alarm_group.setLayout(alarm_layout)
        layout.addWidget(alarm_group)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def update_statistics(self, stats_data: dict):
        """통계 데이터 업데이트"""
        if not stats_data:
            return
        
        # 속도 데이터 업데이트
        for axis, key in [('Velocity X', 'vx'), ('Velocity Y', 'vy'), ('Velocity Z', 'vz')]:
            if key in stats_data:
                self.stat_labels[f"{axis}_current"].setText(f"{stats_data[key]['current']:.2f}")
                self.stat_labels[f"{axis}_max"].setText(f"{stats_data[key]['max']:.2f}")
                self.stat_labels[f"{axis}_min"].setText(f"{stats_data[key]['min']:.2f}")
                self.stat_labels[f"{axis}_avg"].setText(f"{stats_data[key]['avg']:.2f}")
        
        # 변위 데이터 업데이트
        for axis, key in [('Displacement X', 'dx'), ('Displacement Y', 'dy'), ('Displacement Z', 'dz')]:
            if key in stats_data:
                self.stat_labels[f"{axis}_current"].setText(f"{stats_data[key]['current']:.2f}")
                self.stat_labels[f"{axis}_max"].setText(f"{stats_data[key]['max']:.2f}")
                self.stat_labels[f"{axis}_min"].setText(f"{stats_data[key]['min']:.2f}")
                self.stat_labels[f"{axis}_avg"].setText(f"{stats_data[key]['avg']:.2f}")
        
        # 주파수 데이터 업데이트
        for axis, key in [('Frequency X', 'hx'), ('Frequency Y', 'hy'), ('Frequency Z', 'hz')]:
            if key in stats_data:
                self.stat_labels[f"{axis}_current"].setText(f"{stats_data[key]['current']:.2f}")
                self.stat_labels[f"{axis}_max"].setText(f"{stats_data[key]['max']:.2f}")
                self.stat_labels[f"{axis}_min"].setText(f"{stats_data[key]['min']:.2f}")
                self.stat_labels[f"{axis}_avg"].setText(f"{stats_data[key]['avg']:.2f}")
        
        # 온도 데이터 업데이트
        if 'temp' in stats_data and isinstance(stats_data['temp'], dict):
            temp_data = stats_data['temp']
            if 'current' in temp_data:
                self.temp_current_label.setText(f"{temp_data['current']:.2f}°C")
            if 'max' in temp_data:
                self.temp_max_label.setText(f"{temp_data['max']:.2f}°C")
            if 'min' in temp_data:
                self.temp_min_label.setText(f"{temp_data['min']:.2f}°C")
            if 'avg' in temp_data:
                self.temp_avg_label.setText(f"{temp_data['avg']:.2f}°C")
        
        # 수집 통계 업데이트
        if 'total_readings' in stats_data:
            self.total_readings_label.setText(str(stats_data['total_readings']))
        if 'success_rate' in stats_data:
            self.collection_success_rate_label.setText(f"{stats_data['success_rate']:.1f}%")
        if 'failed_readings' in stats_data:
            self.total_errors_label.setText(str(stats_data['failed_readings']))
        if 'elapsed_time' in stats_data:
            # 경과 시간을 시:분:초 형식으로 변환
            elapsed = stats_data['elapsed_time']
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = int(elapsed % 60)
            self.elapsed_time_label.setText(f"{hours}h {minutes}m {seconds}s")


class StatusPanel(QWidget):
    """상태 표시 패널"""
    
    def __init__(self, parent=None):
        """상태 패널 초기화"""
        super().__init__(parent)
        
        layout = QVBoxLayout()
        
        # 연결 상태
        connection_layout = QHBoxLayout()
        connection_layout.addWidget(QLabel("Connection Status:"))
        self.connection_label = QLabel("Disconnected")
        self.connection_label.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addWidget(self.connection_label)
        connection_layout.addStretch()
        layout.addLayout(connection_layout)
        
        # 에러 메시지 표시
        error_layout = QHBoxLayout()
        error_layout.addWidget(QLabel("Status:"))
        self.error_label = QLabel("Ready")
        self.error_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        error_layout.addWidget(self.error_label)
        error_layout.addStretch()
        layout.addLayout(error_layout)
        
        # 포트 정보
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Port:"))
        self.port_label = QLabel("N/A")
        port_layout.addWidget(self.port_label)
        port_layout.addWidget(QLabel("Baud Rate:"))
        self.baud_label = QLabel("N/A")
        port_layout.addWidget(self.baud_label)
        port_layout.addStretch()
        layout.addLayout(port_layout)
        
        # 수집 통계
        stats_layout = QHBoxLayout()
        stats_layout.addWidget(QLabel("Readings:"))
        self.readings_label = QLabel("0")
        stats_layout.addWidget(self.readings_label)
        stats_layout.addWidget(QLabel("Success Rate:"))
        self.success_rate_label = QLabel("0%")
        stats_layout.addWidget(self.success_rate_label)
        stats_layout.addWidget(QLabel("Elapsed Time:"))
        self.elapsed_time_label = QLabel("0s")
        stats_layout.addWidget(self.elapsed_time_label)
        stats_layout.addStretch()
        layout.addLayout(stats_layout)
        
        # 에러 추적
        self.error_count = 0
        self.last_error_time = 0
        
        self.setLayout(layout)
    
    def update_connection_status(self, connected: bool, port: str, baudrate: int):
        """연결 상태 업데이트"""
        if connected:
            self.connection_label.setText("Connected")
            self.connection_label.setStyleSheet("color: green; font-weight: bold;")
            self.port_label.setText(port)
            self.baud_label.setText(str(baudrate))
        else:
            self.connection_label.setText("Disconnected")
            self.connection_label.setStyleSheet("color: red; font-weight: bold;")
            self.port_label.setText("N/A")
            self.baud_label.setText("N/A")
    
    def update_statistics(self, stats: dict):
        """수집 통계 업데이트"""
        self.readings_label.setText(str(stats['total_readings']))
        success_rate = stats['success_rate']
        self.success_rate_label.setText(f"{success_rate:.1f}%")
        
        # Success rate 기반 상태 업데이트
        if success_rate >= 95:
            if self.error_count > 0:
                self.error_count = 0
                self.error_label.setText("✓ Connected - Normal")
                self.error_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        
        elapsed = int(stats['elapsed_time'])
        minutes = elapsed // 60
        seconds = elapsed % 60
        self.elapsed_time_label.setText(f"{minutes}m {seconds}s")
    
    def show_error(self, error_msg: str):
        """에러 메시지 표시"""
        self.error_count += 1
        current_time = time.time()
        
        # 에러 메시지 처리
        if "CRC" in error_msg or "crc" in error_msg:
            self.error_label.setText(f"⚠ CRC Error (Count: {self.error_count})")
            self.error_label.setStyleSheet("color: #FF9800; font-weight: bold;")
        elif "Failed to read" in error_msg:
            self.error_label.setText(f"⚠ Read Failure (Count: {self.error_count})")
            self.error_label.setStyleSheet("color: #FF9800; font-weight: bold;")
        elif "not connected" in error_msg.lower() or "timeout" in error_msg.lower():
            self.error_label.setText(f"❌ Connection Error")
            self.error_label.setStyleSheet("color: #F44336; font-weight: bold;")
        else:
            self.error_label.setText(f"⚠ Error: {error_msg[:50]}...")
            self.error_label.setStyleSheet("color: #FF9800; font-weight: bold;")
        
        self.last_error_time = current_time
    
    def update_connection_status(self, is_connected: bool, port: str = "N/A", baud: int = 0):
        """연결 상태 업데이트"""
        if is_connected:
            self.connection_label.setText("✓ Connected")
            self.connection_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.port_label.setText(port)
            self.baud_label.setText(str(baud))
            self.error_label.setText("✓ Connected - Normal")
            self.error_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.error_count = 0
        else:
            self.connection_label.setText("✗ Disconnected")
            self.connection_label.setStyleSheet("color: red; font-weight: bold;")
            self.port_label.setText("N/A")
            self.baud_label.setText("N/A")
            self.error_label.setText("Disconnected")
            self.error_label.setStyleSheet("color: red; font-weight: bold;")


class VisualizationWindow(QMainWindow):
    """메인 시각화 윈도우"""
    
    def __init__(self, parent=None):
        """윈도우 초기화"""
        super().__init__(parent)
        
        self.setWindowTitle("WTVB01-485 Vibration Sensor - Real-time Monitoring")
        self.setGeometry(100, 100, 1600, 900)
        
        # 중앙 위젯
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 주 레이아웃
        main_layout = QVBoxLayout()
        
        # 상단: 연결 컨트롤
        control_layout = QHBoxLayout()
        
        control_layout.addWidget(QLabel("COM Port:"))
        self.port_combo = QComboBox()
        self.port_combo.addItems(get_available_ports())
        control_layout.addWidget(self.port_combo)
        
        control_layout.addWidget(QLabel("Baud Rate:"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(['4800', '9600', '19200', '38400', '57600', '115200', '230400'])
        self.baud_combo.setCurrentText('9600')
        control_layout.addWidget(self.baud_combo)
        
        control_layout.addWidget(QLabel("Slave ID (Hex):"))
        self.slave_id_spin = QSpinBox()
        self.slave_id_spin.setMinimum(0x01)
        self.slave_id_spin.setMaximum(0x7F)
        self.slave_id_spin.setValue(0x50)
        self.slave_id_spin.setDisplayIntegerBase(16)
        control_layout.addWidget(self.slave_id_spin)
        
        self.connect_button = QPushButton("Connect")
        control_layout.addWidget(self.connect_button)
        
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False)
        control_layout.addWidget(self.disconnect_button)
        
        self.refresh_ports_button = QPushButton("Refresh Ports")
        control_layout.addWidget(self.refresh_ports_button)
        
        control_layout.addStretch()
        
        main_layout.addLayout(control_layout)
        
        # 상태 패널
        self.status_panel = StatusPanel()
        main_layout.addWidget(self.status_panel)
        
        # 탭 위젯 - 각 측정값별 그래프
        self.tab_widget = QTabWidget()
        
        # 진동 속도 탭
        self.velocity_graphs = TriAxisGraphWidget("Vibration Velocity (mm/s)")
        self.tab_widget.addTab(self.velocity_graphs, "Velocity")
        
        # 진동 변위 탭
        self.displacement_graphs = TriAxisGraphWidget("Vibration Displacement (um)")
        self.tab_widget.addTab(self.displacement_graphs, "Displacement")
        
        # 진동 주파수 탭
        self.frequency_graphs = TriAxisGraphWidget("Vibration Frequency (Hz)")
        self.tab_widget.addTab(self.frequency_graphs, "Frequency")
        
        # 가속도 탭
        self.acceleration_graphs = TriAxisGraphWidget("Acceleration (g)")
        self.tab_widget.addTab(self.acceleration_graphs, "Acceleration")
        
        # 온도 탭
        self.temperature_graph = GraphWidget("Temperature (°C)", "Temp")
        self.tab_widget.addTab(self.temperature_graph, "Temperature")
        
        # 분석 및 통계 탭
        self.analytics_widget = AnalyticsWidget()
        self.tab_widget.addTab(self.analytics_widget, "Analytics")
        
        # 이상 진동 감지 탭
        self.anomaly_widget = AnomalyDetectionWidget()
        self.tab_widget.addTab(self.anomaly_widget, "Anomaly Detection")
        
        # 실시간 모니터링 탭
        self.monitoring_widget = RealtimeMonitoringWidget()
        self.tab_widget.addTab(self.monitoring_widget, "Real-time Monitoring")
        
        # 센서 설정 탭
        self.config_widget = SensorConfigWidget()
        self.tab_widget.addTab(self.config_widget, "Sensor Configuration")
        
        # 시리얼 모니터 탭
        self.serial_monitor_widget = SerialMonitorWidget()
        self.tab_widget.addTab(self.serial_monitor_widget, "Serial Monitor")
        
        main_layout.addWidget(self.tab_widget)
        
        # 상태바
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")
        
        central_widget.setLayout(main_layout)
        
        # 센서 및 수집기 (초기화됨)
        self.sensor: Optional[WTVBSensor] = None
        self.collector: Optional[DataCollector] = None
        self.analyzer: Optional[MultiAxisAnalyzer] = None
        self.baseline_calculator: Optional[BaselineCalculator] = None
        self.anomaly_detector: Optional[AnomalyDetector] = None
        
        # Baseline 수집용 변수
        self.baseline_data_buffer = None
        self.baseline_collection_timer = None
        
        # 타이머 (주기적 업데이트)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._on_update_timer)
        self.update_timer.start(100)  # 100ms마다 업데이트
        
        # 신호 연결
        self.connect_button.clicked.connect(self._on_connect_clicked)
        self.disconnect_button.clicked.connect(self._on_disconnect_clicked)
        self.refresh_ports_button.clicked.connect(self._on_refresh_ports_clicked)
        
        # Anomaly Detection 탭 버튼 연결
        self.anomaly_widget.start_baseline_button.clicked.connect(self._on_start_baseline_collection)
        self.anomaly_widget.stop_baseline_button.clicked.connect(self._on_stop_baseline_collection)
        # Calculate Thresholds 버튼 찾아서 연결 (AnomalyDetectionWidget 내부에서 생성)
        # 대신 custom 메서드를 anomaly_widget에 연결
    
    def _on_connect_clicked(self):
        """연결 버튼 클릭"""
        port = self.port_combo.currentText()
        baudrate = int(self.baud_combo.currentText())
        slave_id = self.slave_id_spin.value()
        
        if not port:
            self.statusBar.showMessage("Please select a COM port")
            return
        
        try:
            # 센서 생성 및 연결
            self.sensor = WTVBSensor(port=port, baudrate=baudrate, slave_id=slave_id)
            
            if not self.sensor.connect():
                self.statusBar.showMessage(f"Failed to connect to {port}")
                return
            
            # 데이터 수집기 생성
            self.collector = DataCollector(self.sensor, buffer_size=1000, collection_interval=0.05)
            self.analyzer = MultiAxisAnalyzer(self.collector.buffer)
            
            # 콜백 연결
            self.collector.on_data_received = self._on_data_received
            self.collector.on_error = self._on_error
            self.collector.on_connection_lost = self._on_connection_lost
            
            # 수집 시작
            if self.collector.start():
                self.connect_button.setEnabled(False)
                self.disconnect_button.setEnabled(True)
                self.port_combo.setEnabled(False)
                self.baud_combo.setEnabled(False)
                self.slave_id_spin.setEnabled(False)
                
                # 센서 설정 위젯에 센서 객체 연결
                self.config_widget.set_sensor(self.sensor)
                self.config_widget._log_status("✓ Connected to sensor. Ready for configuration.")
                
                # 시리얼 모니터 위젯에 센서 객체 연결
                self.serial_monitor_widget.set_sensor(self.sensor)
                
                self.status_panel.update_connection_status(True, port, baudrate)
                self.statusBar.showMessage(f"Connected to {port} at {baudrate} bps")
            else:
                self.statusBar.showMessage("Failed to start data collection")
        
        except Exception as e:
            self.statusBar.showMessage(f"Connection error: {str(e)}")
    
    def _on_disconnect_clicked(self):
        """연결 해제 버튼 클릭"""
        if self.collector:
            self.collector.stop()
        
        # 시리얼 모니터 정지
        if self.serial_monitor_widget.monitoring:
            self.serial_monitor_widget._on_stop_monitor()
        
        if self.sensor:
            self.sensor.disconnect()
        
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.port_combo.setEnabled(True)
        self.baud_combo.setEnabled(True)
        self.slave_id_spin.setEnabled(True)
        
        self.status_panel.update_connection_status(False, "", 0)
        self.statusBar.showMessage("Disconnected")
        
        # 그래프 초기화
        self.velocity_graphs.clear_data()
        self.displacement_graphs.clear_data()
        self.frequency_graphs.clear_data()
        self.acceleration_graphs.clear_data()
        self.temperature_graph.clear_data()
        
        # Analytics 탭 초기화
        self.analytics_widget.update_statistics(None)
    
    def _on_refresh_ports_clicked(self):
        """포트 새로고침"""
        current_port = self.port_combo.currentText()
        self.port_combo.clear()
        self.port_combo.addItems(get_available_ports())
        
        # 이전 포트가 있으면 선택
        index = self.port_combo.findText(current_port)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)
    
    def _on_data_received(self, data):
        """데이터 수신 콜백"""
        # UI 업데이트는 메인 스레드에서만 가능하므로 신호 사용 고려
        # 여기서는 간단하게 처리
        pass
    
    def _on_error(self, error_msg: str):
        """에러 콜백"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error: {error_msg}")
        # Status Panel에 에러 메시지 표시
        self.status_panel.show_error(error_msg)
    
    def _on_connection_lost(self):
        """연결 끊김 콜백"""
        self._on_disconnect_clicked()
        self.statusBar.showMessage("Connection lost")
    
    def _on_update_timer(self):
        """주기적 업데이트 (타이머)"""
        if not self.collector or not self.sensor.is_connected:
            return
        
        # 최신 데이터 가져오기
        latest_data = self.collector.get_latest_data()
        if latest_data:
            # 그래프 업데이트
            self.velocity_graphs.update_data(latest_data.vx, latest_data.vy, latest_data.vz)
            self.displacement_graphs.update_data(latest_data.dx, latest_data.dy, latest_data.dz)
            self.frequency_graphs.update_data(latest_data.hx, latest_data.hy, latest_data.hz)
            self.acceleration_graphs.update_data(latest_data.ax, latest_data.ay, latest_data.az)
            self.temperature_graph.update_data(latest_data.temp)
        
        # 통계 업데이트
        stats = self.collector.get_statistics()
        self.status_panel.update_statistics(stats)
        
        # Analytics 탭용 상세 통계
        if self.analyzer:
            # 한 번만 호출하여 효율성 개선
            velocity_stats = self.analyzer.get_velocity_statistics()
            displacement_stats = self.analyzer.get_displacement_statistics()
            frequency_stats = self.analyzer.get_frequency_statistics()
            temperature_stats = self.analyzer.get_temperature_statistics()
            
            analytics_stats = {
                **stats,
                'vx': velocity_stats.get('vx', {'current': 0, 'max': 0, 'min': 0, 'avg': 0}),
                'vy': velocity_stats.get('vy', {'current': 0, 'max': 0, 'min': 0, 'avg': 0}),
                'vz': velocity_stats.get('vz', {'current': 0, 'max': 0, 'min': 0, 'avg': 0}),
                'dx': displacement_stats.get('dx', {'current': 0, 'max': 0, 'min': 0, 'avg': 0}),
                'dy': displacement_stats.get('dy', {'current': 0, 'max': 0, 'min': 0, 'avg': 0}),
                'dz': displacement_stats.get('dz', {'current': 0, 'max': 0, 'min': 0, 'avg': 0}),
                'hx': frequency_stats.get('hx', {'current': 0, 'max': 0, 'min': 0, 'avg': 0}),
                'hy': frequency_stats.get('hy', {'current': 0, 'max': 0, 'min': 0, 'avg': 0}),
                'hz': frequency_stats.get('hz', {'current': 0, 'max': 0, 'min': 0, 'avg': 0}),
                'temp': temperature_stats
            }
            self.analytics_widget.update_statistics(analytics_stats)
            
            # Baseline 수집 중이면 데이터 추가 및 실시간 시각화
            if self.anomaly_widget.baseline_collection_active and self.baseline_data_buffer:
                latest_data = self.collector.get_latest_data()
                if latest_data:
                    self.baseline_data_buffer.add(latest_data)
                    self.anomaly_widget.baseline_collected_count += 1
                    duration = self.anomaly_widget.baseline_duration_spin.value()
                    
                    # 실시간 그래프 업데이트
                    self.anomaly_widget.update_realtime_graphs(latest_data)
                    
                    # 실시간 통계 계산 및 표시
                    self._update_baseline_realtime_stats()
                    
                    # 진행도 업데이트
                    self.anomaly_widget.update_baseline_status(duration, self.anomaly_widget.baseline_collected_count)
            
            # 실시간 이상 감지 (Threshold가 계산된 후에만)
            if self.anomaly_detector and latest_data:
                # 최근 10개 데이터로 RMS 계산
                all_data = self.collector.buffer.get_all()
                window_data = all_data[-10:] if len(all_data) >= 10 else all_data
                
                # 이상 감지 수행
                anomaly_results = self.anomaly_detector.detect_anomaly(latest_data, window_data)
                
                # 모니터링 위젯 업데이트
                if anomaly_results:
                    # anomaly_results를 모니터링 형식으로 변환
                    monitoring_status = {}
                    for axis, result in anomaly_results.items():
                        state = 'CRITICAL' if result['status'] == 'anomaly' else \
                                'WARNING' if result['status'] == 'warning' else 'NORMAL'
                        threshold_for_state = result['threshold_critical'] if state == 'CRITICAL' else result['threshold_warning']
                        monitoring_status[axis] = {
                            'state': state,
                            'value': result['current_value'],
                            'threshold': threshold_for_state
                        }
                    
                    self.monitoring_widget.update_monitoring_status(latest_data, monitoring_status)
                    
                    # 새로운 이상 감지 이벤트 기록
                    self._check_and_log_anomalies(anomaly_results)
    
    def _on_start_baseline_collection(self):
        """Baseline 수집 시작"""
        if not self.collector or not self.collector.is_running:
            self.statusBar.showMessage("Sensor not connected. Please connect first.")
            return
        
        from data_collector import DataBuffer
        self.baseline_data_buffer = DataBuffer(max_size=10000)
        self.anomaly_widget._on_start_baseline()
        self.statusBar.showMessage("Baseline collection started...")
    
    def _on_stop_baseline_collection(self):
        """Baseline 수집 종료"""
        if not self.anomaly_widget.baseline_collection_active:
            return
        
        # Baseline 계산 (먼저 진행, _on_stop_baseline 호출 전)
        if self.baseline_data_buffer:
            data_list = self.baseline_data_buffer.get_all()
            
            baseline_calc = BaselineCalculator()
            calc_result = baseline_calc.calculate_baseline(self.baseline_data_buffer)
            
            if calc_result:
                save_result = baseline_calc.save_baseline()
                if save_result:
                    self.baseline_calculator = baseline_calc
                    self.anomaly_widget.baseline_calculator = baseline_calc
                    self.anomaly_widget.update_baseline_info(baseline_calc.get_baseline())
                    self.statusBar.showMessage(f"Baseline saved with {self.anomaly_widget.baseline_collected_count} data points")
                else:
                    self.statusBar.showMessage("Failed to save baseline")
            else:
                self.statusBar.showMessage(f"Insufficient data: {self.anomaly_widget.baseline_collected_count} points collected")
        
        # 마지막에 상태 변경 및 플래그 업데이트
        self.anomaly_widget._on_stop_baseline()
        self.anomaly_widget.baseline_collection_active = False
    
    def _update_baseline_realtime_stats(self):
        """Baseline 수집 중 실시간 통계 업데이트"""
        if not self.baseline_data_buffer:
            return
        
        import numpy as np
        
        data_list = self.baseline_data_buffer.get_all()
        if not data_list:
            return
        
        stats = {}
        axes = [
            ('vx', [d.vx for d in data_list]),
            ('vy', [d.vy for d in data_list]),
            ('vz', [d.vz for d in data_list]),
            ('dx', [d.dx for d in data_list]),
            ('dy', [d.dy for d in data_list]),
            ('dz', [d.dz for d in data_list]),
        ]
        
        for axis_name, values in axes:
            if values:
                values_array = np.array(values)
                stats[axis_name] = {
                    'count': len(values),
                    'mean': float(np.mean(values_array)),
                    'std': float(np.std(values_array)),
                    'min': float(np.min(values_array)),
                    'max': float(np.max(values_array)),
                    'rms': float(np.sqrt(np.mean(values_array ** 2)))
                }
        
        # 테이블 업데이트
        self.anomaly_widget.update_statistics_table(stats)
    
    def _check_and_log_anomalies(self, anomaly_results: dict):
        """이상 감지 결과 확인 및 로그 기록"""
        from datetime import datetime
        
        for axis, result in anomaly_results.items():
            status = result['status']
            
            # NORMAL -> WARNING, WARNING -> CRITICAL, CRITICAL -> WARNING 등의 상태 변화만 기록
            if status != 'normal':
                timestamp = datetime.now().strftime("%H:%M:%S")
                state_text = "🔴 CRITICAL" if status == 'anomaly' else "🟠 WARNING"
                threshold_for_state = result['threshold_critical'] if status == 'anomaly' else result['threshold_warning']
                self.monitoring_widget.add_anomaly_event(
                    timestamp, 
                    axis.upper(), 
                    state_text,
                    result['current_value'],
                    threshold_for_state
                )
    
    def setup_anomaly_detector(self):
        """이상 감지 기능 초기화 (Threshold 계산 후 호출)"""
        if self.baseline_calculator:
            # 튜닝 파라미터는 기본값 사용. 필요 시 config/GUI 연계 가능.
            self.anomaly_detector = AnomalyDetector(self.baseline_calculator)
            
            # Threshold 계산: AC는 RMS/피크 배수, DC(temp)는 mean+std
            std_multiplier = self.anomaly_widget.std_multiplier_spin.value()
            self.anomaly_detector.calculate_thresholds(std_multiplier)
            
            # 모니터링 위젯에 상태 업데이트
            self.monitoring_widget.update_threshold_status(True)
            print(f"DEBUG: AnomalyDetector initialized with thresholds: {self.anomaly_detector.thresholds}")
    
    def closeEvent(self, event):
        """윈도우 종료 이벤트"""
        if self.collector:
            self.collector.stop()
        if self.sensor:
            self.sensor.disconnect()
        event.accept()


def main():
    """메인 함수"""
    app = QApplication(sys.argv)
    
    # 애플리케이션 스타일 설정
    app.setStyle('Fusion')
    
    # 다크 테마 색상
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
    
    window = VisualizationWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
