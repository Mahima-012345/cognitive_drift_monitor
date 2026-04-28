"""
Eye Blink Detection Module - MediaPipe Face Mesh
For Cognitive Drift Monitor

A. INSTALL COMMANDS:
    pip install mediapipe opencv-python numpy requests

B. MODEL FILE:
    Download face_landmarker.task from:
    https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
    
    Save it in the same folder as eye_tracker.py

Usage:
    python eye_tracker.py [--username USERNAME] [--token TOKEN]

Features:
    - Real-time webcam detection using MediaPipe Face Mesh
    - EAR-based blink detection with smoothing
    - DEBUG_VIEW = False by default (no window freeze)
    - Session data posted to Django every 30 seconds
"""

import cv2
import numpy as np
import time
import requests
import json
import sys
import argparse

DEBUG_VIEW = False  # Set True to show webcam window --use-window to enable

SESSION_DURATION = 30  # Summary interval in seconds

# Blink Detection Sensitivity
EAR_THRESHOLD = 0.23
BLINK_COOLDOWN = 0.15
MIN_BLINK_DURATION = 0.05
MAX_BLINK_DURATION = 0.60

# Eye state smoothing - require sustained abnormal condition
EYE_STATE_WINDOW = 5
DROWSY_RATE_THRESHOLD = 15
EYE_STRAIN_RATE_THRESHOLD = 30

DJANGO_API_URL = "http://127.0.0.1:8000/api/save-eye/"

LEFT_EYE_INDICES = [362, 385, 387, 263, 373, 380]
RIGHT_EYE_INDICES = [33, 160, 158, 133, 153, 144]

MODEL_PATH = "face_landmarker.task"

# Authentication for Django
EYE_USERNAME = None
EYE_TOKEN = None


def calculate_ear(eye_points):
    if len(eye_points) < 6:
        return 0.25
    p1, p2, p3, p4, p5, p6 = [np.array(pt) for pt in eye_points[:6]]
    v1 = np.linalg.norm(p2 - p6)
    v2 = np.linalg.norm(p3 - p5)
    h = np.linalg.norm(p1 - p4)
    if h == 0:
        return 0.25
    return (v1 + v2) / (2.0 * h)


def classify_eye_state_smooth(blink_rate, avg_duration, counts):
    drowsy_c = counts['drowsy']
    fatigue_c = counts['fatigue']
    strain_c = counts['eye_strain']
    normal_c = counts['normal']
    
    is_drowsy = blink_rate < DROWSY_RATE_THRESHOLD and avg_duration > 200
    is_fatigue = 20 < blink_rate <= 30
    is_strain = blink_rate > EYE_STRAIN_RATE_THRESHOLD
    
    if is_drowsy:
        drowsy_c += 1
        normal_c = max(0, normal_c - 1)
    elif is_strain:
        strain_c += 1
        normal_c = max(0, normal_c - 1)
    elif is_fatigue:
        fatigue_c += 1
        normal_c = max(0, normal_c - 1)
    else:
        drowsy_c = max(0, drowsy_c - 1)
        fatigue_c = max(0, fatigue_c - 1)
        strain_c = max(0, strain_c - 1)
        normal_c += 1
    
    if drowsy_c >= EYE_STATE_WINDOW:
        state = 'drowsy'
    elif strain_c >= EYE_STATE_WINDOW:
        state = 'eye_strain'
    elif fatigue_c >= EYE_STATE_WINDOW:
        state = 'fatigue'
    else:
        state = 'normal'
    
    return state, {'drowsy': drowsy_c, 'fatigue': fatigue_c, 'eye_strain': strain_c, 'normal': normal_c}


def calculate_eye_score(state):
    scores = {'normal': 100, 'drowsy': 60, 'fatigue': 40, 'eye_strain': 20}
    return scores.get(state, 60)


def login_to_django(session, username, password):
    try:
        r = session.get("http://127.0.0.1:8000/login/", timeout=5)
        csrf = session.cookies.get('csrftoken')
        if not csrf:
            return False
        response = session.post(
            "http://127.0.0.1:8000/login/",
            data={'username': username, 'password': password, 'csrfmiddlewaretoken': csrf, 'next': '/dashboard/'},
            timeout=5, headers={'Referer': 'http://127.0.0.1:8000/login/'}
        )
        return response.status_code in [200, 302] or response.ok
    except Exception:
        return False


def post_to_django(session, data):
    # Add authentication to payload
    if EYE_USERNAME and EYE_TOKEN:
        data['username'] = EYE_USERNAME
        data['token'] = EYE_TOKEN
    
    try:
        r = session.post(DJANGO_API_URL, json=data, timeout=10)
        if r.status_code == 200:
            print(f"[OK] Saved to Django! Record ID: {r.json().get('record_id')}")
            return True
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Eye Blink Detection')
    parser.add_argument('--username', type=str, help='Django username')
    parser.add_argument('--token', type=str, help='Monitoring token')
    parser.add_argument('--use-window', action='store_true', help='Show webcam window')
    args = parser.parse_args()
    
    global EYE_USERNAME, EYE_TOKEN, DEBUG_VIEW
    if args.username and args.token:
        EYE_USERNAME = args.username
        EYE_TOKEN = args.token
        print(f"[AUTH] User: {EYE_USERNAME}")
    
    if args.use_window:
        DEBUG_VIEW = True
        print("[WINDOW] Webcam display enabled")
    
    print("=" * 60)
    print("  Eye Blink Detection - MediaPipe")
    print(f"  DEBUG_VIEW: {DEBUG_VIEW}")
    print("=" * 60)
    
    # Initialize MediaPipe
    face_mesh = None
    try:
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        options = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=vision.RunningMode.VIDEO, num_faces=1,
            min_face_detection_confidence=0.5, min_face_presence_confidence=0.5, min_tracking_confidence=0.5
        )
        face_mesh = vision.FaceLandmarker.create_from_options(options)
        print("[OK] MediaPipe ready!")
    except Exception as e:
        print(f"[ERROR] MediaPipe init failed: {e}")
        return
    
    # Open webcam
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Cannot open webcam!")
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    print("[OK] Webcam ready!")
    
    if DEBUG_VIEW:
        cv2.namedWindow("Eye Blink Detection", cv2.WINDOW_NORMAL)
    
    # State tracking
    consecutive_counts = {'drowsy': 0, 'fatigue': 0, 'eye_strain': 0, 'normal': 0}
    baseline_open_ear = None
    adaptive_threshold = None
    calibration_samples = []
    is_calibrating = True
    calib_start_time = None
    blink_state = "open"
    blink_start_time = 0
    
    total_blinks = 0
    window_blinks = 0
    window_blink_durations = []
    last_blink_time = 0
    current_ear = 0.25
    ear_samples = []
    window_start_time = None
    session_start = time.time()
    last_summary_time = session_start
    session_id = 0
    posted_windows = set()
    
    # Credentials
    print("-" * 40)
    django_username = input("Django Username: ").strip()
    django_password = input("Django Password: ").strip()
    print("-" * 40)
    
    if not django_username or not django_password:
        print("[WARN] No credentials - continuing without Django")
        django_connected = False
        session = None
    else:
        session = requests.Session()
        django_connected = login_to_django(session, django_username, django_password)
        if not django_connected:
            print("[WARN] Django login failed")
    
    print("[INFO] Running. Press Ctrl+C to quit.")
    print(f"[INFO] Posting every {SESSION_DURATION} seconds.")
    
    running = True
    while running:
        ret, frame = cap.read()
        if not ret:
            break
        
        current_time = time.time()
        elapsed_since_last_summary = current_time - last_summary_time
        timestamp_ms = int(current_time * 1000)
        
        # MediaPipe detection
        from mediapipe import Image, ImageFormat
        mp_image = Image(image_format=ImageFormat.SRGB, data=frame)
        results = face_mesh.detect_for_video(mp_image, timestamp_ms)
        
        h, w = frame.shape[:2]
        eyes_detected = False
        
        if results.face_landmarks:
            landmarks = results.face_landmarks[0]
            
            def get_eye_points(indices):
                return [(int(landmarks[i].x * w), int(landmarks[i].y * h)) for i in indices]
            
            left_eye = get_eye_points(LEFT_EYE_INDICES)
            right_eye = get_eye_points(RIGHT_EYE_INDICES)
            
            if len(left_eye) >= 6 and len(right_eye) >= 6:
                eyes_detected = True
                current_ear = (calculate_ear(left_eye) + calculate_ear(right_eye)) / 2.0
                ear_samples.append(round(current_ear, 3))
                if len(ear_samples) > 60:
                    ear_samples = ear_samples[-60:]
        
        # Calibration
        if is_calibrating:
            if calib_start_time is None:
                calib_start_time = current_time
            if eyes_detected and current_ear > 0.20:
                calibration_samples.append(current_ear)
            if current_time - calib_start_time >= 5.0 and calibration_samples:
                baseline_open_ear = np.mean(calibration_samples)
                adaptive_threshold = baseline_open_ear * 0.80
                is_calibrating = False
                print(f"[CALIB] EAR: {baseline_open_ear:.3f}, thr: {adaptive_threshold:.3f}")
        
        # Blink detection
        if eyes_detected:
            use_threshold = adaptive_threshold if adaptive_threshold else EAR_THRESHOLD
            
            if blink_state == "open":
                drop_ratio = current_ear / baseline_open_ear if baseline_open_ear else 1.0
                thr = use_threshold if baseline_open_ear else EAR_THRESHOLD
                if current_ear < thr or (baseline_open_ear and drop_ratio < 0.88):
                    blink_state = "closed"
                    blink_start_time = current_time
            
            elif blink_state == "closed":
                if current_ear >= use_threshold:
                    duration = current_time - blink_start_time
                    duration_ms = duration * 1000
                    if MIN_BLINK_DURATION <= duration <= MAX_BLINK_DURATION:
                        if current_time - last_blink_time >= BLINK_COOLDOWN:
                            total_blinks += 1
                            window_blinks += 1
                            window_blink_durations.append(duration_ms)
                            last_blink_time = current_time
                    blink_state = "open"
                elif current_time - blink_start_time > MAX_BLINK_DURATION:
                    blink_state = "open"
        
        if window_start_time is None:
            window_start_time = session_start
        
        # Metrics
        window_elapsed = max(0.1, current_time - window_start_time)
        rate = (window_blinks / window_elapsed) * 60
        avg_duration = np.mean(window_blink_durations) if window_blink_durations else 0
        
        eye_status, consecutive_counts = classify_eye_state_smooth(rate, avg_duration, consecutive_counts)
        eye_score = calculate_eye_score(eye_status)
        
        # Display
        if DEBUG_VIEW:
            cv2.putText(frame, f"Rate: {rate:.1f}/min", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(frame, f"State: {eye_status}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.imshow("Eye Blink Detection", frame)
        
        cv2.waitKey(1)
        
        # 30-second summary
        if elapsed_since_last_summary >= SESSION_DURATION:
            session_id += 1
            interval_rate = window_blinks * 2
            avg_duration = np.mean(window_blink_durations) if window_blink_durations else 0
            interval_score = calculate_eye_score(eye_status)
            
            print(f"[SUMMARY #{session_id}] blinks: {window_blinks}, rate: {interval_rate:.1f}/min, state: {eye_status}")
            
            if django_connected:
                window_id = f"{session_id}_{int(current_time)}"
                if window_id not in posted_windows:
                    posted_windows.add(window_id)
                    post_data = {
                        'ear': round(current_ear, 4),
                        'blink_count': window_blinks,
                        'blink_duration_avg': round(avg_duration, 2),
                        'blink_rate': round(interval_rate, 2),
                        'eye_state': eye_status,
                        'eye_score': interval_score,
                        'fatigue_flag': eye_status in ['drowsy', 'fatigue', 'eye_strain'],
                        'ear_samples': json.dumps(ear_samples[-30:]),
                        'notes': f"Window {session_id}",
                    }
                    post_to_django(session, post_data)
            
            window_blinks = 0
            window_blink_durations = []
            window_start_time = current_time
            last_summary_time = current_time
    
    cap.release()
    if DEBUG_VIEW:
        cv2.destroyAllWindows()
    cv2.waitKey(1)
    print("[INFO] Eye tracker stopped.")


if __name__ == "__main__":
    main()