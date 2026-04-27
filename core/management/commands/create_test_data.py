"""
Management command to create sample test data for dashboard testing.
Usage: python manage.py create_test_data
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from core.models import ReactionSession, EyeRecord, HRVRecord, DriftRecord


class Command(BaseCommand):
    help = 'Creates sample test data for dashboard testing'

    def handle(self, *args, **options):
        # Get or create test user
        user, created = User.objects.get_or_create(
            username='Grace',
            defaults={'email': 'grace@example.com'}
        )
        if created:
            user.set_password('test123')
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Created user: {user.username}'))
        else:
            self.stdout.write(f'Using existing user: {user.username}')

        # Create ReactionSession test data
        reaction = ReactionSession.objects.create(
            user=user,
            mean_rt=350.0,
            std_dev=45.0,
            variability=0.13,
            z_score=-0.5,
            drift_level='stable',
            drift_score=25.0,
            valid_trials=10,
            total_trials=12,
            false_starts=1,
            anticipations=1,
        )
        self.stdout.write(self.style.SUCCESS(f'Created ReactionSession: {reaction.mean_rt}ms, drift_level={reaction.drift_level}'))

        # Create EyeRecord test data
        eye = EyeRecord.objects.create(
            user=user,
            ear=0.28,
            blink_count=15,
            blink_duration_avg=180.0,
            blink_rate=18.0,
            eye_state='normal',
            eye_score=95.0,
            fatigue_flag=False,
        )
        self.stdout.write(self.style.SUCCESS(f'Created EyeRecord: {eye.blink_rate}/min, eye_state={eye.eye_state}'))

        # Create HRVRecord test data
        hrv = HRVRecord.objects.create(
            user=user,
            bpm=72,
            sdnn=45.0,
            stress_level='relaxed',
            hrv_score=85.0,
        )
        self.stdout.write(self.style.SUCCESS(f'Created HRVRecord: {hrv.bpm} BPM, stress_level={hrv.stress_level}'))

        # Create DriftRecord test data
        drift = DriftRecord.objects.create(
            user=user,
            reaction_score=75.0,
            eye_score=80.0,
            hrv_score=70.0,
            final_score=75.0,
            cognitive_state='focused',
            warning_level='none',
            reaction_triggered=False,
            confidence_score=0.85,
        )
        self.stdout.write(self.style.SUCCESS(f'Created DriftRecord: final_score={drift.final_score}, cognitive_state={drift.cognitive_state}'))

        # Print summary
        self.stdout.write(self.style.SUCCESS('\n=== Test Data Summary ==='))
        self.stdout.write(f'User: {user.username}')
        self.stdout.write(f'Reaction: mean_rt={reaction.mean_rt}, drift_level={reaction.drift_level}')
        self.stdout.write(f'eye: blink_rate={eye.blink_rate}, eye_state={eye.eye_state}')
        self.stdout.write(f'hrv: bpm={hrv.bpm}, stress_level={hrv.stress_level}')
        self.stdout.write(f'drift: final_score={drift.final_score}, drift_detected={drift.drift_detected}')