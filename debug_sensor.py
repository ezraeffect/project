"""
센서 통신 디버깅 스크립트
실제로 센서에서 어떤 데이터가 오는지 확인합니다.
"""

import serial
import serial.tools.list_ports
import time


def calculate_crc(data: bytes) -> bytes:
    """Modbus RTU CRC-16 계산"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    crc_low = crc & 0xFF
    crc_high = (crc >> 8) & 0xFF
    return bytes([crc_low, crc_high])


def parse_int16(data: bytes, offset: int) -> int:
    """16비트 부호 있는 정수 파싱"""
    high = data[offset]
    low = data[offset + 1]
    value = (high << 8) | low
    if value & 0x8000:
        value = -(0x10000 - value)
    return value


def parse_uint16(data: bytes, offset: int) -> int:
    """16비트 부호 없는 정수 파싱"""
    high = data[offset]
    low = data[offset + 1]
    return (high << 8) | low


def list_ports():
    """사용 가능한 포트 나열"""
    ports = list(serial.tools.list_ports.comports())
    print("사용 가능한 COM 포트:")
    for p in ports:
        print(f"  - {p.device}: {p.description}")
    return [p.device for p in ports]


def read_registers(ser, slave_id: int, address: int, count: int) -> bytes:
    """레지스터 읽기"""
    command_data = bytes([
        slave_id,
        0x03,
        (address >> 8) & 0xFF,
        address & 0xFF,
        (count >> 8) & 0xFF,
        count & 0xFF
    ])
    crc = calculate_crc(command_data)
    command = command_data + crc
    
    print(f"\n[TX] {command.hex(' ').upper()}")
    
    ser.write(command)
    time.sleep(0.05)  # 응답 대기
    
    expected_length = 3 + (count * 2) + 2
    response = ser.read(expected_length)
    
    if response:
        print(f"[RX] {response.hex(' ').upper()} (길이: {len(response)})")
    else:
        print("[RX] 응답 없음!")
        return None
    
    # CRC 검증
    if len(response) >= 3:
        received_crc = response[-2:]
        calculated_crc = calculate_crc(response[:-2])
        if received_crc != calculated_crc:
            print(f"[!] CRC 오류! 수신: {received_crc.hex()}, 계산: {calculated_crc.hex()}")
            return None
    
    return response[3:-2] if len(response) > 5 else None


def main():
    print("=" * 60)
    print("WTVB01-485 센서 통신 디버깅")
    print("=" * 60)
    
    ports = list_ports()
    if not ports:
        print("사용 가능한 포트가 없습니다!")
        return
    
    # 사용자 입력
    port = input(f"\nCOM 포트 입력 (예: COM3): ").strip()
    if not port:
        port = ports[0] if ports else "COM3"
    
    baudrate = input("보드레이트 입력 (기본: 9600): ").strip()
    baudrate = int(baudrate) if baudrate else 9600
    
    slave_id = input("Slave ID 입력 (기본: 0x50=80): ").strip()
    slave_id = int(slave_id, 16) if slave_id.startswith("0x") else int(slave_id) if slave_id else 0x50
    
    print(f"\n연결 시도: {port}, {baudrate}bps, Slave ID: 0x{slave_id:02X}")
    
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0
        )
        print("연결 성공!")
        
        # 버퍼 클리어
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        print("\n" + "=" * 60)
        print("레지스터 읽기 테스트")
        print("=" * 60)
        
        # 1. 가속도 읽기 (0x34~0x36)
        print("\n--- 가속도 (0x34~0x36) ---")
        data = read_registers(ser, slave_id, 0x34, 3)
        if data and len(data) >= 6:
            ax = parse_int16(data, 0)
            ay = parse_int16(data, 2)
            az = parse_int16(data, 4)
            print(f"  Raw: AX={ax}, AY={ay}, AZ={az}")
            print(f"  변환: AX={ax/32768*16:.4f}g, AY={ay/32768*16:.4f}g, AZ={az/32768*16:.4f}g")
        
        time.sleep(0.1)
        
        # 2. 진동 속도 읽기 (0x3A~0x3C)
        print("\n--- 진동 속도 (0x3A~0x3C) ---")
        data = read_registers(ser, slave_id, 0x3A, 3)
        if data and len(data) >= 6:
            vx = parse_int16(data, 0)
            vy = parse_int16(data, 2)
            vz = parse_int16(data, 4)
            print(f"  Raw: VX={vx}, VY={vy}, VZ={vz}")
            print(f"  매뉴얼 공식: VX={vx}mm/s, VY={vy}mm/s, VZ={vz}mm/s")
            print(f"  /100 적용시: VX={vx/100:.2f}mm/s, VY={vy/100:.2f}mm/s, VZ={vz/100:.2f}mm/s")
        
        time.sleep(0.1)
        
        # 3. 온도 읽기 (0x40)
        print("\n--- 온도 (0x40) ---")
        data = read_registers(ser, slave_id, 0x40, 1)
        if data and len(data) >= 2:
            temp = parse_int16(data, 0)
            print(f"  Raw: TEMP={temp}")
            print(f"  변환: {temp/100:.2f}°C")
        
        time.sleep(0.1)
        
        # 4. 진동 변위 읽기 (0x41~0x43)
        print("\n--- 진동 변위 (0x41~0x43) ---")
        data = read_registers(ser, slave_id, 0x41, 3)
        if data and len(data) >= 6:
            dx = parse_int16(data, 0)
            dy = parse_int16(data, 2)
            dz = parse_int16(data, 4)
            print(f"  Raw: DX={dx}, DY={dy}, DZ={dz}")
            print(f"  변환: DX={dx}um, DY={dy}um, DZ={dz}um")
        
        time.sleep(0.1)
        
        # 5. 진동 주파수 읽기 (0x44~0x46)
        print("\n--- 진동 주파수 (0x44~0x46) ---")
        data = read_registers(ser, slave_id, 0x44, 3)
        if data and len(data) >= 6:
            hx = parse_int16(data, 0)
            hy = parse_int16(data, 2)
            hz = parse_int16(data, 4)
            print(f"  Raw: HX={hx}, HY={hy}, HZ={hz}")
            print(f"  변환: HX={hx/10:.1f}Hz, HY={hy/10:.1f}Hz, HZ={hz/10:.1f}Hz")
        
        # 센서 설정 확인
        print("\n" + "=" * 60)
        print("센서 설정 확인")
        print("=" * 60)
        
        # Cutoff Frequency 읽기 (0x63, 0x64)
        print("\n--- Cutoff Frequency (0x63, 0x64) ---")
        data = read_registers(ser, slave_id, 0x63, 2)
        if data and len(data) >= 4:
            cutoff_int = parse_uint16(data, 0)
            cutoff_frac = parse_uint16(data, 2)
            print(f"  Raw: Integer={cutoff_int}, Fraction={cutoff_frac}")
            print(f"  Cutoff Frequency: {cutoff_int}.{cutoff_frac:02d} Hz")
            print(f"  (이 주파수 미만의 진동은 필터링됩니다)")
        
        # 연속 읽기 테스트
        print("\n" + "=" * 60)
        print("연속 읽기 테스트 (10초)")
        print("센서를 흔들어보세요!")
        print("=" * 60)
        
        start_time = time.time()
        while time.time() - start_time < 10:
            data = read_registers(ser, slave_id, 0x3A, 3)
            if data and len(data) >= 6:
                vx = parse_int16(data, 0)
                vy = parse_int16(data, 2)
                vz = parse_int16(data, 4)
                elapsed = time.time() - start_time
                if vx != 0 or vy != 0 or vz != 0:
                    print(f"  [{elapsed:.1f}s] VX={vx}, VY={vy}, VZ={vz} *** 진동 감지됨! ***")
                else:
                    print(f"  [{elapsed:.1f}s] VX={vx}, VY={vy}, VZ={vz}")
            time.sleep(0.3)
        
        ser.close()
        print("\n연결 종료")
        
    except serial.SerialException as e:
        print(f"연결 오류: {e}")
    except Exception as e:
        print(f"오류: {e}")


if __name__ == "__main__":
    main()
