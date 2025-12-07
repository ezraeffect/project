# read_wtvb01_gui.py
"""
Real-time GUI for WTVB01-485 using a USB->RS485 adapter.

This script reads the sensor in a background thread (via Modbus RTU requests)
and plots Velocity (mm/s), Displacement (um) and Temperature (°C) live using
matplotlib.

Dependencies:
  python -m pip install pyserial matplotlib

Usage (PowerShell):
  python read_wtvb01_gui.py --port COM3 --baud 9600 --id 0x50 --interval 0.2

Notes:
- Keep interval modest (e.g. 0.2-1.0s) to avoid overloading the serial/CPU with
  frequent Modbus requests. For higher-rate streaming use the sensor's high-speed
  mode (requires 230400 baud and behavior differs).
"""

import argparse
import threading
import time
from collections import deque
import struct
import sys

import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation


# --- Modbus helpers (same CRC and request format as read_wtvb01.py) ---

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


def parse_registers_from_response(resp: bytes, count: int):
    if len(resp) < 5:
        raise RuntimeError("Short response")
    bytecount = resp[2]
    expected_len = 1 + 1 + 1 + bytecount + 2
    if len(resp) != expected_len:
        raise RuntimeError(f"Unexpected response length {len(resp)} != {expected_len}")
    if crc16_modbus(resp[:-2]) != (resp[-2] | (resp[-1] << 8)):
        raise RuntimeError("CRC check failed")
    data = resp[3:-2]
    regs = []
    for i in range(0, len(data), 2):
        regs.append(struct.unpack('>h', data[i:i+2])[0])
    if len(regs) != count:
        raise RuntimeError("Mismatch register count")
    return regs


def read_exact(ser: serial.Serial, size: int, timeout: float = 1.0) -> bytes:
    deadline = time.time() + timeout
    buf = bytearray()
    while len(buf) < size and time.time() < deadline:
        chunk = ser.read(size - len(buf))
        if chunk:
            buf.extend(chunk)
        else:
            time.sleep(0.001)
    return bytes(buf)


def read_registers(ser: serial.Serial, addr: int, reg: int, count: int, timeout: float = 1.0):
    req = build_read_request(addr, reg, count)
    ser.reset_input_buffer()
    ser.write(req)
    ser.flush()
    expected = 5 + 2 * count
    resp = read_exact(ser, expected, timeout)
    if len(resp) != expected:
        raise RuntimeError(f"Timeout/short read ({len(resp)} bytes, expected {expected})")
    return parse_registers_from_response(resp, count)


# --- Background reader thread ---

def reader_thread_fn(ser, addr, interval, history, lock, stop_event, timeout):
    """Continuously read a set of registers and update shared deques in `history`.
       history is a dict with keys: 'time', 'vel_x','vel_y','vel_z','dis_x','dis_y','dis_z','temp'
    """
    while not stop_event.is_set():
        t0 = time.time()
        try:
            # Read velocity (VX..VZ)
            vel = read_registers(ser, addr, 0x003A, 3, timeout=timeout)
            # Read displacement (DX..DZ)
            dis = read_registers(ser, addr, 0x0041, 3, timeout=timeout)
            # Read temperature
            temp = read_registers(ser, addr, 0x0040, 1, timeout=timeout)

            with lock:
                history['time'].append(time.time())
                history['vel_x'].append(vel[0])
                history['vel_y'].append(vel[1])
                history['vel_z'].append(vel[2])
                history['dis_x'].append(dis[0])
                history['dis_y'].append(dis[1])
                history['dis_z'].append(dis[2])
                history['temp'].append(temp[0] / 100.0)
        except Exception as e:
            # on error, append NaNs/time so plot shows gap; but keep running
            with lock:
                history['time'].append(time.time())
                history['vel_x'].append(float('nan'))
                history['vel_y'].append(float('nan'))
                history['vel_z'].append(float('nan'))
                history['dis_x'].append(float('nan'))
                history['dis_y'].append(float('nan'))
                history['dis_z'].append(float('nan'))
                history['temp'].append(float('nan'))
            print("Read error:", e)
        # sleep remaining interval
        dt = time.time() - t0
        to_sleep = interval - dt
        if to_sleep > 0:
            time.sleep(to_sleep)


# --- GUI / plotting ---

def run_gui(port, baud, addr, interval, timeout, history_len=500):
    # shared data structures
    lock = threading.Lock()
    history = {
        'time': deque(maxlen=history_len),
        'vel_x': deque(maxlen=history_len),
        'vel_y': deque(maxlen=history_len),
        'vel_z': deque(maxlen=history_len),
        'dis_x': deque(maxlen=history_len),
        'dis_y': deque(maxlen=history_len),
        'dis_z': deque(maxlen=history_len),
        'temp': deque(maxlen=history_len),
    }

    try:
        ser = serial.Serial(port, baud, timeout=0.05)
    except Exception as e:
        print("Failed to open serial port:", e)
        sys.exit(1)

    stop_event = threading.Event()
    th = threading.Thread(target=reader_thread_fn, args=(ser, addr, interval, history, lock, stop_event, timeout))
    th.daemon = True
    th.start()

    # Prepare plot
    try:
        plt.style.use('seaborn')
    except Exception:
        # Not critical: fall back to default style and inform the user how to enable seaborn
        print("matplotlib style 'seaborn' not available; using default style.")
        print("To enable seaborn style install seaborn: python -m pip install seaborn")
        plt.style.use('default')
    fig, axs = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

    # Velocity subplot
    ax_vel = axs[0]
    line_vx, = ax_vel.plot([], [], label='Vx', color='tab:blue')
    line_vy, = ax_vel.plot([], [], label='Vy', color='tab:orange')
    line_vz, = ax_vel.plot([], [], label='Vz', color='tab:green')
    ax_vel.set_ylabel('Velocity (mm/s)')
    ax_vel.legend(loc='upper left')
    ax_vel.grid(True)

    # Displacement subplot
    ax_dis = axs[1]
    line_dx, = ax_dis.plot([], [], label='Dx', color='tab:blue')
    line_dy, = ax_dis.plot([], [], label='Dy', color='tab:orange')
    line_dz, = ax_dis.plot([], [], label='Dz', color='tab:green')
    ax_dis.set_ylabel('Displacement (um)')
    ax_dis.legend(loc='upper left')
    ax_dis.grid(True)

    # Temperature subplot
    ax_tmp = axs[2]
    line_tmp, = ax_tmp.plot([], [], label='Temp', color='tab:red')
    ax_tmp.set_ylabel('Temp (°C)')
    ax_tmp.set_xlabel('Time')
    ax_tmp.legend(loc='upper left')
    ax_tmp.grid(True)

    # Animation update
    def update(frame):
        with lock:
            times = list(history['time'])
            vx = list(history['vel_x'])
            vy = list(history['vel_y'])
            vz = list(history['vel_z'])
            dx = list(history['dis_x'])
            dy = list(history['dis_y'])
            dz = list(history['dis_z'])
            tmp = list(history['temp'])

        if not times:
            return line_vx, line_vy, line_vz, line_dx, line_dy, line_dz, line_tmp

        # x-axis: seconds relative to last sample
        t0 = times[0]
        x = [t - t0 for t in times]

        line_vx.set_data(x, vx)
        line_vy.set_data(x, vy)
        line_vz.set_data(x, vz)
        line_dx.set_data(x, dx)
        line_dy.set_data(x, dy)
        line_dz.set_data(x, dz)
        line_tmp.set_data(x, tmp)

        # autoscale
        ax_vel.relim(); ax_vel.autoscale_view()
        ax_dis.relim(); ax_dis.autoscale_view()
        ax_tmp.relim(); ax_tmp.autoscale_view()

        # set x limits to show full window
        ax_tmp.set_xlim(left=0, right=x[-1])

        return line_vx, line_vy, line_vz, line_dx, line_dy, line_dz, line_tmp

    ani = animation.FuncAnimation(fig, update, interval=max(50, int(interval*1000)), blit=False)

    try:
        plt.tight_layout()
        plt.show()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        th.join(timeout=1.0)
        ser.close()


def main():
    parser = argparse.ArgumentParser(description='Live plot for WTVB01-485')
    parser.add_argument('--port', required=True, help='Serial port (e.g. COM3)')
    parser.add_argument('--baud', type=int, default=9600, help='Baud rate (default 9600)')
    parser.add_argument('--id', type=lambda x: int(x,0), default=0x50, help='Modbus device ID')
    parser.add_argument('--interval', type=float, default=0.5, help='Read interval seconds')
    parser.add_argument('--timeout', type=float, default=0.8, help='Per-request timeout (s)')
    args = parser.parse_args()

    run_gui(args.port, args.baud, args.id, args.interval, args.timeout)


if __name__ == '__main__':
    main()
