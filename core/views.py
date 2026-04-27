# core/views.py
"""
Views for Cognitive Drift Detection System.
Phase 1 - Core web foundation with API endpoints.
"""

DEBUG = True  # Set to False to disable debug prints

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Avg, Max, Min, Count
from datetime import timedelta
import json

from .models import (
    UserProfile, DriftRecord, ReactionSession, EyeRecord,
    HRVRecord, WarningLog, GoalRecord, PomodoroSession, DistractionRecord
)
from .forms import (
    UserRegistrationForm, UserProfileForm, LoginForm,
    ReactionSessionForm, EyeRecordForm, HRVRecordForm
)
from .fusion_engine import calculate_fusion
from .models import FusionRecord
from .validation_engine import (
    evaluate_suspected_drift,
    validate_reaction_confirmation,
    get_latest_validation_status
)
from .warning_levels import get_warning_info, get_level_display_name, WARNING_MESSAGES


def calculate_reaction_score(mean_rt, baseline_rt, std_dev):
    """
    Calculate reaction score using both baseline comparison AND absolute speed.
    
    Phase 9: Combined relative + absolute scoring
    
    Args:
        mean_rt: Mean reaction time in ms
        baseline_rt: User's personal baseline RT (from get_baseline_for_user)
        std_dev: Standard deviation of reaction times
    
    Returns:
        dict with: score, status, explanation
    """
    if mean_rt is None or mean_rt <= 0:
        return {
            'score': 0,
            'status': 'Moderate Drift',
            'explanation': 'No valid reaction time'
        }
    
    result = {
        'score': 0,
        'status': 'Stable',
        'explanation': ''
    }
    
    baseline_diff = 0
    relative_score = None
    
    # 1. Relative baseline score
    if baseline_rt is not None and baseline_rt > 0:
        baseline_diff = (mean_rt - baseline_rt) / baseline_rt
        
        if baseline_diff <= 0:
            relative_score = 100
        elif baseline_diff <= 0.05:
            relative_score = 90
        elif baseline_diff <= 0.10:
            relative_score = 75
        elif baseline_diff <= 0.15:
            relative_score = 60
        else:
            relative_score = 40
    
    # 2. Absolute reaction score
    if mean_rt < 250:
        absolute_score = 100
    elif mean_rt < 350:
        absolute_score = 85
    elif mean_rt < 500:
        absolute_score = 65
    elif mean_rt < 700:
        absolute_score = 45
    else:
        absolute_score = 30
    
    # 3. Final reaction score
    if relative_score is not None:
        result['score'] = (0.6 * relative_score) + (0.4 * absolute_score)
    else:
        result['score'] = absolute_score
    
    # 4. Variability penalty
    if std_dev is not None:
        if std_dev > 150:
            result['score'] -= 10
        elif std_dev > 100:
            result['score'] -= 5
    
    # 5. Clamp score
    result['score'] = max(0, min(100, round(result['score'], 1)))
    
    # 6. Reaction status
    if result['score'] >= 85:
        result['status'] = 'Excellent'
    elif result['score'] >= 70:
        result['status'] = 'Stable'
    elif result['score'] >= 50:
        result['status'] = 'Mild Drift'
    else:
        result['status'] = 'Moderate Drift'
    
    # 7. Explanation
    if relative_score is not None:
        rel_indicator = "faster than" if baseline_diff <= 0 else f"{int(baseline_diff*100)}% slower than"
        result['explanation'] = f"mean_rt={mean_rt}ms, {rel_indicator} baseline ({baseline_rt}ms), abs_score={absolute_score}"
    else:
        result['explanation'] = f"mean_rt={mean_rt}ms (no baseline), abs_score={absolute_score}"
    
    return result


def map_state_to_level(current_state):
    """Phase 7: Centralized state to level mapping"""
    state_lower = str(current_state).lower() if current_state else ""
    
    if state_lower in ["stable", "normal", "no data"]:
        return 0, "Level 0"
    elif state_lower == "mild_drift":
        return 1, "Level 1"
    elif state_lower in ["moderate_drift", "suspected_drift"]:
        return 2, "Level 2"
    elif state_lower == "confirmed_drift":
        return 3, "Level 3"
    elif state_lower == "chronic_drift":
        return 4, "Level 4"
    else:
        return 0, "Level 0"

def home(request):
    """Landing page for the application."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'core/home.html')


@require_http_methods(["GET", "POST"])
def signup_view(request):
    """User registration view."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.username}! Your account has been created.')
            return redirect('dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserRegistrationForm()

    return render(request, 'core/signup.html', {'form': form})


@require_http_methods(["GET", "POST"])
def login_view(request):
    """User login view."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()

    return render(request, 'core/login.html', {'form': form})


@login_required
def logout_view(request):
    """User logout view."""
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


@login_required
def dashboard(request):
    """Main dashboard showing cognitive drift summary and recent data."""
    user = request.user
    profile = user.profile

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    # Debug prints - must show actual data
    print("="*50)
    print("USER:", user)
    print("="*50)
    
    # Get latest records for user
    latest_drift = DriftRecord.objects.filter(user=user).order_by('-timestamp').first()
    latest_reaction = ReactionSession.objects.filter(user=user).order_by('-timestamp').first()
    latest_eye = EyeRecord.objects.filter(user=user).order_by('-timestamp').first()
    latest_hrv = HRVRecord.objects.filter(user=user).order_by('-timestamp').first()
    
    print("LATEST_REACTION:", latest_reaction)
    print("LATEST_EYE:", latest_eye)
    print("LATEST_HRV:", latest_hrv)
    print("LATEST_DRIFT:", latest_drift)
    
    # Get counts
    reaction_count = ReactionSession.objects.filter(user=user).count()
    eye_count = EyeRecord.objects.filter(user=user).count()
    hrv_count = HRVRecord.objects.filter(user=user).count()
    drift_count = DriftRecord.objects.filter(user=user).count()
    
    print(f"RECORD COUNTS - Reaction: {reaction_count}, Eye: {eye_count}, HRV: {hrv_count}, Drift: {drift_count}")
    
    if latest_hrv:
        if DEBUG:
            print(f"[DASHBOARD DEBUG] HRV: bpm={latest_hrv.bpm}, sdnn={latest_hrv.sdnn}, stress_level={latest_hrv.stress_level}, hrv_score={latest_hrv.hrv_score}")
    else:
        if DEBUG:
            total_hrv = HRVRecord.objects.count()
            all_hrv = HRVRecord.objects.all()[:3]
            print(f"[DASHBOARD DEBUG] No HRVRecord for user: {user}, total in DB: {total_hrv}")
            for h in all_hrv:
                print(f"[DASHBOARD DEBUG]   -> HRV ID={h.id}, user={h.user}, bpm={h.bpm}")

    unacknowledged_warnings = WarningLog.objects.filter(
        user=user, acknowledged=False
    ).count()

    recent_warnings = WarningLog.objects.filter(
        user=user
    ).order_by('-timestamp')[:20]

    unique_recent_warnings = []
    seen_combos = set()
    for w in recent_warnings:
        combo = (w.warning_level, w.warning_message[:50])
        if combo not in seen_combos:
            seen_combos.add(combo)
            unique_recent_warnings.append(w)
        if len(unique_recent_warnings) >= 5:
            break

    recent_warnings = unique_recent_warnings

    # Get latest warning for toast popup (Level 2+ only)
    latest_warning = WarningLog.objects.filter(
        user=user,
        warning_level__in=['level_2', 'level_3', 'level_4']
    ).order_by('-timestamp').first()

    recent_drifts = DriftRecord.objects.filter(
        user=user
    ).order_by('-timestamp')[:10]
    
    today_pomodoros = PomodoroSession.objects.filter(
        user=user, start_time__gte=today_start, completed=True
    ).count()

    today_distractions = DistractionRecord.objects.filter(
        user=user, timestamp__gte=today_start
    ).count()
    
    # Today's goal
    today_goal = GoalRecord.objects.filter(user=user, date=timezone.now().date()).first()
    
    # Recent distractions (last 5)
    recent_distractions_list = DistractionRecord.objects.filter(
        user=user
    ).order_by('-timestamp')[:5]
    
    # Recent pomodoro sessions for today
    recent_pomodoros = PomodoroSession.objects.filter(
        user=user, start_time__gte=today_start
    ).order_by('-start_time')[:5]

    chart_labels = []
    chart_final_scores = []
    chart_reaction = []
    chart_eye = []
    chart_hrv = []

    # Use DriftRecord for trend chart (last 7 days)
    weekly_drift_records = DriftRecord.objects.filter(
        user=user, timestamp__gte=week_ago
    ).order_by('timestamp')

    for record in weekly_drift_records:
        chart_labels.append(record.timestamp.strftime('%b %d %H:%M'))
        chart_final_scores.append(record.final_score if record.final_score else 0)
        chart_reaction.append(record.reaction_score if record.reaction_score else 0)
        chart_eye.append(record.eye_score if record.eye_score else 0)
        chart_hrv.append(record.hrv_score if record.hrv_score else 0)

    # If no DriftRecord exists but all 3 sensor data exist, create/update one
    if not latest_drift and latest_reaction and latest_eye and latest_hrv:
        reaction_score_val = latest_reaction.drift_score if latest_reaction.drift_score else 50.0
        eye_score_val = latest_eye.eye_score if latest_eye.eye_score else 50.0
        hrv_score_val = latest_hrv.hrv_score if latest_hrv.hrv_score else 50.0
        
        # Fusion formula: weighted average
        final_score_calc = (
            0.4 * reaction_score_val +
            0.3 * eye_score_val +
            0.3 * hrv_score_val
        )
        
        # INVERTED: lower score = more drift
        if final_score_calc >= 70:
            cognitive_state = 'focused'
            warning_level = 'none'
        elif final_score_calc >= 50:
            cognitive_state = 'mild_drift'
            warning_level = 'low'
        elif final_score_calc >= 30:
            cognitive_state = 'moderate_drift'
            warning_level = 'medium'
        else:
            cognitive_state = 'severe_drift'
            warning_level = 'high'
        
        # Save/update DriftRecord
        latest_drift = DriftRecord.objects.create(
            user=user,
            reaction_score=reaction_score_val,
            eye_score=eye_score_val,
            hrv_score=hrv_score_val,
            final_score=final_score_calc,
            cognitive_state=cognitive_state,
            warning_level=warning_level,
            reaction_triggered=False,
            confidence_score=0.7,
        )
        if DEBUG:
            print(f"[DASHBOARD] Created DriftRecord: final_score={final_score_calc}, state={cognitive_state}")

    # HRV chart data - last 30 records
    recent_hrv_records = HRVRecord.objects.filter(
        user=user
    ).order_by('-timestamp')[:30]
    
    hrv_chart_labels = []
    hrv_chart_bpm = []
    hrv_chart_sdnn = []
    
    for record in reversed(list(recent_hrv_records)):
        hrv_chart_labels.append(record.timestamp.strftime('%H:%M:%S'))
        hrv_chart_bpm.append(record.bpm)
        hrv_chart_sdnn.append(record.sdnn)
    
    hrv_count = HRVRecord.objects.filter(user=user).count()

    # Get latest fusion and check for chronic drift
    latest_fusion = FusionRecord.objects.filter(user=user).order_by('-timestamp').first()
    
    # Phase 7: Auto-run fusion if:
    # 1. No fusion exists, OR
    # 2. Latest fusion is older than 5 minutes, OR
    # 3. New sensor data since last fusion
    needs_fusion = False
    if not latest_fusion:
        needs_fusion = True
    else:
        # Check for new sensor data after latest fusion
        new_reaction = ReactionSession.objects.filter(user=user, timestamp__gt=latest_fusion.timestamp).first()
        new_eye = EyeRecord.objects.filter(user=user, timestamp__gt=latest_fusion.timestamp).first()
        new_hrv = HRVRecord.objects.filter(user=user, timestamp__gt=latest_fusion.timestamp).first()
        if new_reaction or new_eye or new_hrv:
            needs_fusion = True
        
        # Also check if fusion is older than 5 minutes
        if timezone.now() - latest_fusion.timestamp > timedelta(minutes=5):
            needs_fusion = True
    
    # Auto-run fusion if needed (all sensors have data)
    if needs_fusion:
        reaction = ReactionSession.objects.filter(user=user).order_by('-timestamp').first()
        eye = EyeRecord.objects.filter(user=user).order_by('-timestamp').first()
        hrv = HRVRecord.objects.filter(user=user).order_by('-timestamp').first()
        
        if reaction and eye and hrv:
            try:
                if DEBUG:
                    print(f"[DASHBOARD] Auto-running fusion...")
                # Use drift_score only if it's > 0, otherwise calculate from mean_rt
                if reaction.drift_score and reaction.drift_score > 0:
                    reaction_score = reaction.drift_score
                elif reaction.mean_rt:
                    reaction_score = 100 - (reaction.mean_rt / 10)
                else:
                    reaction_score = 50
                reaction_score = max(0, min(100, reaction_score))
                eye_score = eye.eye_score if eye.eye_score is not None else 50
                hrv_score = hrv.hrv_score if hrv.hrv_score is not None else 50
                
                from core.fusion_engine import calculate_fusion
                result = calculate_fusion(reaction_score, eye_score, hrv_score)
                
                latest_fusion = FusionRecord.objects.create(
                    user=user,
                    reaction_score=reaction_score,
                    eye_score=eye_score,
                    hrv_score=hrv_score,
                    final_drift_score=result["final_score"],
                    confidence_level=result["confidence"],
                    final_state=result["state"],
                    trigger_reaction_test=result["trigger"],
                    intervention_message=result["message"]
                )
                if DEBUG:
                    print(f"[DASHBOARD] Auto-fusion created: {result['state']}")
            except Exception as e:
                if DEBUG:
                    print(f"[DASHBOARD] Auto-fusion error: {e}")
    
    # Chronic drift check: last 5 records, if 3+ are MODERATE or CONFIRMED
    chronic_state = None
    latest_fusion = FusionRecord.objects.filter(user=user).order_by('-timestamp').first()
    if latest_fusion:
        recent_5 = FusionRecord.objects.filter(user=user).order_by('-timestamp')[:5]
        drift_count = sum(1 for r in recent_5 if r.final_state in ['MODERATE_DRIFT', 'CONFIRMED_DRIFT'])
        if drift_count >= 3:
            chronic_state = 'CHRONIC_DRIFT'
    
    # Phase 6: Get existing validation status (DON'T create new automatically)
    # Just fetch the latest validation - don't create on every load
    existing_validation = get_latest_validation_status(user)
    if DEBUG and existing_validation:
        print(f"[DASHBOARD] Existing validation: {existing_validation.get('status')}")
    
    # Sync FusionRecord with existing validation
    if existing_validation and latest_fusion:
        val_status = existing_validation.get('status')
        latest_fusion.validation_status = val_status
        latest_fusion.save()
        if DEBUG:
            print(f"[DASHBOARD] Synced FusionRecord with: {val_status}")
    
    # State display name mapping
    state_display = {
        'STABLE': 'Stable',
        'MILD_DRIFT': 'Mild Drift',
        'MODERATE_DRIFT': 'Moderate Drift',
        'CONFIRMED_DRIFT': 'Confirmed Drift',
        'CHRONIC_DRIFT': 'Chronic Drift',
        'SUSPECTED_DRIFT': 'Suspected Drift',
        'SUSPENDED_DRIFT': 'Suspended',
        'INCOMPLETE_DATA': 'Incomplete Data',
        'No Data': 'No Data',
    }
    
    # Phase 6: Get effective state/score from validation (validation OVERRIDES)
    # This ensures false_alert shows NORMAL, not DRIFT
    # Get the DriftValidation record for dashboard display
    drift_validation = get_latest_validation_status(user)
    
    # Map validation status to cognitive state - VALIDATION OVERRIDES everything
    validation_state_map = {
        'confirmed_drift': 'CONFIRMED_DRIFT',
        'suspected': 'SUSPECTED_DRIFT',
        'false_alert': 'STABLE',
        'normal': 'STABLE',
    }
    
    if drift_validation:
        # VALIDATION EXISTS - use validation status to determine state
        val_status = drift_validation.get('status')
        effective_state = validation_state_map.get(val_status, 'SUSPENDED_DRIFT')
        # Override chronic state when validation is active
        chronic_state = None
        
        if val_status == 'confirmed_drift':
            effective_score = latest_fusion.get_effective_score() if latest_fusion else 50.0
        elif val_status == 'false_alert':
            effective_score = 15.0  # Safe score
        elif val_status == 'suspected':
            effective_score = 40.0  # Mild drift warning
        else:
            effective_score = latest_fusion.get_effective_score() if latest_fusion else None
    elif latest_fusion:
        # NO VALIDATION - fallback to Phase 5 logic
        effective_state = latest_fusion.get_effective_state()
        effective_score = latest_fusion.get_effective_score()
    else:
        effective_state = None
        effective_score = None
    
    validation_status = drift_validation.get('status') if drift_validation else None
    
    # Phase 7 fix: Calculate current cognitive state from LATEST sensor data ONLY
    # NOT from old validation records
    
    # Determine individual signal states from latest records
    reaction_signal = 'stable'  # default
    eye_signal = 'normal'      # default
    hrv_signal = 'normal'     # default
    
    if latest_reaction:
        reaction_signal = latest_reaction.drift_level if latest_reaction.drift_level else 'stable'
    
    if latest_eye:
        eye_signal = latest_eye.eye_state if latest_eye.eye_state else 'normal'
    
    if latest_hrv:
        hrv_signal = latest_hrv.stress_level if latest_hrv.stress_level else 'normal'
    
    # Count abnormal signals (not stable/normal/relaxed)
    abnormal_count = 0
    if reaction_signal not in ['stable', 'good', 'normal']:
        abnormal_count += 1
    if eye_signal not in ['normal', 'good', 'relaxed', 'stable']:
        abnormal_count += 1
    if hrv_signal not in ['relaxed', 'normal', 'good', 'low_stress']:
        abnormal_count += 1
    
    # Phase 7: Calculate current cognitive state from latest sensor signals
    # Phase 7 fix: Use latest DriftRecord only if ALL THREE sensors have data
    # If not all sensors exist, show incomplete data
    
    # Check if all 3 sensor data exists
    all_sensors_exist = latest_reaction is not None and latest_eye is not None and latest_hrv is not None
    
    # Default confidence level - will be overwritten when data exists
    confidence_level = 'Unavailable'
    
    if latest_drift and all_sensors_exist:
        # Use DriftRecord only when all sensors have data
        cognitive_state_map = {
            'focused': 'STABLE',
            'mild_drift': 'MILD_DRIFT',
            'moderate_drift': 'MODERATE_DRIFT',
            'severe_drift': 'CONFIRMED_DRIFT',
        }
        effective_state = cognitive_state_map.get(latest_drift.cognitive_state, 'STABLE')
        effective_score = latest_drift.final_score if latest_drift.final_score else 50.0
        warning_level_from_drift = latest_drift.warning_level if latest_drift.warning_level else 'none'
        
        # Calculate level from cognitive_state
        if latest_drift.cognitive_state == 'focused':
            warning_level = 0
            confidence_level = 'Normal'
        elif latest_drift.cognitive_state == 'mild_drift':
            warning_level = 1
            confidence_level = 'Low'
        elif latest_drift.cognitive_state == 'moderate_drift':
            warning_level = 2
            confidence_level = 'Medium'
        elif latest_drift.cognitive_state == 'severe_drift':
            warning_level = 3
            confidence_level = 'High'
        else:
            warning_level = 0
            confidence_level = 'Normal'
    else:
        # Either no DriftRecord OR incomplete sensor data
        if all_sensors_exist:
            # All sensors have data but no DriftRecord yet - calculate on-the-fly
            reaction_score_val = latest_reaction.drift_score if latest_reaction.drift_score else 50.0
            eye_score_val = latest_eye.eye_score if latest_eye.eye_score else 50.0
            hrv_score_val = latest_hrv.hrv_score if latest_hrv.hrv_score else 50.0
            
            # Fusion formula: weighted average
            effective_score = (
                0.4 * reaction_score_val +
                0.3 * eye_score_val +
                0.3 * hrv_score_val
            )
            
            # Determine cognitive state (INVERTED: lower score = more drift)
            if effective_score >= 70:
                effective_state = 'STABLE'
                warning_level = 0
                confidence_level = 'Normal'
            elif effective_score >= 50:
                effective_state = 'MILD_DRIFT'
                warning_level = 1
                confidence_level = 'Low'
            elif effective_score >= 30:
                effective_state = 'MODERATE_DRIFT'
                warning_level = 2
                confidence_level = 'Medium'
            else:
                effective_state = 'CONFIRMED_DRIFT'
                warning_level = 3
                confidence_level = 'High'
        else:
            # Missing sensor data - incomplete
            effective_state = 'INCOMPLETE_DATA'
            effective_score = None
            warning_level = None
            confidence_level = 'Unavailable'
            abnormal_signals = ['Required sensor data missing']
    
    fusion_state_display = state_display.get(effective_state, 'No Data') if effective_state else 'No Data'

    # Debug output
    if DEBUG:
        print(f"[PHASE7 DEBUG] all_sensors_exist: {all_sensors_exist}")
        print(f"[PHASE7 DEBUG] latest_drift: {latest_drift}")
        print(f"[PHASE7 DEBUG] effective_state: {effective_state}, warning_level: {warning_level}")
    
    warning_info = {
        0: {'level': 'none', 'display': 'Stable', 'color': 'success'},
        1: {'level': 'low', 'display': 'Low', 'color': 'info'},
        2: {'level': 'medium', 'display': 'Medium', 'color': 'warning'},
        3: {'level': 'high', 'display': 'High', 'color': 'danger'},
    }.get(warning_level, {'level': 'none', 'display': 'Unknown', 'color': 'secondary'})

    # Get warning info and recommendations from DriftRecord ONLY
    if not all_sensors_exist:
        # Incomplete data - show different message first
        recommendations = [
            "Complete all three tests to get cognitive state recommendation.",
            "Run Reaction Test, Eye Tracker, and HRV Sensor.",
        ]
    elif warning_level == 0:
        # Stable/focused
        recommendations = [
            "You are focused. Keep going!",
            "Take regular breaks to maintain focus.",
        ]
    elif warning_level == 1:
        recommendations = [
            "Stay focused - take short breaks if needed.",
            "Adjust posture and stay hydrated.",
        ]
    elif warning_level == 2:
        recommendations = [
            "Take a 5-10 minute break.",
            "Drink water and stretch.",
        ]
    elif warning_level == 3:
        recommendations = [
            "Stop session briefly and rest.",
            "Consider ending for today.",
        ]
    else:
        recommendations = []

    # Phase 6: Intervention message based on validation status
    intervention_messages = {
        'normal': {'message': 'You are focused. Keep going!', 'level': 'info', 'color': 'success'},
        'false_alert': {'message': 'You are focused. Keep going!', 'level': 'info', 'color': 'success'},
        'suspected': {'message': 'You might be losing focus. Consider taking a short break.', 'level': 'low', 'color': 'warning'},
        'confirmed_drift': {'message': 'Cognitive fatigue detected. Take a 10–15 minute break.', 'level': 'high', 'color': 'danger'},
        'waiting_reaction': {'message': 'Reaction test needed to confirm status.', 'level': 'medium', 'color': 'warning'},
    }
    validation_status_key = validation_status if validation_status else 'normal'
    intervention = intervention_messages.get(validation_status_key, intervention_messages['normal'])

    context = {
        'profile': profile,
        'latest_drift': latest_drift,
        'latest_reaction': latest_reaction,
        'latest_eye': latest_eye,
        'latest_hrv': latest_hrv,
        'unacknowledged_warnings': unacknowledged_warnings,
        'recent_warnings': recent_warnings,
        'recent_drifts': recent_drifts,
        'today_pomodoros': today_pomodoros,
        'today_distractions': today_distractions,
        'focus_minutes': profile.pomodoro_focus_minutes,
        'break_minutes': profile.pomodoro_break_minutes,
        'today_goal': today_goal,
        'recent_distractions': recent_distractions_list,
        'recent_pomodoros': recent_pomodoros,
        'chart_labels': json.dumps(chart_labels),
        'chart_final_scores': json.dumps(chart_final_scores),
        'chart_reaction': json.dumps(chart_reaction),
        'chart_eye': json.dumps(chart_eye),
        'chart_hrv': json.dumps(chart_hrv),
        'reaction_baseline': ReactionSession.get_baseline_for_user(user),
        'hrv_chart_labels': json.dumps(hrv_chart_labels),
        'hrv_chart_bpm': json.dumps(hrv_chart_bpm),
        'hrv_chart_sdnn': json.dumps(hrv_chart_sdnn),
        'hrv_record_count': hrv_count,
        'latest_fusion': latest_fusion,
        'fusion_state_display': fusion_state_display,
        'effective_score': effective_score,
        'effective_state': effective_state,
        'validation_status': validation_status,
        'drift_validation': drift_validation,
        'chronic_state': chronic_state,
        'intervention': intervention,
        # Phase 7: Warning level system
        'warning_level': warning_level,
        'warning_info': warning_info,
        'recommendations': recommendations,
        'level_display': get_level_display_name(warning_level),
        # Phase 7: Current state from latest sensor data ONLY
        'current_state': effective_state if effective_state else 'No Data',
        'current_level': warning_level,
        'abnormal_count': abnormal_count,
        'all_sensors_exist': all_sensors_exist,
        'confidence_level': confidence_level,
    }
    
    # Phase 7 debug: Print current badge values
    if DEBUG:
        print(f"[TEMPLATE DEBUG] current_state: {effective_state}, current_level: {warning_level}, abnormal_count: {abnormal_count}")

    # Add baseline info to context for template
    baseline = ReactionSession.get_baseline_for_user(user)
    context['reaction_baseline_established'] = baseline['established']
    context['reaction_baseline_mean'] = baseline['baseline_mean']
    context['reaction_baseline_count'] = baseline['session_count']

    return render(request, 'core/dashboard.html', context)


@login_required
def profile_view(request):
    """User profile and settings view."""
    profile = request.user.profile

    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserProfileForm(instance=profile)

    return render(request, 'core/profile.html', {'form': form, 'profile': profile})


@login_required
def history_view(request):
    """History page showing all user records."""
    user = request.user

    drift_records = DriftRecord.objects.filter(user=user).order_by('-timestamp')[:50]
    reaction_records = ReactionSession.objects.filter(user=user).order_by('-timestamp')[:20]
    eye_records = EyeRecord.objects.filter(user=user).order_by('-timestamp')[:20]
    hrv_records = HRVRecord.objects.filter(user=user).order_by('-timestamp')[:20]
    warning_records = WarningLog.objects.filter(user=user).order_by('-timestamp')[:20]
    goal_records = GoalRecord.objects.filter(user=user).order_by('-date')[:20]
    pomodoro_records = PomodoroSession.objects.filter(user=user).order_by('-start_time')[:20]
    distraction_records = DistractionRecord.objects.filter(user=user).order_by('-timestamp')[:20]

    context = {
        'drift_records': drift_records,
        'reaction_records': reaction_records,
        'eye_records': eye_records,
        'hrv_records': hrv_records,
        'warning_records': warning_records,
        'goal_records': goal_records,
        'pomodoro_records': pomodoro_records,
        'distraction_records': distraction_records,
    }

    return render(request, 'core/history.html', context)


@login_required
def reaction_test_view(request):
    """
    Reaction Time Test page.
    Phase 2 - Reaction Time Module.
    Shows the reaction test interface with baseline status.
    """
    user = request.user
    baseline = ReactionSession.get_baseline_for_user(user)
    latest_session = ReactionSession.objects.filter(user=user).order_by('-timestamp').first()
    
    # Get recent sessions for display
    recent_sessions = ReactionSession.objects.filter(user=user).order_by('-timestamp')[:5]
    
    context = {
        'baseline_established': baseline['established'],
        'baseline_session_count': baseline['session_count'],
        'baseline_mean': round(baseline['baseline_mean'], 2) if baseline['baseline_mean'] else None,
        'sessions_needed': max(0, 3 - baseline['session_count']),
        'latest_session': latest_session,
        'recent_sessions': recent_sessions,
    }
    
    return render(request, 'core/reaction_test.html', context)


@login_required
def acknowledge_warning(request, warning_id):
    """Mark a warning as acknowledged."""
    try:
        warning = WarningLog.objects.get(id=warning_id, user=request.user)
        warning.acknowledged = True
        warning.save()
        return JsonResponse({'success': True})
    except WarningLog.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Warning not found'}, status=404)


# =============================================================================
# API ENDPOINTS - JSON responses for frontend AJAX calls
# =============================================================================

@login_required
def api_dashboard_summary(request):
    """
    API endpoint for dashboard summary data.
    Returns latest scores and current status.
    """
    user = request.user

    latest_drift = DriftRecord.objects.filter(user=user).order_by('-timestamp').first()
    latest_reaction = ReactionSession.objects.filter(user=user).order_by('-timestamp').first()
    latest_eye = EyeRecord.objects.filter(user=user).order_by('-timestamp').first()
    latest_hrv = HRVRecord.objects.filter(user=user).order_by('-timestamp').first()

    unacknowledged = WarningLog.objects.filter(user=user, acknowledged=False).count()

    data = {
        'user': {
            'username': user.username,
            'full_name': user.profile.full_name,
        },
        'latest_scores': {
            'reaction': latest_reaction.mean_rt if latest_reaction else None,
            'reaction_score': latest_drift.reaction_score if latest_drift else None,
            'eye_score': latest_drift.eye_score if latest_drift else None,
            'hrv_score': latest_drift.hrv_score if latest_drift else None,
            'final_score': latest_drift.final_score if latest_drift else None,
        },
        'cognitive_state': latest_drift.cognitive_state if latest_drift else 'no_data',
        'warning_level': latest_drift.warning_level if latest_drift else None,
        'unacknowledged_warnings': unacknowledged,
        'pomodoro': {
            'enabled': user.profile.pomodoro_enabled,
            'focus_minutes': user.profile.pomodoro_focus_minutes,
            'break_minutes': user.profile.pomodoro_break_minutes,
        }
    }

    return JsonResponse(data)


@login_required
def api_drift_records(request):
    """
    API endpoint for drift records.
    Returns recent drift analysis results.
    """
    user = request.user
    limit = int(request.GET.get('limit', 20))

    records = DriftRecord.objects.filter(user=user).order_by('-timestamp')[:limit]

    data = {
        'records': [
            {
                'id': r.id,
                'timestamp': r.timestamp.isoformat(),
                'reaction_score': r.reaction_score,
                'eye_score': r.eye_score,
                'hrv_score': r.hrv_score,
                'final_score': r.final_score,
                'cognitive_state': r.cognitive_state,
                'warning_level': r.warning_level,
                'reaction_triggered': r.reaction_triggered,
                'confidence_score': r.confidence_score,
            }
            for r in records
        ]
    }

    return JsonResponse(data)


@login_required
def api_reaction_records(request):
    """API endpoint for reaction session records."""
    user = request.user
    limit = int(request.GET.get('limit', 20))

    records = ReactionSession.objects.filter(user=user).order_by('-timestamp')[:limit]

    data = {
        'records': [
            {
                'id': r.id,
                'timestamp': r.timestamp.isoformat(),
                'mean_rt': r.mean_rt,
                'std_dev': r.std_dev,
                'variability': r.variability,
                'z_score': r.z_score,
                'valid_trials': r.valid_trials,
                'false_starts': r.false_starts,
                'anticipations': r.anticipations,
                'accuracy': r.accuracy,
                'drift_level': r.drift_level,
                'confidence_score': r.confidence_score,
                'baseline_mean': r.baseline_mean_at_time,
                'percent_change': r.percent_change_from_baseline,
                'notes': r.notes,
            }
            for r in records
        ]
    }

    return JsonResponse(data)


@login_required
def api_eye_records(request):
    """API endpoint for eye tracking records."""
    user = request.user
    limit = int(request.GET.get('limit', 20))

    records = EyeRecord.objects.filter(user=user).order_by('-timestamp')[:limit]

    data = {
        'records': [
            {
                'id': r.id,
                'timestamp': r.timestamp.isoformat(),
                'blink_rate': r.blink_rate,
                'blink_duration': r.blink_duration,
                'eye_state': r.eye_state,
                'eye_score': r.eye_score,
                'notes': r.notes,
            }
            for r in records
        ]
    }

    return JsonResponse(data)


@login_required
def api_hrv_records(request):
    """API endpoint for HRV records."""
    user = request.user
    limit = int(request.GET.get('limit', 20))

    records = HRVRecord.objects.filter(user=user).order_by('-timestamp')[:limit]

    data = {
        'records': [
            {
                'id': r.id,
                'timestamp': r.timestamp.isoformat(),
                'bpm': r.bpm,
                'sdnn': r.sdnn,
                'stress_level': r.stress_level,
                'hrv_score': r.hrv_score,
                'notes': r.notes,
            }
            for r in records
        ]
    }

    return JsonResponse(data)


@login_required
def api_warnings(request):
    """API endpoint for warning logs."""
    user = request.user
    limit = int(request.GET.get('limit', 20))
    unacknowledged_only = request.GET.get('unacknowledged', 'false').lower() == 'true'

    queryset = WarningLog.objects.filter(user=user)
    if unacknowledged_only:
        queryset = queryset.filter(acknowledged=False)

    records = queryset.order_by('-timestamp')[:limit]

    data = {
        'records': [
            {
                'id': r.id,
                'timestamp': r.timestamp.isoformat(),
                'warning_level': r.warning_level,
                'warning_message': r.warning_message,
                'trigger_source': r.trigger_source,
                'acknowledged': r.acknowledged,
            }
            for r in records
        ]
    }

    return JsonResponse(data)


@login_required
def api_chart_data(request):
    """API endpoint for dashboard chart data."""
    user = request.user
    days = int(request.GET.get('days', 7))

    start_date = timezone.now() - timedelta(days=days)

    records = DriftRecord.objects.filter(
        user=user, timestamp__gte=start_date
    ).order_by('timestamp')

    data = {
        'labels': [],
        'final_scores': [],
        'reaction_scores': [],
        'eye_scores': [],
        'hrv_scores': [],
    }

    for r in records:
        data['labels'].append(r.timestamp.strftime('%b %d %H:%M'))
        data['final_scores'].append(r.final_score if r.final_score else 0)
        data['reaction_scores'].append(r.reaction_score if r.reaction_score else 0)
        data['eye_scores'].append(r.eye_score if r.eye_score else 0)
        data['hrv_scores'].append(r.hrv_score if r.hrv_score else 0)

    return JsonResponse(data)


# =============================================================================
# PLACEHOLDER POST ENDPOINTS - For future sensor/module integration
# =============================================================================

@csrf_exempt
@login_required
def api_save_reaction(request):
    """
    Placeholder POST endpoint for saving reaction test results.
    To be integrated with reaction time sensor module in Phase 2.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    print("Saving reaction for:", request.user)
    
    try:
        data = json.loads(request.body)
        form = ReactionSessionForm(data)

        if form.is_valid():
            session = ReactionSession.objects.create(
                user=request.user,
                mean_rt=form.cleaned_data['mean_rt'],
                std_rt=form.cleaned_data['std_rt'],
                variability=form.cleaned_data['variability'],
                z_score=form.cleaned_data['z_score'],
                valid_trials=form.cleaned_data['valid_trials'],
                total_trials=form.cleaned_data['total_trials'],
                false_starts=form.cleaned_data['false_starts'],
                anticipations=form.cleaned_data['anticipations'],
                drift_status=form.cleaned_data['drift_status'],
                notes=form.cleaned_data.get('notes', ''),
            )

            reaction_score = min(100, max(0, 50 + (form.cleaned_data['z_score'] * 10)))
            
            baseline = ReactionSession.get_baseline_for_user(request.user)
            baseline_rt = baseline.get('baseline_mean') if baseline else None
            
            score_result = calculate_reaction_score(
                form.cleaned_data['mean_rt'],
                baseline_rt,
                form.cleaned_data.get('std_rt')
            )
            reaction_score = score_result['score']

            drift_record = DriftRecord.objects.create(
                user=request.user,
                reaction_score=reaction_score,
                reaction_triggered=True,
            )

            return JsonResponse({
                'success': True,
                'session_id': session.id,
                'drift_record_id': drift_record.id,
                'reaction_score': reaction_score,
            })
        else:
            return JsonResponse({'error': 'Invalid data', 'details': form.errors}, status=400)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@login_required
def api_save_eye(request):
    """
    API endpoint for saving eye tracking data from OpenCV module.
    Phase 3 - Eye Monitoring Module.
    """
    print("Saving eye for:", request.user)
    print("="*50)
    print("[EYE SAVE] REQUEST RECEIVED")
    print(f"[EYE SAVE] Method: {request.method}")
    print(f"[EYE SAVE] User: {request.user}")
    print("="*50)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        print(f"[EYE SAVE] Data keys: {list(data.keys())}")
        
        form = EyeRecordForm(data)

        if form.is_valid():
            print(f"[EYE SAVE] Form valid. Cleaning data...")
            
            eye_record = EyeRecord.objects.create(
                user=request.user,
                ear=form.cleaned_data.get('ear'),
                blink_count=form.cleaned_data.get('blink_count', 0),
                blink_duration_avg=form.cleaned_data.get('blink_duration_avg'),
                blink_rate=form.cleaned_data.get('blink_rate'),
                eye_state=form.cleaned_data.get('eye_state', 'normal'),
                eye_score=form.cleaned_data.get('eye_score', 50),
                fatigue_flag=form.cleaned_data.get('fatigue_flag', False),
                ear_samples_json=form.cleaned_data.get('ear_samples', ''),
                notes=form.cleaned_data.get('notes', ''),
            )
            
            # Phase 7 debug: Print saved data
            print(f"[EYE SAVE] ====================")
            print(f"[EYE SAVE] User: {request.user}")
            print(f"[EYE SAVE] is_authenticated: {request.user.is_authenticated}")
            print(f"[EYE SAVE] Saved EyeRecord ID: {eye_record.id}")
            print(f"[EYE SAVE] EyeRecord user: {eye_record.user}")
            print(f"[EYE SAVE] blink_count: {eye_record.blink_count}")
            print(f"[EYE SAVE] blink_rate: {eye_record.blink_rate}")
            print(f"[EYE SAVE] eye_state: {eye_record.eye_state}")
            print(f"[EYE SAVE] eye_score: {eye_record.eye_score}")
            print(f"[EYE SAVE] ====================")
            
            # Update DriftRecord with eye score
            try:
                latest_drift = DriftRecord.objects.filter(
                    user=request.user
                ).order_by('-timestamp').first()

                eye_score = form.cleaned_data.get('eye_score', 50)
                
                if latest_drift:
                    latest_drift.eye_score = eye_score
                    if latest_drift.reaction_score:
                        latest_drift.final_score = (latest_drift.reaction_score + eye_score + (latest_drift.hrv_score or 0)) / 3
                    latest_drift.save()
                    print(f"[EYE SAVE] Updated DriftRecord ID: {latest_drift.id}")
                    drift_id = latest_drift.id
                else:
                    drift_record = DriftRecord.objects.create(
                        user=request.user,
                        eye_score=eye_score,
                    )
                    print(f"[EYE SAVE] Created new DriftRecord ID: {drift_record.id}")
                    drift_id = drift_record.id
            except Exception as e:
                print(f"[EYE SAVE] Error updating DriftRecord: {e}")
                drift_id = None

            return JsonResponse({
                'success': True,
                'record_id': eye_record.id,
                'eye_state': eye_record.eye_state,
                'eye_score': eye_record.eye_score,
                'drift_record_id': drift_id,
            })
        else:
            print(f"[EYE SAVE] Form errors: {form.errors}")
            return JsonResponse({'error': 'Invalid data', 'details': str(form.errors)}, status=400)

    except json.JSONDecodeError as e:
        print(f"[EYE SAVE] JSON decode error: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        print(f"[EYE SAVE] Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@login_required
def api_save_hrv(request):
    """
    POST endpoint for saving HRV data from Arduino MAX30102 sensor.
    Phase 4 - HRV Module.
    
    Accepts JSON:
    - bpm: heart rate
    - sdnn: HRV standard deviation
    - ir_value: raw infrared sensor value (optional)
    - stress: stress level string from Arduino (e.g., "Low Stress", "High Stress")
    - hrv_score: computed score (optional, calculated if not provided)
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    print("Saving HRV for:", request.user)
    
    try:
        data = json.loads(request.body)
        form = HRVRecordForm(data)

        if form.is_valid():
            bpm = form.cleaned_data['bpm']
            sdnn = form.cleaned_data['sdnn']
            ir_value = form.cleaned_data.get('ir_value')
            
            stress_str = data.get('stress', 'normal')
            stress_level = map_arduino_stress(stress_str)
            
            hrv_score = form.cleaned_data.get('hrv_score')
            if hrv_score is None:
                hrv_score = calculate_hrv_score(bpm, sdnn, stress_level)
            
            record = HRVRecord.objects.create(
                user=request.user,
                bpm=bpm,
                sdnn=sdnn,
                ir_value=ir_value,
                stress_level=stress_level,
                hrv_score=hrv_score,
                notes=form.cleaned_data.get('notes', ''),
            )
            
            # Phase 7 debug: Print saved data
            print(f"[HRV SAVE] ====================")
            print(f"[HRV SAVE] User: {request.user}")
            print(f"[HRV SAVE] is_authenticated: {request.user.is_authenticated}")
            print(f"[HRV SAVE] Saved HRVRecord ID: {record.id}")
            print(f"[HRV SAVE] HRVRecord user: {record.user}")
            print(f"[HRV SAVE] bpm: {record.bpm}")
            print(f"[HRV SAVE] sdnn: {record.sdnn}")
            print(f"[HRV SAVE] stress_level: {record.stress_level}")
            print(f"[HRV SAVE] hrv_score: {record.hrv_score}")
            print(f"[HRV SAVE] ====================")

            try:
                latest_drift = DriftRecord.objects.filter(
                    user=request.user
                ).order_by('-timestamp').first()

                if latest_drift:
                    latest_drift.hrv_score = hrv_score
                    latest_drift.save()
                    drift_id = latest_drift.id
                else:
                    drift_record = DriftRecord.objects.create(
                        user=request.user,
                        hrv_score=hrv_score,
                    )
                    drift_id = drift_record.id
            except:
                drift_id = None

            return JsonResponse({
                'success': True,
                'record_id': record.id,
                'hrv_score': hrv_score,
                'stress_level': stress_level,
                'drift_record_id': drift_id,
            })
        else:
            return JsonResponse({'error': 'Invalid data', 'details': form.errors}, status=400)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def map_arduino_stress(stress_str, sdnn=None):
    """Map Arduino stress string to model choices based on SDNN.
    
    SDNN-based classification:
    - sdnn < 30: High Stress
    - 30-60: Moderate
    - 60-120: Relaxed
    - > 120: Unstable
    """
    if sdnn is not None:
        if sdnn > 120:
            return 'unstable'
        elif sdnn >= 60:
            return 'relaxed'
        elif sdnn >= 30:
            return 'moderate'
        else:
            return 'high_stress'
    
    stress_str_lower = stress_str.lower() if stress_str else 'normal'
    
    if 'unstable' in stress_str_lower:
        return 'unstable'
    elif 'high stress' in stress_str_lower or 'high_stress' in stress_str_lower:
        return 'high_stress'
    elif 'moderate' in stress_str_lower:
        return 'moderate_stress'
    elif 'relaxed' in stress_str_lower:
        return 'relaxed'
    elif 'mild' in stress_str_lower:
        return 'mild_stress'
    return 'normal'


def calculate_hrv_score(bpm, sdnn, stress_level):
    """Calculate HRV score (0-100) based on BPM, SDNN, and stress level.
    Higher score = better HRV (more relaxed).
    """
    base_score = 50
    
    if 60 <= bpm <= 80:
        base_score += 15
    elif bpm < 60:
        base_score += 10
    elif bpm > 100:
        base_score -= 15
    elif bpm > 85:
        base_score -= 10
    
    if 60 <= sdnn <= 100:
        base_score += 15
    elif sdnn > 100:
        base_score += 10
    elif 30 <= sdnn < 60:
        base_score += 5
    elif sdnn < 20:
        base_score -= 15
    elif sdnn < 30:
        base_score -= 10
    
    stress_penalty = {
        'relaxed': -15,
        'normal': 0,
        'mild_stress': 10,
        'moderate_stress': 20,
        'high_stress': 30,
    }
    base_score += stress_penalty.get(stress_level, 0)
    
    return max(0, min(100, base_score))


@csrf_exempt
def api_hrv_bridge_login(request):
    """
    Bridge login endpoint - authenticates Python bridge script.
    Returns session cookie on success.
    
    Expects JSON: {"username": "...", "password": "..."}
    Returns: {"success": true, "username": "..."} with session cookie
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return JsonResponse({'success': False, 'error': 'Username and password required'}, status=400)
    
    try:
        user_obj = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': f'User "{username}" not found'}, status=401)
    
    user = authenticate(request, username=username, password=password)
    
    if user is not None:
        login(request, user)
        return JsonResponse({
            'success': True,
            'username': user.username,
            'user_id': user.id,
            'message': 'Authenticated successfully'
        })
    else:
        return JsonResponse({'success': False, 'error': 'Invalid password for user "' + username + '"'}, status=401)


@csrf_exempt
@login_required
def api_hrv_bridge(request):
    """
    API endpoint for HRV serial bridge script.
    Phase 4 - HRV Module.
    
    Requires authenticated session (login via /api/hrv-bridge-login/ first).
    
    Accepts JSON:
    - ir: raw infrared value (optional)
    - bpm: heart rate (required)
    - sdnn: SDNN value (required)
    - stress: Arduino stress string (e.g., "Low Stress")
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    
    bpm = data.get('bpm')
    sdnn = data.get('sdnn')
    
    if bpm is None or sdnn is None:
        return JsonResponse({'success': False, 'error': 'Missing bpm or sdnn'}, status=400)
    
    try:
        bpm = float(bpm)
        sdnn = float(sdnn)
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'bpm and sdnn must be numbers'}, status=400)
    
    ir_value = data.get('ir')
    stress_str = data.get('stress', 'normal')
    stress_level = map_arduino_stress(stress_str, sdnn)
    hrv_score = calculate_hrv_score(bpm, sdnn, stress_level)
    
    try:
        record = HRVRecord.objects.create(
            user=request.user,
            bpm=bpm,
            sdnn=sdnn,
            ir_value=ir_value,
            stress_level=stress_level,
            hrv_score=hrv_score,
        )
        
        return JsonResponse({
            'success': True,
            'status': 'saved',
            'record_id': record.id,
            'hrv_score': hrv_score,
            'stress_level': stress_level,
            'user': request.user.username,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
def api_save_reaction_session(request):
    """
    API endpoint for saving complete reaction test session data.
    Phase 2 - Reaction Time Module.
    
    Expects JSON with:
    - raw_reaction_times: array of all reaction times (ms)
    - clean_reaction_times: array of valid reaction times (ms)
    - false_starts: count of clicks before stimulus
    - anticipations: count of RT < 100ms
    - valid_trials: count of valid trials
    - total_trials: total trials attempted
    - notes: optional session notes
    
    Returns:
    - session_id: saved session ID
    - baseline_status: info about user's baseline
    - drift_level: classified drift level
    - percent_change: change from baseline percentage
    - confidence_score: session quality score
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        user = request.user
        
        # Phase 7 debug
        print(f"[REACTION SAVE] ====================")
        print(f"[REACTION SAVE] User from request: {user}")
        print(f"[REACTION SAVE] is_authenticated: {user.is_authenticated}")
        print(f"[REACTION SAVE] ====================")
        
        raw_times = data.get('raw_reaction_times', [])
        clean_times = data.get('clean_reaction_times', [])
        false_starts = int(data.get('false_starts', 0))
        anticipations = int(data.get('anticipations', 0))
        valid_trials = int(data.get('valid_trials', 0))
        total_trials = int(data.get('total_trials', 0))
        notes = data.get('notes', '')
        
        # Phase 6: Server-side data cleaning - cap unrealistic reaction times
        # Valid human reaction time: 150ms - 1200ms
        MIN_RT = 150
        MAX_RT = 1200
        
        # Cap values outside range to min/max
        clean_times = [max(MIN_RT, min(MAX_RT, rt)) for rt in clean_times]
        
        if DEBUG:
            print(f"[REACTION] Times after capping: {clean_times}")
        
        if not clean_times or len(clean_times) < 5:
            return JsonResponse({
                'error': 'Insufficient valid trials',
                'details': 'Need at least 5 valid trials'
            }, status=400)
        
        mean_rt = sum(clean_times) / len(clean_times)
        std_dev = (sum((x - mean_rt) ** 2 for x in clean_times) / len(clean_times)) ** 0.5 if len(clean_times) > 1 else 0
        variability = std_dev / mean_rt if mean_rt > 0 else 0
        
        session = ReactionSession.objects.create(
            user=user,
            mean_rt=round(mean_rt, 2),
            std_dev=round(std_dev, 2),
            variability=round(variability, 4),
            z_score=0,
            valid_trials=valid_trials,
            total_trials=total_trials,
            false_starts=false_starts,
            anticipations=anticipations,
            raw_reaction_times_json=json.dumps(raw_times),
            clean_reaction_times_json=json.dumps(clean_times),
            notes=notes,
        )
        
        # Phase 7 debug
        print(f"[REACTION SAVE] ====================")
        print(f"[REACTION SAVE] Saved Session ID: {session.id}")
        print(f"[REACTION SAVE] Session user: {session.user}")
        print(f"[REACTION SAVE] mean_rt: {session.mean_rt}")
        print(f"[REACTION SAVE] drift_level: {session.drift_level}")
        print(f"[REACTION SAVE] drift_score: {session.drift_score}")
        print(f"[REACTION SAVE] ====================")
        
        session.refresh_from_db()
        baseline = ReactionSession.get_baseline_for_user(user)
        
        baseline_rt = baseline.get('baseline_mean') if baseline else None
        
        score_result = calculate_reaction_score(session.mean_rt, baseline_rt, session.std_dev)
        reaction_score = score_result['score']
        
        if DEBUG:
            print(f"[REACTION SAVE] reaction_score: {reaction_score}, status: {score_result['status']}")
        
        # Save drift_score to session for Phase 5 fusion
        session.drift_score = reaction_score
        session.save()
        
        try:
            latest_drift = DriftRecord.objects.filter(user=user).order_by('-timestamp').first()
            if DEBUG:
                print(f"[REACTION SAVE] Latest drift record: {latest_drift}")
            
            if latest_drift:
                latest_drift.reaction_score = reaction_score
                latest_drift.reaction_triggered = True
                
                if latest_drift.eye_score and latest_drift.hrv_score:
                    latest_drift.final_score = (reaction_score + latest_drift.eye_score + latest_drift.hrv_score) / 3
                
                # INVERTED: lower score = more drift
                if reaction_score >= 70:
                    latest_drift.cognitive_state = 'focused'
                elif reaction_score >= 50:
                    latest_drift.cognitive_state = 'mild_drift'
                elif reaction_score >= 30:
                    latest_drift.cognitive_state = 'moderate_drift'
                else:
                    latest_drift.cognitive_state = 'severe_drift'
                
                latest_drift.save()
                print(f"[REACTION SAVE] Updated existing DriftRecord ID: {latest_drift.id}")
                drift_id = latest_drift.id
            else:
                cognitive_state = 'focused' if reaction_score >= 70 else ('mild_drift' if reaction_score >= 50 else ('moderate_drift' if reaction_score >= 30 else 'severe_drift'))
                drift_record = DriftRecord.objects.create(
                    user=user,
                    reaction_score=reaction_score,
                    reaction_triggered=True,
                    cognitive_state=cognitive_state,
                )
                print(f"[REACTION SAVE] Created new DriftRecord ID: {drift_record.id}")
                drift_id = drift_record.id
        except Exception as e:
            print(f"[REACTION SAVE] ERROR updating DriftRecord: {e}")
            import traceback
            traceback.print_exc()
            drift_id = None
        
        return JsonResponse({
            'success': True,
            'session_id': session.id,
            'saved_session': {
                'mean_rt': session.mean_rt,
                'std_dev': session.std_dev,
                'variability': session.variability,
                'valid_trials': session.valid_trials,
            },
            'baseline_status': {
                'established': baseline['established'],
                'session_count': baseline['session_count'],
                'baseline_mean': round(baseline['baseline_mean'], 2) if baseline['baseline_mean'] else None,
                'sessions_needed': max(0, 3 - baseline['session_count']),
            },
            'drift_analysis': {
                'drift_level': session.drift_level,
                'drift_level_display': session.get_drift_level_display(),
                'percent_change': round(session.percent_change_from_baseline, 2) if session.percent_change_from_baseline else None,
                'z_score': round(session.z_score, 3) if session.z_score else 0,
                'drift_score': round(session.drift_score, 2) if session.drift_score else None,
            },
            'confidence': {
                'score': round(session.confidence_score, 2),
                'level': session.confidence_level,
            },
            'drift_record_id': drift_id,
        })
        
        # Phase 6: Auto-validate after reaction test completes
        try:
            validation_result = validate_reaction_confirmation(user)
            if DEBUG:
                print(f"[REACTION] Validation result: {validation_result}")
                print(f"[REACTION] Status: {validation_result.get('status')}, Drift confirmed: {validation_result.get('drift_confirmed')}")
        except Exception as e:
            if DEBUG:
                print(f"[REACTION] Validation error: {e}")
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        import traceback
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def api_reaction_baseline(request):
    """API endpoint to get current user's reaction baseline status."""
    baseline = ReactionSession.get_baseline_for_user(request.user)
    return JsonResponse({
        'baseline': {
            'established': baseline['established'],
            'session_count': baseline['session_count'],
            'baseline_mean': round(baseline['baseline_mean'], 2) if baseline['baseline_mean'] else None,
            'baseline_sd': round(baseline['baseline_sd'], 2) if baseline['baseline_sd'] else None,
            'sessions_needed': max(0, 3 - baseline['session_count']),
        }
    })


@login_required
def api_reaction_chart_data(request):
    """API endpoint for Chart.js reaction time trend data."""
    user = request.user
    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)
    
    sessions = ReactionSession.objects.filter(
        user=user, timestamp__gte=start_date
    ).order_by('timestamp')
    
    baseline = ReactionSession.get_baseline_for_user(user)
    
    labels = [s.timestamp.strftime('%b %d %H:%M') for s in sessions]
    mean_rts = [s.mean_rt for s in sessions]
    upper_bound = [baseline['baseline_mean'] * 1.1 if baseline['baseline_mean'] else None] * len(sessions)
    lower_bound = [baseline['baseline_mean'] * 0.9 if baseline['baseline_mean'] else None] * len(sessions)
    
    return JsonResponse({
        'labels': labels,
        'datasets': [
            {
                'label': 'Mean RT (ms)',
                'data': mean_rts,
                'borderColor': '#dc3545',
                'backgroundColor': 'rgba(220, 53, 69, 0.1)',
                'tension': 0.3,
            },
            {
                'label': 'Baseline ±10%',
                'data': upper_bound if baseline['established'] else [None] * len(sessions),
                'borderColor': 'rgba(40, 167, 69, 0.4)',
                'borderDash': [5, 5],
                'fill': False,
                'pointRadius': 0,
            },
        ],
        'baseline': {
            'established': baseline['established'],
            'mean': round(baseline['baseline_mean'], 2) if baseline['baseline_mean'] else None,
        }
    })






@login_required
def run_fusion(request):

    reaction = ReactionSession.objects.filter(user=request.user).order_by('-timestamp').first()
    eye = EyeRecord.objects.filter(user=request.user).order_by('-timestamp').first()
    hrv = HRVRecord.objects.filter(user=request.user).order_by('-timestamp').first()

    # Safety check
    if not reaction or not eye or not hrv:
        return JsonResponse({"error": "Not enough data"}, status=400)

    # ✅ FIXED LINES with fallback logic
    if DEBUG:
        print(f"[FUSION] reaction.drift_score = {reaction.drift_score}, mean_rt = {reaction.mean_rt}")
    if reaction.drift_score is not None:
        reaction_score = reaction.drift_score
    elif reaction.mean_rt is not None:
        reaction_score = max(0, min(100, 100 - (reaction.mean_rt / 10)))
    else:
        reaction_score = 0
    if DEBUG:
        print(f"[FUSION] final reaction_score = {reaction_score}")
    eye_score = eye.eye_score if eye.eye_score is not None else 0
    hrv_score = hrv.hrv_score if hrv.hrv_score is not None else 0

    result = calculate_fusion(reaction_score, eye_score, hrv_score)


    

    FusionRecord.objects.create(
        user=request.user,
        reaction_score=reaction_score,
        eye_score=eye_score,
        hrv_score=hrv_score,
        final_drift_score=result["final_score"],
        confidence_level=result["confidence"],
        final_state=result["state"],
        trigger_reaction_test=result["trigger"],
        intervention_message=result["message"]
    )

    return JsonResponse(result)


# =============================================================================
# PHASE 6 PART 1: SMART VALIDATION ENGINE API ENDPOINTS
# =============================================================================

@login_required
def api_evaluate_suspected_drift(request):
    """
    API endpoint to evaluate suspected cognitive drift.
    
    Checks:
    - User study hours configuration
    - Latest eye monitoring result
    - Latest HRV monitoring result
    
    Returns JSON with drift assessment and whether reaction test is required.
    
    Where to connect: Phase 6 Part 2 intervention module
    """
    result = evaluate_suspected_drift(request.user)
    return JsonResponse(result)


@login_required
def api_validate_reaction_confirmation(request):
    """
    API endpoint to validate drift after reaction test completion.
    
    Compares latest reaction result with user's personalized baseline.
    Determines if drift is confirmed or was a false alert.
    
    Returns JSON with validation result.
    """
    result = validate_reaction_confirmation(request.user)
    return JsonResponse(result)


@login_required
def api_validation_status(request):
    """
    API endpoint to get current validation status.
    
    Returns the latest validation record for dashboard display.
    """
    status = get_latest_validation_status(request.user)
    if status is None:
        return JsonResponse({'status': 'no_validation', 'message': 'No validation records yet'})
    return JsonResponse(status)


# =============================================================================
# PHASE 8 - Productivity & Behavior Layer
# =============================================================================

@login_required
def api_start_pomodoro(request):
    """
    Start a new Pomodoro session (focus or break).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        session_type = data.get('session_type', 'focus')  # focus or break
        focus_minutes = int(data.get('focus_minutes', 25))
        break_minutes = int(data.get('break_minutes', 5))
        
        # Create new PomodoroSession
        pomodoro = PomodoroSession.objects.create(
            user=request.user,
            start_time=timezone.now(),
            focus_minutes=focus_minutes,
            break_minutes=break_minutes,
            completed=False,
        )
        
        return JsonResponse({
            'success': True,
            'session_id': pomodoro.id,
            'session_type': session_type,
            'message': f'{session_type.title()} session started!'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def api_complete_pomodoro(request):
    """
    Complete a Pomodoro session - creates and marks as complete.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        session_type = data.get('session_type', 'focus')
        duration_minutes = int(data.get('duration_minutes', 25))
        
        # Create and complete the session in one go
        pomodoro = PomodoroSession.objects.create(
            user=request.user,
            start_time=timezone.now() - timedelta(minutes=duration_minutes),
            end_time=timezone.now(),
            focus_minutes=duration_minutes,
            break_minutes=5,
            completed=True,
        )
        
        # Get today's completed pomodoros count
        today = timezone.now().date()
        today_count = PomodoroSession.objects.filter(
            user=request.user,
            completed=True,
            start_time__date=today
        ).count()
        
        return JsonResponse({
            'success': True,
            'pomodoro_id': pomodoro.id,
            'pomodoros_today': today_count,
            'message': 'Pomodoro completed!'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def goal_settings(request):
    """
    Goal settings page - view and manage daily goals.
    """
    user = request.user
    today = timezone.now().date()
    
    # Get today's goal
    today_goal = GoalRecord.objects.filter(user=user, date=today).first()
    
    # Get all goals for this user
    all_goals = GoalRecord.objects.filter(user=user).order_by('-date')[:10]
    
    context = {
        'today_goal': today_goal,
        'all_goals': all_goals,
    }
    return render(request, 'core/goal_settings.html', context)


@login_required
def api_add_goal(request):
    """
    Add a new daily goal.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        goal_title = data.get('goal_title')
        target_value = float(data.get('target_value', 60))  # minutes
        subject = data.get('subject', 'Study')
        
        today = timezone.now().date()
        
        # Check if goal already exists for today
        existing = GoalRecord.objects.filter(user=request.user, date=today).first()
        if existing:
            existing.goal_title = goal_title
            existing.target_value = target_value
            existing.save()
            goal = existing
        else:
            goal = GoalRecord.objects.create(
                user=request.user,
                date=today,
                goal_title=goal_title,
                target_value=target_value,
                achieved_value=0,
            )
        
        return JsonResponse({
            'success': True,
            'goal_id': goal.id,
            'goal_title': goal.goal_title,
            'target_value': goal.target_value,
            'completion_percent': goal.completion_percent,
            'status': goal.status,
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def api_complete_goal(request, goal_id):
    """
    Mark a goal as complete.
    """
    try:
        goal = GoalRecord.objects.get(id=goal_id, user=request.user)
        goal.achieved_value = goal.target_value
        goal.completion_percent = 100
        goal.status = 'completed'
        goal.save()
        
        return JsonResponse({
            'success': True,
            'goal_id': goal.id,
            'status': goal.status,
        })
        
    except GoalRecord.DoesNotExist:
        return JsonResponse({'error': 'Goal not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
def api_log_distraction(request):
    """
    Log a distraction occurrence.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        distraction_type = data.get('distraction_type', 'other')
        distraction_name = data.get('distraction_name', '')
        notes = data.get('notes', '')
        
        distraction = DistractionRecord.objects.create(
            user=request.user,
            distraction_name=distraction_name or distraction_type,
            distraction_type=distraction_type,
            notes=notes,
        )
        
        # Get today's distraction count
        today = timezone.now().date()
        today_count = DistractionRecord.objects.filter(
            user=request.user,
            timestamp__date=today
        ).count()
        
        return JsonResponse({
            'success': True,
            'distraction_id': distraction.id,
            'distractions_today': today_count,
            'message': 'Distraction logged!'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
