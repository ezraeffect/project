# WTVB01-485 Vibration Sensor User Manual

**Manual v2.5-05-06** | www.wit-motion.com

---

## Contents

1. Product Overview
2. Parameters
3. Hardware connection method
4. How to use the software
5. Software Configuration
6. Communication Protocol

---

## 1. Product Overview

1. The module has its own voltage stabilization circuit, the working voltage is 5V~36V, and the connection is convenient.

2. The use of advanced digital filtering technology can effectively reduce measurement noise and improve measurement accuracy.

3. At the same time, we provide users with the Witmotion.exe software, instructions for use, and development manuals required to minimize the research and development time for various needs.

4. Support 485 interface. It is convenient for users to choose the best connection method. The serial port rate is adjustable from 4800bps to 230400bps, and the default is 230400bps in high-speed mode.

5. **Application areas**: It can be widely used in bearing vibration measurement and real-time monitoring of rotating machinery such as submersible pumps, fans, steam turbines, coal mills, oxygen generators, generators, centrifuges, compressors, water pumps, motors, etc.

6. The three-axis displacement, three-axis speed, and three-axis frequency outputs can satisfy users' all-round measurement of vibration and impact, and determine whether the measured object (motor water pump) is damaged. If there is a machine failure caused by bearing wear, bearing cracking, poor dynamic balance, and misalignment, the vibration sensor can detect the failure in advance and issue an early warning to prevent the machine from continuing to work under bad conditions and causing damage, thereby causing economic losses.

7. **Multiple installation methods**: magnetic connection, threaded connection. Firm and stable, easy to install and disassemble.

8. Stud bolts with positive and negative threads: stainless steel hexagonal stud bolts with positive and negative threads, stud screws, left-handed and right-handed bidirectional screws

---

## 2. Parameters

### 2.1. Basic parameters

| Parameter | Condition | Minimum | Default | Maximum |
|-----------|-----------|---------|---------|---------|
| Communication interface | 485 interface | 4800bps | 9600bps | 230400bps |
| Output | Chip time, 3-axis acceleration, 3-axis vibration speed, 3-axis vibration displacement, 3-axis vibration frequency, chip temperature |
| Range | Vibration speed: 0~100mm/s, vibration displacement: 0~30000um, vibration frequency: 5-100hz |
| Accuracy | <FS±4% |
| Operating temperature | -40℃ | | 85℃ |
| Storage temperature | -40℃ | | 85℃ |
| Impact resistance | 20000g |
| Protection level | IP67 |

### 2.2. Parameter Description

#### 1. Output content

- **Vibration velocity**: the speed at which the vibration point of an object moves when it vibrates
- **Vibration displacement**: Amplitude, the amplitude of the vibration point when the object vibrates
- **Vibration frequency**: the number of times an object vibrates per unit time when it vibrates
- **Temperature**: Chip operating temperature, not external temperature

#### 2. Accuracy

`<FS±4%`: indicates 4% of the measuring range. Taking vibration displacement as an example, when the actual displacement value is 300um, the data error is 4% of 300um. When the actual value is 3000um, the data error is 4% of 3000um.

**Note**: The product has requirements for vibration frequency and is not suitable for low-frequency vibration scenarios. The vibration frequency must be at least 5Hz to ensure data reliability.

#### 3. Detection cycle (temporarily unavailable)

The chip processes data at a rate of 100 Hz, which means the chip processes 100 pieces of data per second.

#### 4. Cutoff frequency (temporarily unavailable)

The cutoff frequency is the frequency you set. The sensor will recognize vibration frequencies above that frequency. For example, if you set the cutoff frequency to 10Hz, the sensor will filter out vibration frequencies below 10Hz.

If the cutoff frequency is set to 10Hz and the detection period is set to 100Hz, then the output is the data with a vibration frequency higher than 10Hz among the 100 data in 1 second.

### 2.3. Product size

WTVB01-485 product dimensions: *(refer to original document for diagram)*

### 2.4. Electrical parameters

| Parameter | Condition | Minimum | Default | Maximum |
|-----------|-----------|---------|---------|---------|
| Supply voltage | | 9 V | 12V | 36V |
| Working current | Working (12V) | 8 mA | | |

### 2.5. Parameter comparison

*(refer to original document for comparison table)*

---

## 3. Hardware connection method

### 3.1. Wiring method

*(refer to original document for wiring diagram)*

### 3.2. Installation

Thread size: *(refer to original document for installation details)*

---

## 4. How to use the software

### 4.1. CH340 Driver Installation

**Witmotion.exe software download link**:
https://drive.google.com/file/d/10xysnkuyUwi3AK_t3965SLr5Yt6YKE-u/view?usp=drive_link

**CH340 driver download link**:
https://drive.google.com/file/d/1JidopB42R9EsCzMAYC3Ya9eJ8JbHapRF/view?usp=drive_link

**Note**: If Witmotion.exe cannot run, please download and install .net framework4.0

To the computer via a USB adapter, open Witmotion.exe, and after installing the CH340 driver, you can query the corresponding port number in the device manager.

After the device is connected, open the Witmotion.exe software.

### 4.2. Connect Witmotion.exe

#### 4.2.1. Automatic search

1. Select the model number of WT-VB01-485.
2. Click Search device.
3. Check the serial port number.
4. After the connection is successful, the data will be displayed on the software.

#### 4.2.2. Manual connection

1. Select the model number of WT-VB01-485.
2. Select the baud rate of the corresponding port. The default baud rate is 9600
3. Enter the corresponding ID (the default is 0x50) and click the + sign to add the device.

### 4.3. Graph

Click on the graph to get graphs of vibration velocity, vibration acceleration, vibration displacement and temperature (normal mode); in high-speed mode, only the vibration displacement graph has data.

**Normal mode (curve graph)**: *(refer to original document)*

**High speed mode (curve graph)**: *(refer to original document)*

### 4.4. Scatter plot

If you need to obtain a complete vibration displacement scatter plot, it is recommended to use high-speed mode to view it.

---

## 5. Software Configuration

### 5.1. Restore settings

Click "Configuration" and then click "Restore Settings" in the sensor configuration interface to restore the factory settings.

### 5.2. Restart

Click "Configure" and then click "Restart" in the sensor configuration interface to restart the sensor.

### 5.3. Communication rate

Open "Configuration", click the drop-down menu of "Serial Port Baud Rate" in the sensor configuration interface, select the serial port baud rate to be modified, and you can change the current serial port baud rate (the default serial port baud rate is 9600). 

The serial port baud rate can be: 4800, 9600, 19200, 38400, 57600, 115200, 230400

### 5.4. Device Address

Open "Configuration", click the "Modbus Address" input box in the sensor configuration interface, enter the Modbus address and then click Set to change the Modbus address (the default Modbus address is 0x50). 

The Modbus address ranges from 0x00 to 0x7F.

### 5.5. Recording Data

Open "Record" and click "Start Recording" to record the output data of the sensor.

### 5.6. High-speed mode

**Note**: High-speed mode actively outputs vibration displacement data at high speed, which can be used to analyze complex motion trajectories.

**Operation**: Click the high-speed mode button, the sensor will enter the high-speed active output mode (1000Hz), only output the three-axis high-frequency vibration displacement, and the baud rate of the sensor will automatically switch to 230400.

Configuration is not possible at this time. If you want to restore normal mode, you can power on the sensor again and search or add devices again.

After switching to high-speed mode, click "Search Device" to re-identify the device, and the baud rate will automatically switch to 230400. No parameter configuration can be performed in high-speed mode. If you want to restore to normal mode, you can power on the sensor again and then search or add the device again.

---

## 6. Communication Protocol

**Protocol**: MODBUS protocol  
**Level**: 485 level (default baud rate: 9600bps)

### 6.1. Read register format

The data is sent in hexadecimal format, not ASCII.

Each register address, register number, and data are represented by two bytes. The high and low bits of the register address are represented by ADDRH and ADDRL, the high and low bits of the register number are represented by LENH and LENL, and the high and low bits of the data are represented by DATA1H and DATA1L.

The last two bits of the read instruction are standard CRC check bits.

#### Send command

| Modbus Address | Function code | Register high 8 bits | Register lower 8 bits | Read length high 8 bits | Read length lower 8 bits | Check digit high 8 bits | Check digit lower 8 bits |
|----------------|---------------|---------------------|----------------------|------------------------|-------------------------|------------------------|-------------------------|
| ID | 0x03 (Read) | ADDRH[15:8] | ADDRL[7:0] | LENH[15:8] | LENL[7:0] | CRCH[15:8] | CRCL[7:0] |

#### Data return

| Modbus Address | Function code | Read length | Data high 8 bits | Data lower 8 bits | ... | Data high 8 bits | Data lower 8 bits | Check digit high 8 bits | Check digit lower 8 bits |
|----------------|---------------|------------|-----------------|------------------|-----|-----------------|------------------|------------------------|-------------------------|
| ID | 0x03 (Read) | LEN[7:0] | DATA1H[15:8] | DATA1L[7:0] | ... | DATAnH | DATAnL | CRCH[15:8] | CRCL[7:0] |

### 6.2. Write register format

The data is sent in hexadecimal format, not ASCII.

Each register address and write data are represented by two bytes. The high and low bits of the register address are represented by ADDRH and ADDRL, and the high and low bits of the write data are represented by DATAH and DATAL.

#### Send command

| Modbus Address | Function code | Register high 8 bits | Register lower 8 bits | Data high 8 bits | Data lower 8 bits | Check digit high 8 bits | Check digit lower 8 bits |
|----------------|---------------|---------------------|----------------------|-----------------|------------------|------------------------|-------------------------|
| ID | 0x06 (Write) | ADDRH[15:8] | ADDRL[7:0] | DATAH[15:8] | DATAL[7:0] | CRCH[15:8] | CRCL[7:0] |

#### Data return

| Modbus Address | Function code | Register high 8 bits | Register lower 8 bits | Data high 8 bits | Data lower 8 bits | Check digit high 8 bits | Check digit lower 8 bits |
|----------------|---------------|---------------------|----------------------|-----------------|------------------|------------------------|-------------------------|
| ID | 0x06 (Write) | ADDRH[15:8] | ADDRL[7:0] | DATAH[15:8] | DATAL[7:0] | CRCH[15:8] | CRCL[7:0] |

#### Note:

The instruction writing operation needs to be performed in three steps:

1. **Unlock**: `0x50 0x06 0x00 0x69 0xB5 0x88 0x22 0xA1`. The unlocking will take effect within ten seconds.
2. Send the instructions that need to be modified.
3. **Save**: `0x50 0X06 0X00 0X00 0X00 0X84 0X4B`

### 6.3. Register Address Table

| Register Address | Symbol | Meaning |
|-----------------|--------|---------|
| 0x00 | SAVE | Save/Restart/Restore to Factory |
| 0x04 | BAUD | Serial port baud rate |
| 0x1A | IICADDR | Device Address |
| 0x30 | YYMM | Month Year |
| 0x31 | DDH | Date |
| 0x32 | MMSS | Seconds and minutes |
| 0x33 | MS | millisecond |
| 0x34 | AX | X-axis acceleration |
| 0x35 | AY | Y-axis acceleration |
| 0x36 | AZ | Z-axis acceleration |
| 0x3A | VX | X-axis vibration speed |
| 0x3B | VY | Y-axis vibration speed |
| 0x3C | VZ | Z-axis vibration speed |
| 0x40 | TEMP | Chip temperature |
| 0x41 | DX | X-axis vibration displacement |
| 0x42 | DY | Y-axis vibration displacement |
| 0x43 | DZ | Z-axis vibration displacement |
| 0x44 | HX | X-axis vibration frequency |
| 0x45 | HkDJ | Y-axis vibration frequency |
| 0x46 | HZZ | Z-axis vibration frequency |
| 0x47 | FDNFX | X-axis vibration displacement (high speed mode) |
| 0x48 | FDNFY | Y-axis vibration displacement (high speed mode) |
| 0x49 | FZD | Z-axis vibration displacement (high speed mode) |
| 0x62 | MODBUSMODEL | High-speed mode |
| 0x63 | CUTOFFFREQI | Cutoff frequency integer |
| 0x64 | CUTOFFFREQF | Cutoff frequency fraction |
| 0x65 | SAMPLEFREQ | Detection cycle |

### 6.4. Register Description

All the following examples are instructions when the Modbus address is 0x50 (default). If you change the Modbus address, you need to change the address and CRC check bit in the instruction accordingly.

#### 1. SAVE (Save/Restart/Restore to Factory)

- **Register Name**: SAVE
- **Register address**: 0 (0x00)
- **Read/write direction**: R/W
- **Default value**: 0x0000

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:0 | SAVE[15:0] | Save: 0x0000<br>Restart: 0x00FF<br>Factory reset: 0x0001 |

**Example**:
```
Send:  50 06 00 69 B5 88 22 A1 (unlock valid for 10S)
Return: 50 06 00 69 B5 88 22 A1
Send:  50 06 00 00 00 FF C4 0B (restart)
Return: 50 06 00 00 00 FF C4 0B
```

#### 2. BAUD (serial port baud rate)

- **Register name**: BAUD
- **Register address**: 4 (0x04)
- **Read/write direction**: R/W
- **Default value**: 0x0002

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:4 | | |
| 3:0 | BAUD[3:0] | Set the serial port baud rate:<br>0001(0x01) 4800bps<br>0010(0x02): 9600bps<br>0011(0x03): 19200bps<br>0100(0x04): 38400bps<br>0101(0x05): 57600bps<br>0110(0x06): 115200bps<br>0111(0x07): 230400bps |

**Example**:
```
Send:  50 06 00 69 B5 88 22 A1 (unlock valid for 10S)
Return: 50 06 00 69 B5 88 22 A1
Send:  50 06 00 04 00 06 45 88 (set the serial port baud rate to 115200)
Send:  50 06 00 00 00 00 84 4B (saved at 115200 baud)
Return: 50 06 00 00 00 00 84 4B
```

#### 3. IICADDR (device address)

- **Register Name**: IICADDR
- **Register address**: 26 (0x1A)
- **Read/write direction**: R/W
- **Default value**: 0x0050

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:8 | | |
| 7:0 | IICADDR[7:0] | Set the device address, used for I2C and Modbus communication, use 0x01~0x7F |

**Example**:
```
Send:  50 06 00 69 B5 88 22 A1 (unlock valid for 10S)
Return: 50 06 00 69 B5 88 22 A1
Send:  50 06 00 1A 00 02 24 4D (set the device address to 0x02)
Return: 50 06 00 1A 00 02 24 4D
Send:  02 06 00 69 B5 88 2F 13 (unlock valid for 10S)
Return: 02 06 00 69 B5 88 2F 13
Send:  02 06 00 00 00 00 89 F9 (Save)
Return: 02 06 00 00 00 00 89 F9
```

#### 4. YYMM~MS (on-chip time)

- **Register name**: YYMM~MS
- **Register address**: 48~51 (0x30~0x33)
- **Read/write direction**: R/W
- **Default time**: (2015, 1, 1, 00, 00, 59, 00)

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:8 | YYMM[15:8] | moon |
| 7:0 | YYMM[7:0] | Year |
| 15:8 | DDHH[15:8] | hour |
| 7:0 | DDHH[7:0] | day |
| 15:8 | MMSS[15:8] | Second |
| 7:0 | MMSS[7:0] | point |
| 15:0 | MS[15:0] | millisecond |

**Example**:
```
Send:  50 06 00 69 B5 88 22 A1 (unlock valid for 10S)
Return: 50 06 00 69 B5 88 22 A1
Send:  50 06 00 30 03 16 05 7A (set year and month 22-03)
Return: 50 06 00 30 03 16 05 7A
Send:  50 06 00 31 09 0C D3 D1 (set date and time 12-09)
Return: 50 06 00 31 09 0C D3 D1
Send:  50 06 00 32 3A 1E B7 2C (set minutes and seconds to 30:58)
Return: 50 06 00 32 3A 1E B7 2C
Send:  50 06 00 33 01 F4 74 53 (set milliseconds to 500)
Return: 50 06 00 33 01 F4 74 53
Send:  50 06 00 00 00 00 84 4B (save)
Return: 50 06 00 00 00 00 84 4B
```

#### 5. AX~AZ (acceleration)

- **Register name**: AX~AZ
- **Register address**: 52~54 (0x34~0x36)
- **Read/write direction**: R
- **Default value**: 0x0000

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:0 | AX[15:0] | Acceleration X = AX[15:0]/32768*16g (g is the acceleration due to gravity, which can be 9.8m/s²) |
| 15:0 | AY[15:0] | Acceleration Y = AY[15:0]/32768*16g (g is the acceleration due to gravity, which can be 9.8m/s²) |
| 15:0 | AZ[15:0] | Acceleration Z = AZ[15:0]/32768*16g (g is the acceleration due to gravity, which can be 9.8m/s²) |

**Example**:
```
Send:  50 03 00 34 00 03 49 84 (read three-axis acceleration)
Return: 50 03 06 AXH AXL AYH AYL AZH AZL CRCH CRCL

AX[15:0]=((short)AXH <<8)|AXL;
AY[15:0]=((short)AYH <<8)|AYL;
AZ[15:0]=((short)AZH <<8)|AZL;
```

#### 6. VX~VZ (vibration speed)

- **Register name**: VX~VZ
- **Register address**: 58~60 (0x3A~0x3C)
- **Read/write direction**: R
- **Default value**: 0x0000

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:0 | VX[15:0] | Vibration speed VX (mm/S) = ((VXH << 8) \| VXL) |
| 15:0 | VY[15:0] | Vibration velocity VY (mm/S) = ((VYH << 8) \| VYL) |
| 15:0 | VZ[15:0] | Vibration velocity VZ (mm/S) = ((VZH << 8) \| VZL) |

**Example**:
```
Send:  50 03 00 3A 00 03 28 47 (read the three-axis vibration speed)
Return: 50 03 06 VXH VXL VYH VYL VZH VZL CRCH CRCL

VX[15:0]=(((short)VXH <<8)|VXL);
VY[15:0]=(((short)VYH <<8)|VYL);
VZ[15:0]=(((short)VZH <<8)|VZL);
```

#### 7. Reserve

- **Register Name**: Reserved
- **Register address**: 61~63 (0x3D~0x3F)
- **Read/write direction**: R
- **Default value**: 0x0000

#### 8. TEMP (Temperature)

- **Register Name**: TEMP
- **Register address**: 64 (0x40)
- **Read/write direction**: R
- **Default value**: 0x0000

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:0 | TEMP[15:0] | Temperature = TEMP[15:0]/100°C |

**Example**:
```
Send:  50 03 00 40 00 01 88 5F (read chip temperature)
Return: 50 03 02 TEMPH TEMPL CRCH CRCL

TEMP[15:0]=(((short)TEMPH <<8)|TEMPL);
```

#### 9. DX~DZ (vibration displacement)

- **Register name**: DX~DZ
- **Register address**: 65~67 (0x41~0x43)
- **Read/write direction**: R
- **Default value**: 0x0000

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:0 | DX[15:0] | Vibration displacement DX(um)=((DXH << 8)\| DXL) |
| 15:0 | DY[15:0] | Vibration displacement DY(um)=((DYH << 8)\| DYL) |
| 15:0 | DZ[15:0] | Vibration displacement DZ(um)=((DZH << 8\| DZL) |

**Example**:
```
Send:  50 03 00 41 00 03 58 5E (read triaxial vibration displacement)
Return: 50 03 06 DXH DXL DYH DYL DZH DZL CRCH CRCL

DX[15:0]=(((short)DXH <<8)|DXL);
DY[15:0]=(((short)DYH <<8)|DYL);
DZ[15:0]=(((short)DZH <<8)|DZL);
```

#### 10. HZX~HZZ (vibration frequency)

- **Register name**: HZX~HZZ
- **Register address**: 68~70 (0x44~0x46)
- **Read/write direction**: R
- **Default value**: 0x0000

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:0 | HZX[15:0] | Vibration frequency HZX(Hz)=((HZXH << 8)\| HZXL)/10 |
| 15:0 | HZY[15:0] | Vibration frequency HZY(Hz)=((HZYH << 8)\| HZYL)/10 |
| 15:0 | HZZ[15:0] | Vibration frequency HZZ(Hz)=((HZZH << 8\| HZZL)/10 |

**Example**:
```
Send:  50 03 00 44 00 03 48 5F (read the three-axis vibration frequency)
Return: 50 03 06 HZXH HZXL HZYH HZYL HZZH HZZL CRCH CRCL

HZX[15:0]=(((short)HZXH <<8)|HZXL)/10;
HZY[15:0]=(((short)HZYH <<8)|HZYL)/10;
HZZ[15:0]=(((short)HZZH <<8)|HZZL)/10;
```

#### 11. FDNFX~FDNFZ (High-speed mode vibration displacement)

- **Register name**: FDNFX~FDNFZ
- **Register address**: 71~73 (0x47~0x49)
- **Read/write direction**: R
- **Default value**: 0x0000

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:0 | FDNFX[15:0] | High frequency vibration displacement FDNFX(um)=((FDNFXH << 8)\| FDNFXL) |
| 15:0 | FDNFY[15:0] | High frequency vibration displacement FDNFY(um)=((FDNFYH << 8)\| FDNFYL) |
| 15:0 | FDNFZ[15:0] | High frequency vibration displacement FDNFZ(um)=((FDNFZH << 8\| FDNFZL) |

**Example**:
```
Send:  50 03 00 47 00 03 B8 5F (read three-axis high-frequency vibration displacement)
Return: 50 03 06 FDNFXH FDNFXL FDNFYH FDNFYL FDNFZH FDNFZL CRCH CRCL

FDNFX[15:0]=(((short)FDNFXH <<8)|FDNFXL);
FDNFY[15:0]=(((short)FDNFYH <<8)|FDNFYL);
FDNFZ[15:0]=(((short)FDNFZH <<8)|FDNFZL);
```

#### 12. MODBOUSMODEL (high speed mode)

- **Register Name**: MODBOUSMODEL
- **Register address**: 98 (0x62)
- **Read/write direction**: R/W
- **Default value**: 0x0000

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:0 | SAVE[15:0] | High-speed mode is 0x0001 |

**Example**:
```
Send:  50 06 00 69 B5 88 22 A1 (unlock valid for 10S)
Return: 50 06 00 69 B5 88 22 A1
Send:  50 06 00 62 00 01 E4 55 (high speed mode) returns (230400 Baud)
```

**Note**: After sending, it will enter high-speed mode. This mode actively returns high-frequency displacement data. At this time, no instructions can be sent. Normal mode can be restored after power off.

In high-speed mode, do not send setup and save commands to avoid incorrectly modifying the sensor configuration. If you want to exit high-speed mode, power on the sensor again.

#### 13. CUTOFFFREQI, CUTOFFFREQF (cutoff frequency - temporarily ineffective)

**Register name**: CUTOFFFREQI (integer 0~100)
- **Register address**: 99(0x63)
- **Read/write direction**: R/W
- **Default value**: 0x000A

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:2 | | |
| 1:0 | CUTOFFFREQI[1:0] | Cut-off frequency is used to filter out the interference of other clutter on the sensor, which can be set between 0.00~200.00Hz |

**Register Name**: CUTOFFFREQF (setting a decimal point of 0 to 99 is equivalent to setting it to 0.00 to 0.99)
- **Register address**: 100(0x64)
- **Read/write direction**: R/W
- **Default value**: 0x000A

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:2 | | |
| 1:0 | CUTOFFFREQF[1:0] | Cut-off frequency is used to filter out the interference of other clutter on the sensor, which can be set between 0.00~200.00Hz |

**Example: Set the cutoff frequency to 10.99 Hz**
```
Send:  50 06 00 69 B5 88 22 A1 (unlock valid for 10S)
Return: 50 06 00 69 B5 88 22 A1
Send:  50 06 00 63 00 0A F4 52 (Set the integer part of the cutoff frequency to 10)
Return: 50 06 00 63 00 0A F4 52
Send:  50 06 00 64 00 63 85 BD (set the decimal part of the cutoff frequency to 99)
Return: 50 06 00 64 00 63 85 BD
Send:  50 06 00 00 00 00 84 4B (save)
Return: 50 06 00 00 00 00 84 4B
```

The cutoff frequency setting requires the use of two registers, CUTOFFFREQI and CUTOFFFREQF.

Description of the decimal part of the cutoff frequency: set the decimal value x100 (set .99, the actual decimal part needs to be set to 99)

#### 14. SAMPLEFREQ (detection period)

- **Register Name**: SAMPLEFREQ
- **Register address**: 101 (0x65)
- **Read/write direction**: R/W
- **Default value**: 0x0064

| Bit | NAME | FUNCTION |
|-----|------|----------|
| 15:2 | | |
| 1:0 | SAMPLEFREQ[1:0] | The detection cycle, the reciprocal of which is the amount of data output per second, can be set between 1 and 200 Hz |

**Example**:
```
Send:  50 06 00 69 B5 88 22 A1 (valid within 10 seconds after unlocking)
Return: 50 06 00 69 B5 88 22 A1
Send:  50 06 00 65 00 64 14 53 (set the detection cycle to 100Hz)
Return: 50 06 00 65 00 64 14 53
Send:  50 06 00 00 00 00 84 4B (save)
Return: 50 06 00 00 00 00 84 4B
```

---

## End of Manual

For more information, visit: www.wit-motion.com