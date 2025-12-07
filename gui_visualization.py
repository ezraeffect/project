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
    QComboBox, QSpinBox, QGridLayout, QGroupBox, QFrame
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread, QDateTime, QPointF
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtChart import QChart, QChartView, QLineSeries, QDateTimeAxis, QValueAxis

from data_collector import DataCollector, MultiAxisAnalyzer
from sensor_communication import WTVBSensor, get_available_ports


class ChartManager:
    """차트 생성 및 관리 클래스"""
    
    @staticmethod
    def create_chart(title: str, y_label: str = "Value") -> tuple:
        """
        차트 생성
        
        Returns:
            (chart, chart_view, series_list) 튜플
        """
        chart = QChart()
        chart.setTitle(title)
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.setBackgroundBrush(QColor("#f5f5f5"))
        chart.setTitleBrush(QColor("#333333"))
        
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
        
        # 제목
        title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
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
        self.success_rate_label.setText(f"{stats['success_rate']:.1f}%")
        
        elapsed = int(stats['elapsed_time'])
        minutes = elapsed // 60
        seconds = elapsed % 60
        self.elapsed_time_label.setText(f"{minutes}m {seconds}s")


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
        
        # 타이머 (주기적 업데이트)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._on_update_timer)
        self.update_timer.start(200)  # 200ms마다 업데이트
        
        # 신호 연결
        self.connect_button.clicked.connect(self._on_connect_clicked)
        self.disconnect_button.clicked.connect(self._on_disconnect_clicked)
        self.refresh_ports_button.clicked.connect(self._on_refresh_ports_clicked)
    
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
            self.collector = DataCollector(self.sensor, buffer_size=1000, collection_interval=0.1)
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
        print(f"Error: {error_msg}")
    
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
