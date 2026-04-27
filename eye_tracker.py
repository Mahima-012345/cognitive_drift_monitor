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
    python eye_tracker.py

Features:
    - Real-time webcam detection using MediaPipe Face Mesh
    - EAR-based blink detection with simple state machine
    - Non-blocking loop using cv2.waitKey(1)
    - Session data sent to Django AFTER session ends (ONE POST only)
"""

import cv2
import numpy as np
import time
import requests
import os

# =============================================================================
# CONFIGURATION
# =============================================================================

SESSION_DURATION = 30  # Summary interval in seconds (not session duration)

# Phase 7: Blink Detection Sensitivity - Tunable
EAR_THRESHOLD = 0.23        # Base threshold (overridden by adaptive)
EYE_AR_CONSEC_FRAMES = 1    # Reduced: 1-2 frames for fast natural blinks
BLINK_COOLDOWN = 0.15        # Debounce to avoid double counting (150ms)
MIN_BLINK_DURATION = 0.05  # Reduced: capture fast blinks (50ms)
MAX_BLINK_DURATION = 0.60  # Natural blink max (600ms)
EAR_DEBUG = True           # Show live EAR values

# Phase 7: Adaptive blink detection variables
baseline_open_ear = None
adaptive_threshold = None
calibration_samples = []
calibration_duration = 5.0  # 5 seconds calibration
is_calibrating = True
calib_start_time = None

# Blink state machine states
BLINK_STATE_OPEN = "open"
BLINK_STATE_CLOSED = "closed_candidate"
BLINK_STATE_CONFIRMED = "confirmed"
blink_state = BLINK_STATE_OPEN

DJANGO_API_URL = "http://127.0.0.1:8000/api/save-eye/"
DJANGO_USER = None  # Set at runtime
DJANGO_PASSWORD = None  # Set at runtime

LEFT_EYE_INDICES = [362, 385, 387, 263, 373, 380]
RIGHT_EYE_INDICES = [33, 160, 158, 133, 153, 144]

MODEL_PATH = "face_landmarker.task"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def calculate_ear(eye_points):
    if len(eye_points) < 6:
        return 0.25
    
    p1, p2, p3, p4, p5, p6 = [np.array(pt) for pt in eye_points[:6]]
    
    v1 = np.linalg.norm(p2 - p6)
    v2 = np.linalg.norm(p3 - p5)
    h = np.linalg.norm(p1 - p4)
    
    if h == 0:
        return 0.25
    
    ear = (v1 + v2) / (2.0 * h)
    return ear


def classify_eye_state(blink_rate):
    # Phase 7: Classification based on 30-second window blink rate
    if blink_rate < 15:
        return 'drowsy'  # Too low = sleepy/tired
    elif blink_rate <= 20:
        return 'normal'  # Healthy range
    elif blink_rate <= 30:
        return 'fatigue'  # Mild eye strain from too much focus
    else:
        return 'eye_strain'  # Excessive blinking = eye strain


def calculate_eye_score(state):
    scores = {
        'normal': 100,
        'drowsy': 60,
        'fatigue': 40,
        'eye_strain': 20,
    }
    return scores.get(state, 60)


def login_to_django(session, username, password):
    try:
        r = session.get("http://127.0.0.1:8000/login/", timeout=5)
        csrf = session.cookies.get('csrftoken')
        
        if not csrf:
            print("[WARN] Could not get CSRF token")
            return False
        
        response = session.post(
            "http://127.0.0.1:8000/login/",
            data={
                'username': username,
                'password': password,
                'csrfmiddlewaretoken': csrf,
                'next': '/dashboard/'
            },
            timeout=5,
            headers={'Referer': 'http://127.0.0.1:8000/login/'}
        )
        
        if response.status_code in [200, 302] or response.ok:
            print(f"[OK] Logged into Django as '{username}'")
            return True
        else:
            print(f"[WARN] Login failed: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"[WARN] Django login failed: {e}")
    
    return False


def post_to_django(session, data):
    try:
        r = session.post(
            DJANGO_API_URL,
            json=data,
            timeout=10
        )
        
        if r.status_code == 200:
            result = r.json()
            record_id = result.get('record_id', 'N/A')
            print(f"[OK] Saved to Django! Record ID: {record_id}")
            return True
        else:
            print(f"[ERROR] HTTP {r.status_code}: {r.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("[WARN] Could not connect to Django server")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


# =============================================================================
# MAIN TRACKER
# =============================================================================

def main():
    print("=" * 60)
    print("  Eye Blink Detection - MediaPipe Face Mesh")
    print("=" * 60)
    print()
    
    # Initialize MediaPipe Face Mesh
    print("[INFO] Initializing MediaPipe Face Mesh...")
    face_mesh = None
    
    try:
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        
        options = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5
        )
        face_mesh = vision.FaceLandmarker.create_from_options(options)
        print("[OK] MediaPipe ready!")
        
    except ImportError as e:
        print(f"[ERROR] MediaPipe not installed: {e}")
        print("       Run: pip install mediapipe")
        return
    except FileNotFoundError:
        print(f"[ERROR] {MODEL_PATH} not found!")
        print("       Download from:")
        print("       https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task")
        return
    except Exception as e:
        print(f"[ERROR] MediaPipe init failed: {e}")
        return
    
    # Open webcam
    print("[INFO] Opening webcam...")
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("[ERROR] Cannot open webcam!")
        return
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    print("[OK] Webcam ready!")
    
    # Main tracking variables (reset every interval)
    total_blinks = 0       # All blinks since program started
    window_blinks = 0       # Blinks in current 30-second window
    window_blink_durations = []  # Blink durations for current window
    blink_in_progress = False
    blink_start_time = 0
    last_blink_time = 0
    current_ear = 0.25
    ear_samples = []
    window_start_time = None   # Track start of current 30-second window
    
    # Phase 7: Initialize adaptive blink detection
    
    # Phase 7: Initialize adaptive blink detection
    baseline_open_ear = None
    adaptive_threshold = None
    calibration_samples = []
    is_calibrating = True
    calib_start_time = None
    BLINK_STATE_OPEN = "open"
    BLINK_STATE_CLOSED = "closed_candidate"
    blink_state = BLINK_STATE_OPEN
    
    # Timing control
    session_start = time.time()
    last_summary_time = session_start
    session_id = 0  # Counter for duplicate prevention
    
    posted_windows = set()  # Track posted window IDs to prevent duplicates
    
    # Get Django credentials
    print()
    print("-" * 40)
    django_username = input("Django Username: ").strip()
    django_password = input("Django Password: ").strip()
    print("-" * 40)
    print()
    
    if not django_username or not django_password:
        print("[WARN] Empty credentials - continuing without Django")
        django_connected = False
        session = None
    else:
        # Connect to Django
        session = requests.Session()
        django_connected = login_to_django(session, django_username, django_password)
        
        if not django_connected:
            print("[INFO] Continuing without Django (local tracking still works)")
    
    print()
    print("[INFO] Continuous mode started. Press 'q' to quit.")
    print(f"[INFO] Summary will be posted every {SESSION_DURATION} seconds.")
    print(f"[INFO] EAR threshold: {EAR_THRESHOLD}, Consec frames: {EYE_AR_CONSEC_FRAMES}")
    print()
    
    # Main tracking loop
    running = True
    while running:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Failed to read frame")
            break
        
        current_time = time.time()
        elapsed = current_time - session_start
        elapsed_since_last_summary = current_time - last_summary_time
        timestamp_ms = int(current_time * 1000)
        
        # Process with MediaPipe
        from mediapipe import Image, ImageFormat
        mp_image = Image(image_format=ImageFormat.SRGB, data=frame)
        results = face_mesh.detect_for_video(mp_image, timestamp_ms)
        
        h, w = frame.shape[:2]
        face_detected = False
        eyes_detected = False
        
        if results.face_landmarks:
            face_detected = True
            landmarks = results.face_landmarks[0]
            
            def get_eye_points(indices):
                pts = []
                for idx in indices:
                    lm = landmarks[idx]
                    x = int(lm.x * w)
                    y = int(lm.y * h)
                    pts.append((x, y))
                return pts
            
            left_eye = get_eye_points(LEFT_EYE_INDICES)
            right_eye = get_eye_points(RIGHT_EYE_INDICES)
            
            if len(left_eye) >= 6 and len(right_eye) >= 6:
                eyes_detected = True
                
                left_ear = calculate_ear(left_eye)
                right_ear = calculate_ear(right_eye)
                current_ear = (left_ear + right_ear) / 2.0
                
                ear_samples.append(round(current_ear, 3))
                if len(ear_samples) > 60:
                    ear_samples = ear_samples[-60:]
                
                # Draw eye landmarks
                for pt in left_eye:
                    cv2.circle(frame, pt, 2, (0, 255, 0), -1)
                for pt in right_eye:
                    cv2.circle(frame, pt, 2, (0, 255, 0), -1)
        
        # Phase 7: Improved blink detection logic
        # Adaptive calibration (first 5 seconds)
        if is_calibrating:
            if calib_start_time is None:
                calib_start_time = current_time
            calib_elapsed = current_time - calib_start_time
            
            if eyes_detected and current_ear > 0.20:
                calibration_samples.append(current_ear)
            
            if calib_elapsed >= calibration_duration and calibration_samples:
                baseline_open_ear = np.mean(calibration_samples)
                adaptive_threshold = baseline_open_ear * 0.80  # 20% drop = blink
                is_calibrating = False
                print(f"[CALIB] Baseline EAR: {baseline_open_ear:.3f}, Adaptive threshold: {adaptive_threshold:.3f}")
            elif EAR_DEBUG and int(calib_elapsed) % 1 == 0:
                print(f"[CALIB] {calib_elapsed:.1f}s / {calibration_duration}s...")
        
        # Blink detection with state machine
        if eyes_detected:
            # Use adaptive threshold if available, otherwise fallback to base
            use_threshold = adaptive_threshold if adaptive_threshold else EAR_THRESHOLD
            
            # Debug output
            if EAR_DEBUG and len(ear_samples) % 15 == 0:
                base_val = f"{baseline_open_ear:.3f}" if baseline_open_ear else "N/A"
                print(f"[EAR] {current_ear:.3f} | thr: {use_threshold:.3f} | base: {base_val} | state: {blink_state}")
            
            # State machine
            if blink_state == BLINK_STATE_OPEN:
                # Check for eye closure (EAR drops below adaptive threshold)
                drop_ratio = current_ear / baseline_open_ear if baseline_open_ear else 1.0
                threshold_for_check = use_threshold if baseline_open_ear else EAR_THRESHOLD
                if current_ear < threshold_for_check or (baseline_open_ear and drop_ratio < 0.88):  # 12% drop
                    blink_state = BLINK_STATE_CLOSED
                    blink_start_time = current_time
            
            elif blink_state == BLINK_STATE_CLOSED:
                # Eye might be blinking - check if it opened back up
                if current_ear >= use_threshold:
                    duration = current_time - blink_start_time
                    duration_ms = duration * 1000
                    
                    # Valid blink duration: 50ms to 600ms
                    if MIN_BLINK_DURATION <= duration <= MAX_BLINK_DURATION:
                        # Debounce check
                        if current_time - last_blink_time >= BLINK_COOLDOWN:
                            total_blinks += 1
                            window_blinks += 1
                            window_blink_durations.append(duration_ms)
                            last_blink_time = current_time
                            # Rate based on current window only
                            window_elapsed = current_time - (window_start_time or session_start)
                            window_elapsed = max(0.1, window_elapsed)
                            rate = (window_blinks / window_elapsed) * 60
                            print(f"[BLINK #{total_blinks}] {duration_ms:.0f}ms | win rate: {rate:.1f}/min | EAR={current_ear:.3f}")
                    
                    blink_state = BLINK_STATE_OPEN
                else:
                    # Still closed - check for timeout (max duration exceeded)
                    duration = current_time - blink_start_time
                    if duration > MAX_BLINK_DURATION:
                        blink_state = BLINK_STATE_OPEN  # Reset without counting

        # Initialize window start time at program start
        if window_start_time is None:
            window_start_time = session_start
        
        # Phase 7: Keyboard test - press 'b' to simulate blink
        key = cv2.waitKey(1) & 0xFF
        if key == ord('b'):
            # Simulate a manual blink
            total_blinks += 1
            window_blinks += 1
            window_blink_durations.append(150)  # 150ms typical blink
            last_blink_time = current_time
            window_elapsed = current_time - (window_start_time or session_start)
            window_elapsed = max(0.1, window_elapsed)
            rate = (window_blinks / window_elapsed) * 60
            print(f"[BLINK #{total_blinks}] 150ms (KEYBOARD TEST) | win rate: {rate:.1f}/min")
        
        # Calculate metrics using 30-second window
        window_elapsed = current_time - (window_start_time or session_start)
        window_elapsed = max(0.1, window_elapsed)
        rate = (window_blinks / window_elapsed) * 60  # Rate based on current 30-sec window
        avg_duration = np.mean(window_blink_durations) if window_blink_durations else 0
        eye_status = classify_eye_state(rate)
        eye_score = calculate_eye_score(eye_status)
        
        # Draw overlay
        cv2.putText(frame, "REAL MODE", (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"EAR: {current_ear:.3f}", (10, 55),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"Window Blinks: {window_blinks}", (10, 85),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"Rate: {rate:.1f}/min", (10, 115),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"State: {eye_status.upper()}", (10, 145),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, f"Score: {eye_score}", (10, 175),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        
        elapsed_total = int(current_time - session_start)
        cv2.putText(frame, f"Elapsed: {elapsed_total}s", (10, 205),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        next_summary_in = max(0, SESSION_DURATION - int(elapsed_since_last_summary))
        cv2.putText(frame, f"Next: {next_summary_in}s", (10, 230),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        state_colors = {
            'normal': (0, 255, 0),
            'drowsy': (0, 165, 255),
            'fatigue': (0, 140, 255),
            'eye_strain': (0, 0, 255)
        }
        color = state_colors.get(eye_status, (255, 255, 255))
        cv2.rectangle(frame, (5, frame.shape[0]-10), 
                     (frame.shape[1]-5, frame.shape[0]-5), color, -1)
        
        cv2.putText(frame, "Press 'q' to quit", (frame.shape[1]-200, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        cv2.imshow("Eye Blink Detection - MediaPipe", frame)
        
        # Non-blocking key check
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            running = False
            continue
        
        # Check if 30-second summary interval reached
        elapsed_since_last_summary = current_time - last_summary_time
        if elapsed_since_last_summary >= SESSION_DURATION:
            session_id += 1
            # Use window_blinks for 30-second summary
            interval_rate = window_blinks * 2  # 30 sec * 2 = per minute
            avg_duration = np.mean(window_blink_durations) if window_blink_durations else 0
            interval_state = classify_eye_state(interval_rate)
            interval_score = calculate_eye_score(interval_state)
            fatigue_flag = interval_state in ['drowsy', 'fatigue', 'eye_strain']
            
            print()
            print("=" * 60)
            print(f"  {SESSION_DURATION}-SECOND SUMMARY #{session_id}")
            print("=" * 60)
            print(f"  Window Duration: {SESSION_DURATION}s")
            print(f"  Window Blinks:   {window_blinks}")
            print(f"  Total Blinks:    {total_blinks}")
            print(f"  Blink Rate:    {interval_rate:.1f}/min")
            print(f"  Avg Duration: {avg_duration:.0f}ms")
            print(f"  Eye State:     {interval_state}")
            print(f"  Eye Score:    {interval_score}")
            print(f"  Fatigue:     {'Yes' if fatigue_flag else 'No'}")
            print("=" * 60)
            
            # POST to Django (with duplicate prevention)
            if django_connected:
                window_id = f"{session_id}_{int(current_time)}"
                if window_id not in posted_windows:
                    posted_windows.add(window_id)
                    print("[INFO] Sending data to Django...")
                    
                    import json
                    post_data = {
                        'ear': round(current_ear, 4),
                        'blink_count': window_blinks,
                        'blink_duration_avg': round(avg_duration, 2),
                        'blink_rate': round(interval_rate, 2),
                        'eye_state': interval_state,
                        'eye_score': interval_score,
                        'fatigue_flag': fatigue_flag,
                        'ear_samples': json.dumps(ear_samples[-30:] if ear_samples else []),
                        'notes': f"Window {session_id}: {SESSION_DURATION}s | {window_blinks} blinks",
                    }
                    
                    print(f"[DEBUG] Posting: blink_count={window_blinks}, blink_rate={interval_rate:.1f}, eye_state={interval_state}, eye_score={interval_score}")
                    post_to_django(session, post_data)
                else:
                    print("[DEBUG] Window already posted, skipping duplicate.")
            
            # Reset window counters for next window
            window_blinks = 0
            window_blink_durations = []
            window_start_time = current_time
            last_summary_time = current_time
    
    # Cleanup
    cv2.waitKey(1)  # Process any pending window events
    cap.release()
    cv2.destroyAllWindows()
    cv2.waitKey(1)  # Ensure windows are destroyed
    
    print("[INFO] Eye tracker stopped.")


if __name__ == "__main__":
    main()
