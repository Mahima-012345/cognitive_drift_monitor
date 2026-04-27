# core/admin.py
"""
Django admin configuration for Cognitive Drift Detection System.
Phase 1 - Core web foundation.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import (
    UserProfile, DriftRecord, ReactionSession, EyeRecord,
    HRVRecord, WarningLog, GoalRecord, PomodoroSession, DistractionRecord
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['username', 'full_name', 'age', 'pomodoro_enabled', 'warning_enabled', 'created_at']
    list_filter = ['pomodoro_enabled', 'warning_enabled', 'created_at']
    search_fields = ['user__username', 'full_name', 'user__email']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']

    def username(self, obj):
        return obj.user.username
    username.short_description = 'Username'


@admin.register(DriftRecord)
class DriftRecordAdmin(admin.ModelAdmin):
    list_display = ['user', 'timestamp', 'final_score_display', 'cognitive_state', 'warning_level_display', 'reaction_triggered']
    list_filter = ['cognitive_state', 'warning_level', 'reaction_triggered', 'timestamp']
    search_fields = ['user__username']
    ordering = ['-timestamp']
    readonly_fields = ['timestamp', 'final_score']

    def final_score_display(self, obj):
        if obj.final_score is not None:
            color = 'green' if obj.final_score < 30 else ('orange' if obj.final_score < 60 else 'red')
            return mark_safe(f'<span style="color: {color};">{obj.final_score:.1f}</span>')
        return '-'
    final_score_display.short_description = 'Final Score'

    def warning_level_display(self, obj):
        if obj.warning_level:
            colors = {'none': 'gray', 'low': 'blue', 'medium': 'orange', 'high': 'red', 'critical': 'darkred'}
            return mark_safe(f'<span style="color: {colors.get(obj.warning_level, "black")};">{obj.warning_level.title()}</span>')
        return '-'
    warning_level_display.short_description = 'Warning'


@admin.register(ReactionSession)
class ReactionSessionAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'timestamp', 'mean_rt', 'valid_trials', 'total_trials',
        'drift_level', 'confidence_score'
    ]
    list_filter = ['drift_level', 'confidence_level', 'timestamp']
    search_fields = ['user__username', 'notes']
    ordering = ['-timestamp']
    readonly_fields = ['timestamp']
    
    fieldsets = (
        ('User & Time', {
            'fields': ('user', 'timestamp')
        }),
        ('Core Statistics', {
            'fields': ('mean_rt', 'std_dev', 'variability', 'z_score')
        }),
        ('Trial Counts', {
            'fields': ('valid_trials', 'total_trials', 'false_starts', 'anticipations')
        }),
        ('Baseline Comparison', {
            'fields': ('baseline_mean_at_time', 'baseline_sd_at_time', 'sessions_in_baseline', 'percent_change_from_baseline')
        }),
        ('Drift & Confidence', {
            'fields': ('drift_score', 'drift_level', 'confidence_score', 'confidence_level')
        }),
        ('Additional', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )

    def drift_level_display(self, obj):
        colors = {
            'baseline_building': 'gray',
            'stable': 'green',
            'mild_drift': 'orange',
            'moderate_drift': 'darkorange',
            'severe_drift': 'red'
        }
        color = colors.get(obj.drift_level, 'black')
        return mark_safe(f'<span style="color: {color};">{obj.get_drift_level_display()}</span>')
    drift_level_display.short_description = 'Drift Level'

    def baseline_info(self, obj):
        if obj.baseline_mean_at_time:
            pct = obj.percent_change_from_baseline
            sign = '+' if pct and pct > 0 else ''
            pct_str = f"{pct:.1f}" if pct is not None else "0.0"
            return f"vs {obj.baseline_mean_at_time:.0f}ms ({sign}{pct_str}%)"
        return 'Building baseline'
    baseline_info.short_description = 'vs Baseline'

    def confidence_display(self, obj):
        if obj.confidence_score is None:
            return mark_safe('<span style="color: gray;">No data</span>')
        score = float(obj.confidence_score)
        colors = {'high': 'green', 'medium': 'orange', 'low': 'red', 'provisional': 'gray'}
        level = obj.confidence_level if obj.confidence_level else 'unknown'
        return mark_safe(f'<span style="color: {colors.get(level, "black")};">{score:.0%} ({level})</span>')
    confidence_display.short_description = 'Confidence'

    def accuracy_display(self, obj):
        acc = obj.accuracy
        color = 'green' if acc > 80 else ('orange' if acc > 50 else 'red')
        return mark_safe(f'<span style="color: {color};">{acc:.1f}%</span>')
    accuracy_display.short_description = 'Accuracy'


@admin.register(EyeRecord)
class EyeRecordAdmin(admin.ModelAdmin):
    list_display = ['user', 'timestamp', 'ear_display', 'blink_count', 'blink_rate_display', 'eye_state_display', 'eye_score_display']
    list_filter = ['eye_state', 'fatigue_flag', 'timestamp']
    search_fields = ['user__username']
    ordering = ['-timestamp']
    readonly_fields = ['timestamp']

    def ear_display(self, obj):
        if obj.ear is not None:
            try:
                return f"{float(obj.ear):.3f}"
            except (ValueError, TypeError):
                return '-'
        return '-'
    ear_display.short_description = 'EAR'

    def blink_rate_display(self, obj):
        if obj.blink_rate is not None:
            try:
                return f"{float(obj.blink_rate):.1f}/min"
            except (ValueError, TypeError):
                return '-'
        return '-'
    blink_rate_display.short_description = 'Blink Rate'

    def _state_color(self, obj):
        state = obj.eye_state
        if state == 'focused':
            return 'green'
        elif state == 'drowsy':
            return 'red'
        elif state == 'distracted':
            return 'orange'
        return 'gray'

    def eye_state_display(self, obj):
        color = self._state_color(obj)
        state_name = obj.get_eye_state_display() if obj.eye_state else 'Unknown'
        return mark_safe(f'<span style="color: {color};">{state_name}</span>')
    eye_state_display.short_description = 'State'

    def eye_score_display(self, obj):
        if obj.eye_score is not None:
            if obj.eye_score >= 60:
                color = 'green'
            elif obj.eye_score >= 40:
                color = 'orange'
            else:
                color = 'red'
            return mark_safe(f'<span style="color: {color};">{obj.eye_score:.0f}</span>')
        return mark_safe('<span style="color: gray;">-</span>')
    eye_score_display.short_description = 'Eye Score'


@admin.register(HRVRecord)
class HRVRecordAdmin(admin.ModelAdmin):
    list_display = ['user', 'timestamp', 'bpm', 'sdnn', 'ir_value', 'stress_level', 'hrv_score_display']
    list_filter = ['stress_level', 'timestamp']
    search_fields = ['user__username']
    ordering = ['-timestamp']
    readonly_fields = ['timestamp']

    def hrv_score_display(self, obj):
        try:
            score_val = obj.hrv_score
            if score_val is None:
                return mark_safe('<span style="color: gray;">-</span>')
            score = float(str(score_val))
            if score >= 60:
                color = 'green'
            elif score >= 40:
                color = 'orange'
            else:
                color = 'red'
            return mark_safe(f'<span style="color: {color};">{score:.1f}</span>')
        except (ValueError, TypeError):
            return mark_safe('<span style="color: gray;">err</span>')
    hrv_score_display.short_description = 'HRV Score'


@admin.register(WarningLog)
class WarningLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'timestamp', 'warning_level_display', 'trigger_source', 'acknowledged']
    list_filter = ['warning_level', 'acknowledged', 'trigger_source', 'timestamp']
    search_fields = ['user__username', 'warning_message']
    ordering = ['-timestamp']
    readonly_fields = ['timestamp']

    def warning_level_display(self, obj):
        colors = {'info': 'blue', 'low': 'green', 'medium': 'orange', 'high': 'red', 'critical': 'darkred'}
        return mark_safe(f'<span style="color: {colors.get(obj.warning_level, "black")};">{obj.warning_level.title()}</span>')
    warning_level_display.short_description = 'Level'


@admin.register(GoalRecord)
class GoalRecordAdmin(admin.ModelAdmin):
    list_display = ['user', 'date', 'goal_title', 'completion_display', 'status']
    list_filter = ['status', 'date']
    search_fields = ['user__username', 'goal_title']
    ordering = ['-date']
    readonly_fields = ['completion_percent']

    def completion_display(self, obj):
        color = 'green' if obj.completion_percent >= 100 else ('orange' if obj.completion_percent > 50 else 'red')
        return mark_safe(f'<span style="color: {color};">{obj.completion_percent:.1f}%</span>')
    completion_display.short_description = 'Completion'


@admin.register(PomodoroSession)
class PomodoroSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'start_time', 'end_time', 'focus_minutes', 'break_minutes', 'completed', 'interruption_count']
    list_filter = ['completed', 'start_time']
    search_fields = ['user__username']
    ordering = ['-start_time']


@admin.register(DistractionRecord)
class DistractionRecordAdmin(admin.ModelAdmin):
    list_display = ['user', 'timestamp', 'distraction_name', 'distraction_type', 'blocked_during_focus']
    list_filter = ['distraction_type', 'blocked_during_focus', 'timestamp']
    search_fields = ['user__username', 'distraction_name']
    ordering = ['-timestamp']
    readonly_fields = ['timestamp']
