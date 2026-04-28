# hrv_bridge.py
"""
HRV Serial Bridge - Reads Arduino serial data and sends to Django API.
Phase 4 - HRV Module (Enhanced with signal validation).

Features:
    - Token-based authentication
    - Signal quality validation (IR threshold)
    - BPM validation (45-130 BPM range)
    - Sudden BPM jump detection (> 20 BPM rejected)
    - RR interval validation (400-1500 ms)
    - SDNN computation (minimum 10 valid RR intervals)
    - Moving average smoothing (last 5 readings)
    - HRV classification (SDNN-based stress levels)
    - Clear console output showing posted/skipped readings

Usage:
    python hrv_bridge.py [--username USERNAME] [--token TOKEN]
"""

import serial
import json
import time
import requests
import sys
import argparse
import statistics

SERIAL_PORT = "COM14"
BAUD_RATE = 115200
BASE_URL = "http://127.0.0.1:8000"

MIN_POST_INTERVAL = 5.0
SIGNIFICANT_CHANGE_BPM = 5.0
SIGNIFICANT_CHANGE_SDNN = 10.0

IR_THRESHOLD = 50000
BPM_MIN = 45
BPM_MAX = 130
RR_MIN_MS = 400
RR_MAX_MS = 1500
BPM_JUMP_THRESHOLD = 20
MIN_VALID_RR_FOR_SDNN = 10
SMOOTHING_WINDOW = 5

HRV_USERNAME = None
HRV_TOKEN = None

session = requests.Session()
last_post_time = 0
last_valid_bpm = None

valid_rr_intervals = []
valid_bpm_readings = []

last_signal_status = "Unknown"
last_stress_level = "Measuring"


def get_signal_status(ir_value, data):
    """Determine signal quality based on IR value and data."""
    global last_signal_status
    
    if ir_value is None:
        if "status" in data:
            status = data.get("status", "")
            if status in ["no_finger", "finger_removed"]:
                last_signal_status = "No Finger"
                return "No Finger"
            elif status == "stabilized":
                last_signal_status = "Good"
                return "Good"
            elif status == "unstable":
                last_signal_status = "Unstable"
                return "Unstable"
        last_signal_status = "Unstable"
        return "Unstable"
    
    if ir_value < IR_THRESHOLD:
        last_signal_status = "No Finger"
        return "No Finger"
    
    last_signal_status = "Good"
    return "Good"


def validate_bpm(bpm):
    """Validate BPM is within acceptable range and no sudden jump."""
    global last_valid_bpm
    
    if bpm < BPM_MIN or bpm > BPM_MAX:
        return False, f"BPM {bpm} outside range ({BPM_MIN}-{BPM_MAX})"
    
    if last_valid_bpm is not None:
        bpm_jump = abs(bpm - last_valid_bpm)
        if bpm_jump > BPM_JUMP_THRESHOLD:
            return False, f"BPM jump detected: {last_valid_bpm} -> {bpm} ({bpm_jump:.0f} BPM change)"
    
    return True, "OK"


def validate_rr_interval(rr_ms):
    """Validate RR interval is physiologically plausible."""
    if rr_ms < RR_MIN_MS or rr_ms > RR_MAX_MS:
        return False, f"RR interval {rr_ms:.0f}ms outside range ({RR_MIN_MS}-{RR_MAX_MS}ms)"
    return True, "OK"


def compute_sdnn(rr_list):
    """Compute SDNN from list of RR intervals in milliseconds."""
    if len(rr_list) < 2:
        return None
    return statistics.stdev(rr_list)


def compute_mean_rr(rr_list):
    """Compute mean RR interval from list in milliseconds."""
    if not rr_list:
        return None
    return statistics.mean(rr_list)


def classify_stress(sdnn, signal_quality):
    """Classify stress level based on SDNN.
    
    Only returns actual stress classification when signal quality is Good.
    SDNN-based classification:
    - SDNN >= 50 ms -> Low Stress (Relaxed)
    - SDNN 30-49 ms -> Moderate Stress
    - SDNN < 30 ms -> High Stress
    """
    global last_stress_level
    
    if signal_quality != "Good" or sdnn is None:
        last_stress_level = "Invalid / Measuring"
        return "Invalid / Measuring"
    
    if sdnn >= 50:
        last_stress_level = "Low Stress"
        return "Low Stress"
    elif sdnn >= 30:
        last_stress_level = "Moderate Stress"
        return "Moderate Stress"
    else:
        last_stress_level = "High Stress"
        return "High Stress"


def smooth_bpm(bpm):
    """Add BPM to history and return moving average."""
    valid_bpm_readings.append(bpm)
    if len(valid_bpm_readings) > SMOOTHING_WINDOW:
        valid_bpm_readings.pop(0)
    return statistics.mean(valid_bpm_readings)


def smooth_sdnn(sdnn):
    """Add SDNN to history and return moving average."""
    global valid_rr_intervals
    
    if sdnn is not None:
        valid_sdnn_readings.append(sdnn)
        if len(valid_sdnn_readings) > SMOOTHING_WINDOW:
            valid_sdnn_readings.pop(0)
        return statistics.mean(valid_sdnn_readings)
    return None


valid_sdnn_readings = []


def bridge_login(username, password):
    """Login to Django and maintain session."""
    login_url = BASE_URL + "/api/hrv-bridge-login/"
    
    try:
        response = session.post(
            login_url,
            json={"username": username, "password": password},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print(f"[BRIDGE] Logged in as: {data.get('username')}")
                return True
            else:
                print(f"[BRIDGE] Login failed: {data.get('error', 'Unknown error')}")
                return False
        elif response.status_code == 401:
            print(f"[BRIDGE] Login failed: {response.json().get('error', 'Invalid credentials')}")
            return False
        else:
            print(f"[BRIDGE] Login HTTP error: {response.status_code}")
            return False
            
    except requests.RequestException as e:
        print(f"[BRIDGE] Login connection error: {e}")
        return False


def post_hrv_data(data):
    """Send HRV data to Django API."""
    global last_post_time
    
    current_time = time.time()
    
    if current_time - last_post_time < MIN_POST_INTERVAL:
        return False
    
    if HRV_USERNAME and HRV_TOKEN:
        data['username'] = HRV_USERNAME
        data['token'] = HRV_TOKEN
    
    hrv_url = BASE_URL + "/api/hrv-bridge/"
    
    try:
        response = session.post(
            hrv_url,
            json=data,
            timeout=5
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                last_post_time = current_time
                return True
            else:
                print(f"[BRIDGE] API error: {result.get('error', 'Unknown')}")
                return False
        elif response.status_code == 401:
            print(f"[BRIDGE] Session expired")
            return False
        else:
            print(f"[BRIDGE] HTTP {response.status_code}")
            return False
            
    except requests.RequestException as e:
        print(f"[BRIDGE] POST error: {e}")
        return False


def is_status_only(data):
    """Check if JSON is just a status message."""
    return "status" in data and len(data.keys()) == 1


def parse_arduino_data(line):
    """Parse Arduino JSON data and extract HRV values."""
    try:
        data = json.loads(line)
        return data
    except json.JSONDecodeError:
        return None


def get_credentials():
    """Get username and password from user."""
    print("\n" + "=" * 50)
    print("Django Login")
    print("=" * 50)
    username = input("Username: ").strip()
    password = input("Password: ")
    
    if not username or not password:
        print("Error: Username and password required")
        return None, None
    
    return username, password


def main():
    global HRV_USERNAME, HRV_TOKEN, last_valid_bpm, valid_rr_intervals
    global valid_bpm_readings, valid_sdnn_readings
    
    saved_count = 0
    skip_count = 0
    skipped_reasons = {}
    ser = None
    
    print("=" * 60)
    print("HRV Serial Bridge (with Signal Validation)")
    print("=" * 60)
    print(f"Serial: {SERIAL_PORT} @ {BAUD_RATE} baud")
    print(f"Min post interval: {MIN_POST_INTERVAL}s")
    print(f"BPM range: {BPM_MIN}-{BPM_MAX}")
    print(f"IR threshold: {IR_THRESHOLD}")
    print(f"RR interval range: {RR_MIN_MS}-{RR_MAX_MS}ms")
    print(f"Min valid RR for SDNN: {MIN_VALID_RR_FOR_SDNN}")
    print()
    
    username, password = get_credentials()
    
    if not username or not password:
        return
    
    HRV_USERNAME = username
    
    if not bridge_login(username, password):
        print("[BRIDGE] Cannot proceed without authentication")
        retry = input("Retry? (y/n): ").lower().strip()
        if retry == 'y':
            main()
        return
    
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        print(f"\n[BRIDGE] Connected to {SERIAL_PORT}")
        print("[BRIDGE] Place finger on sensor...\n")
        
        skip_count = 0
        saved_count = 0
        skipped_reasons = {}
        closed = False
        
        while True:
            try:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                
                if not line:
                    continue
                
                if line.startswith("{") and line.endswith("}"):
                    data = parse_arduino_data(line)
                    
                    if data is None:
                        continue
                    
                    if is_status_only(data):
                        status = data.get('status', 'unknown')
                        signal_status = get_signal_status(None, data)
                        
                        status_messages = {
                            'hrv_module_started': 'HRV module ready',
                            'finger_detected': 'Finger detected - measuring...',
                            'stabilized': 'Measurements stabilized',
                            'no_finger': 'Remove finger or place properly',
                            'finger_removed': 'Remove finger or place properly',
                            'unstable': 'Signal unstable - hold steady',
                        }
                        msg = status_messages.get(status, status)
                        
                        if signal_status == "No Finger":
                            print(f"[SIGNAL] {msg}")
                        elif signal_status == "Unstable":
                            print(f"[SIGNAL] {msg}")
                        else:
                            print(f"[STATUS] {msg}")
                        continue
                    
                    ir_value = data.get('ir') or data.get('ir_value') or data.get('IR')
                    bpm_raw = data.get('bpm') or data.get('BPM')
                    rr_raw = data.get('rr') or data.get('RR') or data.get('rr_ms') or data.get('RR_ms')
                    sdnn_raw = data.get('sdnn') or data.get('SDNN')
                    
                    if bpm_raw is None:
                        continue
                    
                    try:
                        bpm_raw = float(bpm_raw)
                    except (ValueError, TypeError):
                        print(f"[SKIP] Invalid BPM value: {bpm_raw}")
                        continue
                    
                    signal_status = get_signal_status(ir_value, data)
                    
                    if signal_status == "No Finger":
                        skip_count += 1
                        reason = "No Finger"
                        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
                        print(f"[SKIP] Unstable signal / finger not placed properly")
                        continue
                    
                    valid, msg = validate_bpm(bpm_raw)
                    if not valid:
                        skip_count += 1
                        reason = msg
                        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
                        print(f"[SKIP] {msg}")
                        continue
                    
                    rr_valid = False
                    rr_ms = None
                    if rr_raw is not None:
                        try:
                            rr_ms = float(rr_raw)
                            valid_rr, msg = validate_rr_interval(rr_ms)
                            if valid_rr:
                                valid_rr_intervals.append(rr_ms)
                                rr_valid = True
                                if len(valid_rr_intervals) > 100:
                                    valid_rr_intervals = valid_rr_intervals[-50:]
                            else:
                                print(f"[SKIP] {msg}")
                        except (ValueError, TypeError):
                            pass
                    
                    if len(valid_rr_intervals) < MIN_VALID_RR_FOR_SDNN:
                        skip_count += 1
                        reason = f"Waiting for more RR intervals ({len(valid_rr_intervals)}/{MIN_VALID_RR_FOR_SDNN})"
                        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
                        print(f"[SKIP] Insufficient RR data ({len(valid_rr_intervals)}/{MIN_VALID_RR_FOR_SDNN})")
                        continue
                    
                    sdnn_raw_val = compute_sdnn(valid_rr_intervals)
                    
                    if sdnn_raw_val is None or sdnn_raw_val < 5:
                        skip_count += 1
                        reason = "Invalid SDNN"
                        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
                        print(f"[SKIP] SDNN too low: {sdnn_raw_val}")
                        continue
                    
                    bpm_smoothed = smooth_bpm(bpm_raw)
                    sdnn_smoothed = smooth_sdnn(sdnn_raw_val)
                    
                    stress = classify_stress(sdnn_smoothed, signal_status)
                    
                    last_valid_bpm = bpm_raw
                    
                    post_data = {
                        'bpm': round(bpm_smoothed, 1),
                        'sdnn': round(sdnn_smoothed, 1) if sdnn_smoothed else round(sdnn_raw_val, 1),
                        'ir': ir_value,
                        'stress': stress,
                    }
                    
                    current_time = time.time()
                    should_post = (current_time - last_post_time) >= MIN_POST_INTERVAL
                    
                    if should_post and post_hrv_data(post_data):
                        saved_count += 1
                        posted_bpm = post_data.get('bpm', 0)
                        posted_sdnn = post_data.get('sdnn', 0)
                        posted_stress = post_data.get('stress', 'unknown')
                        print(f"[HRV] BPM:{posted_bpm:.0f} SDNN:{posted_sdnn:.1f} Stress:{posted_stress} Signal:{signal_status} Posted:Yes")
                    else:
                        skip_count += 1
                        reason = "Min interval not met"
                        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
                        print(f"[SKIP] BPM:{bpm_smoothed:.0f} SDNN:{sdnn_smoothed:.1f} Stress:{stress} Signal:{signal_status} Posted:No (min interval)")
                        
                else:
                    pass
                    
            except KeyboardInterrupt:
                print("\n[BRIDGE] Stopped by user")
                break
            except serial.SerialException as e:
                print(f"[BRIDGE] Serial error: {e}")
                break
            except Exception as e:
                print(f"[BRIDGE] Error: {e}")
                time.sleep(1)
                
    except serial.SerialException as e:
        print(f"\n[BRIDGE] Cannot open serial port: {e}")
    finally:
        # Variables are always initialized before reaching finally block
        if ser and ser.is_open:  # type: ignore
            ser.close()
        
        print(f"\n[BRIDGE] Done.")
        print(f"  Saved readings: {saved_count}")
        print(f"  Skipped readings: {skip_count}")
        
        if skipped_reasons:
            print(f"\n  Skip reasons:")
            for reason, count in skipped_reasons.items():
                print(f"    {reason}: {count}")


if __name__ == "__main__":
    main()