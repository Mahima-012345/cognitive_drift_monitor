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

SESSION_DURATION = 30

EAR_THRESHOLD = 0.23
CONSEC_FRAMES = 2
BLINK_COOLDOWN = 0.20
MIN_BLINK_DURATION = 0.03
MAX_BLINK_DURATION = 0.50

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
    if blink_rate < 15:
        return 'drowsy'
    elif blink_rate <= 20:
        return 'normal'
    elif blink_rate <= 30:
        return 'fatigue'
    else:
        return 'eye_strain'


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
    
    # Initialize tracking variables
    blink_count = 0
    blink_durations = []
    
    closed_frames = 0
    blink_in_progress = False
    blink_start_time = 0
    last_blink_time = 0
    
    session_start = time.time()
    current_ear = 0.25
    ear_samples = []
    
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
    else:
        # Connect to Django
        session = requests.Session()
        django_connected = login_to_django(session, django_username, django_password)
        
        if not django_connected:
            print("[INFO] Continuing without Django (local tracking still works)")
    
    print()
    print(f"[INFO] Session will run for {SESSION_DURATION} seconds...")
    print("[INFO] Press 'q' to quit early")
    print()
    
    # Main loop
    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Failed to read frame")
            break
        
        current_time = time.time()
        elapsed = current_time - session_start
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
        
        # Blink detection logic
        if eyes_detected:
            if current_ear < EAR_THRESHOLD:
                # Eye is closed - track consecutive closed frames
                if not blink_in_progress:
                    # Start tracking this blink immediately
                    blink_in_progress = True
                    blink_start_time = current_time
                    closed_frames = 1
                else:
                    closed_frames += 1
                
            else:
                # Eye is open
                if blink_in_progress:
                    duration = current_time - blink_start_time
                    duration_ms = duration * 1000
                    
                    # Check cooldown to avoid double-counting rapid blinks
                    if (current_time - last_blink_time) >= BLINK_COOLDOWN:
                        if MIN_BLINK_DURATION <= duration <= MAX_BLINK_DURATION:
                            blink_count += 1
                            blink_durations.append(duration_ms)
                            last_blink_time = current_time
                            rate = (blink_count / max(0.1, elapsed)) * 60
                            print(f"[BLINK #{blink_count}] {duration_ms:.0f}ms | {rate:.1f}/min")
                    
                    blink_in_progress = False
                
                closed_frames = 0
        
        # Calculate metrics
        rate = (blink_count / max(0.1, elapsed)) * 60
        avg_duration = np.mean(blink_durations) if blink_durations else 0
        eye_status = classify_eye_state(rate)
        eye_score = calculate_eye_score(eye_status)
        
        # Draw overlay
        cv2.putText(frame, "REAL MODE", (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"EAR: {current_ear:.3f}", (10, 55),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"Blinks: {blink_count}", (10, 85),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"Rate: {rate:.1f}/min", (10, 115),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"State: {eye_status.upper()}", (10, 145),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, f"Score: {eye_score}", (10, 175),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        
        remaining = max(0, SESSION_DURATION - int(elapsed))
        cv2.putText(frame, f"Time: {remaining}s", (10, 205),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        if not face_detected:
            cv2.putText(frame, "No face detected", (10, 235),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        elif not eyes_detected:
            cv2.putText(frame, "Eye landmarks not detected", (10, 235),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
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
        if key == ord('q') or elapsed >= SESSION_DURATION:
            break
    
    # Cleanup
    cap.release()
    cv2.destroyAllWindows()
    
    # Session summary
    final_duration = time.time() - session_start
    final_rate = (blink_count / max(0.1, final_duration)) * 60
    final_avg_dur = np.mean(blink_durations) if blink_durations else 0
    final_state = classify_eye_state(final_rate)
    final_score = calculate_eye_score(final_state)
    fatigue_flag = final_state in ['drowsy', 'fatigue', 'eye_strain']
    
    print()
    print("=" * 60)
    print("  SESSION SUMMARY")
    print("=" * 60)
    print(f"  Duration:     {int(final_duration)}s")
    print(f"  Total Blinks: {blink_count}")
    print(f"  Blink Rate:   {final_rate:.1f}/min")
    print(f"  Avg Duration: {final_avg_dur:.0f}ms")
    print(f"  Eye State:    {final_state}")
    print(f"  Eye Score:    {final_score}")
    print(f"  Fatigue:      {'Yes' if fatigue_flag else 'No'}")
    print("=" * 60)
    print()
    
    # POST to Django ONE TIME after session ends
    if django_connected:
        print("[INFO] Sending data to Django...")
        
        import json
        post_data = {
            'ear': round(current_ear, 4),
            'blink_count': blink_count,
            'blink_duration_avg': round(final_avg_dur, 2),
            'blink_rate': round(final_rate, 2),
            'eye_state': final_state,
            'eye_score': final_score,
            'fatigue_flag': fatigue_flag,
            'ear_samples': json.dumps(ear_samples[-30:] if ear_samples else []),
            'notes': f"Session: {int(final_duration)}s | {blink_count} blinks",
        }
        
        print(f"[DEBUG] Posting: blink_count={blink_count}, blink_rate={final_rate:.1f}, eye_state={final_state}, eye_score={final_score}")
        post_to_django(session, post_data)
    else:
        print("[INFO] Skipping Django POST (not connected)")
    
    print("[INFO] Eye tracker closed.")


if __name__ == "__main__":
    main()
