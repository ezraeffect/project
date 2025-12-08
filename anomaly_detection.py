"""
이상 진동 감지 모듈
시간 도메인 지표(RMS, Peak)를 기반으로 정상/이상 상태를 판별
"""

import numpy as np
import json
import os
from typing import Dict, List, Optional, Tuple
from data_collector import DataBuffer, SensorData


class BaselineCalculator:
    """Baseline 계산 및 관리 클래스"""
    
    def __init__(self, baseline_file: str = "baseline.json"):
        """
        초기화
        
        Args:
            baseline_file: baseline 저장 파일
        """
        self.baseline_file = baseline_file
        self.baseline = {
            'vx': {}, 'vy': {}, 'vz': {},
            'dx': {}, 'dy': {}, 'dz': {},
            'ax': {}, 'ay': {}, 'az': {},
            'temp': {}
        }
    
    def calculate_time_domain_features(self, values: List[float]) -> Dict:
        """
        시간 도메인 지표 계산
        
        Args:
            values: 센서 데이터 값 리스트
            
        Returns:
            RMS, Peak, Mean, Std 등의 지표
        """
        if not values:
            return {
                'rms': 0, 'peak': 0, 'mean': 0, 'std': 0,
                'min': 0, 'max': 0, 'crest_factor': 0
            }
        
        values = np.array(values)
        
        # RMS (Root Mean Square)
        rms = np.sqrt(np.mean(values ** 2))
        
        # Peak (절대값 최대)
        peak = np.max(np.abs(values))
        
        # Mean
        mean = np.mean(values)
        
        # Standard Deviation
        std = np.std(values)
        
        # Min, Max
        min_val = np.min(values)
        max_val = np.max(values)
        
        # Crest Factor (Peak / RMS)
        crest_factor = peak / rms if rms > 0 else 0
        
        return {
            'rms': float(rms),
            'peak': float(peak),
            'mean': float(mean),
            'std': float(std),
            'min': float(min_val),
            'max': float(max_val),
            'crest_factor': float(crest_factor)
        }
    
    def calculate_baseline(self, data_buffer: DataBuffer) -> bool:
        """
        Baseline 계산
        
        Args:
            data_buffer: 수집된 데이터 버퍼
            
        Returns:
            성공 여부
        """
        data_list = data_buffer.get_all()
        
        if len(data_list) < 10:  # 최소 10개 데이터 필요
            print(f"Warning: Baseline calculation requires at least 10 data points, got {len(data_list)}")
            return False
        
        # 각 축별 데이터 추출
        axes_data = {
            'vx': [d.vx for d in data_list],
            'vy': [d.vy for d in data_list],
            'vz': [d.vz for d in data_list],
            'dx': [d.dx for d in data_list],
            'dy': [d.dy for d in data_list],
            'dz': [d.dz for d in data_list],
            'ax': [d.ax for d in data_list],
            'ay': [d.ay for d in data_list],
            'az': [d.az for d in data_list],
            'temp': [d.temp for d in data_list]
        }
        
        # 각 축별 지표 계산
        for axis, values in axes_data.items():
            self.baseline[axis] = self.calculate_time_domain_features(values)
        
        return True
    
    def save_baseline(self) -> bool:
        """
        Baseline을 파일에 저장
        
        Returns:
            성공 여부
        """
        try:
            with open(self.baseline_file, 'w') as f:
                json.dump(self.baseline, f, indent=2)
            print(f"Baseline saved to {self.baseline_file}")
            return True
        except Exception as e:
            print(f"Error saving baseline: {e}")
            return False
    
    def load_baseline(self) -> bool:
        """
        파일에서 Baseline 로드
        
        Returns:
            성공 여부
        """
        try:
            if os.path.exists(self.baseline_file):
                with open(self.baseline_file, 'r') as f:
                    self.baseline = json.load(f)
                print(f"Baseline loaded from {self.baseline_file}")
                return True
            else:
                print(f"Baseline file not found: {self.baseline_file}")
                return False
        except Exception as e:
            print(f"Error loading baseline: {e}")
            return False
    
    def get_baseline(self) -> Dict:
        """Baseline 반환"""
        return self.baseline


class AnomalyDetector:
    """이상 진동 감지 클래스"""
    
    def __init__(self, baseline_calculator: BaselineCalculator):
        """
        초기화
        
        Args:
            baseline_calculator: BaselineCalculator 인스턴스
        """
        self.baseline_calc = baseline_calculator
        self.thresholds = {}
        self.anomaly_history = []
    
    def calculate_thresholds(self, std_multiplier: float = 2.0, 
                            baseline: Optional[Dict] = None) -> Dict:
        """
        임계값 계산 (Baseline 기반)
        
        Args:
            std_multiplier: 표준편차 배수 (기본값: 2.0)
            baseline: Baseline 데이터 (None이면 저장된 baseline 사용)
            
        Returns:
            각 축별 임계값
        """
        if baseline is None:
            baseline = self.baseline_calc.get_baseline()
        
        self.thresholds = {}
        
        for axis, features in baseline.items():
            # 임계값 = Mean + (Std * multiplier)
            mean = features.get('mean', 0)
            std = features.get('std', 0)
            rms = features.get('rms', 0)
            
            # 다양한 임계값 설정
            self.thresholds[axis] = {
                'warning': mean + std * std_multiplier,        # 주의 수준
                'critical': mean + std * (std_multiplier * 1.5),  # 경고 수준
                'rms_baseline': rms,
                'rms_threshold': rms * (1 + std_multiplier * 0.1)
            }
        
        return self.thresholds
    
    def detect_anomaly(self, current_data: SensorData, 
                      window_data: List[SensorData],
                      use_rms: bool = True) -> Dict:
        """
        이상 진동 감지
        
        Args:
            current_data: 현재 센서 데이터
            window_data: 윈도우 내 센서 데이터 (최근 N개)
            use_rms: RMS 기반 감지 사용 여부
            
        Returns:
            감지 결과 {'axis': status, ...}
        """
        if not self.thresholds:
            return {}
        
        anomaly_results = {}
        
        # 각 축별 감지
        axes = [
            ('vx', current_data.vx, [d.vx for d in window_data]),
            ('vy', current_data.vy, [d.vy for d in window_data]),
            ('vz', current_data.vz, [d.vz for d in window_data]),
            ('dx', current_data.dx, [d.dx for d in window_data]),
            ('dy', current_data.dy, [d.dy for d in window_data]),
            ('dz', current_data.dz, [d.dz for d in window_data]),
            ('ax', current_data.ax, [d.ax for d in window_data]),
            ('ay', current_data.ay, [d.ay for d in window_data]),
            ('az', current_data.az, [d.az for d in window_data]),
        ]
        
        for axis_name, current_val, window_vals in axes:
            if axis_name not in self.thresholds:
                continue
            
            threshold = self.thresholds[axis_name]
            status = 'normal'
            
            if use_rms and window_vals:
                # RMS 기반 감지
                rms = np.sqrt(np.mean(np.array(window_vals) ** 2))
                if rms > threshold.get('rms_threshold', float('inf')):
                    status = 'anomaly'
                elif rms > threshold.get('rms_baseline', 0) * 1.2:
                    status = 'warning'
            else:
                # 현재값 기반 감지
                if abs(current_val) > threshold['critical']:
                    status = 'anomaly'
                elif abs(current_val) > threshold['warning']:
                    status = 'warning'
            
            anomaly_results[axis_name] = {
                'status': status,
                'current_value': float(current_val),
                'threshold_warning': float(threshold['warning']),
                'threshold_critical': float(threshold['critical'])
            }
        
        return anomaly_results
    
    def get_anomaly_score(self, anomaly_results: Dict) -> float:
        """
        종합 이상 점수 계산 (0~100)
        
        Args:
            anomaly_results: 감지 결과
            
        Returns:
            이상 점수
        """
        if not anomaly_results:
            return 0.0
        
        anomaly_count = sum(1 for r in anomaly_results.values() 
                          if r['status'] == 'anomaly')
        warning_count = sum(1 for r in anomaly_results.values() 
                          if r['status'] == 'warning')
        
        # 점수: 이상 100점, 주의 50점
        score = (anomaly_count * 100 + warning_count * 50) / len(anomaly_results)
        return min(score, 100.0)  # 최대 100점
    
    def record_anomaly(self, timestamp: float, anomaly_results: Dict, score: float):
        """이상 기록"""
        self.anomaly_history.append({
            'timestamp': timestamp,
            'results': anomaly_results,
            'score': score
        })
    
    def get_anomaly_history(self, limit: int = 100) -> List:
        """이상 기록 반환"""
        return self.anomaly_history[-limit:]


if __name__ == "__main__":
    # 테스트 코드
    from data_collector import DataBuffer
    
    # 테스트 데이터 생성
    buffer = DataBuffer()
    for i in range(100):
        data = SensorData()
        data.vx = np.sin(i * 0.1) * 10
        data.vy = np.cos(i * 0.1) * 10
        data.vz = 5
        buffer.add(data)
    
    # Baseline 계산
    calc = BaselineCalculator()
    calc.calculate_baseline(buffer)
    
    print("Baseline:")
    print(json.dumps(calc.get_baseline(), indent=2))
