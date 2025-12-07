# motor_vibration_analysis.py
"""
PyQt5 + Matplotlib 기반 모터 이상 진동 감지 시스템 (실시간 센서 모드)

기능:
- 실시간 센서 데이터 수집 (100Hz 샘플링, Modbus RTU)
- 실시간 신호 시각화 (3축 가속도, 진동속도, 진동변위, 온도)
- FFT 분석 및 주파수 스펙트럼 표시
- 3축 RMS/피크 계산 및 임계치 비교
- 베이스라인 학습 (자동 임계치 설정)
- 히스테리시스 기반 False Alarm 감소
- 임계치 설정 GUI (사용자 조정 가능)
- 경보 발생 시 GUI 시각적 표시
- 경보 이벤트 CSV 로깅

Dependencies:
  python -m pip install pyqt5 matplotlib pandas numpy pyserial
"""

import sys
import os
from datetime import datetime
from collections import deque
import threading
import time
import struct

import numpy as np
import pandas as pd
import serial
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as mpatches

# 한글 폰트 설정
try:
    # Windows 시스템 폰트 사용
    if sys.platform == 'win32':
        matplotlib.rcParams['font.sans-serif'] = ['Malgun Gothic', 'DejaVu Sans']
    else:
        matplotlib.rcParams['font.sans-serif'] = ['DejaVu Sans']
    matplotlib.rcParams['axes.unicode_minus'] = False
except Exception as e:
    print(f"폰트 설정 오류: {e}")

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTabWidget, QLabel, QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox,
                             QGroupBox, QGridLayout, QTextEdit, QFileDialog, QMessageBox, QComboBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QListWidget, QListWidgetItem)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QThread
from PyQt5.QtGui import QColor, QFont


class ModbusRTU:
    """Modbus RTU 통신"""
    
    @staticmethod
    def crc16_modbus(data: bytes) -> int:
        """CRC16 계산"""
        crc = 0xFFFF
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 0x0001:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return crc & 0xFFFF
    
    @staticmethod
    def build_read_request(addr: int, reg: int, count: int) -> bytes:
        """Modbus 읽기 요청 생성"""
        pkt = bytes([addr & 0xFF, 0x03, (reg >> 8) & 0xFF, reg & 0xFF, (count >> 8) & 0xFF, count & 0xFF])
        crc = ModbusRTU.crc16_modbus(pkt)
        return pkt + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
    
    @staticmethod
    def parse_registers_from_response(data: bytes, count: int):
        """응답 데이터 파싱"""
        if len(data) < 5 + 2 * count:
            raise RuntimeError("응답 데이터 부족")
        
        crc_recv = (data[-1] << 8) | data[-2]
        crc_calc = ModbusRTU.crc16_modbus(data[:-2])
        if crc_recv != crc_calc:
            raise RuntimeError(f"CRC 오류: {crc_recv:04X} != {crc_calc:04X}")
        
        regs = []
        for i in range(count):
            offset = 3 + i * 2
            val = (data[offset] << 8) | data[offset + 1]
            regs.append(val)
        return regs
    
    @staticmethod
    def read_registers(ser: serial.Serial, addr: int, reg: int, count: int, timeout: float = 1.0):
        """레지스터 읽기"""
        req = ModbusRTU.build_read_request(addr, reg, count)
        ser.reset_input_buffer()
        ser.write(req)
        ser.flush()
        
        expected = 5 + 2 * count
        start_time = time.time()
        data = b''
        
        while len(data) < expected:
            if time.time() - start_time > timeout:
                raise RuntimeError(f"타임아웃 ({len(data)}/{expected} bytes)")
            
            try:
                chunk = ser.read(expected - len(data))
                if chunk:
                    data += chunk
            except serial.SerialException:
                pass
            time.sleep(0.01)
        
        return ModbusRTU.parse_registers_from_response(data, count)
    
    @staticmethod
    def raw_to_float(high: int, low: int) -> float:
        """Raw 레지스터 값을 float으로 변환"""
        raw = ((high & 0xFFFF) << 16) | (low & 0xFFFF)
        return struct.unpack('>f', struct.pack('>I', raw))[0]


class DataProcessor:
    """신호 처리 및 분석"""
    
    def __init__(self):
        self.fs = 100.0  # 샘플링 주파수 100Hz (고정)
    
    def compute_fft(self, signal, window_size=512):
        """신호의 FFT 계산 - 확대된 윈도우 (512 샘플)"""
        if signal is None or len(signal) < 2:
            return None, None
        signal = np.array(signal, dtype=float)
        # NaN 제거
        valid = ~np.isnan(signal)
        if valid.sum() < 2:
            return None, None
        signal = signal[valid]
        
        # 윈도우 크기 설정 (최대 512)
        N = min(len(signal), window_size)
        if N < 2:
            return None, None
        
        # 마지막 N개 샘플 사용 (최신 데이터)
        signal = signal[-N:] if len(signal) > N else signal
        
        # Hann 윈도우로 스펙트럼 누설 감소
        win = np.hanning(N)
        signal_win = signal * win
        
        # FFT 계산 (성능 최적화: 2의 거듭제곱으로 패딩)
        N_fft = 2 ** int(np.ceil(np.log2(N)))
        Y = np.fft.rfft(signal_win, n=N_fft)
        
        freqs = np.fft.rfftfreq(N_fft, 1.0 / self.fs) if self.fs else np.fft.rfftfreq(N_fft)
        mag = np.abs(Y) / (np.sum(win) / 2.0)
        
        return freqs, mag
    
    def compute_rms(self, signal):
        """RMS 계산"""
        if signal is None or len(signal) == 0:
            return np.nan
        signal = np.array(signal, dtype=float)
        valid = ~np.isnan(signal)
        if valid.sum() == 0:
            return np.nan
        return np.sqrt(np.mean(signal[valid] ** 2))
    
    def compute_peak(self, signal):
        """피크 계산"""
        if signal is None or len(signal) == 0:
            return np.nan
        signal = np.array(signal, dtype=float)
        valid = ~np.isnan(signal)
        if valid.sum() == 0:
            return np.nan
        return np.max(np.abs(signal[valid]))
    
    def compute_baseline(self, data_list):
        """베이스라인 학습 (정상 상태 신호 특성)"""
        if not data_list or len(data_list) < 100:
            return None
        
        data_array = np.array(data_list, dtype=float)
        valid = ~np.isnan(data_array)
        if valid.sum() < 100:
            return None
        
        data_valid = data_array[valid]
        
        baseline = {
            'mean': np.mean(data_valid),
            'std': np.std(data_valid),
            'max': np.max(data_valid),
            'min': np.min(data_valid),
            'rms': np.sqrt(np.mean(data_valid ** 2)),
            'crest_factor': np.max(np.abs(data_valid)) / np.sqrt(np.mean(data_valid ** 2)) if np.sqrt(np.mean(data_valid ** 2)) > 0 else 0
        }
        return baseline
    
    def compute_percentile_based_threshold(self, baseline):
        """베이스라인 기반 적응형 임계치 (95 percentile)"""
        if not baseline:
            return None
        
        # 정상 범위: mean ± 3σ
        threshold = baseline['mean'] + 3 * baseline['std']
        return max(threshold, baseline['max'] * 1.5)


class SensorReader(threading.Thread):
    """센서 읽기 스레드 - 고속 샘플링 (100Hz)"""
    
    def __init__(self, port, baud, addr, interval, data_queue, stop_event):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.addr = addr
        self.interval = interval  # 기본 0.01s = 100Hz
        self.data_queue = data_queue
        self.stop_event = stop_event
        self.ser = None
        self.error_count = 0
        self.success_count = 0
    
    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1.0)
            self.ser.reset_input_buffer()
            
            while not self.stop_event.is_set():
                try:
                    t0 = time.time()
                    
                    # 가속도 읽기
                    acc_regs = ModbusRTU.read_registers(self.ser, self.addr, 0x0034, 6, timeout=0.5)
                    acc_x = ModbusRTU.raw_to_float(acc_regs[0], acc_regs[1])
                    acc_y = ModbusRTU.raw_to_float(acc_regs[2], acc_regs[3])
                    acc_z = ModbusRTU.raw_to_float(acc_regs[4], acc_regs[5])
                    
                    # 온도 읽기
                    temp_regs = ModbusRTU.read_registers(self.ser, self.addr, 0x0040, 1, timeout=0.5)
                    temp = temp_regs[0] / 100.0
                    
                    # 진동속도 읽기
                    vel_regs = ModbusRTU.read_registers(self.ser, self.addr, 0x003A, 6, timeout=0.5)
                    vel_x = ModbusRTU.raw_to_float(vel_regs[0], vel_regs[1])
                    vel_y = ModbusRTU.raw_to_float(vel_regs[2], vel_regs[3])
                    vel_z = ModbusRTU.raw_to_float(vel_regs[4], vel_regs[5])
                    
                    # 진동변위 읽기
                    disp_regs = ModbusRTU.read_registers(self.ser, self.addr, 0x0041, 6, timeout=0.5)
                    disp_x = ModbusRTU.raw_to_float(disp_regs[0], disp_regs[1])
                    disp_y = ModbusRTU.raw_to_float(disp_regs[2], disp_regs[3])
                    disp_z = ModbusRTU.raw_to_float(disp_regs[4], disp_regs[5])
                    
                    # 주파수 읽기
                    freq_regs = ModbusRTU.read_registers(self.ser, self.addr, 0x0044, 6, timeout=0.5)
                    freq_x = ModbusRTU.raw_to_float(freq_regs[0], freq_regs[1])
                    freq_y = ModbusRTU.raw_to_float(freq_regs[2], freq_regs[3])
                    freq_z = ModbusRTU.raw_to_float(freq_regs[4], freq_regs[5])
                    
                    data = {
                        'timestamp': datetime.now(),
                        'acc_x': acc_x, 'acc_y': acc_y, 'acc_z': acc_z,
                        'vel_x': vel_x, 'vel_y': vel_y, 'vel_z': vel_z,
                        'disp_x': disp_x, 'disp_y': disp_y, 'disp_z': disp_z,
                        'freq_x': freq_x, 'freq_y': freq_y, 'freq_z': freq_z,
                        'temp': temp
                    }
                    
                    self.data_queue.append(data)
                    if len(self.data_queue) > 500:
                        self.data_queue.popleft()
                    
                    dt = time.time() - t0
                    to_sleep = self.interval - dt
                    if to_sleep > 0:
                        time.sleep(to_sleep)
                
                except Exception as e:
                    self.error_count += 1
                    if self.error_count % 10 == 0:  # 10번 오류 시마다 로깅
                        print(f"센서 읽기 오류 ({self.error_count}회): {e}")
                    
                    # 적응형 대기: 오류 많을수록 더 오래 대기
                    backoff = min(0.1, 0.01 * (self.error_count / 10))
                    time.sleep(backoff)
        
        finally:
            if self.ser:
                self.ser.close()


class MotorVibrationGUI(QMainWindow):
    """메인 GUI"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("모터 이상 진동 감지 시스템 - 실시간 (100Hz)")
        self.setGeometry(100, 100, 1400, 900)
        
        self.processor = DataProcessor()
        
        # 실시간 센서 데이터 (5120개 = 51.2초 @ 100Hz)
        self.data_queue = deque(maxlen=5120)
        self.data_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.sensor_reader = None
        
        # 베이스라인 학습
        self.baseline = None
        self.baseline_data = []
        self.is_learning = False
        self.learning_count = 0
        
        # False Alarm 감소
        self.alarm_hysteresis = {}  # {alarm_type: (is_alarmed, consecutive_count)}
        self.alarm_threshold_count = 3  # 연속 3회 초과 시만 경보
        
        # 임계치 저장소
        self.thresholds = {
            'acc_rms_max': 2.0,
            'vel_peak_max': 100.0,
            'disp_peak_max': 500.0,
            'temp_max': 60.0,
        }
        
        # 이벤트 로그
        self.event_log = []
        
        self.init_ui()
        
        # 타이머 (30fps 갱신)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_display)
        self.timer.setInterval(33)  # ~30fps
        
    def init_ui(self):
        """UI 초기화"""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout()
        
        # 탭 위젯
        tabs = QTabWidget()
        
        # 탭1: 신호 표시
        tab1 = self.create_signal_tab()
        tabs.addTab(tab1, "신호 표시")
        
        # 탭2: FFT 분석
        tab2 = self.create_fft_tab()
        tabs.addTab(tab2, "FFT 분석")
        
        # 탭3: 임계치 설정
        tab3 = self.create_threshold_tab()
        tabs.addTab(tab3, "임계치 설정")
        
        # 탭4: 이벤트 로그
        tab4 = self.create_log_tab()
        tabs.addTab(tab4, "이벤트 로그")
        
        layout.addWidget(tabs)
        
        # 제어 패널
        control = self.create_control_panel()
        layout.addWidget(control)
        
        central.setLayout(layout)
    
    def create_signal_tab(self):
        """신호 표시 탭"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Matplotlib Figure
        self.fig_signal = Figure(figsize=(12, 5), dpi=100)
        self.canvas_signal = FigureCanvas(self.fig_signal)
        
        # 서브플롯
        self.ax_acc = self.fig_signal.add_subplot(2, 2, 1)
        self.ax_vel = self.fig_signal.add_subplot(2, 2, 2)
        self.ax_disp = self.fig_signal.add_subplot(2, 2, 3)
        self.ax_temp = self.fig_signal.add_subplot(2, 2, 4)
        
        self.ax_acc.set_title("3축 가속도 (g)")
        self.ax_vel.set_title("3축 진동속도 (mm/s)")
        self.ax_disp.set_title("3축 진동변위 (μm)")
        self.ax_temp.set_title("온도 (°C)")
        
        for ax in [self.ax_acc, self.ax_vel, self.ax_disp, self.ax_temp]:
            ax.grid(True)
            ax.legend()
        
        layout.addWidget(self.canvas_signal)
        
        # 상태 패널
        status_group = QGroupBox("현재 상태")
        status_layout = QGridLayout()
        
        self.label_status = QLabel("대기 중...")
        self.label_status.setFont(QFont("Arial", 11, QFont.Bold))
        self.label_status.setStyleSheet("color: green;")
        
        status_layout.addWidget(QLabel("상태:"), 0, 0)
        status_layout.addWidget(self.label_status, 0, 1)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        widget.setLayout(layout)
        return widget
    
    def create_fft_tab(self):
        """FFT 분석 탭"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Matplotlib Figure
        self.fig_fft = Figure(figsize=(12, 5), dpi=100)
        self.canvas_fft = FigureCanvas(self.fig_fft)
        
        # 서브플롯
        self.ax_fft_acc = self.fig_fft.add_subplot(1, 3, 1)
        self.ax_fft_vel = self.fig_fft.add_subplot(1, 3, 2)
        self.ax_fft_disp = self.fig_fft.add_subplot(1, 3, 3)
        
        self.ax_fft_acc.set_title("가속도 FFT")
        self.ax_fft_vel.set_title("진동속도 FFT")
        self.ax_fft_disp.set_title("진동변위 FFT")
        
        for ax in [self.ax_fft_acc, self.ax_fft_vel, self.ax_fft_disp]:
            ax.grid(True)
            ax.set_xlabel("Frequency (Hz)")
            ax.set_ylabel("Amplitude")
        
        layout.addWidget(self.canvas_fft)
        widget.setLayout(layout)
        return widget
    
    def create_threshold_tab(self):
        """임계치 설정 탭 - 베이스라인 학습 포함"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 베이스라인 학습 그룹
        baseline_group = QGroupBox("베이스라인 학습 (정상 상태 신호 특성)")
        baseline_layout = QGridLayout()
        
        self.btn_start_learning = QPushButton("학습 시작 (30초)")
        self.btn_start_learning.clicked.connect(self.start_baseline_learning)
        self.label_learning_status = QLabel("학습 대기 중")
        self.label_learning_status.setStyleSheet("color: blue;")
        
        baseline_layout.addWidget(QLabel("상태:"), 0, 0)
        baseline_layout.addWidget(self.label_learning_status, 0, 1)
        baseline_layout.addWidget(self.btn_start_learning, 1, 0, 1, 2)
        
        baseline_group.setLayout(baseline_layout)
        layout.addWidget(baseline_group)
        
        # 임계치 설정 그룹
        group = QGroupBox("수동 임계치 설정")
        grid = QGridLayout()
        
        self.threshold_inputs = {}
        
        items = [
            ('acc_rms_max', '가속도 RMS 최대 (g)', 2.0),
            ('vel_peak_max', '진동속도 피크 최대 (mm/s)', 100.0),
            ('disp_peak_max', '진동변위 피크 최대 (μm)', 500.0),
            ('temp_max', '온도 최대 (°C)', 60.0),
        ]
        
        for i, (key, label, default) in enumerate(items):
            qlabel = QLabel(label)
            qspin = QDoubleSpinBox()
            qspin.setValue(default)
            qspin.setMaximum(9999.0)
            qspin.setMinimum(0.0)
            qspin.setSingleStep(0.1)
            self.threshold_inputs[key] = qspin
            grid.addWidget(qlabel, i, 0)
            grid.addWidget(qspin, i, 1)
        
        btn_apply = QPushButton("적용")
        btn_apply.clicked.connect(self.apply_thresholds)
        grid.addWidget(btn_apply, len(items), 0, 1, 2)
        
        group.setLayout(grid)
        layout.addWidget(group)
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_log_tab(self):
        """이벤트 로그 탭"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 테이블
        self.table_log = QTableWidget()
        self.table_log.setColumnCount(4)
        self.table_log.setHorizontalHeaderLabels(["시간", "이벤트 타입", "내용", "상태"])
        self.table_log.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        layout.addWidget(QLabel("이벤트 로그:"))
        layout.addWidget(self.table_log)
        
        # 버튼
        btn_layout = QHBoxLayout()
        btn_clear = QPushButton("로그 초기화")
        btn_clear.clicked.connect(self.clear_log)
        btn_save = QPushButton("로그 저장 (CSV)")
        btn_save.clicked.connect(self.save_log_csv)
        
        btn_layout.addWidget(btn_clear)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        
        widget.setLayout(layout)
        return widget
    
    def create_control_panel(self):
        """제어 패널"""
        group = QGroupBox("실시간 센서 제어")
        layout = QHBoxLayout()
        
        # 센서 연결 설정
        layout.addWidget(QLabel("포트:"))
        self.combo_port = QComboBox()
        self.update_ports()
        layout.addWidget(self.combo_port)
        
        layout.addWidget(QLabel("보드율:"))
        self.spin_baud = QSpinBox()
        self.spin_baud.setValue(9600)
        self.spin_baud.setMaximum(230400)
        layout.addWidget(self.spin_baud)
        
        layout.addWidget(QLabel("ID:"))
        self.spin_id = QSpinBox()
        self.spin_id.setValue(0x50)
        self.spin_id.setMaximum(0xFF)
        self.spin_id.setDisplayIntegerBase(16)
        layout.addWidget(self.spin_id)
        
        # 센서 시작/정지
        self.btn_sensor = QPushButton("센서 시작")
        self.btn_sensor.clicked.connect(self.toggle_sensor)
        layout.addWidget(self.btn_sensor)
        
        # 상태 및 통계
        self.label_info = QLabel("준비 완료 | 100Hz 샘플링 | FFT 윈도우: 512")
        self.label_info.setStyleSheet("color: green; font-weight: bold;")
        layout.addWidget(self.label_info)
        
        layout.addStretch()
        group.setLayout(layout)
        return group
    
    def update_ports(self):
        """포트 목록 업데이트"""
        self.combo_port.clear()
        try:
            import serial.tools.list_ports
            ports = [port.device for port in serial.tools.list_ports.comports()]
            if ports:
                self.combo_port.addItems(ports)
            else:
                self.combo_port.addItem("포트 없음")
        except:
            self.combo_port.addItem("COM3")
            self.combo_port.addItem("COM4")
    
    def toggle_sensor(self):
        """센서 시작/정지"""
        if self.sensor_reader is None or not self.sensor_reader.is_alive():
            # 센서 시작
            try:
                port = self.combo_port.currentText()
                if port == "포트 없음":
                    QMessageBox.warning(self, "경고", "사용 가능한 포트가 없습니다.")
                    return
                
                baud = self.spin_baud.value()
                addr = self.spin_id.value()
                
                self.stop_event.clear()
                self.data_queue.clear()
                # 100Hz 샘플링 = 0.01초 간격
                self.sensor_reader = SensorReader(port, baud, addr, 0.01, self.data_queue, self.stop_event)
                self.sensor_reader.start()
                
                self.btn_sensor.setText("센서 정지")
                self.label_info.setText(f"센서 연결: {port} ({baud} baud)")
                self.label_info.setStyleSheet("color: blue; font-weight: bold;")
                
                self.timer.start()
            except Exception as e:
                QMessageBox.critical(self, "오류", f"센서 연결 실패: {str(e)}")
        else:
            # 센서 정지
            self.stop_sensor()
    
    def stop_sensor(self):
        """센서 정지"""
        self.stop_event.set()
        if self.sensor_reader:
            self.sensor_reader.join(timeout=2.0)
        self.sensor_reader = None
        self.btn_sensor.setText("센서 시작")
        self.label_info.setText("센서 정지됨")
        self.label_info.setStyleSheet("color: orange;")
        self.timer.stop()
    
    def update_display(self):
        """디스플레이 업데이트"""
        # 베이스라인 학습 진행
        if self.is_learning:
            self.update_baseline_learning()
        
        # 실시간 센서 모드
        if not self.data_queue:
            return
        
        with self.data_lock:
            recent_data = list(self.data_queue)
            
            if not recent_data:
                return
            
            # 최근 10개 데이터
            window_data = recent_data[-10:] if len(recent_data) >= 10 else recent_data
            
            # 최신 데이터
            latest = recent_data[-1]
            acc_x = latest['acc_x']
            acc_y = latest['acc_y']
            acc_z = latest['acc_z']
            vel_x = latest['vel_x']
            vel_y = latest['vel_y']
            vel_z = latest['vel_z']
            disp_x = latest['disp_x']
            disp_y = latest['disp_y']
            disp_z = latest['disp_z']
            temp = latest['temp']
            
            # 신호 플롯 업데이트
            self.update_signal_plot_sensor(window_data, acc_x, acc_y, acc_z, vel_x, vel_y, vel_z, disp_x, disp_y, disp_z, temp)
            
            # FFT 플롯 업데이트
            self.update_fft_plot_sensor(window_data)
            
            # 임계치 확인 및 경보
            self.check_thresholds_sensor(window_data, temp)
            
            # 상태 라벨 업데이트
            time_str = latest['timestamp'].strftime("%H:%M:%S.%f")[:-3]
            info = f"{time_str} | Acc:({acc_x:.3f}, {acc_y:.3f}, {acc_z:.3f}g) | Temp:{temp:.1f}°C | 버퍼:{len(recent_data)}"
            self.label_info.setText(info)
    
    def update_signal_plot_sensor(self, window_data, acc_x, acc_y, acc_z, vel_x, vel_y, vel_z, disp_x, disp_y, disp_z, temp):
        """실시간 센서용 신호 플롯 업데이트"""
        self.fig_signal.clear()
        self.ax_acc = self.fig_signal.add_subplot(2, 2, 1)
        self.ax_vel = self.fig_signal.add_subplot(2, 2, 2)
        self.ax_disp = self.fig_signal.add_subplot(2, 2, 3)
        self.ax_temp = self.fig_signal.add_subplot(2, 2, 4)
        
        if window_data:
            acc_xs = np.array([d['acc_x'] for d in window_data])
            acc_ys = np.array([d['acc_y'] for d in window_data])
            acc_zs = np.array([d['acc_z'] for d in window_data])
            
            vel_xs = np.array([d['vel_x'] for d in window_data])
            vel_ys = np.array([d['vel_y'] for d in window_data])
            vel_zs = np.array([d['vel_z'] for d in window_data])
            
            disp_xs = np.array([d['disp_x'] for d in window_data])
            disp_ys = np.array([d['disp_y'] for d in window_data])
            disp_zs = np.array([d['disp_z'] for d in window_data])
            
            temps = np.array([d['temp'] for d in window_data])
            
            x = np.arange(len(acc_xs))
            
            self.ax_acc.plot(x, acc_xs, 'b-', label='X', marker='o')
            self.ax_acc.plot(x, acc_ys, 'g-', label='Y', marker='s')
            self.ax_acc.plot(x, acc_zs, 'r-', label='Z', marker='^')
            self.ax_acc.set_title("3축 가속도 (g)")
            self.ax_acc.legend()
            self.ax_acc.grid(True)
            
            self.ax_vel.plot(x, vel_xs, 'b-', label='X', marker='o')
            self.ax_vel.plot(x, vel_ys, 'g-', label='Y', marker='s')
            self.ax_vel.plot(x, vel_zs, 'r-', label='Z', marker='^')
            self.ax_vel.set_title("3축 진동속도 (mm/s)")
            self.ax_vel.legend()
            self.ax_vel.grid(True)
            
            self.ax_disp.plot(x, disp_xs, 'b-', label='X', marker='o')
            self.ax_disp.plot(x, disp_ys, 'g-', label='Y', marker='s')
            self.ax_disp.plot(x, disp_zs, 'r-', label='Z', marker='^')
            self.ax_disp.set_title("3축 진동변위 (μm)")
            self.ax_disp.legend()
            self.ax_disp.grid(True)
            
            self.ax_temp.plot(x, temps, 'r-', label='Temp', marker='o')
            self.ax_temp.set_title("온도 (°C)")
            self.ax_temp.legend()
            self.ax_temp.grid(True)
        
        self.canvas_signal.draw()
    
    def start_baseline_learning(self):
        """베이스라인 학습 시작 (30초)"""
        if not self.data_queue:
            QMessageBox.warning(self, "경고", "센서 데이터가 없습니다. 센서를 먼저 시작하세요.")
            return
        
        self.is_learning = True
        self.learning_count = 0
        self.baseline_data = []
        self.btn_start_learning.setEnabled(False)
        self.label_learning_status.setText("학습 중... (0/30초)")
        self.label_learning_status.setStyleSheet("color: orange; font-weight: bold;")
    
    def update_baseline_learning(self):
        """베이스라인 학습 진행"""
        if not self.is_learning or not self.data_queue:
            return
        
        self.learning_count += 1
        self.label_learning_status.setText(f"학습 중... ({self.learning_count}/30초)")
        
        # 현재 데이터 수집
        with self.data_lock:
            recent_data = list(self.data_queue)
        
        if recent_data:
            latest = recent_data[-1]
            self.baseline_data.append({
                'acc_x': latest['acc_x'],
                'vel_x': latest['vel_x'],
                'disp_x': latest['disp_x'],
            })
        
        # 30초 완료
        if self.learning_count >= 30:
            self.is_learning = False
            self.finalize_baseline_learning()
    
    def finalize_baseline_learning(self):
        """베이스라인 학습 완료"""
        if len(self.baseline_data) < 100:
            QMessageBox.warning(self, "오류", "충분한 데이터가 수집되지 않았습니다.")
            self.btn_start_learning.setEnabled(True)
            self.label_learning_status.setText("학습 실패")
            self.label_learning_status.setStyleSheet("color: red;")
            return
        
        # 베이스라인 계산
        acc_list = [d['acc_x'] for d in self.baseline_data]
        vel_list = [d['vel_x'] for d in self.baseline_data]
        disp_list = [d['disp_x'] for d in self.baseline_data]
        
        baseline_acc = self.processor.compute_baseline(acc_list)
        baseline_vel = self.processor.compute_baseline(vel_list)
        baseline_disp = self.processor.compute_baseline(disp_list)
        
        if not (baseline_acc and baseline_vel and baseline_disp):
            QMessageBox.warning(self, "오류", "베이스라인 계산 실패")
            self.btn_start_learning.setEnabled(True)
            return
        
        # 베이스라인 기반 임계치 설정
        acc_threshold = self.processor.compute_percentile_based_threshold(baseline_acc)
        vel_threshold = self.processor.compute_percentile_based_threshold(baseline_vel)
        disp_threshold = self.processor.compute_percentile_based_threshold(baseline_disp)
        
        # UI 업데이트
        self.threshold_inputs['acc_rms_max'].setValue(acc_threshold)
        self.threshold_inputs['vel_peak_max'].setValue(vel_threshold)
        self.threshold_inputs['disp_peak_max'].setValue(disp_threshold)
        
        self.apply_thresholds()
        
        msg = (f"베이스라인 학습 완료!\n\n"
               f"추천 임계치:\n"
               f"- 가속도 RMS: {acc_threshold:.2f}g\n"
               f"- 진동속도 피크: {vel_threshold:.1f}mm/s\n"
               f"- 진동변위 피크: {disp_threshold:.0f}μm\n\n"
               f"베이스라인 통계:\n"
               f"- 가속도: μ={baseline_acc['mean']:.3f}g, σ={baseline_acc['std']:.3f}g\n"
               f"- 진동속도: μ={baseline_vel['mean']:.1f}mm/s, σ={baseline_vel['std']:.1f}mm/s\n"
               f"- 진동변위: μ={baseline_disp['mean']:.0f}μm, σ={baseline_disp['std']:.0f}μm")
        
        QMessageBox.information(self, "성공", msg)
        self.btn_start_learning.setEnabled(True)
        self.label_learning_status.setText(f"학습 완료 ({len(self.baseline_data)} 샘플)")
        self.label_learning_status.setStyleSheet("color: green; font-weight: bold;")
    
    def apply_thresholds(self):
        """임계치 적용"""
        for key, widget in self.threshold_inputs.items():
            self.thresholds[key] = widget.value()
        QMessageBox.information(self, "성공", "임계치가 적용되었습니다.")
    
    def add_log_event(self, event_type, content, status="정상"):
        """이벤트 로그 추가"""
        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.event_log.append({
            'time': now,
            'type': event_type,
            'content': content,
            'status': status
        })
        
        # 테이블에 추가
        row = self.table_log.rowCount()
        self.table_log.insertRow(row)
        self.table_log.setItem(row, 0, QTableWidgetItem(now))
        self.table_log.setItem(row, 1, QTableWidgetItem(event_type))
        self.table_log.setItem(row, 2, QTableWidgetItem(content))
        
        status_item = QTableWidgetItem(status)
        if status == "이상":
            status_item.setBackground(QColor(255, 200, 200))
        self.table_log.setItem(row, 3, status_item)
        
        # 맨 아래로 스크롤
        self.table_log.scrollToBottom()
    
    def update_fft_plot_sensor(self, window_data):
        """실시간 센서용 FFT 플롯 업데이트"""
        self.fig_fft.clear()
        self.ax_fft_acc = self.fig_fft.add_subplot(1, 3, 1)
        self.ax_fft_vel = self.fig_fft.add_subplot(1, 3, 2)
        self.ax_fft_disp = self.fig_fft.add_subplot(1, 3, 3)
        
        if window_data and len(window_data) > 2:
            acc_xs = np.array([d['acc_x'] for d in window_data])
            acc_ys = np.array([d['acc_y'] for d in window_data])
            acc_zs = np.array([d['acc_z'] for d in window_data])
            
            freqs_acc, mag_acc_x = self.processor.compute_fft(acc_xs)
            _, mag_acc_y = self.processor.compute_fft(acc_ys)
            _, mag_acc_z = self.processor.compute_fft(acc_zs)
            
            if freqs_acc is not None:
                self.ax_fft_acc.plot(freqs_acc, mag_acc_x, 'b-', label='X')
                self.ax_fft_acc.plot(freqs_acc, mag_acc_y, 'g-', label='Y')
                self.ax_fft_acc.plot(freqs_acc, mag_acc_z, 'r-', label='Z')
                self.ax_fft_acc.set_title("가속도 FFT")
                self.ax_fft_acc.set_xlabel("Frequency (Hz)")
                self.ax_fft_acc.set_ylabel("Amplitude")
                self.ax_fft_acc.set_xlim(0, 50)
                self.ax_fft_acc.legend()
                self.ax_fft_acc.grid(True)
            
            vel_xs = np.array([d['vel_x'] for d in window_data])
            vel_ys = np.array([d['vel_y'] for d in window_data])
            vel_zs = np.array([d['vel_z'] for d in window_data])
            
            freqs_vel, mag_vel_x = self.processor.compute_fft(vel_xs)
            _, mag_vel_y = self.processor.compute_fft(vel_ys)
            _, mag_vel_z = self.processor.compute_fft(vel_zs)
            
            if freqs_vel is not None:
                self.ax_fft_vel.plot(freqs_vel, mag_vel_x, 'b-', label='X')
                self.ax_fft_vel.plot(freqs_vel, mag_vel_y, 'g-', label='Y')
                self.ax_fft_vel.plot(freqs_vel, mag_vel_z, 'r-', label='Z')
                self.ax_fft_vel.set_title("진동속도 FFT")
                self.ax_fft_vel.set_xlabel("Frequency (Hz)")
                self.ax_fft_vel.set_ylabel("Amplitude")
                self.ax_fft_vel.set_xlim(0, 50)
                self.ax_fft_vel.legend()
                self.ax_fft_vel.grid(True)
            
            disp_xs = np.array([d['disp_x'] for d in window_data])
            disp_ys = np.array([d['disp_y'] for d in window_data])
            disp_zs = np.array([d['disp_z'] for d in window_data])
            
            freqs_disp, mag_disp_x = self.processor.compute_fft(disp_xs)
            _, mag_disp_y = self.processor.compute_fft(disp_ys)
            _, mag_disp_z = self.processor.compute_fft(disp_zs)
            
            if freqs_disp is not None:
                self.ax_fft_disp.plot(freqs_disp, mag_disp_x, 'b-', label='X')
                self.ax_fft_disp.plot(freqs_disp, mag_disp_y, 'g-', label='Y')
                self.ax_fft_disp.plot(freqs_disp, mag_disp_z, 'r-', label='Z')
                self.ax_fft_disp.set_title("진동변위 FFT")
                self.ax_fft_disp.set_xlabel("Frequency (Hz)")
                self.ax_fft_disp.set_ylabel("Amplitude")
                self.ax_fft_disp.set_xlim(0, 50)
                self.ax_fft_disp.legend()
                self.ax_fft_disp.grid(True)
        
        self.canvas_fft.draw()
    
    def check_thresholds_sensor(self, window_data, temp):
        """실시간 센서용 임계치 확인 - False Alarm 감소 로직 포함"""
        if not window_data or len(window_data) < 2:
            return
        
        alarms = []
        
        acc_xs = np.array([d['acc_x'] for d in window_data])
        acc_rms = self.processor.compute_rms(acc_xs)
        
        # 1. 가속도 RMS 확인 (히스테리시스)
        alarm_key = "acc_rms"
        if not np.isnan(acc_rms) and acc_rms > self.thresholds['acc_rms_max'] * 1.1:  # 10% 마진
            if alarm_key not in self.alarm_hysteresis:
                self.alarm_hysteresis[alarm_key] = (False, 0)
            _, count = self.alarm_hysteresis[alarm_key]
            self.alarm_hysteresis[alarm_key] = (False, count + 1)
            
            if count + 1 >= self.alarm_threshold_count:
                alarms.append(f"가속도 RMS 초과: {acc_rms:.3f}g > {self.thresholds['acc_rms_max']:.1f}g")
                self.alarm_hysteresis[alarm_key] = (True, self.alarm_threshold_count)
        else:
            if alarm_key in self.alarm_hysteresis:
                del self.alarm_hysteresis[alarm_key]
        
        # 2. 진동속도 피크 확인
        vel_xs = np.array([d['vel_x'] for d in window_data])
        vel_peak = self.processor.compute_peak(vel_xs)
        
        alarm_key = "vel_peak"
        if not np.isnan(vel_peak) and vel_peak > self.thresholds['vel_peak_max'] * 1.1:
            if alarm_key not in self.alarm_hysteresis:
                self.alarm_hysteresis[alarm_key] = (False, 0)
            _, count = self.alarm_hysteresis[alarm_key]
            self.alarm_hysteresis[alarm_key] = (False, count + 1)
            
            if count + 1 >= self.alarm_threshold_count:
                alarms.append(f"진동속도 피크 초과: {vel_peak:.1f}mm/s > {self.thresholds['vel_peak_max']:.1f}mm/s")
                self.alarm_hysteresis[alarm_key] = (True, self.alarm_threshold_count)
        else:
            if alarm_key in self.alarm_hysteresis:
                del self.alarm_hysteresis[alarm_key]
        
        # 3. 진동변위 피크 확인
        disp_xs = np.array([d['disp_x'] for d in window_data])
        disp_peak = self.processor.compute_peak(disp_xs)
        
        alarm_key = "disp_peak"
        if not np.isnan(disp_peak) and disp_peak > self.thresholds['disp_peak_max'] * 1.1:
            if alarm_key not in self.alarm_hysteresis:
                self.alarm_hysteresis[alarm_key] = (False, 0)
            _, count = self.alarm_hysteresis[alarm_key]
            self.alarm_hysteresis[alarm_key] = (False, count + 1)
            
            if count + 1 >= self.alarm_threshold_count:
                alarms.append(f"진동변위 피크 초과: {disp_peak:.0f}μm > {self.thresholds['disp_peak_max']:.0f}μm")
                self.alarm_hysteresis[alarm_key] = (True, self.alarm_threshold_count)
        else:
            if alarm_key in self.alarm_hysteresis:
                del self.alarm_hysteresis[alarm_key]
        
        # 4. 온도 확인
        alarm_key = "temp"
        if not np.isnan(temp) and temp > self.thresholds['temp_max'] * 1.05:
            if alarm_key not in self.alarm_hysteresis:
                self.alarm_hysteresis[alarm_key] = (False, 0)
            _, count = self.alarm_hysteresis[alarm_key]
            self.alarm_hysteresis[alarm_key] = (False, count + 1)
            
            if count + 1 >= self.alarm_threshold_count:
                alarms.append(f"온도 초과: {temp:.1f}°C > {self.thresholds['temp_max']:.1f}°C")
                self.alarm_hysteresis[alarm_key] = (True, self.alarm_threshold_count)
        else:
            if alarm_key in self.alarm_hysteresis:
                del self.alarm_hysteresis[alarm_key]
        
        # 경보 표시
        if alarms:
            self.label_status.setText("⚠ 경보 발생! (연속 확인됨)")
            self.label_status.setStyleSheet("color: red; font-weight: bold; background-color: yellow;")
            for alarm in alarms:
                self.add_log_event("경보", alarm, "이상")
        else:
            self.label_status.setText("✓ 정상")
            self.label_status.setStyleSheet("color: green;")
    
    def clear_log(self):
        """로그 초기화"""
        self.event_log.clear()
        self.table_log.setRowCount(0)
    
    def save_log_csv(self):
        """로그를 CSV로 저장"""
        if not self.event_log:
            QMessageBox.warning(self, "경고", "저장할 로그가 없습니다.")
            return
        
        filepath, _ = QFileDialog.getSaveFileName(self, "로그 저장", "", "CSV Files (*.csv)")
        if not filepath:
            return
        
        try:
            df = pd.DataFrame(self.event_log)
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            QMessageBox.information(self, "성공", f"로그가 저장되었습니다:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 실패: {str(e)}")


def main():
    app = QApplication(sys.argv)
    window = MotorVibrationGUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
