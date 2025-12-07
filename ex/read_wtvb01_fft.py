# read_wtvb01_fft.py
"""
Real-time FFT viewer for WTVB01-485 (Witmotion) over Modbus-RTU (USB->RS485).

- Reads AX/AY/AZ (acceleration) and DX/DY/DZ (displacement) registers periodically.
- Maintains a rolling window of samples and computes FFT per axis.
- Plots time-domain and frequency-domain (FFT) views in real time using matplotlib.

Dependencies:
  python -m pip install pyserial numpy matplotlib

Usage (PowerShell):
  python read_wtvb01_fft.py --port COM3 --baud 9600 --id 0x50 --interval 0.01 --window 2.0

Notes / cautions:
- Modbus over RS-485 is relatively slow; to get meaningful FFTs you need a sampling
  interval small enough (e.g. sensor output rate 100Hz -> interval <= 0.01s). The
  sensor's detection cycle is typically 100Hz in normal mode (see manual). If your
  Modbus polling is too slow, the FFT will be low-resolution / aliasing-prone.
- For true high-rate streaming use the sensor's high-speed mode (requires 230400
  baud and behavior differs; be careful).
"""

import argparse
import threading
import time
from collections import deque
import struct
import sys

import serial
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# --- Modbus helpers (CRC, request/response) ---

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
            time.sleep(0.001)
    return bytes(buf)


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


# --- Reader thread: collect AX/AY/AZ and DX/DY/DZ ---

def reader_thread(ser, addr, interval, timeout, acc_buffers, dis_buffers, time_buffer, lock, stop_event):
    """Read sensor registers and append to buffers. Values appended as floats.
    acc_buffers, dis_buffers: dict of deques for 'x','y','z'
    time_buffer: deque for timestamps
    """
    while not stop_event.is_set():
        t0 = time.time()
        try:
            # AX..AZ start at 0x34, count=3
            acc_regs = read_registers(ser, addr, 0x0034, 3, timeout=timeout)
            # DX..DZ start at 0x41, count=3 (um)
            dis_regs = read_registers(ser, addr, 0x0041, 3, timeout=timeout)

            # convert acc: raw / 32768 * 16 -> g
            acc_vals = [r / 32768.0 * 16.0 for r in acc_regs]
            # displacement is raw in um
            dis_vals = [float(r) for r in dis_regs]

            with lock:
                time_buffer.append(time.time())
                acc_buffers['x'].append(acc_vals[0])
                acc_buffers['y'].append(acc_vals[1])
                acc_buffers['z'].append(acc_vals[2])
                dis_buffers['x'].append(dis_vals[0])
                dis_buffers['y'].append(dis_vals[1])
                dis_buffers['z'].append(dis_vals[2])
        except Exception as e:
            # on error, append NaN to keep timing consistent
            with lock:
                time_buffer.append(time.time())
                acc_buffers['x'].append(np.nan)
                acc_buffers['y'].append(np.nan)
                acc_buffers['z'].append(np.nan)
                dis_buffers['x'].append(np.nan)
                dis_buffers['y'].append(np.nan)
                dis_buffers['z'].append(np.nan)
            print("Read error:", e)
        dt = time.time() - t0
        to_sleep = interval - dt
        if to_sleep > 0:
            time.sleep(to_sleep)


# --- FFT utilities ---

def compute_fft(window_samples, fs):
    # window_samples: 1D numpy array, may contain nan -> ignore via mask
    mask = ~np.isnan(window_samples)
    if mask.sum() < 2:
        return None, None
    samples = window_samples[mask]
    # if samples are shorter than requested, pad with zeros to next power of two
    N = len(samples)
    # apply Hann window
    win = np.hanning(N)
    samples_win = samples * win
    # FFT (rfft)
    Y = np.fft.rfft(samples_win)
    freqs = np.fft.rfftfreq(N, 1.0 / fs)
    # amplitude scaling: divide by sum of window (to get approximate amplitude)
    scale = np.sum(win) / 2.0
    mag = np.abs(Y) / scale
    return freqs, mag


# --- GUI / Plotting ---

def run_fft_gui(port, baud, addr, interval, timeout, window_sec, history_len_seconds=10):
    # sampling rate approximated by 1/interval
    fs = 1.0 / interval if interval > 0 else 1.0
    # sample count for FFT window
    n_window = max(4, int(round(window_sec * fs)))
    # history length in samples
    maxlen = int(round(history_len_seconds * fs))

    # deques
    acc_buffers = {'x': deque(maxlen=maxlen), 'y': deque(maxlen=maxlen), 'z': deque(maxlen=maxlen)}
    dis_buffers = {'x': deque(maxlen=maxlen), 'y': deque(maxlen=maxlen), 'z': deque(maxlen=maxlen)}
    time_buffer = deque(maxlen=maxlen)

    lock = threading.Lock()
    stop_event = threading.Event()

    try:
        ser = serial.Serial(port, baud, timeout=0.05)
    except Exception as e:
        print("Failed to open serial port:", e)
        sys.exit(1)

    th = threading.Thread(target=reader_thread, args=(ser, addr, interval, timeout, acc_buffers, dis_buffers, time_buffer, lock, stop_event))
    th.daemon = True
    th.start()

    # plotting layout: 2 rows x 2 cols
    try:
        plt.style.use('seaborn')
    except Exception:
        plt.style.use('default')

    fig, axs = plt.subplots(2, 2, figsize=(12, 8))

    # Acc time series (top-left)
    ax_acc_time = axs[0, 0]
    line_acc_x, = ax_acc_time.plot([], [], label='Acc X (g)')
    line_acc_y, = ax_acc_time.plot([], [], label='Acc Y (g)')
    line_acc_z, = ax_acc_time.plot([], [], label='Acc Z (g)')
    ax_acc_time.set_title('Acceleration - Time Domain')
    ax_acc_time.set_xlabel('Time (s)')
    ax_acc_time.set_ylabel('g')
    ax_acc_time.legend()
    ax_acc_time.grid(True)

    # Acc FFT (top-right)
    ax_acc_fft = axs[0, 1]
    line_accf_x, = ax_acc_fft.plot([], [], label='Acc X')
    line_accf_y, = ax_acc_fft.plot([], [], label='Acc Y')
    line_accf_z, = ax_acc_fft.plot([], [], label='Acc Z')
    ax_acc_fft.set_title(f'Acceleration - FFT window {n_window} samples (~{window_sec:.2f}s)')
    ax_acc_fft.set_xlabel('Frequency (Hz)')
    ax_acc_fft.set_ylabel('Amplitude')
    ax_acc_fft.legend()
    ax_acc_fft.grid(True)

    # Displacement time series (bottom-left)
    ax_dis_time = axs[1, 0]
    line_dis_x, = ax_dis_time.plot([], [], label='Dis X (um)')
    line_dis_y, = ax_dis_time.plot([], [], label='Dis Y (um)')
    line_dis_z, = ax_dis_time.plot([], [], label='Dis Z (um)')
    ax_dis_time.set_title('Displacement - Time Domain')
    ax_dis_time.set_xlabel('Time (s)')
    ax_dis_time.set_ylabel('um')
    ax_dis_time.legend()
    ax_dis_time.grid(True)

    # Displacement FFT (bottom-right)
    ax_dis_fft = axs[1, 1]
    line_disf_x, = ax_dis_fft.plot([], [], label='Dis X')
    line_disf_y, = ax_dis_fft.plot([], [], label='Dis Y')
    line_disf_z, = ax_dis_fft.plot([], [], label='Dis Z')
    ax_dis_fft.set_title(f'Displacement - FFT window {n_window} samples (~{window_sec:.2f}s)')
    ax_dis_fft.set_xlabel('Frequency (Hz)')
    ax_dis_fft.set_ylabel('Amplitude')
    ax_dis_fft.legend()
    ax_dis_fft.grid(True)

    plt.tight_layout()

    def update(frame):
        with lock:
            times = np.array(time_buffer)
            acc_x = np.array(acc_buffers['x'])
            acc_y = np.array(acc_buffers['y'])
            acc_z = np.array(acc_buffers['z'])
            dis_x = np.array(dis_buffers['x'])
            dis_y = np.array(dis_buffers['y'])
            dis_z = np.array(dis_buffers['z'])

        if times.size == 0:
            return (line_acc_x, line_acc_y, line_acc_z, line_accf_x, line_accf_y, line_accf_z,
                    line_dis_x, line_dis_y, line_dis_z, line_disf_x, line_disf_y, line_disf_z)

        # Time axis in seconds relative to last window
        t0 = times[0]
        x_time = times - t0

        # update time series lines (show last n_window samples)
        # take last up to n_window samples
        xs = x_time[-n_window:]
        acc_x_w = acc_x[-n_window:]
        acc_y_w = acc_y[-n_window:]
        acc_z_w = acc_z[-n_window:]
        dis_x_w = dis_x[-n_window:]
        dis_y_w = dis_y[-n_window:]
        dis_z_w = dis_z[-n_window:]

        line_acc_x.set_data(xs, acc_x_w)
        line_acc_y.set_data(xs, acc_y_w)
        line_acc_z.set_data(xs, acc_z_w)
        ax_acc_time.relim(); ax_acc_time.autoscale_view()

        line_dis_x.set_data(xs, dis_x_w)
        line_dis_y.set_data(xs, dis_y_w)
        line_dis_z.set_data(xs, dis_z_w)
        ax_dis_time.relim(); ax_dis_time.autoscale_view()

        # compute FFT on the current window (padding/trimming done inside compute_fft)
        # Acc FFT
        freqs = None
        mag_x = mag_y = mag_z = None
        if xs.size >= 4:
            freqs, mag_x = compute_fft(np.array(acc_x_w, dtype=float), fs)
            _, mag_y = compute_fft(np.array(acc_y_w, dtype=float), fs)
            _, mag_z = compute_fft(np.array(acc_z_w, dtype=float), fs)

        if freqs is not None:
            line_accf_x.set_data(freqs, mag_x)
            line_accf_y.set_data(freqs, mag_y)
            line_accf_z.set_data(freqs, mag_z)
            ax_acc_fft.set_xlim(0, fs / 2)
            # autoscale y with small margin
            allmag = np.hstack([mag_x, mag_y, mag_z])
            ymax = np.nanmax(allmag) if allmag.size else 1.0
            ax_acc_fft.set_ylim(0, max(1e-6, ymax * 1.1))

        # Displacement FFT
        freqs_d = None
        if xs.size >= 4:
            freqs_d, dmag_x = compute_fft(np.array(dis_x_w, dtype=float), fs)
            _, dmag_y = compute_fft(np.array(dis_y_w, dtype=float), fs)
            _, dmag_z = compute_fft(np.array(dis_z_w, dtype=float), fs)

        if freqs_d is not None:
            line_disf_x.set_data(freqs_d, dmag_x)
            line_disf_y.set_data(freqs_d, dmag_y)
            line_disf_z.set_data(freqs_d, dmag_z)
            ax_dis_fft.set_xlim(0, fs / 2)
            allmag = np.hstack([dmag_x, dmag_y, dmag_z])
            ymax = np.nanmax(allmag) if allmag.size else 1.0
            ax_dis_fft.set_ylim(0, max(1e-6, ymax * 1.1))

        # ensure x limits for time plots
        ax_acc_time.set_xlim(xs[0], xs[-1])
        ax_dis_time.set_xlim(xs[0], xs[-1])

        return (line_acc_x, line_acc_y, line_acc_z, line_accf_x, line_accf_y, line_accf_z,
                line_dis_x, line_dis_y, line_dis_z, line_disf_x, line_disf_y, line_disf_z)

    ani = animation.FuncAnimation(fig, update, interval=max(50, int(interval * 1000)), blit=False)

    try:
        plt.show()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        th.join(timeout=1.0)
        ser.close()


def main():
    parser = argparse.ArgumentParser(description='Real-time FFT viewer for WTVB01-485')
    parser.add_argument('--port', required=True, help='Serial port (e.g. COM3)')
    parser.add_argument('--baud', type=int, default=9600, help='Baud rate')
    parser.add_argument('--id', type=lambda x: int(x, 0), default=0x50, help='Modbus device ID')
    parser.add_argument('--interval', type=float, default=0.02, help='Poll interval seconds (e.g. 0.01 for 100Hz)')
    parser.add_argument('--timeout', type=float, default=0.08, help='Per-request timeout (s)')
    parser.add_argument('--window', type=float, default=2.0, help='FFT window length in seconds')
    args = parser.parse_args()

    print('Note: For useful FFT results you need a sampling rate high enough (1/--interval).')
    print('Sensor default detection cycle is often 100Hz; ensure interval <= 0.01 for 100Hz sampling.')

    run_fft_gui(args.port, args.baud, args.id, args.interval, args.timeout, args.window)


if __name__ == '__main__':
    main()
