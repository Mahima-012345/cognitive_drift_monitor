# eye_tracker_fallback.py
"""
Phase 3 - Eye Blink Tracker (Simple OpenCV Version)
Fallback version using only OpenCV Haar Cascades.
Works without dlib installation.

Usage:
    python eye_tracker_fallback.py
"""

import cv2
import numpy as np
import time
import json

# =============================================================================
# CONFIGURATION
# =============================================================================

# Eye detection thresholds (simplified)
EYE_AR_THRESHOLD = 0.25  # Eye aspect ratio threshold
BLINK_FRAMES = 2        # Frames eye must be closed
BLINK_COOLDOWN = 0.25   # Seconds between blinks
MIN_BLINK_TIME = 0.05    # Minimum blink duration
MAX_BLINK_TIME = 0.60   # Maximum blink duration

# Fatigue
DROWSY_THRESHOLD = 600  # ms

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 50)
    print("Eye Blink Tracker (Simple OpenCV Version)")
    print("=" * 50)
    
    # Load cascades
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )
    eye_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_eye_tree_eyeglasses.xml'
    )
    
    if face_cascade.empty() or eye_cascade.empty():
        print("[ERROR] Cascade files not found!")
        return
    
    print("[OK] Cascades loaded")
    
    # Webcam
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Cannot open webcam!")
        return
    print("[OK] Webcam ready")
    
    # State
    blink_count = 0
    blink_start = None
    blink_times = []
    consecutive_closed = 0
    blink_active = False
    last_blink = 0
    session_start = time.time()
    
    print("\n[INFO] Press 'q' to quit\n")
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            
            eyes_detected = False
            
            for (x, y, w, h) in faces:
                roi_gray = gray[y:y+h, x:x+w]
                eyes = eye_cascade.detectMultiScale(roi_gray)
                
                if len(eyes) >= 2:
                    eyes_detected = True
                    
                    # Draw face rectangle
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                    
                    # Get eye regions
                    eye_heights = []
                    for (ex, ey, ew, eh) in eyes[:2]:
                        eye_heights.append(eh)
                        cv2.rectangle(frame, 
                                    (x+ex, y+ey), 
                                    (x+ex+ew, y+ey+eh),
                                    (0, 255, 255), 1)
                    
                    # Simple blink detection based on eye height
                    avg_height = np.mean(eye_heights)
                    eye_closed = avg_height < 10
                    
                    if eye_closed:
                        consecutive_closed += 1
                        
                        if not blink_active and consecutive_closed >= BLINK_FRAMES:
                            if time.time() - last_blink >= BLINK_COOLDOWN:
                                blink_active = True
                                blink_start = time.time()
                                print(f"[STARTED] blink #{blink_count + 1}")
                    else:
                        if blink_active and blink_start is not None:
                            duration = time.time() - blink_start
                            
                            if MIN_BLINK_TIME <= duration <= MAX_BLINK_TIME:
                                blink_count += 1
                                blink_times.append(duration * 1000)
                                print(f"[COUNTED] blink #{blink_count} ({duration*1000:.0f}ms)")
                            elif duration < MIN_BLINK_TIME:
                                print(f"[REJECT] too_short")
                            else:
                                print(f"[REJECT] too_long")
                            
                            blink_active = False
                            blink_start = None
                            last_blink = time.time()
                        
                        consecutive_closed = 0
                    break
            
            # Calculate metrics
            duration = time.time() - session_start
            rate = (blink_count / duration * 60) if duration > 0 else 0
            avg_dur = np.mean(blink_times) if blink_times else 0
            fatigue = avg_dur > DROWSY_THRESHOLD
            
            # Classify
            if fatigue:
                state = 'drowsy'
            elif rate < 15:
                state = 'fatigue'
            elif rate <= 20:
                state = 'normal'
            else:
                state = 'eye_strain'
            
            score = {'normal': 90, 'fatigue': 60, 'eye_strain': 40, 'drowsy': 25}.get(state, 50)
            
            # Display
            cv2.putText(frame, f"EAR/Height: {avg_height if eyes_detected else 0:.1f}", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(frame, f"Blinks: {blink_count}", 
                       (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, f"Rate: {rate:.1f}/min", 
                       (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(frame, f"State: {state}", 
                       (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            if not eyes_detected:
                cv2.putText(frame, "NO EYES DETECTED", 
                           (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            
            cv2.imshow("Eye Tracker - Press 'q'", frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    finally:
        cap.release()
        cv2.destroyAllWindows()
        
        print("\n" + "=" * 50)
        print("Session Summary:")
        print(f"  Duration: {int(duration)}s")
        print(f"  Blinks: {blink_count}")
        print(f"  Rate: {rate:.1f}/min")
        print(f"  State: {state}")
        print("=" * 50)
        print("\nNote: This is the simple OpenCV-only version.")
        print("For better accuracy, install dlib and use eye_tracker.py")


if __name__ == "__main__":
    main()
