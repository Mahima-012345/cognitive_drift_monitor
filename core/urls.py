# core/urls.py
"""
URL routing for Cognitive Drift Detection System.
Phase 1 - Core web foundation.
Phase 2 - Reaction Time Module.
"""

from django.urls import path
from . import views

urlpatterns = [
    # Public pages
    path('', views.home, name='home'),
    
    # Authentication
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Protected pages
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('history/', views.history_view, name='history'),
    
    # Phase 2 - Reaction Test
    path('reaction-test/', views.reaction_test_view, name='reaction_test'),
    
    # Warning acknowledgment
    path('acknowledge-warning/<int:warning_id>/', views.acknowledge_warning, name='acknowledge_warning'),
    
    # API endpoints - GET (data retrieval)
    path('api/dashboard-summary/', views.api_dashboard_summary, name='api_dashboard_summary'),
    path('api/drift-records/', views.api_drift_records, name='api_drift_records'),
    path('api/reaction-records/', views.api_reaction_records, name='api_reaction_records'),
    path('api/eye-records/', views.api_eye_records, name='api_eye_records'),
    path('api/hrv-records/', views.api_hrv_records, name='api_hrv_records'),
    path('api/warnings/', views.api_warnings, name='api_warnings'),
    path('api/chart-data/', views.api_chart_data, name='api_chart_data'),
    
    # Phase 2 - Reaction Test APIs
    path('api/reaction-baseline/', views.api_reaction_baseline, name='api_reaction_baseline'),
    path('api/reaction-chart-data/', views.api_reaction_chart_data, name='api_reaction_chart_data'),
    path('api/save-reaction-session/', views.api_save_reaction_session, name='api_save_reaction_session'),
    
    # Legacy API endpoints
    path('api/save-reaction/', views.api_save_reaction, name='api_save_reaction'),
    path('api/save-eye/', views.api_save_eye, name='api_save_eye'),
    path('api/save-hrv/', views.api_save_hrv, name='api_save_hrv'),
    
    # Phase 4 - HRV Bridge API (used by hrv_bridge.py)
    path('api/hrv-bridge-login/', views.api_hrv_bridge_login, name='api_hrv_bridge_login'),
    path('api/hrv-bridge/', views.api_hrv_bridge, name='api_hrv_bridge'),


    #Phase 5 - Fusion
    path('fusion/', views.run_fusion, name='fusion'),
    
    # Phase 6 Part 1 - Smart Validation Engine
    path('api/evaluate-drift/', views.api_evaluate_suspected_drift, name='api_evaluate_drift'),
    path('api/validate-reaction/', views.api_validate_reaction_confirmation, name='api_validate_reaction'),
    path('api/validation-status/', views.api_validation_status, name='api_validation_status'),
    
    # Phase 8 - Productivity & Behavior Layer
    path('api/start-pomodoro/', views.api_start_pomodoro, name='api_start_pomodoro'),
    path('api/complete-pomodoro/', views.api_complete_pomodoro, name='api_complete_pomodoro'),
    path('goal-settings/', views.goal_settings, name='goal_settings'),
    path('api/add-goal/', views.api_add_goal, name='api_add_goal'),
    path('api/complete-goal/<int:goal_id>/', views.api_complete_goal, name='api_complete_goal'),
    path('api/log-distraction/', views.api_log_distraction, name='api_log_distraction'),
]
