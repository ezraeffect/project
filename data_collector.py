"""
실시간 데이터 수집 및 버퍼링 모듈
멀티스레딩을 사용하여 UI와 분리된 데이터 수집
"""

import threading
import time
import queue
from typing import Optional, Callable, List
from collections import deque
from sensor_communication import WTVBSensor, SensorData


class DataBuffer:
    """센서 데이터를 저장하는 순환 버퍼"""
    
    def __init__(self, max_size: int = 1000):
        """
        버퍼 초기화
        
        Args:
            max_size: 최대 저장 크기
        """
        self.max_size = max_size
        self.buffer = deque(maxlen=max_size)
        self.lock = threading.Lock()
    
    def add(self, data: SensorData) -> None:
        """데이터 추가"""
        with self.lock:
            self.buffer.append(data)
    
    def get_latest(self) -> Optional[SensorData]:
        """최신 데이터 반환"""
        with self.lock:
            if len(self.buffer) > 0:
                return self.buffer[-1]
            return None
    
    def get_all(self) -> List[SensorData]:
        """모든 데이터 반환"""
        with self.lock:
            return list(self.buffer)
    
    def get_last_n(self, n: int) -> List[SensorData]:
        """최신 n개 데이터 반환"""
        with self.lock:
            return list(self.buffer)[-n:]
    
    def get_by_time_range(self, start_time: float, end_time: float) -> List[SensorData]:
        """
        시간 범위로 데이터 반환
        
        Args:
            start_time: 시작 시간 (Unix timestamp)
            end_time: 종료 시간 (Unix timestamp)
            
        Returns:
            해당 범위의 데이터 리스트
        """
        with self.lock:
            result = []
            for data in self.buffer:
                if start_time <= data.timestamp <= end_time:
                    result.append(data)
            return result
    
    def clear(self) -> None:
        """버퍼 초기화"""
        with self.lock:
            self.buffer.clear()
    
    def size(self) -> int:
        """현재 버퍼 크기"""
        with self.lock:
            return len(self.buffer)
    
    def to_dict_list(self) -> List[dict]:
        """딕셔너리 리스트로 변환"""
        with self.lock:
            return [data.to_dict() for data in self.buffer]


class DataCollector:
    """센서 데이터 수집 및 관리 클래스"""
    
    def __init__(self, sensor: WTVBSensor, buffer_size: int = 1000, 
                 collection_interval: float = 0.1):
        """
        데이터 수집기 초기화
        
        Args:
            sensor: WTVB센서 인스턴스
            buffer_size: 데이터 버퍼 크기
            collection_interval: 데이터 수집 간격 (초)
        """
        self.sensor = sensor
        self.buffer = DataBuffer(buffer_size)
        self.collection_interval = collection_interval
        
        self.thread = None
        self.is_running = False
        self.stop_event = threading.Event()
        
        # 이벤트 콜백
        self.on_data_received: Optional[Callable[[SensorData], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_connection_lost: Optional[Callable[[], None]] = None
        
        # 통계
        self.total_readings = 0
        self.failed_readings = 0
        self.last_error = None
        self.start_time = None
        self.lock = threading.Lock()
    
    def start(self) -> bool:
        """데이터 수집 시작"""
        if self.is_running:
            return False
        
        if not self.sensor.is_connected:
            error_msg = "Sensor not connected"
            if self.on_error:
                self.on_error(error_msg)
            return False
        
        self.is_running = True
        self.stop_event.clear()
        self.start_time = time.time()
        self.total_readings = 0
        self.failed_readings = 0
        
        self.thread = threading.Thread(target=self._collect_data_loop, daemon=True)
        self.thread.start()
        
        return True
    
    def stop(self) -> None:
        """데이터 수집 중지"""
        if not self.is_running:
            return
        
        self.is_running = False
        self.stop_event.set()
        
        if self.thread:
            self.thread.join(timeout=5.0)
    
    def _collect_data_loop(self) -> None:
        """데이터 수집 루프"""
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while not self.stop_event.is_set():
            try:
                # 센서 연결 상태 확인
                if not self.sensor.is_connected:
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        if self.on_connection_lost:
                            self.on_connection_lost()
                        break
                    time.sleep(self.collection_interval)
                    continue
                
                # 데이터 읽기
                start_read = time.time()
                data = self.sensor.read_all_data()
                read_time = time.time() - start_read
                
                if data:
                    # 버퍼에 저장
                    self.buffer.add(data)
                    
                    # 콜백 실행
                    if self.on_data_received:
                        try:
                            self.on_data_received(data)
                        except Exception as e:
                            self.last_error = f"Callback error: {e}"
                    
                    with self.lock:
                        self.total_readings += 1
                        consecutive_errors = 0
                else:
                    # 읽기 실패
                    consecutive_errors += 1
                    with self.lock:
                        self.failed_readings += 1
                    
                    # 상세한 에러 메시지 생성
                    if hasattr(self.sensor, 'modbus') and self.sensor.modbus.last_error:
                        error_detail = self.sensor.modbus.last_error
                    else:
                        error_detail = f"Attempt {consecutive_errors}/{max_consecutive_errors}"
                    
                    error_msg = f"Failed to read sensor data - {error_detail}"
                    if self.on_error:
                        self.on_error(error_msg)
                
                # 수집 간격 조정 (읽기 시간 고려)
                remaining_time = self.collection_interval - read_time
                if remaining_time > 0:
                    time.sleep(remaining_time)
                
            except Exception as e:
                consecutive_errors += 1
                self.last_error = str(e)
                error_msg = f"Data collection error: {e}"
                if self.on_error:
                    self.on_error(error_msg)
                
                time.sleep(self.collection_interval)
    
    def get_latest_data(self) -> Optional[SensorData]:
        """최신 데이터 반환"""
        return self.buffer.get_latest()
    
    def get_all_data(self) -> List[SensorData]:
        """모든 버퍼 데이터 반환"""
        return self.buffer.get_all()
    
    def get_last_n_data(self, n: int) -> List[SensorData]:
        """최신 n개 데이터 반환"""
        return self.buffer.get_last_n(n)
    
    def get_data_by_time_range(self, duration_seconds: float) -> List[SensorData]:
        """
        최근 n초의 데이터 반환
        
        Args:
            duration_seconds: 시간 범위 (초)
            
        Returns:
            해당 범위의 데이터 리스트
        """
        current_time = time.time()
        start_time = current_time - duration_seconds
        return self.buffer.get_by_time_range(start_time, current_time)
    
    def clear_buffer(self) -> None:
        """버퍼 초기화"""
        self.buffer.clear()
    
    def get_acceleration_amplitudes(self, window_size: int = 50) -> tuple:
        """최근 데이터에서 가속도 진폭 계산 (peak-to-peak / 2)"""
        recent_data = self.buffer.get_last_n(min(window_size, self.buffer.size()))
        if len(recent_data) < 2:
            return (0.0, 0.0, 0.0)
        
        ax_values = [d.ax for d in recent_data]
        ay_values = [d.ay for d in recent_data]
        az_values = [d.az for d in recent_data]
        
        ax_amp = (max(ax_values) - min(ax_values)) / 2.0 if ax_values else 0.0
        ay_amp = (max(ay_values) - min(ay_values)) / 2.0 if ay_values else 0.0
        az_amp = (max(az_values) - min(az_values)) / 2.0 if az_values else 0.0
        
        return (ax_amp, ay_amp, az_amp)
    
    def get_statistics(self) -> dict:
        """수집 통계 반환"""
        with self.lock:
            success_rate = 0.0
            if self.total_readings + self.failed_readings > 0:
                success_rate = (self.total_readings / 
                              (self.total_readings + self.failed_readings) * 100)
            
            elapsed_time = 0.0
            if self.start_time:
                elapsed_time = time.time() - self.start_time
            
            return {
                'total_readings': self.total_readings,
                'failed_readings': self.failed_readings,
                'success_rate': success_rate,
                'elapsed_time': elapsed_time,
                'buffer_size': self.buffer.size(),
                'is_running': self.is_running,
                'last_error': self.last_error
            }
    
    def __del__(self):
        """소멸자"""
        if self.is_running:
            self.stop()


class MultiAxisAnalyzer:
    """3축 데이터 분석 클래스"""
    
    def __init__(self, data_buffer: DataBuffer):
        """
        분석기 초기화
        
        Args:
            data_buffer: 데이터 버퍼
        """
        self.data_buffer = data_buffer
    
    def get_velocity_statistics(self, duration_seconds: float = 60) -> dict:
        """
        진동 속도 통계
        
        Args:
            duration_seconds: 분석 기간 (초) - 현재는 사용되지 않음, 전체 버퍼 데이터 사용
            
        Returns:
            통계 정보 (min, max, avg, current)
        """
        # 버퍼의 모든 데이터 사용
        data_list = self.data_buffer.get_all()
        
        if not data_list:
            return {
                'vx': {'min': 0, 'max': 0, 'avg': 0, 'current': 0},
                'vy': {'min': 0, 'max': 0, 'avg': 0, 'current': 0},
                'vz': {'min': 0, 'max': 0, 'avg': 0, 'current': 0}
            }
        
        vx_values = [d.vx for d in data_list]
        vy_values = [d.vy for d in data_list]
        vz_values = [d.vz for d in data_list]
        
        def calc_stats(values):
            if not values:
                return {'min': 0, 'max': 0, 'avg': 0, 'current': 0}
            return {
                'min': min(values),
                'max': max(values),
                'avg': sum(values) / len(values),
                'current': values[-1] if values else 0
            }
        
        return {
            'vx': calc_stats(vx_values),
            'vy': calc_stats(vy_values),
            'vz': calc_stats(vz_values)
        }
    
    def get_displacement_statistics(self, duration_seconds: float = 60) -> dict:
        """진동 변위 통계"""
        # 버퍼의 모든 데이터 사용
        data_list = self.data_buffer.get_all()
        
        if not data_list:
            return {
                'dx': {'min': 0, 'max': 0, 'avg': 0, 'current': 0},
                'dy': {'min': 0, 'max': 0, 'avg': 0, 'current': 0},
                'dz': {'min': 0, 'max': 0, 'avg': 0, 'current': 0}
            }
        
        dx_values = [d.dx for d in data_list]
        dy_values = [d.dy for d in data_list]
        dz_values = [d.dz for d in data_list]
        
        def calc_stats(values):
            if not values:
                return {'min': 0, 'max': 0, 'avg': 0, 'current': 0}
            return {
                'min': min(values),
                'max': max(values),
                'avg': sum(values) / len(values),
                'current': values[-1] if values else 0
            }
        
        return {
            'dx': calc_stats(dx_values),
            'dy': calc_stats(dy_values),
            'dz': calc_stats(dz_values)
        }
    
    def get_frequency_statistics(self, duration_seconds: float = 60) -> dict:
        """진동 주파수 통계"""
        # 버퍼의 모든 데이터 사용
        data_list = self.data_buffer.get_all()
        
        if not data_list:
            return {
                'hx': {'min': 0, 'max': 0, 'avg': 0, 'current': 0},
                'hy': {'min': 0, 'max': 0, 'avg': 0, 'current': 0},
                'hz': {'min': 0, 'max': 0, 'avg': 0, 'current': 0}
            }
        
        hx_values = [d.hx for d in data_list]
        hy_values = [d.hy for d in data_list]
        hz_values = [d.hz for d in data_list]
        
        def calc_stats(values):
            if not values:
                return {'min': 0, 'max': 0, 'avg': 0, 'current': 0}
            return {
                'min': min(values),
                'max': max(values),
                'avg': sum(values) / len(values),
                'current': values[-1] if values else 0
            }
        
        return {
            'hx': calc_stats(hx_values),
            'hy': calc_stats(hy_values),
            'hz': calc_stats(hz_values)
        }
    
    def get_temperature_statistics(self, duration_seconds: float = 60) -> dict:
        """온도 통계"""
        # 버퍼의 모든 데이터 사용
        data_list = self.data_buffer.get_all()
        
        if not data_list:
            return {'min': 0, 'max': 0, 'avg': 0, 'current': 0}
        
        temp_values = [d.temp for d in data_list]
        
        if not temp_values:
            return {'min': 0, 'max': 0, 'avg': 0, 'current': 0}
        
        return {
            'min': min(temp_values),
            'max': max(temp_values),
            'avg': sum(temp_values) / len(temp_values),
            'current': temp_values[-1] if temp_values else 0
        }


if __name__ == "__main__":
    # 테스트 코드
    pass
