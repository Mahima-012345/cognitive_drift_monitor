# core/models.py
"""
Database models for Cognitive Drift Detection System.
Phase 1 - Core database foundation.
All records are user-linked for per-user baseline comparison in future phases.
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserProfile(models.Model):
    """
    Extended user profile linked one-to-one with Django User.
    Stores user preferences and study settings.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    full_name = models.CharField(max_length=255, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    study_start_time = models.TimeField(null=True, blank=True, help_text="Default study session start time")
    study_end_time = models.TimeField(null=True, blank=True, help_text="Default study session end time")
    pomodoro_enabled = models.BooleanField(default=False)
    pomodoro_focus_minutes = models.PositiveIntegerField(default=25)
    pomodoro_break_minutes = models.PositiveIntegerField(default=5)
    daily_goal = models.CharField(max_length=255, blank=True, help_text="Daily study goal description")
    distraction_list = models.TextField(blank=True, help_text="List of common distractions (one per line)")
    warning_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}'s Profile"

    def get_distractions_list(self):
        """Returns distraction list as a list of strings."""
        if self.distraction_list:
            return [d.strip() for d in self.distraction_list.split('\n') if d.strip()]
        return []


class DriftRecord(models.Model):
    """
    Stores cognitive drift analysis results.
    Combines reaction time, eye tracking, and HRV data into final drift assessment.
    """
    COGNITIVE_STATE_CHOICES = [
        ('focused', 'Focused'),
        ('mild_drift', 'Mild Drift'),
        ('moderate_drift', 'Moderate Drift'),
        ('severe_drift', 'Severe Drift'),
    ]
    
    WARNING_LEVEL_CHOICES = [
        ('none', 'None'),
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='drift_records')
    timestamp = models.DateTimeField(default=timezone.now)
    reaction_score = models.FloatField(null=True, blank=True, help_text="Reaction time based score (0-100)")
    eye_score = models.FloatField(null=True, blank=True, help_text="Eye tracking based score (0-100)")
    hrv_score = models.FloatField(null=True, blank=True, help_text="Heart rate variability score (0-100)")
    final_score = models.FloatField(null=True, blank=True, help_text="Combined final drift score (0-100, higher = more drift)")
    cognitive_state = models.CharField(max_length=20, choices=COGNITIVE_STATE_CHOICES, default='focused')
    warning_level = models.CharField(max_length=10, choices=WARNING_LEVEL_CHOICES, null=True, blank=True)
    reaction_triggered = models.BooleanField(default=False, help_text="Whether reaction test was triggered")
    confidence_score = models.FloatField(null=True, blank=True, help_text="Model confidence (0-1)")

    class Meta:
        verbose_name = "Drift Record"
        verbose_name_plural = "Drift Records"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
        ]

    def __str__(self):
        return f"Drift Record - {self.user.username} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"

    def save(self, *args, **kwargs):
        if self.final_score is None and all([self.reaction_score, self.eye_score, self.hrv_score]):
            self.final_score = (self.reaction_score + self.eye_score + self.hrv_score) / 3
        if self.cognitive_state == 'focused' and self.final_score and self.final_score > 30:
            self.cognitive_state = 'mild_drift'
        if self.cognitive_state == 'mild_drift' and self.final_score and self.final_score > 50:
            self.cognitive_state = 'moderate_drift'
        if self.final_score and self.final_score > 70:
            self.cognitive_state = 'severe_drift'
        super().save(*args, **kwargs)


class ReactionSession(models.Model):
    """
    Stores reaction time test session data.
    Used for measuring cognitive alertness through reaction tests.
    Phase 2 - Enhanced with baseline comparison and drift classification.
    """
    DRIFT_LEVEL_CHOICES = [
        ('baseline_building', 'Baseline Building'),
        ('stable', 'Stable'),
        ('mild_drift', 'Mild Drift'),
        ('moderate_drift', 'Moderate Drift'),
        ('severe_drift', 'Severe Drift'),
    ]
    
    CONFIDENCE_LEVEL_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
        ('provisional', 'Provisional'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reaction_sessions')
    timestamp = models.DateTimeField(default=timezone.now)
    
    # Core statistics (calculated from clean valid trials)
    mean_rt = models.FloatField(null=True, blank=True, help_text="Mean reaction time in milliseconds (clean trials)")
    std_dev = models.FloatField(null=True, blank=True, help_text="Standard deviation of clean reaction times")
    variability = models.FloatField(null=True, blank=True, help_text="Coefficient of variation (std_dev / mean)")
    z_score = models.FloatField(null=True, blank=True, help_text="Z-score relative to user's personal baseline")
    
    # Trial counts
    valid_trials = models.PositiveIntegerField(default=0, help_text="Number of valid trials")
    total_trials = models.PositiveIntegerField(default=0, help_text="Total trials attempted")
    false_starts = models.PositiveIntegerField(default=0, help_text="Clicks before stimulus appeared")
    anticipations = models.PositiveIntegerField(default=0, help_text="RT < 100ms (too fast)")
    
    # Raw data storage (JSON)
    raw_reaction_times_json = models.TextField(blank=True, help_text="All reaction times (including flagged)")
    clean_reaction_times_json = models.TextField(blank=True, help_text="Clean valid reaction times only")
    
    # Baseline comparison fields
    baseline_mean_at_time = models.FloatField(null=True, blank=True, help_text="Baseline mean when session was saved")
    baseline_sd_at_time = models.FloatField(null=True, blank=True, help_text="Baseline SD when session was saved")
    sessions_in_baseline = models.PositiveIntegerField(default=0, help_text="Number of sessions used to establish baseline")
    percent_change_from_baseline = models.FloatField(null=True, blank=True, help_text="Change from baseline in percent")
    
    # Drift classification
    drift_score = models.FloatField(null=True, blank=True, help_text="Overall drift score (0-100)")
    drift_level = models.CharField(max_length=20, choices=DRIFT_LEVEL_CHOICES, default='baseline_building')
    
    # Confidence
    confidence_score = models.FloatField(default=1.0, help_text="Session quality/confidence (0-1)")
    confidence_level = models.CharField(max_length=15, choices=CONFIDENCE_LEVEL_CHOICES, default='high')
    
    # Legacy field for compatibility
    drift_status = models.CharField(max_length=20, choices=[('stable','Stable'),('warning','Warning'),('drifting','Drifting'),('critical','Critical')], default='stable')
    
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Reaction Session"
        verbose_name_plural = "Reaction Sessions"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
        ]

    def __str__(self):
        return f"Reaction Session - {self.user.username} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"

    @property
    def accuracy(self):
        """Percentage of valid trials from total attempts."""
        if self.total_trials > 0:
            return (self.valid_trials / self.total_trials) * 100
        return 0
    
    @property
    def flagged_trial_rate(self):
        """Percentage of trials that were flagged (false starts + anticipations)."""
        if self.total_trials > 0:
            flagged = self.false_starts + self.anticipations
            return (flagged / self.total_trials) * 100
        return 0

    @classmethod
    def get_baseline_for_user(cls, user):
        """
        Calculate personal baseline for a user based on their first 3 completed sessions.
        Returns a dict with baseline_mean, baseline_sd, and session_count.
        """
        sessions = cls.objects.filter(
            user=user, 
            mean_rt__isnull=False
        ).order_by('timestamp')[:3]
        
        if len(sessions) < 3:
            return {
                'baseline_mean': None,
                'baseline_sd': None,
                'session_count': len(sessions),
                'established': False
            }
        
        # Calculate baseline from first 3 sessions
        session_means = [s.mean_rt for s in sessions if s.mean_rt is not None]
        if not session_means:
            return {
                'baseline_mean': None,
                'baseline_sd': None,
                'session_count': 0,
                'established': False
            }
        
        baseline_mean = sum(session_means) / len(session_means)
        
        # Baseline SD is the average of the session SDs (only non-null values)
        session_sds = [s.std_dev for s in sessions if s.std_dev is not None]
        baseline_sd = sum(session_sds) / len(session_sds) if session_sds else 0
        
        return {
            'baseline_mean': baseline_mean,
            'baseline_sd': baseline_sd,
            'session_count': len(sessions),
            'established': True
        }

    def calculate_baseline_comparison(self):
        """
        Calculate how this session compares to user's baseline.
        Updates baseline fields and drift classification.
        """
        baseline = self.get_baseline_for_user(self.user)
        
        self.sessions_in_baseline = baseline['session_count']
        self.baseline_mean_at_time = baseline['baseline_mean']
        self.baseline_sd_at_time = baseline['baseline_sd']
        
        if not baseline['established']:
            self.drift_level = 'baseline_building'
            self.percent_change_from_baseline = None
            self.z_score = 0
            self.drift_score = None
            self.confidence_level = 'provisional'
            self.confidence_score = 0.5
            return
        
        # Calculate percent change from baseline
        if baseline['baseline_mean'] and baseline['baseline_mean'] > 0:
            self.percent_change_from_baseline = ((self.mean_rt - baseline['baseline_mean']) / baseline['baseline_mean']) * 100
        
        # Calculate z-score: (current_mean - baseline_mean) / baseline_sd
        if baseline['baseline_sd'] and baseline['baseline_sd'] > 0:
            self.z_score = (self.mean_rt - baseline['baseline_mean']) / baseline['baseline_sd']
        
        # Classify drift level
        self.classify_drift()
        
        # Calculate confidence
        self.calculate_confidence()

    def classify_drift(self):
        """
        Classify drift level based on percent change from baseline.
        - Stable: within ±5% of baseline
        - Mild Drift: >5% to 10% slower
        - Moderate Drift: >10% to 15% slower
        - Severe Drift: >15% slower
        """
        if self.baseline_mean_at_time is None:
            self.drift_level = 'baseline_building'
            return
        
        pct = self.percent_change_from_baseline or 0
        
        # Check if significantly faster (possible improvement)
        if pct < -10:
            self.drift_level = 'stable'  # Faster is good, mark as stable
        elif -5 <= pct <= 5:
            self.drift_level = 'stable'
        elif 5 < pct <= 10:
            self.drift_level = 'mild_drift'
        elif 10 < pct <= 15:
            self.drift_level = 'moderate_drift'
        else:  # > 15%
            self.drift_level = 'severe_drift'
        
        # Calculate drift score (0-100, higher = more drift)
        # Map percent change to score: 0% = 0, >20% = 100
        drift_percent = max(0, pct - 5) if pct > 5 else 0
        self.drift_score = min(100, drift_percent * 5)
        
        # Update legacy drift_status for compatibility
        drift_mapping = {
            'stable': 'stable',
            'mild_drift': 'warning',
            'moderate_drift': 'drifting',
            'severe_drift': 'critical',
            'baseline_building': 'stable'
        }
        self.drift_status = drift_mapping.get(self.drift_level, 'stable')

    def calculate_confidence(self):
        """
        Calculate confidence score based on session quality.
        Factors: flagged rate, valid trial count, baseline establishment.
        """
        base_confidence = 1.0
        
        # Reduce confidence for high flagged rate
        flagged_rate = self.flagged_trial_rate
        if flagged_rate > 30:
            base_confidence -= 0.3
        elif flagged_rate > 20:
            base_confidence -= 0.2
        elif flagged_rate > 10:
            base_confidence -= 0.1
        
        # Reduce confidence for low valid trial count
        if self.valid_trials < 15:
            base_confidence -= 0.2
        elif self.valid_trials < 18:
            base_confidence -= 0.1
        
        # Provisional if baseline not established
        if self.drift_level == 'baseline_building':
            base_confidence = min(base_confidence, 0.5)
            self.confidence_level = 'provisional'
        elif base_confidence >= 0.8:
            self.confidence_level = 'high'
        elif base_confidence >= 0.6:
            self.confidence_level = 'medium'
        else:
            self.confidence_level = 'low'
        
        self.confidence_score = max(0.1, base_confidence)

    def save(self, *args, **kwargs):
        """Auto-calculate baseline comparison before saving."""
        # Only calculate if not already calculated (avoid overwriting)
        if self.drift_level == 'baseline_building' or self.baseline_mean_at_time is None:
            self.calculate_baseline_comparison()
        super().save(*args, **kwargs)


class EyeRecord(models.Model):
    """
    Stores eye tracking data from computer vision module.
    Tracks blink patterns and eye state for drowsiness detection.
    Phase 3 - Eye Monitoring Module.
    """
    EYE_STATE_CHOICES = [
        ('normal', 'Normal'),
        ('fatigue', 'Fatigue'),
        ('eye_strain', 'Eye Strain'),
        ('drowsy', 'Drowsy'),
        ('looking_away', 'Looking Away'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='eye_records')
    timestamp = models.DateTimeField(default=timezone.now)
    
    # Eye metrics from OpenCV
    ear = models.FloatField(null=True, blank=True, help_text="Eye Aspect Ratio (0.0-0.3)")
    blink_count = models.PositiveIntegerField(default=0, help_text="Total blinks detected in session")
    blink_duration_avg = models.FloatField(null=True, blank=True, help_text="Average blink duration in ms")
    blink_rate = models.FloatField(null=True, blank=True, help_text="Blinks per minute")
    
    # Eye state and scoring
    eye_state = models.CharField(max_length=20, choices=EYE_STATE_CHOICES, default='normal')
    eye_score = models.FloatField(help_text="Computed eye fatigue/drowsiness score (0-100)")
    fatigue_flag = models.BooleanField(default=False, help_text="True if drowsiness detected")
    
    # Raw data storage
    ear_samples_json = models.TextField(blank=True, help_text="Recent EAR samples for trend analysis")
    
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Eye Record"
        verbose_name_plural = "Eye Records"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
        ]

    def __str__(self):
        return f"Eye Record - {self.user.username} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class HRVRecord(models.Model):
    """
    Stores heart rate variability data from physiological sensors.
    HRV is a key indicator of stress and cognitive load.
    Phase 4 - HRV Module (MAX30102 + Arduino).
    """
    STRESS_LEVEL_CHOICES = [
        ('relaxed', 'Relaxed'),
        ('normal', 'Normal'),
        ('mild_stress', 'Mild Stress'),
        ('moderate_stress', 'Moderate Stress'),
        ('high_stress', 'High Stress'),
        ('unstable', 'Unstable'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hrv_records')
    timestamp = models.DateTimeField(default=timezone.now)
    bpm = models.FloatField(help_text="Heart rate in beats per minute")
    sdnn = models.FloatField(help_text="SDNN - Standard deviation of NN intervals (ms)")
    ir_value = models.IntegerField(null=True, blank=True, help_text="Infrared sensor raw value from MAX30102")
    stress_level = models.CharField(max_length=20, choices=STRESS_LEVEL_CHOICES, default='normal')
    hrv_score = models.FloatField(null=True, blank=True, help_text="Computed HRV-based stress/fatigue score (0-100)")
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "HRV Record"
        verbose_name_plural = "HRV Records"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
        ]

    def __str__(self):
        return f"HRV Record - {self.user.username} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class WarningLog(models.Model):
    """
    Stores cognitive drift warnings and alerts.
    Tracks when warnings were triggered and their acknowledgment status.
    """
    WARNING_LEVEL_CHOICES = [
        ('info', 'Info'),
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    TRIGGER_SOURCE_CHOICES = [
        ('reaction', 'Reaction Test'),
        ('eye', 'Eye Tracking'),
        ('hrv', 'HRV Sensor'),
        ('combined', 'Combined Analysis'),
        ('manual', 'Manual Trigger'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='warning_logs')
    timestamp = models.DateTimeField(default=timezone.now)
    warning_level = models.CharField(max_length=10, choices=WARNING_LEVEL_CHOICES)
    warning_message = models.TextField()
    trigger_source = models.CharField(max_length=20, choices=TRIGGER_SOURCE_CHOICES)
    acknowledged = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Warning Log"
        verbose_name_plural = "Warning Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['acknowledged']),
        ]

    def __str__(self):
        return f"Warning [{self.warning_level}] - {self.user.username} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class GoalRecord(models.Model):
    """
    Stores daily study goals and their completion status.
    Links goals to user productivity tracking.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='goal_records')
    date = models.DateField()
    goal_title = models.CharField(max_length=255)
    target_value = models.FloatField(help_text="Target value (e.g., study hours, tasks)")
    achieved_value = models.FloatField(default=0)
    completion_percent = models.FloatField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    class Meta:
        verbose_name = "Goal Record"
        verbose_name_plural = "Goal Records"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['user', '-date']),
        ]

    def __str__(self):
        return f"Goal - {self.user.username} - {self.goal_title} ({self.date})"

    def save(self, *args, **kwargs):
        if self.target_value > 0:
            self.completion_percent = min(100, (self.achieved_value / self.target_value) * 100)
        if self.completion_percent >= 100:
            self.status = 'completed'
        elif self.completion_percent > 0:
            self.status = 'in_progress'
        super().save(*args, **kwargs)


class PomodoroSession(models.Model):
    """
    Stores Pomodoro technique session data.
    Tracks focus and break periods for productivity analysis.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pomodoro_sessions')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    focus_minutes = models.PositiveIntegerField(default=25)
    break_minutes = models.PositiveIntegerField(default=5)
    completed = models.BooleanField(default=False)
    interruption_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Pomodoro Session"
        verbose_name_plural = "Pomodoro Sessions"
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['user', '-start_time']),
        ]

    def __str__(self):
        return f"Pomodoro - {self.user.username} - {self.start_time.strftime('%Y-%m-%d %H:%M')}"

    @property
    def duration_minutes(self):
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds() / 60
        return 0


class DistractionRecord(models.Model):
    """
    Records distractions encountered during study sessions.
    Used for pattern analysis and distraction management.
    """
    DISTRACTION_TYPE_CHOICES = [
        ('social_media', 'Social Media'),
        ('notification', 'Notification'),
        ('environment', 'Environment'),
        ('thought', 'Intrusive Thought'),
        ('physical', 'Physical Need'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='distraction_records')
    timestamp = models.DateTimeField(default=timezone.now)
    distraction_name = models.CharField(max_length=255)
    distraction_type = models.CharField(max_length=20, choices=DISTRACTION_TYPE_CHOICES, default='other')
    blocked_during_focus = models.BooleanField(default=False, help_text="Was the distraction blocked during focus period")
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Distraction Record"
        verbose_name_plural = "Distraction Records"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
        ]

    def __str__(self):
        return f"Distraction - {self.user.username} - {self.distraction_name}"

class FusionRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    reaction_score = models.FloatField(null=True, blank=True)
    eye_score = models.FloatField(null=True, blank=True)
    hrv_score = models.FloatField(null=True, blank=True)

    final_drift_score = models.FloatField(null=True, blank=True)

    confidence_level = models.CharField(max_length=20, null=True, blank=True)
    final_state = models.CharField(max_length=30, null=True, blank=True)

    trigger_reaction_test = models.BooleanField(default=False)

    intervention_message = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} - {self.final_state}"