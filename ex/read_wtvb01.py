# read_wtvb01.py
"""
Simple Modbus-RTU reader for WTVB01-485 (Witmotion) using a USB->RS485 adapter.
Reads acceleration, velocity, displacement, frequency and temperature registers
and prints human-readable values.

Usage example (PowerShell):
  python read_wtvb01.py --port COM3 --baud 9600 --id 0x50 --interval 1.0

Requires: pyserial
  python -m pip install pyserial
"""

import serial
import struct
import time
import argparse


def crc16_modbus(data: bytes) -> int:
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


def build_read_request(addr: int, reg: int, count: int) -> bytes:
    pkt = bytes([addr & 0xFF, 0x03, (reg >> 8) & 0xFF, reg & 0xFF, (count >> 8) & 0xFF, count & 0xFF])
    crc = crc16_modbus(pkt)
    return pkt + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def read_exact(ser: serial.Serial, size: int, timeout: float = 1.0) -> bytes:
    deadline = time.time() + timeout
    buf = bytearray()
    while len(buf) < size and time.time() < deadline:
        chunk = ser.read(size - len(buf))
        if chunk:
            buf.extend(chunk)
        else:
            # small sleep to avoid busy loop
            time.sleep(0.001)
    return bytes(buf)


def parse_registers_from_response(resp: bytes, count: int):
    # resp: addr(1) func(1) bytecount(1) data(2*count) crc_lo(1) crc_hi(1)
    if len(resp) < 5:
        raise RuntimeError("Short response")
    bytecount = resp[2]
    expected_len = 1 + 1 + 1 + bytecount + 2
    if len(resp) != expected_len:
        raise RuntimeError(f"Unexpected response length {len(resp)} != {expected_len}")
    # CRC check
    if crc16_modbus(resp[:-2]) != (resp[-2] | (resp[-1] << 8)):
        raise RuntimeError("CRC check failed")
    data = resp[3:-2]
    regs = []
    for i in range(0, len(data), 2):
        regs.append(struct.unpack('>h', data[i:i+2])[0])  # big-endian signed 16-bit
    if len(regs) != count:
        raise RuntimeError("Mismatch register count")
    return regs


def read_registers(ser: serial.Serial, addr: int, reg: int, count: int, timeout: float = 1.0):
    req = build_read_request(addr, reg, count)
    ser.reset_input_buffer()
    ser.write(req)
    ser.flush()
    # expected response length = 1(addr)+1(func)+1(bytecount)+2*count(data)+2(crc)
    expected = 5 + 2 * count
    resp = read_exact(ser, expected, timeout)
    if len(resp) != expected:
        raise RuntimeError(f"Timeout/short read ({len(resp)} bytes, expected {expected})")
    return parse_registers_from_response(resp, count)


def convert_and_print(regs_map):
    # regs_map: dict of name -> list/values (raw registers)
    # Conversions per manual:
    # Acceleration AX~AZ: raw/32768.0*16 (g)
    # Vibration speed VX~VZ: raw (mm/s)
    # Displacement DX~DZ: raw (um)
    # Frequency HZX~HZZ: raw/10.0 (Hz)
    # Temp TEMP: raw/100.0 (°C)
    if 'acc' in regs_map:
        acc = [r / 32768.0 * 16.0 for r in regs_map['acc']]
        print(f"Acceleration (g): X={acc[0]:.4f}, Y={acc[1]:.4f}, Z={acc[2]:.4f}")
    if 'vel' in regs_map:
        vel = regs_map['vel']
        print(f"Velocity (mm/s): X={vel[0]}, Y={vel[1]}, Z={vel[2]}")
    if 'dis' in regs_map:
        dis = regs_map['dis']
        print(f"Displacement (um): X={dis[0]}, Y={dis[1]}, Z={dis[2]}")
    if 'hz' in regs_map:
        hz = [r / 10.0 for r in regs_map['hz']]
        print(f"Frequency (Hz): X={hz[0]:.1f}, Y={hz[1]:.1f}, Z={hz[2]:.1f}")
    if 'temp' in regs_map:
        t = regs_map['temp'][0] / 100.0
        print(f"Temperature (°C): {t:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Read WTVB01-485 registers over Modbus RTU")
    parser.add_argument("--port", required=True, help="Serial port (e.g. COM3)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (default 9600)")
    parser.add_argument("--id", type=lambda x: int(x,0), default=0x50, help="Modbus device ID (hex ok, default 0x50)")
    parser.add_argument("--interval", type=float, default=1.0, help="Read interval seconds")
    parser.add_argument("--timeout", type=float, default=1.0, help="Serial read timeout per request (s)")
    args = parser.parse_args()

    with serial.Serial(args.port, args.baud, timeout=0.05) as ser:
        print(f"Opened {args.port} @ {args.baud}bps, id=0x{args.id:02X}")
        try:
            while True:
                try:
                    regs = {}
                    regs['acc'] = read_registers(ser, args.id, 0x0034, 3, timeout=args.timeout)   # AX(0x34) AX..AZ
                    regs['vel'] = read_registers(ser, args.id, 0x003A, 3, timeout=args.timeout)   # VX(0x3A)
                    regs['dis'] = read_registers(ser, args.id, 0x0041, 3, timeout=args.timeout)   # DX(0x41)
                    regs['hz']  = read_registers(ser, args.id, 0x0044, 3, timeout=args.timeout)   # HZX(0x44)
                    regs['temp']= read_registers(ser, args.id, 0x0040, 1, timeout=args.timeout)   # TEMP(0x40)
                    print(f"\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                    convert_and_print(regs)
                except Exception as e:
                    print("Read error:", e)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("Exiting")


if __name__ == "__main__":
    main()
