import serial
import time
from typing import Iterable, Optional

SENSOR_PORT = "COM4"
SENSOR_BAUD = 115200
ARDUINO_PORT = "COM3"
ARDUINO_BAUD = 9600
ALERT_THRESHOLD = 15
ALERT_COMMAND = b"R"
UNLOCK_CMD = bytes.fromhex("FF AA 69 88 B5")
SAVE_CMD = bytes.fromhex("FF AA 00 00 00")
READ_PREFIX = bytes.fromhex("FF AA 27")
HEADER = bytes.fromhex("55 71")
READ_BLOCK_LEN = 20

REG_RATE = 0x03        # 데이터 반환 레이트 (Hz 선택)
REG_SAMPLEFREQ = 0x5F  # 감지 주기 (1~100Hz)
REG_FREQ_START = 0x44  # HZX 시작 주소


def build_read_cmd(reg: int) -> bytes:
    return READ_PREFIX + bytes([reg & 0xFF, 0x00])


def build_write_cmd(reg: int, value: int) -> bytes:
    lo = value & 0xFF
    hi = (value >> 8) & 0xFF
    return bytes([0xFF, 0xAA, reg & 0xFF, lo, hi])


def read_register_block(raw: bytes) -> list[int]:
    data = raw[4:20]
    out = []
    for i in range(0, len(data), 2):
        out.append(data[i] | (data[i + 1] << 8))
    return out


def _read_packet(ser: serial.Serial, timeout: float = 0.5) -> Optional[bytes]:
    """헤더 동기화를 포함하여 완전한 20바이트 패킷을 읽어온다."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        first = ser.read(1)
        if not first:
            continue
        if first != HEADER[:1]:
            continue
        second = ser.read(1)
        if second != HEADER[1:]:
            continue
        rest = ser.read(READ_BLOCK_LEN - 2)
        if len(rest) != READ_BLOCK_LEN - 2:
            print("[warn] partial packet received")
            continue
        return first + second + rest
    return None


def read_registers(ser: serial.Serial, reg: int, retries: int = 3) -> Optional[list[int]]:
    for attempt in range(retries):
        ser.reset_input_buffer()
        ser.write(build_read_cmd(reg))
        raw = _read_packet(ser)
        if raw is None:
            print("[warn] read timeout (no full packet)")
            continue
        start_addr = raw[2] | (raw[3] << 8)
        if start_addr != reg:
            print(f"[warn] unexpected start addr {start_addr:#04x} (expect {reg:#04x}), raw={raw.hex(' ')}")
            continue
        block = read_register_block(raw)
        return block
    return None


def send_commands(ser: serial.Serial, cmds: Iterable[bytes], delay: float = 0.05) -> None:
    for cmd in cmds:
        ser.write(cmd)
        time.sleep(delay)


def configure_sensor(ser: serial.Serial, rate_hz: int = 10, sample_freq: int = 100) -> None:
    rate_map = {1: 0x03, 2: 0x04, 5: 0x05, 10: 0x06, 20: 0x07, 50: 0x08, 100: 0x09, 200: 0x0A}
    rate_value = rate_map.get(rate_hz)
    if rate_value is None:
        raise ValueError(f"지원하지 않는 RATE: {rate_hz}Hz")
    ser.reset_input_buffer()
    send_commands(ser, [UNLOCK_CMD, build_write_cmd(REG_RATE, rate_value), SAVE_CMD], delay=0.1)
    send_commands(ser, [UNLOCK_CMD, build_write_cmd(REG_SAMPLEFREQ, sample_freq), SAVE_CMD], delay=0.1)


def verify_settings(ser: serial.Serial) -> None:
    rate_block = read_registers(ser, REG_RATE)
    sample_block = read_registers(ser, REG_SAMPLEFREQ)
    if rate_block:
        print(f"[info] RATE register raw: {rate_block[0]:#04x}")
    if sample_block:
        print(f"[info] SAMPLEFREQ raw: {sample_block[0]}")


def main():
    with serial.Serial(SENSOR_PORT, SENSOR_BAUD, timeout=0.2) as sensor, \
            serial.Serial(ARDUINO_PORT, ARDUINO_BAUD, timeout=0.2) as arduino:
        sensor.reset_input_buffer()
        configure_sensor(sensor)
        verify_settings(sensor)
        last_print = time.perf_counter()
        while True:
            values = read_registers(sensor, REG_FREQ_START)
            now = time.perf_counter()
            if values:
                dx, dy, dz = values[0], values[2], values[4]
                delta = now - last_print
                print(f"{delta:6.3f}s | X: {dx:4d} Hz, Y: {dy:4d} Hz, Z: {dz:4d} Hz")
                last_print = now
                if dx >= ALERT_THRESHOLD:
                    arduino.write(ALERT_COMMAND)
                    print("[info] ALERT sent to Arduino")
            else:
                print("[warn] read timeout (after retries)")
            time.sleep(0.05)


if __name__ == "__main__":
    main()
