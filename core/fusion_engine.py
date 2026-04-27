def calculate_fusion(reaction_score, eye_score, hrv_score):
    """
    Calculate cognitive drift fusion from sensor scores.
    
    phase 9 update: Handle invalid HRV (None) - if HRV data is invalid
    (sensor noise), it should not contribute to cognitive drift calculation.
    """
    
    # Phase 9: Handle invalid/None HRV score
    # If HRV is invalid (None), exclude it from calculation
    hrv_valid = hrv_score is not None
    
    if hrv_valid:
        # All 3 sensors available - use standard weighting
        final_score = (reaction_score * 0.4) + (eye_score * 0.3) + (hrv_score * 0.3)
    else:
        # HRV invalid - use 2-sensor fusion with adjusted weights
        # Exclude HRV from drift confirmation
        final_score = (reaction_score * 0.5) + (eye_score * 0.5)
    
    # Count abnormal signals (only count HRV if valid)
    abnormal_count = 0
    
    if reaction_score < 50:
        abnormal_count += 1
    
    if eye_score < 50:
        abnormal_count += 1
    
    # Only count HRV if it's valid - don't let invalid HRV confirm drift
    if hrv_valid and hrv_score < 50:
        abnormal_count += 1
    
    # Confidence level based on abnormal count
    if abnormal_count == 1:
        confidence = "LOW"
    elif abnormal_count == 2:
        confidence = "MEDIUM"
    elif abnormal_count == 3:
        confidence = "HIGH"
    else:
        confidence = "NONE"

    # Step 4: Final state
    if abnormal_count == 0:
        state = "STABLE"
    elif abnormal_count == 1:
        state = "MILD_DRIFT"
    elif abnormal_count == 2:
        state = "MODERATE_DRIFT"
    else:
        state = "CONFIRMED_DRIFT"

    # Step 5: Trigger reaction test
    trigger = False
    if eye_score < 50 and hrv_score < 50:
        trigger = True

    # Step 6: Message
    if state == "STABLE":
        message = "You are focused. Keep going!"
    elif state == "MILD_DRIFT":
        message = "Stay focused. Avoid distractions."
    elif state == "MODERATE_DRIFT":
        message = "Take a short break."
    else:
        message = "You are highly distracted. Take rest."

    return {
        "final_score": final_score,
        "confidence": confidence,
        "state": state,
        "trigger": trigger,
        "message": message
    }