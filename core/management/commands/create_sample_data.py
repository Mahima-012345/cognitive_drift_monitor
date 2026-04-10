# core/management/commands/create_sample_data.py
"""
Management command to create sample data for testing and demonstration.
Phase 1 - Core web foundation.

Usage:
    python manage.py create_sample_data
    python manage.py create_sample_data --user username
    python manage.py create_sample_data --days 14
"""

import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from core.models import (
    UserProfile, DriftRecord, ReactionSession, EyeRecord,
    HRVRecord, WarningLog, GoalRecord, PomodoroSession, DistractionRecord
)


class Command(BaseCommand):
    help = 'Creates sample data for testing the Cognitive Drift Detection System'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Username to create data for (creates demo user if not exists)'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days of data to create (default: 7)'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing sample data before creating new'
        )

    def handle(self, *args, **options):
        username = options['user'] or 'demo_user'
        days = options['days']
        clear = options['clear']

        # Create or get user
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': f'{username}@example.com',
            }
        )
        
        if created:
            user.set_password('demo123')
            user.save()
            self.stdout.write(f'Created demo user: {username} (password: demo123)')
        else:
            self.stdout.write(f'Using existing user: {username}')

        # Get or create profile
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'full_name': 'Demo Student',
                'age': 21,
                'study_start_time': '09:00',
                'study_end_time': '18:00',
                'pomodoro_enabled': True,
                'pomodoro_focus_minutes': 25,
                'pomodoro_break_minutes': 5,
                'daily_goal': 'Study 6 hours, complete 3 chapters',
                'distraction_list': 'Facebook\nInstagram\nYouTube\nTwitter',
                'warning_enabled': True,
            }
        )

        if clear:
            self.stdout.write('Clearing existing data...')
            DriftRecord.objects.filter(user=user).delete()
            ReactionSession.objects.filter(user=user).delete()
            EyeRecord.objects.filter(user=user).delete()
            HRVRecord.objects.filter(user=user).delete()
            WarningLog.objects.filter(user=user).delete()
            GoalRecord.objects.filter(user=user).delete()
            PomodoroSession.objects.filter(user=user).delete()
            DistractionRecord.objects.filter(user=user).delete()

        self.stdout.write(f'Creating {days} days of sample data...')
        
        now = timezone.now()
        
        # Create historical data
        for day in range(days, 0, -1):
            day_start = now - timedelta(days=day)
            
            # Create 3-5 drift records per day
            records_per_day = random.randint(3, 5)
            for i in range(records_per_day):
                record_time = day_start + timedelta(hours=random.randint(9, 17), minutes=random.randint(0, 59))
                
                # Generate realistic scores
                reaction_score = random.uniform(15, 75)
                eye_score = random.uniform(10, 80)
                hrv_score = random.uniform(20, 70)
                final_score = (reaction_score + eye_score + hrv_score) / 3
                
                # Determine cognitive state based on score
                if final_score < 25:
                    cognitive_state = 'focused'
                    warning_level = 'none'
                elif final_score < 40:
                    cognitive_state = 'mild_drift'
                    warning_level = 'low'
                elif final_score < 60:
                    cognitive_state = 'moderate_drift'
                    warning_level = 'medium'
                else:
                    cognitive_state = 'severe_drift'
                    warning_level = 'high'
                
                drift = DriftRecord.objects.create(
                    user=user,
                    timestamp=record_time,
                    reaction_score=round(reaction_score, 1),
                    eye_score=round(eye_score, 1),
                    hrv_score=round(hrv_score, 1),
                    final_score=round(final_score, 1),
                    cognitive_state=cognitive_state,
                    warning_level=warning_level,
                    reaction_triggered=random.choice([True, False]),
                    confidence_score=round(random.uniform(0.7, 0.95), 2),
                )
                
                # Create reaction session
                ReactionSession.objects.create(
                    user=user,
                    timestamp=record_time,
                    mean_rt=round(random.uniform(250, 450), 1),
                    std_rt=round(random.uniform(20, 80), 1),
                    variability=round(random.uniform(0.1, 0.5), 2),
                    z_score=round(random.uniform(-1, 1.5), 2),
                    valid_trials=random.randint(15, 25),
                    total_trials=random.randint(20, 30),
                    false_starts=random.randint(0, 3),
                    anticipations=random.randint(0, 2),
                    drift_status=['stable', 'stable', 'warning', 'drifting'][random.randint(0, 3)],
                )
                
                # Create eye record
                eye_states = ['open', 'open', 'open', 'closed', 'drowsy', 'looking_away']
                EyeRecord.objects.create(
                    user=user,
                    timestamp=record_time,
                    blink_rate=round(random.uniform(10, 25), 1),
                    blink_duration=round(random.uniform(100, 350), 0),
                    eye_state=random.choice(eye_states),
                    eye_score=round(eye_score, 1),
                )
                
                # Create HRV record
                stress_levels = ['relaxed', 'normal', 'normal', 'mild_stress']
                HRVRecord.objects.create(
                    user=user,
                    timestamp=record_time,
                    bpm=round(random.uniform(60, 95), 0),
                    sdnn=round(random.uniform(30, 80), 1),
                    stress_level=random.choice(stress_levels),
                    hrv_score=round(hrv_score, 1),
                )
                
                # Create warnings for higher drift levels
                if warning_level in ['medium', 'high']:
                    WarningLog.objects.create(
                        user=user,
                        timestamp=record_time,
                        warning_level=warning_level,
                        warning_message=f"Cognitive drift detected: {cognitive_state.replace('_', ' ').title()}",
                        trigger_source=random.choice(['reaction', 'eye', 'hrv', 'combined']),
                        acknowledged=random.choice([True, False]),
                    )
        
        # Create today's data with more variety
        today_records = random.randint(3, 8)
        for i in range(today_records):
            record_time = now - timedelta(minutes=random.randint(10, 240))
            
            reaction_score = random.uniform(15, 85)
            eye_score = random.uniform(10, 85)
            hrv_score = random.uniform(20, 75)
            final_score = (reaction_score + eye_score + hrv_score) / 3
            
            if final_score < 25:
                cognitive_state = 'focused'
                warning_level = 'none'
            elif final_score < 40:
                cognitive_state = 'mild_drift'
                warning_level = 'low'
            elif final_score < 60:
                cognitive_state = 'moderate_drift'
                warning_level = 'medium'
            else:
                cognitive_state = 'severe_drift'
                warning_level = 'high'
            
            DriftRecord.objects.create(
                user=user,
                timestamp=record_time,
                reaction_score=round(reaction_score, 1),
                eye_score=round(eye_score, 1),
                hrv_score=round(hrv_score, 1),
                final_score=round(final_score, 1),
                cognitive_state=cognitive_state,
                warning_level=warning_level,
                reaction_triggered=random.choice([True, False]),
                confidence_score=round(random.uniform(0.7, 0.95), 2),
            )
            
            ReactionSession.objects.create(
                user=user,
                timestamp=record_time,
                mean_rt=round(random.uniform(250, 500), 1),
                std_rt=round(random.uniform(20, 100), 1),
                variability=round(random.uniform(0.1, 0.6), 2),
                z_score=round(random.uniform(-1.5, 2), 2),
                valid_trials=random.randint(15, 25),
                total_trials=random.randint(20, 30),
                false_starts=random.randint(0, 3),
                anticipations=random.randint(0, 2),
                drift_status=['stable', 'warning', 'drifting', 'critical'][random.randint(0, 3)],
            )
            
            EyeRecord.objects.create(
                user=user,
                timestamp=record_time,
                blink_rate=round(random.uniform(8, 30), 1),
                blink_duration=round(random.uniform(100, 400), 0),
                eye_state=random.choice(['open', 'closed', 'drowsy', 'looking_away']),
                eye_score=round(eye_score, 1),
            )
            
            HRVRecord.objects.create(
                user=user,
                timestamp=record_time,
                bpm=round(random.uniform(55, 100), 0),
                sdnn=round(random.uniform(25, 90), 1),
                stress_level=random.choice(['relaxed', 'normal', 'mild_stress', 'moderate_stress']),
                hrv_score=round(hrv_score, 1),
            )
        
        # Create today's warnings
        for _ in range(random.randint(1, 3)):
            WarningLog.objects.create(
                user=user,
                timestamp=now - timedelta(hours=random.randint(1, 5)),
                warning_level=random.choice(['low', 'medium', 'high']),
                warning_message=random.choice([
                    'Increased reaction time variability detected',
                    'Eye fatigue signs detected',
                    'HRV indicates elevated stress levels',
                    'Combined analysis suggests mild cognitive drift',
                    'Consider taking a short break'
                ]),
                trigger_source=random.choice(['reaction', 'eye', 'hrv', 'combined']),
                acknowledged=random.choice([True, False]),
            )
        
        # Create goal records
        for day_offset in range(days):
            date = (now - timedelta(days=day_offset)).date()
            GoalRecord.objects.get_or_create(
                user=user,
                date=date,
                defaults={
                    'goal_title': f'Study Session {days - day_offset}',
                    'target_value': 4.0,
                    'achieved_value': round(random.uniform(2, 5), 1),
                }
            )
        
        # Create pomodoro sessions
        for _ in range(random.randint(3, 8)):
            start = now - timedelta(hours=random.randint(1, 8))
            PomodoroSession.objects.create(
                user=user,
                start_time=start,
                end_time=start + timedelta(minutes=random.randint(20, 30)),
                focus_minutes=random.choice([25, 25, 30]),
                break_minutes=random.choice([5, 5, 10]),
                completed=random.choice([True, True, False]),
                interruption_count=random.randint(0, 3),
            )
        
        # Create distraction records
        distractions = [
            ('Facebook', 'social_media'),
            ('Instagram', 'social_media'),
            ('YouTube', 'social_media'),
            ('Email notification', 'notification'),
            ('Phone call', 'notification'),
            ('Noise outside', 'environment'),
            ('Daydreaming', 'thought'),
            ('Hunger', 'physical'),
            ('Slack message', 'notification'),
        ]
        
        for _ in range(random.randint(5, 12)):
            DistractionRecord.objects.create(
                user=user,
                timestamp=now - timedelta(hours=random.randint(1, 10)),
                distraction_name=random.choice(distractions)[0],
                distraction_type=random.choice(distractions)[1],
                blocked_during_focus=random.choice([True, True, False]),
            )
        
        # Summary
        self.stdout.write(self.style.SUCCESS(f'\nSample data created successfully!'))
        self.stdout.write(f'\nData Summary for {username}:')
        self.stdout.write(f'  - Drift Records: {DriftRecord.objects.filter(user=user).count()}')
        self.stdout.write(f'  - Reaction Sessions: {ReactionSession.objects.filter(user=user).count()}')
        self.stdout.write(f'  - Eye Records: {EyeRecord.objects.filter(user=user).count()}')
        self.stdout.write(f'  - HRV Records: {HRVRecord.objects.filter(user=user).count()}')
        self.stdout.write(f'  - Warning Logs: {WarningLog.objects.filter(user=user).count()}')
        self.stdout.write(f'  - Goal Records: {GoalRecord.objects.filter(user=user).count()}')
        self.stdout.write(f'  - Pomodoro Sessions: {PomodoroSession.objects.filter(user=user).count()}')
        self.stdout.write(f'  - Distraction Records: {DistractionRecord.objects.filter(user=user).count()}')
        self.stdout.write(f'\nLogin credentials:')
        self.stdout.write(f'  Username: {username}')
        self.stdout.write(f'  Password: demo123')
