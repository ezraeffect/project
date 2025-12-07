import serial
import time
from typing import Optional

PORT = "COM3"
BAUD = 115200
READ_PREFIX = bytes.fromhex("FF AA 27")
HEADER = bytes.fromhex("55 71")
READ_BLOCK_LEN = 20

REG_FREQ_START = 0x44  # HZX 시작 address (reads HZX,HZY,HZZ)


def build_read_cmd(reg: int) -> bytes:
    return READ_PREFIX + bytes([reg & 0xFF, 0x00])



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


# The script is intentionally minimal: it reads the 3 frequency registers (HZX/HZY/HZZ)
# starting at REG_FREQ_START and prints them. Removed write/setting helpers.


def main():
    with serial.Serial(PORT, BAUD, timeout=0.2) as ser:
        ser.reset_input_buffer()
        last_print = time.perf_counter()
        while True:
            values = read_registers(ser, REG_FREQ_START)
            now = time.perf_counter()
            if values:
                # values[] is a consecutive list of 16-bit registers starting at 0x44:
                # values[0] = 0x44 HZX (X freq), values[1] = 0x45 HZY (Y freq), values[2] = 0x46 HZZ (Z freq)
                dx, dy, dz = values[0], values[1], values[2]
                # detect obviously invalid readings (e.g. 0xFFFF/near-0xFFFF) and log raw values
                if any(v >= 0xFF00 for v in (dx, dy, dz)):
                    print(f"[debug] suspicious reading, raw values={values}")
                print(f"{now:6.3f}s | X: {dx:4d} Hz, Y: {dy:4d} Hz, Z: {dz:4d} Hz")
                #print(f"RAW: {[hex(v) for v in values]}")
                last_print = now
            else:
                print("[warn] read timeout (after retries)")
            time.sleep(0.05)


if __name__ == "__main__":
    main()
