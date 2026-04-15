# core/views.py
"""
Views for Cognitive Drift Detection System.
Phase 1 - Core web foundation with API endpoints.
"""

from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
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

    latest_drift = DriftRecord.objects.filter(user=user).order_by('-timestamp').first()
    latest_reaction = ReactionSession.objects.filter(user=user).order_by('-timestamp').first()
    latest_eye = EyeRecord.objects.filter(user=user).order_by('-timestamp').first()
    latest_hrv = HRVRecord.objects.filter(user=user).order_by('-timestamp').first()

    unacknowledged_warnings = WarningLog.objects.filter(
        user=user, acknowledged=False
    ).count()

    recent_warnings = WarningLog.objects.filter(
        user=user
    ).order_by('-timestamp')[:5]

    recent_drifts = DriftRecord.objects.filter(
        user=user
    ).order_by('-timestamp')[:10]
    
    today_pomodoros = PomodoroSession.objects.filter(
        user=user, start_time__gte=today_start, completed=True
    ).count()

    today_distractions = DistractionRecord.objects.filter(
        user=user, timestamp__gte=today_start
    ).count()

    weekly_drift_records = DriftRecord.objects.filter(
        user=user, timestamp__gte=week_ago
    ).order_by('timestamp')

    chart_labels = []
    chart_final_scores = []
    chart_reaction = []
    chart_eye = []
    chart_hrv = []

    for record in weekly_drift_records:
        chart_labels.append(record.timestamp.strftime('%b %d %H:%M'))
        chart_final_scores.append(record.final_score if record.final_score else 0)
        chart_reaction.append(record.reaction_score if record.reaction_score else 0)
        chart_eye.append(record.eye_score if record.eye_score else 0)
        chart_hrv.append(record.hrv_score if record.hrv_score else 0)

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
        'chart_labels': json.dumps(chart_labels),
        'chart_final_scores': json.dumps(chart_final_scores),
        'chart_reaction': json.dumps(chart_reaction),
        'chart_eye': json.dumps(chart_eye),
        'chart_hrv': json.dumps(chart_hrv),
        'reaction_baseline': ReactionSession.get_baseline_for_user(user),
    }

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
            
            print(f"[EYE SAVE] EyeRecord created with ID: {eye_record.id}")
            
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
    Placeholder POST endpoint for saving HRV data.
    To be integrated with IoT/physiological sensor module in Phase 4.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        form = HRVRecordForm(data)

        if form.is_valid():
            record = HRVRecord.objects.create(
                user=request.user,
                bpm=form.cleaned_data['bpm'],
                sdnn=form.cleaned_data['sdnn'],
                stress_level=form.cleaned_data['stress_level'],
                hrv_score=form.cleaned_data['hrv_score'],
                notes=form.cleaned_data.get('notes', ''),
            )

            try:
                latest_drift = DriftRecord.objects.filter(
                    user=request.user
                ).order_by('-timestamp').first()

                if latest_drift:
                    latest_drift.hrv_score = form.cleaned_data['hrv_score']
                    latest_drift.save()
                    drift_id = latest_drift.id
                else:
                    drift_record = DriftRecord.objects.create(
                        user=request.user,
                        hrv_score=form.cleaned_data['hrv_score'],
                    )
                    drift_id = drift_record.id
            except:
                drift_id = None

            return JsonResponse({
                'success': True,
                'record_id': record.id,
                'drift_record_id': drift_id,
            })
        else:
            return JsonResponse({'error': 'Invalid data', 'details': form.errors}, status=400)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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
        
        raw_times = data.get('raw_reaction_times', [])
        clean_times = data.get('clean_reaction_times', [])
        false_starts = int(data.get('false_starts', 0))
        anticipations = int(data.get('anticipations', 0))
        valid_trials = int(data.get('valid_trials', 0))
        total_trials = int(data.get('total_trials', 0))
        notes = data.get('notes', '')
        
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
        
        session.refresh_from_db()
        baseline = ReactionSession.get_baseline_for_user(user)
        
        reaction_score = min(100, max(0, 30 + (session.variability * 50) + (session.z_score * 10)))
        print(f"[REACTION SAVE] reaction_score calculated: {reaction_score}")
        
        try:
            latest_drift = DriftRecord.objects.filter(user=user).order_by('-timestamp').first()
            print(f"[REACTION SAVE] Latest drift record: {latest_drift}")
            
            if latest_drift:
                latest_drift.reaction_score = reaction_score
                latest_drift.reaction_triggered = True
                
                if latest_drift.eye_score and latest_drift.hrv_score:
                    latest_drift.final_score = (reaction_score + latest_drift.eye_score + latest_drift.hrv_score) / 3
                
                if reaction_score < 30:
                    latest_drift.cognitive_state = 'focused'
                elif reaction_score < 50:
                    latest_drift.cognitive_state = 'mild_drift'
                elif reaction_score < 70:
                    latest_drift.cognitive_state = 'moderate_drift'
                else:
                    latest_drift.cognitive_state = 'severe_drift'
                
                latest_drift.save()
                print(f"[REACTION SAVE] Updated existing DriftRecord ID: {latest_drift.id}")
                drift_id = latest_drift.id
            else:
                cognitive_state = 'focused' if reaction_score < 30 else ('mild_drift' if reaction_score < 50 else ('moderate_drift' if reaction_score < 70 else 'severe_drift'))
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
