# WTVB01-BT50 Manual — Text Extract (Markdown)

## 1. Product Overview

* Internal voltage-stabilized circuit, built-in 3.7V Li-ion battery.
* Digital filtering for noise reduction and accuracy.
* Provides PC software, app, development manuals.
* Type-C interface, UART 115200bps.
* Cut-off frequency: 0–100Hz.
* Detection cycle: 1–100Hz.
* Outputs: 3-axis displacement, velocity, angle, frequency, temperature.
* Detects bearing wear, cracking, imbalance, etc.
* Applications: pumps, fans, turbines, mills, generators, compressors, motors.

## 2. Parameter Indicators

### Basic

| Item            | Min    | Default | Max    |
| --------------- | ------ | ------- | ------ |
| UART            | 115200 | 115200  | 115200 |
| Detection cycle | 1Hz    | 100Hz   | 100Hz  |
| Cut-off freq    | 1Hz    | 10Hz    | 100Hz  |

### Ranges

* Velocity: 0–50 mm/s
* Angle: 0–180°
* Displacement: 0–30000 µm

### Environmental

* Operating: −20℃ ~ 60℃
* Storage: −40℃ ~ 85℃

## 3. Electrical Parameters

* Charge voltage: 5V
* Battery: 3.7V, 260mAh
* Working current: 15mA
* Standby: 10µA
* Battery life: 6–8h
* Charge time: 2–3h

## 4. Software Usage

### 4.1 App

Link: Google Drive folder (App).

### 4.2 PC Software

* Auto-search sensor; select WTVB01_BT50.
* Manual: choose device → COM port → 115200 → Add.

### 4.3 Curve Display

* Normal mode: velocity, angle, displacement, temperature.
* High-speed mode: displacement only.

### 4.4 Scatter Plot

* Use high-speed mode.

### 4.5 Configurations

* Restore defaults.
* Restart.
* Set cutoff frequency (integer + decimal).
* Set detection cycle (output packets per second).
* Record data.

## 5. Registers

### 5.1 Address Table (Key)

| Addr      | Name          | Description             |
| --------- | ------------- | ----------------------- |
| 0x00      | SAVE          | Save/restart/factory    |
| 0x03      | RRATE         | Return rate             |
| 0x3A–0x3C | VX,VY,VZ      | Velocity                |
| 0x3D–0x3F | ADX,ADY,ADZ   | Angle                   |
| 0x40      | TEMP          | Temperature             |
| 0x41–0x43 | DX,DY,DZ      | Displacement            |
| 0x44–0x46 | HZX,HZY,HZZ   | Frequency               |
| 0x47–0x49 | FDNFX,Y,Z     | High-speed displacement |
| 0x5D–0x5E | CUTOFFFREQI/F | Cutoff freq             |
| 0x5F      | SAMPLEFREQ    | Detection cycle         |
| 0x64      | BatPer        | Battery level           |

### 5.2 Default Upload Packet

* Header: `0x55`
* Flag: `0x61`
* Content: velocity XYZ, angle XYZ, temp, displacement XYZ, frequency XYZ.
* 28 bytes total.

### 5.3 Interpretation

#### Velocity (mm/s)

```
VX = (VXH << 8) | VXL
```

#### Angle (°)

```
ADX = ((ADXH << 8) | ADXL) / 32768 * 180
```

#### Temperature (°C)

```
TEMP = (TEMPH << 8 | TEMPL) / 100
```

#### Displacement (µm)

```
DX = (DXH << 8) | DXL
```

#### Frequency (Hz)

```
HZX = (HZXH << 8) | HZXL
```

### 5.4 Register Read

Send:

```
FF AA 27 XX 00
```

Reply:
Header `55 71` + start register + 8 registers (16 bytes).

### 5.5 Set Instructions

* Unlock (10s):
  `FF AA 69 88 B5`
* Save:
  `FF AA 00 00 00`
* Set return rate:
  `FF AA 03 RR 00`
* Cut-off frequency:

  * Integer: `FF AA 5D II 00`
  * Decimal: `FF AA 5E DD 00`
* Detection cycle:
  `FF AA 5F XX 00`

## 6. Example Packet

```
55 61 11 00 16 00 02 00 02 00 00 00 01 00 E6 0A
43 00 47 00 0A 00 25 00 25 00 25 00
```

---