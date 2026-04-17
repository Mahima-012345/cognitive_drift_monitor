def calculate_fusion(reaction_score, eye_score, hrv_score):

    # Step 1: Final score
    final_score = (reaction_score * 0.4) + (eye_score * 0.3) + (hrv_score * 0.3)

    # Step 2: Count abnormal signals
    abnormal_count = 0

    if reaction_score < 50:
        abnormal_count += 1

    if eye_score < 50:
        abnormal_count += 1

    if hrv_score < 50:
        abnormal_count += 1

    # Step 3: Confidence
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