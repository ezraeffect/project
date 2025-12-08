"""
WTVB01-485 Vibration Sensor Communication Module
Modbus RTU 프로토콜을 사용한 센서 통신 구현
"""

import serial
import struct
import time
from typing import Tuple, Optional, List
from enum import IntEnum


class ModbusRegister(IntEnum):
    """Modbus 레지스터 주소"""
    SAVE = 0x00
    BAUD = 0x04
    IICADDR = 0x1A
    YYMM = 0x30
    DDH = 0x31
    MMSS = 0x32
    MS = 0x33
    AX = 0x34          # X축 가속도
    AY = 0x35          # Y축 가속도
    AZ = 0x36          # Z축 가속도
    VX = 0x3A          # X축 진동 속도 (mm/s)
    VY = 0x3B          # Y축 진동 속도 (mm/s)
    VZ = 0x3C          # Z축 진동 속도 (mm/s)
    TEMP = 0x40        # 칩 온도
    DX = 0x41          # X축 진동 변위 (um)
    DY = 0x42          # Y축 진동 변위 (um)
    DZ = 0x43          # Z축 진동 변위 (um)
    HX = 0x44          # X축 진동 주파수 (Hz)
    HY = 0x45          # Y축 진동 주파수 (Hz)
    HZ = 0x46          # Z축 진동 주파수 (Hz)
    FDNFX = 0x47       # 고속모드 X축 진동 변위
    FDNFY = 0x48       # 고속모드 Y축 진동 변위
    FDNFZ = 0x49       # 고속모드 Z축 진동 변위
    MODBUSMODEL = 0x62 # 고속모드
    CUTOFFFREQI = 0x63 # 차단주파수 정수부
    CUTOFFFREQF = 0x64 # 차단주파수 소수부
    SAMPLEFREQ = 0x65  # 감지 주기


class BaudRate(IntEnum):
    """통신 속도"""
    BAUD_4800 = 0x01
    BAUD_9600 = 0x02
    BAUD_19200 = 0x03
    BAUD_38400 = 0x04
    BAUD_57600 = 0x05
    BAUD_115200 = 0x06
    BAUD_230400 = 0x07


class SensorData:
    """센서 데이터를 저장하는 클래스"""
    def __init__(self):
        self.ax = 0.0  # X축 가속도 (g)
        self.ay = 0.0  # Y축 가속도 (g)
        self.az = 0.0  # Z축 가속도 (g)
        self.vx = 0.0  # X축 진동 속도 (mm/s)
        self.vy = 0.0  # Y축 진동 속도 (mm/s)
        self.vz = 0.0  # Z축 진동 속도 (mm/s)
        self.dx = 0.0  # X축 진동 변위 (um)
        self.dy = 0.0  # Y축 진동 변위 (um)
        self.dz = 0.0  # Z축 진동 변위 (um)
        self.hx = 0.0  # X축 진동 주파수 (Hz)
        self.hy = 0.0  # Y축 진동 주파수 (Hz)
        self.hz = 0.0  # Z축 진동 주파수 (Hz)
        self.temp = 0.0  # 온도 (°C)
        self.timestamp = time.time()

    def to_dict(self):
        """딕셔너리로 변환"""
        return {
            'ax': self.ax, 'ay': self.ay, 'az': self.az,
            'vx': self.vx, 'vy': self.vy, 'vz': self.vz,
            'dx': self.dx, 'dy': self.dy, 'dz': self.dz,
            'hx': self.hx, 'hy': self.hy, 'hz': self.hz,
            'temp': self.temp, 'timestamp': self.timestamp
        }

    def __repr__(self):
        return (f"SensorData(vx={self.vx:.2f}, vy={self.vy:.2f}, vz={self.vz:.2f}, "
                f"dx={self.dx:.1f}, dy={self.dy:.1f}, dz={self.dz:.1f}, "
                f"hx={self.hx:.2f}, hy={self.hy:.2f}, hz={self.hz:.2f}, "
                f"temp={self.temp:.2f})")


class CRCCalculator:
    """Modbus CRC 계산기"""
    
    @staticmethod
    def calculate_crc(data: bytes) -> bytes:
        """
        Modbus RTU CRC-16 계산
        
        Args:
            data: CRC를 계산할 데이터
            
        Returns:
            CRC 값 (2바이트: CRC_LOW, CRC_HIGH)
        """
        crc = 0xFFFF
        
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        
        # Little-endian 형식 (CRC_LOW, CRC_HIGH)
        crc_low = crc & 0xFF
        crc_high = (crc >> 8) & 0xFF
        
        return bytes([crc_low, crc_high])
    
    @staticmethod
    def verify_crc(data: bytes) -> bool:
        """CRC 검증"""
        if len(data) < 3:
            return False
        
        message = data[:-2]
        received_crc = data[-2:]
        calculated_crc = CRCCalculator.calculate_crc(message)
        
        return received_crc == calculated_crc


class ModbusRTU:
    """Modbus RTU 통신 클래스"""
    
    def __init__(self, port: str = 'COM1', baudrate: int = 9600, 
                 timeout: float = 1.0, slave_id: int = 0x50):
        """
        Modbus RTU 초기화
        
        Args:
            port: COM 포트 (예: 'COM1', '/dev/ttyUSB0')
            baudrate: 통신 속도 (기본값: 9600)
            timeout: 타임아웃 (초)
            slave_id: Modbus 슬레이브 ID (기본값: 0x50)
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.slave_id = slave_id
        self.serial = None
        self.is_connected = False
        self.last_error = None  # 마지막 에러 메시지
    
    def connect(self) -> bool:
        """포트 연결"""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout
            )
            self.is_connected = True
            print(f"Connected to {self.port} at {self.baudrate} bps")
            return True
        except serial.SerialException as e:
            print(f"Failed to connect: {e}")
            self.is_connected = False
            return False
    
    def disconnect(self) -> None:
        """포트 해제"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.is_connected = False
            print(f"Disconnected from {self.port}")
    
    def _send_command(self, command: bytes) -> bool:
        """
        명령 전송
        
        Args:
            command: 전송할 명령 (CRC 포함)
            
        Returns:
            성공 여부
        """
        if not self.is_connected or not self.serial:
            return False
        
        try:
            self.serial.write(command)
            return True
        except serial.SerialException as e:
            print(f"Send error: {e}")
            return False
    
    def _read_response(self, expected_length: Optional[int] = None) -> Optional[bytes]:
        """
        응답 수신
        
        Args:
            expected_length: 예상 길이 (생략시 모두 읽음)
            
        Returns:
            수신한 데이터 또는 None
        """
        if not self.is_connected or not self.serial:
            return None
        
        try:
            if expected_length:
                response = self.serial.read(expected_length)
            else:
                response = self.serial.read_all()
            
            if len(response) == 0:
                return None
            
            return response
        except serial.SerialException as e:
            print(f"Read error: {e}")
            return None
    
    def read_registers(self, address: int, count: int = 1) -> Optional[bytes]:
        """
        레지스터 읽기 (Function Code 0x03)
        
        Args:
            address: 레지스터 주소
            count: 읽을 레지스터 개수
            
        Returns:
            읽은 데이터 (바이트 배열) 또는 None
        """
        # 명령 구성: [Slave ID] [Function Code] [Address H] [Address L] [Count H] [Count L] [CRC L] [CRC H]
        command_data = bytes([
            self.slave_id,
            0x03,  # Function Code: Read Holding Registers
            (address >> 8) & 0xFF,
            address & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF
        ])
        
        # CRC 계산 및 추가
        crc = CRCCalculator.calculate_crc(command_data)
        command = command_data + crc
        
        # 명령 전송
        if not self._send_command(command):
            self.last_error = f"Failed to send command for register {address:#06x}"
            print(self.last_error)
            return None
        
        # 응답 수신: [Slave ID] [Function Code] [Byte Count] [Data...] [CRC L] [CRC H]
        # 데이터 바이트 수 = count * 2
        expected_response_length = 3 + (count * 2) + 2  # ID + FC + ByteCount + Data + CRC
        
        time.sleep(0.05)  # 응답 대기
        response = self._read_response(expected_response_length)
        
        if not response:
            self.last_error = f"No response for register {address:#06x} (expected {expected_response_length} bytes)"
            print(self.last_error)
            return None
        
        # CRC 검증
        if not CRCCalculator.verify_crc(response):
            self.last_error = f"CRC verification failed for register {address:#06x}"
            print(self.last_error)
            return None
        
        # 데이터 추출 (CRC 제외)
        data = response[3:-2]
        return data
    
    def write_register(self, address: int, value: int) -> bool:
        """
        레지스터 쓰기 (Function Code 0x06)
        
        Args:
            address: 레지스터 주소
            value: 쓸 값
            
        Returns:
            성공 여부
        """
        # 명령 구성: [Slave ID] [Function Code] [Address H] [Address L] [Value H] [Value L] [CRC L] [CRC H]
        command_data = bytes([
            self.slave_id,
            0x06,  # Function Code: Write Single Register
            (address >> 8) & 0xFF,
            address & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF
        ])
        
        # CRC 계산 및 추가
        crc = CRCCalculator.calculate_crc(command_data)
        command = command_data + crc
        
        # 명령 전송
        if not self._send_command(command):
            return False
        
        # 응답 수신 (에코)
        time.sleep(0.05)
        response = self._read_response(8)  # 응답 길이는 명령과 동일
        
        if not response:
            return False
        
        # CRC 검증
        if not CRCCalculator.verify_crc(response):
            print("CRC verification failed on write response")
            return False
        
        return True


class WTVBSensor:
    """WTVB01-485 센서 클래스"""
    
    def __init__(self, port: str = 'COM1', baudrate: int = 9600, slave_id: int = 0x50):
        """
        센서 초기화
        
        Args:
            port: COM 포트
            baudrate: 통신 속도 (기본값: 9600)
            slave_id: Modbus 슬레이브 ID (기본값: 0x50)
        """
        self.modbus = ModbusRTU(port, baudrate, timeout=1.0, slave_id=slave_id)
        self.current_data = SensorData()
    
    def connect(self) -> bool:
        """센서 연결"""
        return self.modbus.connect()
    
    def disconnect(self) -> None:
        """센서 연결 해제"""
        self.modbus.disconnect()
    
    @property
    def is_connected(self) -> bool:
        """연결 상태"""
        return self.modbus.is_connected
    
    def _parse_int16(self, data: bytes, offset: int) -> int:
        """16비트 부호 있는 정수 파싱"""
        if offset + 1 >= len(data):
            return 0
        high = data[offset]
        low = data[offset + 1]
        value = (high << 8) | low
        
        # 부호 처리 (2의 보수)
        if value & 0x8000:
            value = -(0x10000 - value)
        
        return value
    
    def _parse_uint16(self, data: bytes, offset: int) -> int:
        """16비트 부호 없는 정수 파싱"""
        if offset + 1 >= len(data):
            return 0
        high = data[offset]
        low = data[offset + 1]
        return (high << 8) | low
    
    def read_vibration_velocity(self) -> Optional[SensorData]:
        """
        3축 진동 속도 읽기 (레지스터 0x3A~0x3C)
        단위: mm/s (부호 있는 16비트 정수)
        
        Note: 제조사 프로토콜에서는 값이 100배 확대되어 전송되므로 100으로 나눔
        
        Returns:
            센서 데이터 또는 None
        """
        data = self.modbus.read_registers(ModbusRegister.VX, 3)
        if not data or len(data) < 6:
            return None
        
        vx = self._parse_int16(data, 0) / 100.0  # mm/s (signed)
        vy = self._parse_int16(data, 2) / 100.0  # mm/s (signed)
        vz = self._parse_int16(data, 4) / 100.0  # mm/s (signed)
        
        self.current_data.vx = vx
        self.current_data.vy = vy
        self.current_data.vz = vz
        
        return self.current_data
    
    def read_vibration_displacement(self) -> Optional[SensorData]:
        """
        3축 진동 변위 읽기 (레지스터 0x41~0x43)
        
        Note: 생 값은 정수 um이지만, 소수점 표현을 위해 실수로 변환
        
        Returns:
            센서 데이터 또는 None
        """
        data = self.modbus.read_registers(ModbusRegister.DX, 3)
        if not data or len(data) < 6:
            return None
        
        dx = float(self._parse_int16(data, 0))  # um (converted to float)
        dy = float(self._parse_int16(data, 2))  # um (converted to float)
        dz = float(self._parse_int16(data, 4))  # um (converted to float)
        
        self.current_data.dx = dx
        self.current_data.dy = dy
        self.current_data.dz = dz
        
        return self.current_data
    
    def read_vibration_frequency(self) -> Optional[SensorData]:
        """
        3축 진동 주파수 읽기 (레지스터 0x44~0x46)
        단위: Hz (실제값 / 10, 부호 있는 16비트 정수)
        
        Returns:
            센서 데이터 또는 None
        """
        data = self.modbus.read_registers(ModbusRegister.HX, 3)
        if not data or len(data) < 6:
            return None
        
        hx = self._parse_int16(data, 0) / 10.0  # Hz (signed)
        hy = self._parse_int16(data, 2) / 10.0  # Hz (signed)
        hz = self._parse_int16(data, 4) / 10.0  # Hz (signed)
        
        self.current_data.hx = hx
        self.current_data.hy = hy
        self.current_data.hz = hz
        
        return self.current_data
    
    def read_acceleration(self) -> Optional[SensorData]:
        """
        3축 가속도 읽기 (레지스터 0x34~0x36)
        단위: g (16g 범위)
        
        Returns:
            센서 데이터 또는 None
        """
        data = self.modbus.read_registers(ModbusRegister.AX, 3)
        if not data or len(data) < 6:
            return None
        
        ax_raw = self._parse_int16(data, 0)
        ay_raw = self._parse_int16(data, 2)
        az_raw = self._parse_int16(data, 4)
        
        # 변환: g = raw / 32768 * 16g
        self.current_data.ax = ax_raw / 32768.0 * 16.0
        self.current_data.ay = ay_raw / 32768.0 * 16.0
        self.current_data.az = az_raw / 32768.0 * 16.0
        
        return self.current_data
    
    def read_temperature(self) -> Optional[SensorData]:
        """
        칩 온도 읽기 (레지스터 0x40)
        단위: °C (실제값 / 100)
        
        Returns:
            센서 데이터 또는 None
        """
        data = self.modbus.read_registers(ModbusRegister.TEMP, 1)
        if not data or len(data) < 2:
            return None
        
        temp_raw = self._parse_int16(data, 0)
        self.current_data.temp = temp_raw / 100.0
        
        return self.current_data
    
    def write_register(self, address: int, value: int) -> bool:
        """
        레지스터 쓰기 (Function Code 0x06)
        
        Args:
            address: 레지스터 주소
            value: 쓸 값
            
        Returns:
            성공 여부
        """
        return self.modbus.write_register(address, value)
    
    def read_all_data(self) -> Optional[SensorData]:
        """
        모든 데이터 읽기 (한 번에 모든 값 수집)
        
        Returns:
            센서 데이터 또는 None
        """
        # 각 데이터를 순차적으로 읽기
        if not self.read_vibration_velocity():
            return None
        if not self.read_vibration_displacement():
            return None
        if not self.read_vibration_frequency():
            return None
        if not self.read_acceleration():
            return None
        if not self.read_temperature():
            return None
        
        # 현재 데이터의 타임스탐프 업데이트
        self.current_data.timestamp = time.time()
        
        # 버퍼에 저장하기 위해 새로운 객체 생성 (참조 문제 해결)
        result = SensorData()
        result.ax = self.current_data.ax
        result.ay = self.current_data.ay
        result.az = self.current_data.az
        result.vx = self.current_data.vx
        result.vy = self.current_data.vy
        result.vz = self.current_data.vz
        result.dx = self.current_data.dx
        result.dy = self.current_data.dy
        result.dz = self.current_data.dz
        result.hx = self.current_data.hx
        result.hy = self.current_data.hy
        result.hz = self.current_data.hz
        result.temp = self.current_data.temp
        result.timestamp = self.current_data.timestamp
        
        return result
    
    def set_baudrate(self, baudrate: BaudRate) -> bool:
        """
        통신 속도 변경
        
        Args:
            baudrate: 변경할 통신 속도
            
        Returns:
            성공 여부
        """
        # 잠금 해제 (10초 유효)
        if not self.modbus.write_register(ModbusRegister.SAVE, 0x0069):
            return False
        
        time.sleep(0.1)
        
        # 속도 변경
        if not self.modbus.write_register(ModbusRegister.BAUD, int(baudrate)):
            return False
        
        time.sleep(0.1)
        
        # 저장
        if not self.modbus.write_register(ModbusRegister.SAVE, 0x0000):
            return False
        
        return True
    
    def set_slave_id(self, new_id: int) -> bool:
        """
        Modbus 슬레이브 ID 변경
        
        Args:
            new_id: 새로운 ID (0x01 ~ 0x7F)
            
        Returns:
            성공 여부
        """
        if new_id < 0x01 or new_id > 0x7F:
            return False
        
        # 잠금 해제
        if not self.modbus.write_register(ModbusRegister.SAVE, 0x0069):
            return False
        
        time.sleep(0.1)
        
        # ID 변경
        if not self.modbus.write_register(ModbusRegister.IICADDR, new_id):
            return False
        
        time.sleep(0.1)
        
        # 저장
        if not self.modbus.write_register(ModbusRegister.SAVE, 0x0000):
            return False
        
        # 내부 ID 업데이트
        self.modbus.slave_id = new_id
        
        return True


def get_available_ports() -> List[str]:
    """
    사용 가능한 COM 포트 목록 반환
    
    Returns:
        포트 목록 (예: ['COM1', 'COM3', ...])
    """
    import serial.tools.list_ports
    ports = []
    for port, desc, hwid in serial.tools.list_ports.comports():
        ports.append(port)
    return ports


if __name__ == "__main__":
    # 테스트 코드
    print("Available COM ports:", get_available_ports())
    
    # 센서 연결 및 데이터 읽기 테스트
    # sensor = WTVBSensor(port='COM3', baudrate=9600, slave_id=0x50)
    # if sensor.connect():
    #     for _ in range(5):
    #         data = sensor.read_all_data()
    #         print(data)
    #         time.sleep(1)
    #     sensor.disconnect()
