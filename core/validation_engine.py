"""
Phase 6 Part 1: Smart Validation Engine
========================================

This module provides drift validation logic to prevent false alerts.
It validates suspected cognitive drift through a multi-step process:

1. Check study hours - only flag during active study time
2. Check eye monitoring - look for fatigue/drowsiness
3. Check HRV monitoring - look for stress/abnormal readings
4. If both eye + HRV drift during study hours -> trigger reaction test
5. After reaction test -> compare with personalized baseline
6. Confirm drift or mark as false alert

Where future modules connect:
- Phase 6 Part 2: Will use status 'confirmed_drift' to trigger interventions
- Warning system: Will read validation records to determine warning level
"""

from datetime import datetime, time
from django.utils import timezone
from django.db.models import Q

from .models import (
    DriftValidation,
    FusionRecord,
    ReactionSession,
    WarningLog,
)


def create_warning_safe(user, level, message, source='validation', suggestions=None):
    """
    Create warning with strict duplicate prevention (session-based).
    Only creates warning if no duplicate exists within 10 minutes.
    
    Args:
        user: User instance
        level: 1-4 (mild to chronic) or 'info' for normal
        message: Warning message text
        source: Trigger source (default: 'validation')
        suggestions: Optional list of suggestion strings
    
    Returns:
        WarningLog instance or None if duplicate skipped
    """
    from core.warning_levels import WARNING_MESSAGES
    
    now = timezone.now()
    
    # Convert numeric level to string key
    level_key = f'level_{level}' if isinstance(level, int) else level
    if level_key not in WARNING_MESSAGES and level_key != 'info':
        level_key = 'level_1'
    
    # Get latest warning for this user
    last_warning = WarningLog.objects.filter(user=user).order_by('-timestamp').first()
    
    # Check for duplicate: same level, same message, within 10 minutes (600 seconds)
    if last_warning:
        time_diff = (now - last_warning.timestamp).total_seconds()
        if last_warning.warning_level == level_key and last_warning.warning_message == message and time_diff < 600:
            return None  # Skip duplicate
    
    # Use standardized message if not provided
    if message is None:
        message = WARNING_MESSAGES.get(level_key, {}).get('message', 'Warning triggered')
    
    # Get suggestions from warning levels module if not provided
    if suggestions is None:
        suggestions = WARNING_MESSAGES.get(level_key, {}).get('suggestions', [])
    
    # Create new warning
    return WarningLog.objects.create(
        user=user,
        warning_level=level_key,
        warning_message=message,
        suggestions=suggestions,
        trigger_source=source,
        acknowledged=False,
    )


def check_chronic_drift(user):
    """
    Check if user has 3 or more Level 3 warnings in recent sessions.
    If so, upgrade to Level 4 chronic drift warning.
    
    This implements the chronic drift logic for Phase 7.
    
    Returns:
        WarningLog instance if chronic drift warning created, None otherwise
    """
    from django.utils import timezone
    
    # Count recent high-level warnings (last 7 days)
    week_ago = timezone.now() - timezone.timedelta(days=7)
    recent_high_warnings = WarningLog.objects.filter(
        user=user,
        warning_level='level_3',
        timestamp__gte=week_ago
    ).count()
    
    # Also check session count - if 3+ confirmed drift warnings in recent sessions
    recent_sessions = DriftValidation.objects.filter(
        user=user,
        drift_confirmed=True,
        created_at__gte=week_ago
    ).count()
    
    # If 3+ high warnings OR 3+ confirmed sessions, trigger chronic drift
    if recent_high_warnings >= 3 or recent_sessions >= 3:
        # Check if we already have a level 4 warning recently (within 24 hours)
        recent_level_4 = WarningLog.objects.filter(
            user=user,
            warning_level='level_4',
            timestamp__gte=timezone.now() - timezone.timedelta(hours=24)
        ).exists()
        
        if not recent_level_4:
            warning_msg = 'Persistent decline detected across multiple sessions.'
            suggestions = [
                'Improve sleep and workload balance.',
                'Reduce long continuous study sessions.',
                'Consider speaking with a mentor or health professional if this continues.',
            ]
            return create_warning_safe(user, 4, warning_msg, 'validation', suggestions)
    
    return None


# =============================================================================
# CONFIGURABLE THRESHOLDS - Easy to adjust later
# =============================================================================

DEBUG = True  # Set to False to disable debug prints

THRESHOLDS = {
    # Eye drift: score below this = drift detected (higher = better)
    'eye_score_drift_threshold': 50,
    
    # HRV drift: score below this = drift detected (higher = better)
    'hrv_score_drift_threshold': 50,
    
    # HRV stress levels that indicate drift
    'hrv_drift_stress_levels': ['moderate_stress', 'high_stress', 'unstable'],
    
    # Reaction: percent slowdown from baseline to confirm drift
    'reaction_baseline_slowdown_threshold': 10,  # 10% slowdown = confirmed drift
    
    # Eye states that indicate drift/fatigue
    'eye_drift_states': ['fatigue', 'drowsy', 'eye_strain'],
}


def is_within_study_hours(user_profile):
    """
    Check if current time is within user's configured study hours.
    
    Returns:
        bool: True if within study hours, False otherwise
    """
    if not user_profile:
        return False
    
    if not user_profile.study_start_time or not user_profile.study_end_time:
        return False
    
    now = timezone.now().time()
    start = user_profile.study_start_time
    end = user_profile.study_end_time
    
    # Handle overnight study hours (e.g., 22:00 - 02:00)
    if start > end:
        return now >= start or now <= end
    
    return start <= now <= end


def check_eye_drift(user):
    """
    Check latest eye record for drift indicators.
    
    Drift is detected if:
    - Eye score is below threshold (50), OR
    - Eye state is fatigue/drowsy/eye_strain
    
    Returns:
        dict: {'has_drift': bool, 'score': float, 'state': str, 'reason': str}
    """
    latest_eye = EyeRecord.objects.filter(user=user).order_by('-timestamp').first()
    
    if not latest_eye:
        return {'has_drift': False, 'score': None, 'state': None, 'reason': 'No eye data'}
    
    score = latest_eye.eye_score or 0
    state = latest_eye.eye_state
    threshold = THRESHOLDS['eye_score_drift_threshold']
    
    # Check score threshold
    if score < threshold:
        return {
            'has_drift': True,
            'score': score,
            'state': state,
            'reason': f'Eye score {score:.1f} below threshold {threshold}'
        }
    
    # Check eye state
    if state in THRESHOLDS['eye_drift_states']:
        return {
            'has_drift': True,
            'score': score,
            'state': state,
            'reason': f'Eye state "{state}" indicates fatigue'
        }
    
    return {
        'has_drift': False,
        'score': score,
        'state': state,
        'reason': 'Eye metrics normal'
    }


def check_hrv_drift(user):
    """
    Check latest HRV record for drift indicators.
    
    Drift is detected if:
    - HRV score is below threshold (50), OR
    - Stress level is moderate/high/unstable
    
    Returns:
        dict: {'has_drift': bool, 'score': float, 'stress_level': str, 'reason': str}
    """
    latest_hrv = HRVRecord.objects.filter(user=user).order_by('-timestamp').first()
    
    if not latest_hrv:
        return {'has_drift': False, 'score': None, 'stress_level': None, 'reason': 'No HRV data'}
    
    score = latest_hrv.hrv_score or 0
    stress_level = latest_hrv.stress_level
    threshold = THRESHOLDS['hrv_score_drift_threshold']
    
    # Check score threshold
    if score < threshold:
        return {
            'has_drift': True,
            'score': score,
            'stress_level': stress_level,
            'reason': f'HRV score {score:.1f} below threshold {threshold}'
        }
    
    # Check stress level
    if stress_level in THRESHOLDS['hrv_drift_stress_levels']:
        return {
            'has_drift': True,
            'score': score,
            'stress_level': stress_level,
            'reason': f'Stress level "{stress_level}" indicates stress'
        }
    
    return {
        'has_drift': False,
        'score': score,
        'stress_level': stress_level,
        'reason': 'HRV metrics normal'
    }


def evaluate_suspected_drift(user):
    """
    Main validation function - evaluates whether drift is suspected.
    
    Logic:
    1. Check if within user's study hours
    2. Check eye monitoring for drift
    3. Check HRV monitoring for drift
    4. If BOTH drift during study hours -> suspected drift, reaction test required
    5. Save validation record
    
    Returns:
        dict: {
            'within_study_hours': bool,
            'eye_drift': bool,
            'hrv_drift': bool,
            'suspected_drift': bool,
            'reaction_test_required': bool,
            'status': str,
            'validation_id': int or None,
            'details': dict
        }
    """
    # Get user profile for study hours
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile = None
    
    # Check study hours
    within_hours = is_within_study_hours(profile)
    
    # Check eye drift
    eye_result = check_eye_drift(user)
    eye_drift = eye_result['has_drift']
    
    # Check HRV drift
    hrv_result = check_hrv_drift(user)
    hrv_drift = hrv_result['has_drift']
    
    # Determine suspected drift
    # Only flag as suspected if BOTH conditions met:
    # 1. Within study hours
    # 2. Both eye AND HRV show drift
    suspected = within_hours and eye_drift and hrv_drift
    reaction_required = suspected
    
    # Determine status
    if suspected:
        status = 'suspected'
    elif eye_drift or hrv_drift:
        status = 'pending'  # One signal but not both
    else:
        status = 'normal'
    
    # Create validation record
    validation = DriftValidation.objects.create(
        user=user,
        within_study_hours=within_hours,
        eye_drift=eye_drift,
        hrv_drift=hrv_drift,
        suspected_drift=suspected,
        reaction_test_required=reaction_required,
        status=status,
    )
    
    if DEBUG:
        print(f"[VALIDATION] Created DriftValidation ID={validation.id}")
        print(f"[VALIDATION]   within_study_hours={within_hours}, eye_drift={eye_drift}, hrv_drift={hrv_drift}")
        print(f"[VALIDATION]   suspected={suspected}, reaction_required={reaction_required}, status={status}")
    
    return {
        'within_study_hours': within_hours,
        'eye_drift': eye_drift,
        'hrv_drift': hrv_drift,
        'suspected_drift': suspected,
        'reaction_test_required': reaction_required,
        'status': status,
        'validation_id': validation.id,
        'details': {
            'eye': eye_result,
            'hrv': hrv_result,
            'study_hours': {
                'start': profile.study_start_time if profile else None,
                'end': profile.study_end_time if profile else None,
                'configured': profile and profile.study_start_time is not None,
            }
        }
    }


def validate_reaction_confirmation(user):
    """
    Validates drift confirmation after user completes reaction test.
    
    Logic:
    1. Get latest reaction session for this user
    2. Get user's personalized baseline
    3. Compare current performance vs baseline
    4. If slowdown >= threshold -> confirm drift
    5. Otherwise -> false alert avoided
    6. Update validation record
    
    Returns:
        dict: {
            'validated': bool,
            'drift_confirmed': bool,
            'status': str,
            'reaction_test_completed': bool,
            'validation_id': int or None,
            'details': dict
        }
    """
    # Get the most recent unreviewed validation record OR create one if none exists
    validation = DriftValidation.objects.filter(
        user=user,
        suspected_drift=True,
        reaction_test_completed=False
    ).order_by('-created_at').first()
    
    # If no pending validation, get the most recent one to update
    if not validation:
        validation = DriftValidation.objects.filter(user=user).order_by('-created_at').first()
        if validation and validation.reaction_test_completed:
            # Already completed - create new one
            validation = None
    
    if not validation:
        return {
            'validated': False,
            'drift_confirmed': False,
            'status': 'no_pending_validation',
            'reaction_test_completed': False,
            'validation_id': None,
            'details': {'reason': 'No pending validation record found'}
        }
    
    # Get latest reaction session
    reaction = ReactionSession.objects.filter(user=user).order_by('-timestamp').first()
    
    if not reaction:
        return {
            'validated': False,
            'drift_confirmed': False,
            'status': 'waiting_reaction',
            'reaction_test_completed': False,
            'validation_id': validation.id,
            'details': {'reason': 'No reaction session found'}
        }
    
    # Check if baseline is established
    baseline = ReactionSession.get_baseline_for_user(user)
    
    if not baseline['established']:
        return {
            'validated': False,
            'drift_confirmed': False,
            'status': 'waiting_reaction',
            'reaction_test_completed': False,
            'validation_id': validation.id,
            'details': {
                'reason': 'Baseline not yet established',
                'sessions_needed': 3 - baseline['session_count']
            }
        }
    
    # Compare with baseline
    baseline_mean = baseline['baseline_mean']
    current_mean = reaction.mean_rt
    
    if current_mean is None or baseline_mean is None:
        return {
            'validated': False,
            'drift_confirmed': False,
            'status': 'waiting_reaction',
            'reaction_test_completed': False,
            'validation_id': validation.id,
            'details': {'reason': 'Missing reaction time data'}
        }
    
    # Calculate percent change from baseline
    percent_change = ((current_mean - baseline_mean) / baseline_mean) * 100
    threshold = THRESHOLDS['reaction_baseline_slowdown_threshold']
    
    # Confirm drift if slowdown exceeds threshold
    drift_confirmed = percent_change >= threshold
    
    # Update validation record
    validation.reaction_test_completed = True
    validation.reaction_session = reaction
    
    if drift_confirmed:
        validation.status = 'confirmed_drift'
        validation.drift_confirmed = True
        validation.confirmation_reason = (
            f'Reaction time {percent_change:.1f}% slower than baseline. '
            f'Current: {current_mean:.0f}ms, Baseline: {baseline_mean:.0f}ms. '
            f'Threshold: {threshold}%'
        )
    else:
        validation.status = 'false_alert'
        validation.drift_confirmed = False
        validation.confirmation_reason = (
            f'Reaction time {percent_change:.1f}% from baseline. '
            f'Within acceptable range. '
            f'Current: {current_mean:.0f}ms, Baseline: {baseline_mean:.0f}ms'
        )
    
    validation.save()
    
    if DEBUG:
        print(f"[VALIDATION] Updated DriftValidation ID={validation.id} after reaction test")
        print(f"[VALIDATION]   drift_confirmed={drift_confirmed}, status={validation.status}")
    
    # Create appropriate warning based on drift status
    if drift_confirmed:
        warning_msg = 'Cognitive fatigue confirmed. Take a 10-15 min break.'
        suggestions = [
            'Please stop the session briefly.',
            'Take rest before continuing.',
            'Retake the reaction test after a break.',
        ]
        create_warning_safe(user, 3, warning_msg, 'validation', suggestions)
    else:
        warning_msg = 'Recent session indicates stable focus.'
        suggestions = [
            'Stay focused.',
            'Check your posture.',
            'Take a short breathing pause.',
        ]
        create_warning_safe(user, 1, warning_msg, 'validation', suggestions)
    
    # Check for chronic drift
    check_chronic_drift(user)


def process_validation_with_warnings(user, reaction_score=None, session_record=None):
    """
    Main validation function that creates appropriate warnings.
    Phase 7: Enhanced with level-based warnings and chronic drift detection.
    
    Args:
        user: User instance
        reaction_score: Optional reaction test score
        session_record: Optional session data dict
    
    Returns:
        dict: Validation result with warning info
    """
    from core.warning_levels import get_warning_level_from_state, WARNING_MESSAGES
    
    # Get current cognitive state (from fusion record or defaults)
    latest_fusion = FusionRecord.objects.filter(user=user).order_by('-timestamp').first()
    
    cognitive_state = 'normal'
    drift_confirmed = False
    
    if latest_fusion:
        cognitive_state = latest_fusion.cognitive_state or 'normal'
        drift_confirmed = latest_fusion.validation_status == 'confirmed_drift'
    
    # Get appropriate warning level
    warning_level = get_warning_level_from_state(cognitive_state)
    level_key = f'level_{warning_level}' if warning_level > 0 else 'info'
    
    # Create warning based on level
    warning = None
    if warning_level > 0:
        warning_info = WARNING_MESSAGES.get(level_key, {})
        warning_msg = warning_info.get('message', 'Warning triggered')
        suggestions = warning_info.get('suggestions', [])
        warning = create_warning_safe(user, warning_level, warning_msg, 'validation', suggestions)
    
    # Check for chronic drift (Level 4)
    chronic_warning = None
    if warning_level >= 3:
        chronic_warning = check_chronic_drift(user)
    
    return {
        'warning': warning,
        'chronic_warning': chronic_warning,
        'warning_level': warning_level,
        'cognitive_state': cognitive_state,
        'drift_confirmed': drift_confirmed,
    }


# Existing function updated to use new levels
def process_validation_result(user, validation_result, reaction_score=None):
    """Process validation result and create warnings."""
    from core.warning_levels import WARNING_MESSAGES, get_warning_level_from_state
    
    drift_confirmed = validation_result.get('drift_confirmed', False)
    
    # Create warning log entry (session-based - only at validation decision points)
    if drift_confirmed:
        warning_msg = WARNING_MESSAGES['level_3']['message']
        suggestions = WARNING_MESSAGES['level_3']['suggestions']
        create_warning_safe(user, 3, warning_msg, 'validation', suggestions)
    else:
        warning_msg = WARNING_MESSAGES['level_1']['message']
        suggestions = WARNING_MESSAGES['level_1']['suggestions']
        create_warning_safe(user, 1, warning_msg, 'validation', suggestions)
    
    # Check for chronic drift
    check_chronic_drift(user)
    
    # CRITICAL: Update the latest FusionRecord with validation status
    # This OVERRIDES the calculated drift score with validation result
    latest_fusion = FusionRecord.objects.filter(user=user).order_by('-timestamp').first()
    if latest_fusion:
        latest_fusion.validation_status = validation_result.get('status')
        latest_fusion.intervention_message = validation_result.get('confirmation_reason')
        latest_fusion.save()
        if DEBUG:
            print(f"[VALIDATION] Synced FusionRecord with status={validation_result.get('status')}")
    
    return {
        'validated': True,
        'drift_confirmed': drift_confirmed,
        'status': validation_result.get('status'),
        'reaction_test_completed': True,
        'details': validation_result.get('details', {})
    }
    
    return {
        'validated': True,
        'drift_confirmed': drift_confirmed,
        'status': validation.status,
        'reaction_test_completed': True,
        'validation_id': validation.id,
        'details': {
            'baseline_mean': baseline_mean,
            'current_mean': current_mean,
            'percent_change': percent_change,
            'threshold': threshold,
            'reason': validation.confirmation_reason
        }
    }


def get_latest_validation_status(user):
    """
    Get the current validation status for a user.
    Useful for dashboard display.
    
    Returns:
        dict: Current validation state or None
    """
    latest = DriftValidation.objects.filter(user=user).order_by('-created_at').first()
    
    if not latest:
        return None
    
    return {
        'id': latest.id,
        'status': latest.status,
        'suspected_drift': latest.suspected_drift,
        'reaction_test_required': latest.reaction_test_required,
        'reaction_test_completed': latest.reaction_test_completed,
        'drift_confirmed': latest.drift_confirmed,
        'eye_drift': latest.eye_drift,
        'hrv_drift': latest.hrv_drift,
        'within_study_hours': latest.within_study_hours,
        'confirmation_reason': latest.confirmation_reason,
        'created_at': latest.created_at,
        'updated_at': latest.updated_at,
        'is_active': latest.is_active,
    }
