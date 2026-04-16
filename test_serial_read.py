import serial
import time

PORT = "COM14"
BAUD_RATE = 115200

def main():
    try:
        ser = serial.Serial(PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # allow Arduino to reset
        print(f"Connected to {PORT} at {BAUD_RATE} baud")
        print("Reading serial data...\n")

        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if line:
                print(line)

    except serial.SerialException as e:
        print(f"Serial error: {e}")
    except KeyboardInterrupt:
        print("\nStopped by user.")

if __name__ == "__main__":
    main()