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
        self.last_error = None
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
        
        # Kurtosis (4차 모멘트 / 분산^2). 분산이 0이면 0 반환
        variance = np.var(values)
        kurtosis = np.mean((values - mean) ** 4) / (variance ** 2) if variance > 0 else 0.0

        return {
            'rms': float(rms),
            'peak': float(peak),
            'mean': float(mean),
            'std': float(std),
            'min': float(min_val),
            'max': float(max_val),
            'crest_factor': float(crest_factor),
            'kurtosis': float(kurtosis)
        }

    def _compute_sample_rate(self, data_list: List[SensorData]) -> float:
        """버퍼에서 샘플레이트 추정 (Hz)"""
        if not data_list or len(data_list) < 2:
            return 0.0
        t0 = data_list[0].timestamp
        t1 = data_list[-1].timestamp
        if t1 <= t0:
            return 0.0
        return (len(data_list) - 1) / (t1 - t0)

    def _high_freq_energy(self, values: List[float], sample_rate: float,
                          fmin: float = 2000.0, fmax: Optional[float] = None) -> float:
        """고주파 대역 에너지 계산 (가속도 FFT 기반)

        fmin 이상 구간의 스펙트럼 에너지 합. 샘플레이트가 2*fmin보다 낮으면 0 반환.
        """
        if not values or sample_rate <= 0 or sample_rate < 2 * fmin:
            return 0.0
        arr = np.array(values)
        n = len(arr)
        if n < 4:
            return 0.0
        fft = np.fft.rfft(arr - np.mean(arr))
        freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
        mask = (freqs >= fmin) if fmax is None else ((freqs >= fmin) & (freqs <= fmax))
        if not np.any(mask):
            return 0.0
        energy = np.sum(np.abs(fft[mask]) ** 2) / n
        return float(energy)
    
    def calculate_baseline(self, data_buffer: DataBuffer, min_samples: int = 30,
                           max_zero_std_axes: int = 6) -> bool:
        """
        Baseline 계산 및 간단 검증
        
        Args:
            data_buffer: 수집된 데이터 버퍼
            min_samples: 최소 필요 샘플 수
            max_zero_std_axes: 표준편차가 0인 축 허용 개수
                              (변위, 주파수, VX축은 0일 수 있으므로 여유있게 설정)
        """
        data_list = data_buffer.get_all()
        
        if len(data_list) < min_samples:
            self.last_error = f"Baseline calculation requires at least {min_samples} data points, got {len(data_list)}"
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
        
        # 샘플레이트 추정 (고주파 에너지 계산용)
        sample_rate = self._compute_sample_rate(data_list)

        # 각 축별 지표 계산
        zero_std_axes = 0
        # 중요한 축들 (최소 하나는 유효한 데이터가 있어야 함)
        critical_axes = ['vy', 'vz']  # VY, VZ는 반드시 변동이 있어야 함
        critical_zero_count = 0
        
        for axis, values in axes_data.items():
            features = self.calculate_time_domain_features(values)
            # 고주파 에너지 (가속도 축만 대상)
            if axis in {'ax', 'ay', 'az'}:
                hf_energy = self._high_freq_energy(values, sample_rate, fmin=2000.0)
                features['hf_energy'] = hf_energy
            self.baseline[axis] = features
            if features.get('std', 0) == 0:
                zero_std_axes += 1
                if axis in critical_axes:
                    critical_zero_count += 1
        
        # VY, VZ 둘 다 0이면 유효한 진동 데이터가 없음
        if critical_zero_count >= 2:
            self.last_error = f"Critical velocity axes (VY, VZ) have no variance. Check sensor connection."
            return False
        
        if zero_std_axes > max_zero_std_axes:
            self.last_error = f"Too many axes with zero variance ({zero_std_axes}). Baseline may be invalid."
            return False
        
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
            return True
        except Exception as e:
            self.last_error = f"Error saving baseline: {e}"
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
                return True
            else:
                self.last_error = f"Baseline file not found: {self.baseline_file}"
                return False
        except Exception as e:
            self.last_error = f"Error loading baseline: {e}"
            return False
    
    def get_baseline(self) -> Dict:
        """Baseline 반환"""
        return self.baseline


class AnomalyDetector:
    """이상 진동 감지 클래스"""
    
    def __init__(self, baseline_calculator: BaselineCalculator,
                 min_consecutive: int = 2,
                 hysteresis_ratio: float = 0.9,
                 window_seconds: float = 10.0,
                 warning_rms_factor: float = 1.15,
                 critical_rms_factor: float = 1.30,
                 warning_peak_factor: float = 1.20,
                 critical_peak_factor: float = 1.50,
                 crest_warning_factor: float = 1.20,
                 crest_critical_factor: float = 1.50):
        """
        초기화
        
        Args:
            baseline_calculator: BaselineCalculator 인스턴스
            min_consecutive: 연속 초과 횟수 최소값 (노이즈 완화)
            hysteresis_ratio: 복귀 시 하강 임계 비율 (0~1)
            window_seconds: RMS/피크 계산에 사용할 시간 창(초)
            warning_rms_factor: RMS 경고 배수
            critical_rms_factor: RMS 치명 배수
            warning_peak_factor: 피크 경고 배수
            critical_peak_factor: 피크 치명 배수
            crest_warning_factor: 크레스트팩터 경고 배수
            crest_critical_factor: 크레스트팩터 치명 배수
        """
        self.baseline_calc = baseline_calculator
        self.thresholds = {}
        self.anomaly_history = []
        self.min_consecutive = max(1, min_consecutive)
        self.hysteresis_ratio = max(0.0, min(hysteresis_ratio, 1.0))
        self.state_tracker = {}
        self.window_seconds = max(0.1, window_seconds)
        self.warning_rms_factor = warning_rms_factor
        self.critical_rms_factor = critical_rms_factor
        self.warning_peak_factor = warning_peak_factor
        self.critical_peak_factor = critical_peak_factor
        self.crest_warning_factor = crest_warning_factor
        self.crest_critical_factor = crest_critical_factor
    
    def calculate_thresholds(self, std_multiplier: float = 2.0, 
                            baseline: Optional[Dict] = None) -> Dict:
        """임계값 계산 (Baseline 기반)

        AC 성분(vibration/accel/disp)은 RMS/피크 배수 기반, DC(temp)는 mean+std.
        """
        if baseline is None:
            baseline = self.baseline_calc.get_baseline()
        
        self.thresholds = {}
        ac_axes = {'vx', 'vy', 'vz', 'dx', 'dy', 'dz', 'ax', 'ay', 'az'}
        dc_axes = {'temp'}
        
        for axis, features in baseline.items():
            mean = features.get('mean', 0)
            std = features.get('std', 0)
            rms = features.get('rms', 0)
            peak = features.get('peak', 0)
            crest = features.get('crest_factor', 0)
            if axis in ac_axes:
                kurt = features.get('kurtosis', 0)
                hf_energy = features.get('hf_energy', 0)
                self.thresholds[axis] = {
                    'warning': rms * self.warning_rms_factor,
                    'critical': rms * self.critical_rms_factor,
                    'warning_peak': peak * self.warning_peak_factor,
                    'critical_peak': peak * self.critical_peak_factor,
                    'warning_crest': crest * self.crest_warning_factor if crest else 0,
                    'critical_crest': crest * self.crest_critical_factor if crest else 0,
                    'kurtosis_warning': kurt * 1.3 if kurt else 0,
                    'kurtosis_critical': kurt * 1.6 if kurt else 0,
                    'hf_warning': hf_energy * 2.5 if hf_energy else 0,
                    'hf_critical': hf_energy * 4.0 if hf_energy else 0,
                    'rms_baseline': rms,
                    'method': 'rms_factor'
                }
            elif axis in dc_axes:
                self.thresholds[axis] = {
                    'warning': mean + std * std_multiplier,
                    'critical': mean + std * (std_multiplier * 1.5),
                    'rms_baseline': rms,
                    'method': 'mean_std'
                }
            else:
                # fallback to mean+std
                self.thresholds[axis] = {
                    'warning': mean + std * std_multiplier,
                    'critical': mean + std * (std_multiplier * 1.5),
                    'rms_baseline': rms,
                    'method': 'mean_std'
                }
        
        return self.thresholds

    def _compute_sample_rate(self, data_list: List[SensorData]) -> float:
        """버퍼에서 샘플레이트 추정 (Hz)"""
        if not data_list or len(data_list) < 2:
            return 0.0
        t0 = data_list[0].timestamp
        t1 = data_list[-1].timestamp
        if t1 <= t0:
            return 0.0
        return (len(data_list) - 1) / (t1 - t0)

    def _kurtosis(self, values: List[float]) -> float:
        """윈도우 내 커토시스 계산"""
        if not values:
            return 0.0
        arr = np.array(values)
        mean = np.mean(arr)
        variance = np.var(arr)
        if variance == 0:
            return 0.0
        return float(np.mean((arr - mean) ** 4) / (variance ** 2))

    def _high_freq_energy(self, values: List[float], sample_rate: float,
                          fmin: float = 2000.0, fmax: Optional[float] = None) -> float:
        """고주파 대역 에너지 계산 (가속도 FFT 기반)"""
        if not values or sample_rate <= 0 or sample_rate < 2 * fmin:
            return 0.0
        arr = np.array(values)
        n = len(arr)
        if n < 4:
            return 0.0
        fft = np.fft.rfft(arr - np.mean(arr))
        freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
        mask = (freqs >= fmin) if fmax is None else ((freqs >= fmin) & (freqs <= fmax))
        if not np.any(mask):
            return 0.0
        energy = np.sum(np.abs(fft[mask]) ** 2) / n
        return float(energy)

    def calculate_thresholds_percentile(self, samples: List[SensorData],
                                         warning_pct: float = 95.0,
                                         critical_pct: float = 99.0,
                                         use_abs: bool = True) -> Dict:
        """퍼센타일 기반 임계값 계산

        Args:
            samples: baseline 구간의 센서 데이터 리스트
            warning_pct: 경고 퍼센타일 (0~100)
            critical_pct: 치명 퍼센타일 (0~100)
            use_abs: 절대값 기반 계산 여부 (진동성 신호 권장)
        """
        if not samples:
            return {}
        warning_pct = min(max(warning_pct, 0), 100)
        critical_pct = min(max(critical_pct, 0), 100)
        axes = ['vx', 'vy', 'vz', 'dx', 'dy', 'dz', 'ax', 'ay', 'az', 'temp']
        values = {axis: [] for axis in axes}
        for s in samples:
            for axis in axes:
                v = getattr(s, axis, 0)
                values[axis].append(abs(v) if use_abs else v)
        self.thresholds = {}
        for axis in axes:
            axis_vals = values[axis]
            if not axis_vals:
                continue
            warning_thr = float(np.percentile(axis_vals, warning_pct))
            critical_thr = float(np.percentile(axis_vals, critical_pct))
            rms_val = float(np.sqrt(np.mean(np.array(axis_vals) ** 2)))
            self.thresholds[axis] = {
                'warning': warning_thr,
                'critical': critical_thr,
                'rms_baseline': rms_val,
                'rms_threshold': critical_thr,
                'method': 'percentile'
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
        
        # 시간 창 필터링
        if window_data:
            latest_ts = window_data[-1].timestamp
            window_data = [d for d in window_data if d.timestamp >= latest_ts - self.window_seconds]
        sample_rate = self._compute_sample_rate(window_data) if window_data else 0.0
        
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
            ('temp', current_data.temp, [d.temp for d in window_data])
        ]
        
        for axis_name, current_val, window_vals in axes:
            if axis_name not in self.thresholds:
                continue
            
            threshold = self.thresholds[axis_name]
            tracker = self.state_tracker.setdefault(axis_name, {
                'warning_streak': 0,
                'critical_streak': 0,
                'last_state': 'normal'
            })
            status_raw = 'normal'
            metric_value = abs(current_val)
            warning_thr = threshold.get('warning', 0)
            critical_thr = threshold.get('critical', 0)
            method = threshold.get('method', 'mean_std')
            metrics_data = {}
            
            # RMS/피크/크레스트 기반 (AC)
            if method == 'rms_factor' and use_rms and window_vals:
                arr = np.array(window_vals)
                rms = float(np.sqrt(np.mean(arr ** 2)))
                peak = float(np.max(np.abs(arr))) if arr.size else 0
                crest = peak / rms if rms > 0 else 0
                metrics_data.update({'rms': rms, 'peak': peak, 'crest_factor': crest})
                metric_value = rms
                # RMS 우선 평가
                if rms > critical_thr:
                    status_raw = 'anomaly'
                elif rms > warning_thr:
                    status_raw = 'warning'
                # 피크 평가 (더 심한 상태를 선택)
                if peak > threshold.get('critical_peak', float('inf')):
                    status_raw = 'anomaly'
                    metric_value = peak
                elif peak > threshold.get('warning_peak', float('inf')) and status_raw != 'anomaly':
                    status_raw = 'warning'
                    metric_value = peak
                # 크레스트팩터 평가
                if crest > threshold.get('critical_crest', float('inf')):
                    status_raw = 'anomaly'
                    metric_value = crest
                elif crest > threshold.get('warning_crest', float('inf')) and status_raw != 'anomaly':
                    status_raw = 'warning'
                    metric_value = crest
                # 커토시스 평가
                kurt_warning = threshold.get('kurtosis_warning', 0)
                kurt_critical = threshold.get('kurtosis_critical', 0)
                if kurt_warning or kurt_critical:
                    kurt_val = self._kurtosis(window_vals)
                    metrics_data['kurtosis'] = kurt_val
                    if kurt_critical and kurt_val > kurt_critical:
                        status_raw = 'anomaly'
                        metric_value = kurt_val
                        warning_thr = kurt_warning or warning_thr
                        critical_thr = kurt_critical
                    elif kurt_warning and kurt_val > kurt_warning and status_raw != 'anomaly':
                        status_raw = 'warning'
                        metric_value = kurt_val
                        warning_thr = kurt_warning
                        critical_thr = kurt_critical or critical_thr
                # 고주파 에너지 평가
                hf_warning = threshold.get('hf_warning', 0)
                hf_critical = threshold.get('hf_critical', 0)
                if (hf_warning or hf_critical) and sample_rate > 0:
                    hf_val = self._high_freq_energy(window_vals, sample_rate, fmin=2000.0)
                    metrics_data['hf_energy'] = hf_val
                    if hf_critical and hf_val > hf_critical:
                        status_raw = 'anomaly'
                        metric_value = hf_val
                        warning_thr = hf_warning or warning_thr
                        critical_thr = hf_critical
                    elif hf_warning and hf_val > hf_warning and status_raw != 'anomaly':
                        status_raw = 'warning'
                        metric_value = hf_val
                        warning_thr = hf_warning
                        critical_thr = hf_critical or critical_thr
            else:
                # DC or fallback: 현재값 절대값 기반
                if abs(current_val) > critical_thr:
                    status_raw = 'anomaly'
                elif abs(current_val) > warning_thr:
                    status_raw = 'warning'
                metric_value = abs(current_val)
                metrics_data['value'] = metric_value
            
            # 히스테리시스: 한 번 올라간 상태는 완충 구간을 지나야 내려감
            hysteresis_crit = critical_thr * self.hysteresis_ratio
            hysteresis_warn = warning_thr * self.hysteresis_ratio
            if tracker['last_state'] == 'anomaly' and metric_value >= hysteresis_crit:
                status_raw = 'anomaly'
            elif tracker['last_state'] == 'warning' and metric_value >= hysteresis_warn:
                if status_raw != 'anomaly':
                    status_raw = 'warning'
            
            # 지속 조건: 연속 초과 횟수 충족 시 상태 확정
            if status_raw == 'anomaly':
                tracker['critical_streak'] += 1
                tracker['warning_streak'] += 1
            elif status_raw == 'warning':
                tracker['critical_streak'] = 0
                tracker['warning_streak'] += 1
            else:
                tracker['critical_streak'] = 0
                tracker['warning_streak'] = 0
            
            if tracker['critical_streak'] >= self.min_consecutive:
                status = 'anomaly'
            elif tracker['warning_streak'] >= self.min_consecutive:
                status = 'warning'
            else:
                status = 'normal'
            tracker['last_state'] = status
            
            anomaly_results[axis_name] = {
                'status': status,
                'current_value': float(current_val),
                'threshold_warning': float(threshold['warning']),
                'threshold_critical': float(threshold['critical']),
                'metrics': metrics_data
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
