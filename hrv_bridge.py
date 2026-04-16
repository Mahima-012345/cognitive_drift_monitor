# hrv_bridge.py
"""
HRV Serial Bridge - Reads Arduino serial data and sends to Django API.
Phase 4 - HRV Module.

Features:
    - Session-based authentication
    - Handles stabilized status
    - Significant change detection
    - Minimum posting interval

Usage:
    python hrv_bridge.py
"""

import serial
import json
import time
import requests

SERIAL_PORT = "COM14"
BAUD_RATE = 115200
BASE_URL = "http://127.0.0.1:8000"

MIN_POST_INTERVAL = 5.0
SIGNIFICANT_CHANGE_BPM = 5.0
SIGNIFICANT_CHANGE_SDNN = 10.0

session = requests.Session()
last_post_time = 0
last_bpm = None
last_sdnn = None

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

def is_significant_change(bpm, sdnn):
    """Check if reading changed significantly from last."""
    global last_bpm, last_sdnn
    
    if last_bpm is None or last_sdnn is None:
        last_bpm = bpm
        last_sdnn = sdnn
        return True
    
    bpm_change = abs(bpm - last_bpm)
    sdnn_change = abs(sdnn - last_sdnn)
    
    significant = (bpm_change >= SIGNIFICANT_CHANGE_BPM or 
                   sdnn_change >= SIGNIFICANT_CHANGE_SDNN)
    
    last_bpm = bpm
    last_sdnn = sdnn
    
    return significant

def post_hrv_data(data):
    """Send HRV data to Django API."""
    global last_post_time
    
    current_time = time.time()
    
    if current_time - last_post_time < MIN_POST_INTERVAL:
        return False
    
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
                stress = data.get('stress', 'unknown')
                print(f"[HRV] BPM:{data.get('bpm'):.0f} SDNN:{data.get('sdnn'):.1f} Stress:{stress}")
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

def is_hrv_data(data):
    """Check if JSON contains HRV data."""
    return "bpm" in data and "sdnn" in data

def is_status_only(data):
    """Check if JSON is just a status message."""
    return "status" in data and len(data.keys()) == 1

def main():
    print("=" * 60)
    print("HRV Serial Bridge")
    print("=" * 60)
    print(f"Serial: {SERIAL_PORT} @ {BAUD_RATE} baud")
    print(f"Min post interval: {MIN_POST_INTERVAL}s")
    print()
    
    username, password = get_credentials()
    
    if not username or not password:
        return
    
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
        
        while True:
            try:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                
                if not line:
                    continue
                
                if line.startswith("{") and line.endswith("}"):
                    try:
                        data = json.loads(line)
                        
                        if is_status_only(data):
                            status = data.get('status', 'unknown')
                            status_messages = {
                                'hrv_module_started': 'HRV module ready',
                                'finger_detected': 'Finger detected - measuring...',
                                'stabilized': 'Measurements stabilized',
                                'no_finger': 'Remove finger or place properly',
                            }
                            msg = status_messages.get(status, status)
                            print(f"[STATUS] {msg}")
                            continue
                        
                        if is_hrv_data(data):
                            bpm = data.get('bpm')
                            sdnn = data.get('sdnn')
                            
                            if bpm and sdnn and bpm > 0:
                                if not is_significant_change(bpm, sdnn):
                                    skip_count += 1
                                    continue
                                
                                if post_hrv_data(data):
                                    saved_count += 1
                        else:
                            print(f"[SKIP] {line[:60]}")
                            
                    except json.JSONDecodeError:
                        pass
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
        try:
            ser.close()
        except:
            pass
        print(f"\n[BRIDGE] Done. Saved: {saved_count} | Skipped: {skip_count}")

if __name__ == "__main__":
    main()
