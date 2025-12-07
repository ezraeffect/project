import serial
import time

PORT = 'COM3'
BAUD = 9600

def main():
    with serial.Serial(PORT, BAUD, timeout=1) as ser:
        while True:
            for char in ['R', 'G', 'B']:
                ser.write(char.encode())
                print(f"Sent: {char}")
                time.sleep(1)

if __name__ == "__main__":
    main()
