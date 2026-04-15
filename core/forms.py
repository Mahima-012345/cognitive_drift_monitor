# core/forms.py
"""
Forms for authentication and profile management.
Phase 1 - Core web foundation.
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile


class UserRegistrationForm(UserCreationForm):
    """Form for user registration with additional fields."""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email Address'
        })
    )
    full_name = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Full Name'
        })
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'full_name', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Username'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm Password'
        })

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.full_name = self.cleaned_data['full_name']
            profile.save()
        return user


class UserProfileForm(forms.ModelForm):
    """Form for updating user profile settings."""

    class Meta:
        model = UserProfile
        fields = [
            'full_name', 'age', 'study_start_time', 'study_end_time',
            'pomodoro_enabled', 'pomodoro_focus_minutes', 'pomodoro_break_minutes',
            'daily_goal', 'distraction_list', 'warning_enabled'
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full Name'
            }),
            'age': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Age'
            }),
            'study_start_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'study_end_time': forms.TimeInput(attrs={
                'class': 'form-control',
                'type': 'time'
            }),
            'pomodoro_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'pomodoro_focus_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '120'
            }),
            'pomodoro_break_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '60'
            }),
            'daily_goal': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Study 4 hours, Complete 3 chapters'
            }),
            'distraction_list': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': '4',
                'placeholder': 'Enter distractions, one per line\ne.g.,\nFacebook\nInstagram\nYouTube'
            }),
            'warning_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        focus_min = cleaned_data.get('pomodoro_focus_minutes', 25)
        break_min = cleaned_data.get('pomodoro_break_minutes', 5)
        if break_min >= focus_min:
            self.add_error('pomodoro_break_minutes', 'Break time should be less than focus time')
        return cleaned_data


class LoginForm(forms.Form):
    """Simple login form for authentication."""
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        })
    )


class ReactionSessionForm(forms.Form):
    """Form for saving reaction test results (placeholder for future sensor integration)."""
    mean_rt = forms.FloatField(min_value=0, required=True)
    std_rt = forms.FloatField(min_value=0, required=True)
    variability = forms.FloatField(min_value=0, required=True)
    z_score = forms.FloatField(required=True)
    valid_trials = forms.IntegerField(min_value=0, required=True)
    total_trials = forms.IntegerField(min_value=0, required=True)
    false_starts = forms.IntegerField(min_value=0, required=True)
    anticipations = forms.IntegerField(min_value=0, required=True)
    drift_status = forms.ChoiceField(choices=[
        ('stable', 'Stable'),
        ('warning', 'Warning'),
        ('drifting', 'Drifting'),
        ('critical', 'Critical'),
    ])
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))


class EyeRecordForm(forms.Form):
    """Form for saving eye tracking data from OpenCV module (Phase 3)."""
    ear = forms.FloatField(min_value=0, max_value=0.5, required=False)
    blink_count = forms.IntegerField(min_value=0, required=False, initial=0)
    blink_duration_avg = forms.FloatField(min_value=0, required=False)
    blink_rate = forms.FloatField(min_value=0, required=False)
    eye_state = forms.ChoiceField(choices=[
        ('normal', 'Normal'),
        ('fatigue', 'Fatigue'),
        ('eye_strain', 'Eye Strain'),
        ('drowsy', 'Drowsy'),
        ('looking_away', 'Looking Away'),
    ], required=False, initial='normal')
    eye_score = forms.FloatField(min_value=0, max_value=100, required=True)
    fatigue_flag = forms.BooleanField(required=False, initial=False)
    ear_samples = forms.CharField(required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))


class HRVRecordForm(forms.Form):
    """Form for saving HRV data (placeholder for future IoT integration)."""
    bpm = forms.FloatField(min_value=0, required=True)
    sdnn = forms.FloatField(min_value=0, required=True)
    stress_level = forms.ChoiceField(choices=[
        ('relaxed', 'Relaxed'),
        ('normal', 'Normal'),
        ('mild_stress', 'Mild Stress'),
        ('moderate_stress', 'Moderate Stress'),
        ('high_stress', 'High Stress'),
    ])
    hrv_score = forms.FloatField(min_value=0, max_value=100, required=True)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))
