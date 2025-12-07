# 베이스라인 학습 시스템 상세 분석

## 1. 개요

**베이스라인(Baseline)**: 정상 상태의 센서 신호가 가지는 특성  
**목적**: 정상 상태의 통계적 특성을 학습 → 정상/이상 구분 기준으로 사용

---

## 2. 베이스라인 학습 플로우

```
┌─────────────────────────────────────────────────────────────┐
│ 사용자 "학습 시작" 클릭 (탭3 베이스라인 학습 그룹)          │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ start_baseline_learning() 호출                              │
│                                                             │
│ 1. 모드 확인: 실시간 센서 모드인가?                        │
│ 2. 센서 활성화 확인: data_queue에 데이터가 있는가?         │
│ 3. 상태 초기화:                                            │
│    - is_learning = True                                   │
│    - learning_count = 0                                   │
│    - baseline_data = [] (비우기)                           │
│ 4. UI 업데이트:                                            │
│    - 버튼 비활성화                                        │
│    - 상태 표시 "학습 중... (0/30초)"                      │
│    - 텍스트 색상: 주황색                                   │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 30초 동안 반복 (타이머 콜백 30fps × 30초 = ~900회)        │
│                                                             │
│ update_baseline_learning() - 매 프레임마다 호출            │
│                                                             │
│ 1. 카운트 증가: learning_count += 1                        │
│ 2. UI 업데이트: "학습 중... (N/30초)"                      │
│ 3. 센서 데이터 추출:                                       │
│    with data_lock:                                        │
│        recent_data = list(data_queue)  # 모든 데이터      │
│ 4. 최신 샘플 저장:                                         │
│    latest = recent_data[-1]                               │
│    baseline_data.append({                                 │
│        'acc_x': latest['acc_x'],                          │
│        'vel_x': latest['vel_x'],                          │
│        'disp_x': latest['disp_x']                         │
│    })                                                     │
│ 5. 30초 체크: learning_count >= 30이면 종료              │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ finalize_baseline_learning() - 학습 완료 처리              │
│                                                             │
│ Phase 1: 데이터 유효성 확인                               │
│  - 수집된 샘플: 100개 이상인가?                           │
│  - 없으면: 경고 메시지 + 재학습 요청                      │
│                                                             │
│ Phase 2: 3축 데이터 분리                                  │
│  acc_list = [d['acc_x'] for d in baseline_data]           │
│  vel_list = [d['vel_x'] for d in baseline_data]           │
│  disp_list = [d['disp_x'] for d in baseline_data]         │
│                                                             │
│ Phase 3: 베이스라인 통계 계산                             │
│  → compute_baseline() 호출 (3축 각각)                    │
│                                                             │
│ Phase 4: 적응형 임계치 생성                               │
│  → compute_percentile_based_threshold() 호출              │
│                                                             │
│ Phase 5: UI 업데이트                                      │
│  - 권장 임계치로 입력 필드 설정                           │
│  - 베이스라인 통계 메시지 표시                           │
│  - 상태 "학습 완료 (N개 샘플)"                           │
│  - 텍스트 색상: 초록색                                    │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 핵심 메서드 상세 분석

### 3.1 start_baseline_learning()

```python
def start_baseline_learning(self):
    """베이스라인 학습 시작 (30초)"""
    
    # 1단계: 모드 검증
    if not self.use_sensor:
        QMessageBox.warning(self, "경고", "실시간 센서 모드에서만 학습 가능합니다.")
        return
    #
    # 이유: CSV 재생 모드에서는 의미 없음 (이미 저장된 데이터)
    # CSV 데이터는 이미 특정 조건에서 수집된 것이므로 베이스라인으로 부적합
    
    # 2단계: 센서 활성화 확인
    if not self.data_queue:
        QMessageBox.warning(self, "경고", "센서 데이터가 없습니다. 센서를 먼저 시작하세요.")
        return
    #
    # 이유: 센서에서 데이터가 들어오지 않으면 학습 불가능
    # data_queue는 센서 리더 스레드가 채움
    
    # 3단계: 학습 상태 초기화
    self.is_learning = True              # 학습 모드 활성화
    self.learning_count = 0              # 초 단위 카운터 (0~30)
    self.baseline_data = []              # 이전 학습 데이터 초기화
    
    # 4단계: UI 피드백
    self.btn_start_learning.setEnabled(False)  # 이중 클릭 방지
    self.label_learning_status.setText("학습 중... (0/30초)")
    self.label_learning_status.setStyleSheet("color: orange; font-weight: bold;")
    
    # 실행: 타이머에 의해 update_baseline_learning() 호출 시작
```

**호출 타이밍**:
- 사용자가 "학습 시작 (30초)" 버튼 클릭
- 신호: QPushButton.clicked → start_baseline_learning()

---

### 3.2 update_baseline_learning()

```python
def update_baseline_learning(self):
    """베이스라인 학습 진행 - 타이머에 의해 매 프레임 호출"""
    
    # 1단계: 학습 상태 체크
    if not self.is_learning or not self.data_queue:
        return
    # 이유: 학습이 끝났거나 센서 데이터가 없으면 즉시 종료
    
    # 2단계: 진행 시간 증가
    self.learning_count += 1  # 1 증가
    # 타이머: 33ms (30fps) × 30회 ≈ 1초
    # 따라서 learning_count = 실제 경과 초 단위
    
    # 3단계: UI 진행 표시
    self.label_learning_status.setText(f"학습 중... ({self.learning_count}/30초)")
    # 사용자에게 진행 상황 실시간 표시
    
    # 4단계: 센서 데이터 수집
    with self.data_lock:  # 스레드 안전 (센서 리더 스레드와 동기화)
        recent_data = list(self.data_queue)  # 모든 데이터 복사
    
    # 이유:
    # - data_queue는 센서 리더 스레드가 채움
    # - list()로 복사해야 스레드 안전
    # - recent_data[-1]이 최신 데이터
    
    # 5단계: 최신 샘플 저장
    if recent_data:  # 데이터가 있는가?
        latest = recent_data[-1]  # 큐의 마지막 (최신) 데이터
        
        # 3축 중 X축만 저장 (Y, Z도 가능하지만 X 대표)
        self.baseline_data.append({
            'acc_x': latest['acc_x'],      # 가속도 X축
            'vel_x': latest['vel_x'],      # 진동속도 X축
            'disp_x': latest['disp_x']     # 진동변위 X축
        })
    
    # 6단계: 30초 완료 체크
    if self.learning_count >= 30:  # 30초 이상 경과?
        self.is_learning = False  # 학습 모드 종료
        self.finalize_baseline_learning()  # 최종 처리
```

**타이밍**: update_display() 내부에서 호출
```python
def update_display(self):
    # 베이스라인 학습 진행
    if self.is_learning:
        self.update_baseline_learning()  # ← 매 프레임 호출
    # ...
```

**호출 빈도**: ~30fps = 33ms마다
- 30초 × 30fps ≈ 900회 호출
- 하지만 센서 샘플링은 100Hz = 10ms
- 결과: 100 ~ 300개 샘플 수집

---

### 3.3 finalize_baseline_learning()

```python
def finalize_baseline_learning(self):
    """베이스라인 학습 완료 - 통계 계산 및 임계치 결정"""
    
    # Phase 1: 데이터 유효성
    if len(self.baseline_data) < 100:  # 충분한 샘플?
        QMessageBox.warning(self, "오류", "충분한 데이터가 수집되지 않았습니다.")
        self.btn_start_learning.setEnabled(True)
        self.label_learning_status.setText("학습 실패")
        self.label_learning_status.setStyleSheet("color: red;")
        return
    
    # 이유: 최소 100개 샘플 필요
    # - 30초 × 100Hz = 3000개 가능하지만
    # - UI 업데이트 지연으로 100-300개 정도만 수집
    # - 100개 = 통계적으로 의미 있는 최소값
    
    # Phase 2: 3축 데이터 분리
    acc_list = [d['acc_x'] for d in self.baseline_data]  # 가속도
    vel_list = [d['vel_x'] for d in self.baseline_data]  # 진동속도
    disp_list = [d['disp_x'] for d in self.baseline_data]  # 진동변위
    
    # Phase 3: 베이스라인 통계 계산
    baseline_acc = self.processor.compute_baseline(acc_list)
    baseline_vel = self.processor.compute_baseline(vel_list)
    baseline_disp = self.processor.compute_baseline(disp_list)
    
    # 오류 확인
    if not (baseline_acc and baseline_vel and baseline_disp):
        QMessageBox.warning(self, "오류", "베이스라인 계산 실패")
        self.btn_start_learning.setEnabled(True)
        return
    
    # Phase 4: 적응형 임계치 생성
    acc_threshold = self.processor.compute_percentile_based_threshold(baseline_acc)
    vel_threshold = self.processor.compute_percentile_based_threshold(baseline_vel)
    disp_threshold = self.processor.compute_percentile_based_threshold(baseline_disp)
    
    # Phase 5: UI 업데이트
    self.threshold_inputs['acc_rms_max'].setValue(acc_threshold)
    self.threshold_inputs['vel_peak_max'].setValue(vel_threshold)
    self.threshold_inputs['disp_peak_max'].setValue(disp_threshold)
    
    # Phase 6: 임계치 적용
    self.apply_thresholds()
    
    # Phase 7: 사용자 피드백 메시지
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
```

---

## 4. 통계 계산: compute_baseline()

```python
def compute_baseline(self, data_list):
    """베이스라인 학습 (정상 상태 신호 특성)"""
    
    # 1단계: 데이터 검증
    if not data_list or len(data_list) < 100:
        return None
    
    # 2단계: 배열 변환
    data_array = np.array(data_list, dtype=float)
    
    # 3단계: 유효한 데이터 필터링 (NaN 제거)
    valid = ~np.isnan(data_array)  # NaN이 아닌 인덱스
    if valid.sum() < 100:
        return None
    
    data_valid = data_array[valid]  # NaN 제거된 데이터
    
    # 4단계: 통계량 계산
    baseline = {
        'mean': np.mean(data_valid),           # 평균: μ
        'std': np.std(data_valid),             # 표준편차: σ
        'max': np.max(data_valid),             # 최대값
        'min': np.min(data_valid),             # 최소값
        'rms': np.sqrt(np.mean(data_valid ** 2)),  # 실효값 (RMS)
        'crest_factor': (                      # Crest Factor
            np.max(np.abs(data_valid)) / 
            np.sqrt(np.mean(data_valid ** 2)) 
            if np.sqrt(np.mean(data_valid ** 2)) > 0 else 0
        )
    }
    return baseline
```

### 통계량 해석

```
예시 데이터: 정상 상태 가속도
데이터: [0.1, 0.15, 0.12, 0.18, 0.14, 0.16, ...] (100개)

계산 결과:
┌────────────────┬───────────┬──────────────────────────────────────┐
│ 통계량         │ 값        │ 의미                                 │
├────────────────┼───────────┼──────────────────────────────────────┤
│ mean (μ)       │ 0.145g    │ 정상 상태의 평균 진동 크기           │
│ std (σ)        │ 0.025g    │ 정상 상태의 변동성                   │
│ max            │ 0.20g     │ 정상 상태에서 본 최대값              │
│ min            │ 0.08g     │ 정상 상태에서 본 최소값              │
│ rms            │ 0.148g    │ 에너지 기준 실효값                   │
│ crest_factor   │ 1.38      │ 피크/RMS 비율 (충격 정도)           │
└────────────────┴───────────┴──────────────────────────────────────┘
```

---

## 5. 임계치 계산: compute_percentile_based_threshold()

```python
def compute_percentile_based_threshold(self, baseline):
    """베이스라인 기반 적응형 임계치 (3-σ 규칙)"""
    
    if not baseline:
        return None
    
    # 방법: 3-σ (3 Sigma) 규칙
    # 정상 데이터의 99.73%가 μ ± 3σ 범위 내
    
    threshold = baseline['mean'] + 3 * baseline['std']
    
    # 추가 안전 마진: 최대값의 1.5배
    return max(threshold, baseline['max'] * 1.5)
```

### 임계치 결정 로직

```
예시:
baseline['mean'] = 0.145g
baseline['std'] = 0.025g
baseline['max'] = 0.20g

계산:
1. 3σ 규칙: 0.145 + 3×0.025 = 0.220g
2. 최대값 마진: 0.20 × 1.5 = 0.30g
3. 최종 임계치: max(0.220, 0.30) = 0.30g

해석:
- 정상 데이터 범위: 0.095 ~ 0.220g (μ ± 3σ)
- 경보 기준: 0.30g 초과
- 마진율: (0.30 - 0.220) / 0.220 = 36.4%

결론: 정상 상태에서 벗어나 명백한 이상이 있을 때만 경보 발생
```

---

## 6. 전체 흐름 타이밍 다이어그램

```
시간축 →

0초    시작                학습 시작 클릭
│
├─ 0~0.5초: 센서 시작 대기
│
├─ 0.5~30초: 베이스라인 학습 (learning_count 0→30)
│
│  센서 리더 스레드 (100Hz):
│  ├─ 10ms: 샘플 1, 2, 3, ...
│  └─ 기본 인터벌 0.01s (100Hz)
│
│  GUI 타이머 (30fps):
│  ├─ 33ms: update_baseline_learning() 호출 #1
│  ├─ 66ms: update_baseline_learning() 호출 #2
│  ├─ 99ms: update_baseline_learning() 호출 #3
│  ...
│  └─ 1000ms: learning_count = 1
│
├─ 30초: learning_count >= 30 → 학습 종료 신호
│
├─ 31초: finalize_baseline_learning() 실행
│  ├─ 데이터 검증
│  ├─ 통계 계산
│  ├─ 임계치 결정
│  └─ UI 업데이트
│
└─ 32초: 완료, 사용자에게 메시지 표시
```

---

## 7. 실제 사용 시나리오

### 시나리오: 신규 모터 설치

```
Step 1: 센서 연결 및 시작
  → 포트, 보드율 설정
  → "센서 시작" 클릭
  → data_queue에 센서 데이터 채워짐

Step 2: 정상 상태 확인
  → 모터 정상 운전 상태 확인
  → 온도, 진동 정상 범위 확인

Step 3: 베이스라인 학습
  → 탭3 "학습 시작 (30초)" 클릭
  → 30초 동안 센서 데이터 자동 수집
  → "학습 중... (0/30초)" 진행 표시

Step 4: 학습 완료
  → 메시지 표시:
    ```
    베이스라인 학습 완료!
    
    추천 임계치:
    - 가속도 RMS: 0.30g
    - 진동속도 피크: 85.5mm/s
    - 진동변위 피크: 450μm
    
    베이스라인 통계:
    - 가속도: μ=0.145g, σ=0.025g
    - 진동속도: μ=25.2mm/s, σ=20.1mm/s
    - 진동변위: μ=300μm, σ=50μm
    ```

Step 5: 임계치 자동 적용
  → 입력 필드에 추천값 설정
  → "적용" 버튼 클릭
  → 이후 모니터링 시작

Step 6: 지속적 모니터링
  → 실제 데이터 vs 임계치 비교
  → 임계치 초과 시 경보 발생
```

---

## 8. 베이스라인 학습의 장단점

### ✅ 장점

1. **자동화**: 사용자가 임계치를 직접 설정할 필요 없음
2. **적응형**: 각 모터/환경에 맞는 개별 임계치
3. **통계적 근거**: 3-σ 규칙 (정상 데이터의 99.73%)
4. **신뢰성**: 정상 상태에서의 변동성을 반영
5. **시간 절감**: 30초만에 학습 완료

### ⚠️ 한계

1. **정상 상태 가정**: 학습 중 정상 상태여야 함
2. **샘플 크기**: 100~300개만 수집 (크면 더 정확, 하지만 시간 소요)
3. **단일 축**: 현재는 X축만 학습 (Y, Z 확장 가능)
4. **환경 변화**: 작동 조건 변화 시 재학습 필요
5. **장기 안정성**: 센서 드리프트 고려 없음

---

## 9. 개선 아이디어

### 다중 프로파일 학습
```python
# 조건별 베이스라인 저장
self.baselines = {
    'normal_speed': baseline_1,    # 정상 속도
    'high_speed': baseline_2,      # 고속
    'low_load': baseline_3,        # 저하중
    'high_load': baseline_4        # 고하중
}

# 현재 조건에 맞는 베이스라인 자동 선택
```

### 3축 통합 학습
```python
# 3축 X, Y, Z 모두 학습
for axis in ['x', 'y', 'z']:
    data_list = [d[f'acc_{axis}'] for d in baseline_data]
    baseline[f'acc_{axis}'] = compute_baseline(data_list)
```

### 주기적 재학습
```python
# 매주 1회 자동 재학습
# 센서 드리프트, 환경 변화 추적
```

---

## 결론

베이스라인 학습은 **정상 상태의 신호 특성을 통계적으로 학습**하여 **자동으로 최적의 임계치를 결정**하는 방식입니다.

- **데이터 수집**: 30초 동안 센서 데이터 자동 저장
- **통계 계산**: 평균, 표준편차, RMS 등 6개 통계량
- **임계치 결정**: 3-σ 규칙 + 안전 마진 적용
- **결과**: 정상/이상 구분의 신뢰성 향상

이를 통해 모터의 개별 특성을 반영한 **맞춤형 모니터링**이 가능합니다! 🎯
