"""
Phase 7: Warning and Intervention System
Warning level definitions, messages, and suggestions.
"""

WARNING_MESSAGES = {
    'level_1': {
        'level': 1,
        'level_name': 'Level 1',
        'color': 'info',
        'badge_class': 'bg-info',
        'title': 'Mild Drift',
        'message': 'You seem slightly distracted.',
        'suggestions': [
            'Stay focused.',
            'Check your posture.',
            'Take a short breathing pause.',
        ],
    },
    'level_2': {
        'level': 2,
        'level_name': 'Level 2',
        'color': 'warning',
        'badge_class': 'bg-warning text-dark',
        'title': 'Moderate Drift',
        'message': 'You may be showing signs of fatigue.',
        'suggestions': [
            'Take a 5-10 minute break.',
            'Drink water and stretch.',
            'Avoid multitasking.',
        ],
    },
    'level_3': {
        'level': 3,
        'level_name': 'Level 3',
        'color': 'danger',
        'badge_class': 'bg-danger',
        'title': 'Confirmed Drift',
        'message': 'Cognitive fatigue detected.',
        'suggestions': [
            'Please stop the session briefly.',
            'Take rest before continuing.',
            'Retake the reaction test after a break.',
        ],
    },
    'level_4': {
        'level': 4,
        'level_name': 'Level 4',
        'color': 'dark',
        'badge_class': 'bg-dark',
        'title': 'Chronic Drift',
        'message': 'Persistent decline detected across multiple sessions.',
        'suggestions': [
            'Improve sleep and workload balance.',
            'Reduce long continuous study sessions.',
            'Consider speaking with a mentor or health professional if this continues.',
        ],
    },
}

DRIFT_LEVEL_MAPPING = {
    'focused': 0,
    'stable': 0,
    'normal': 0,
    'mild_drift': 1,
    'mild': 1,
    'moderate_drift': 2,
    'moderate': 2,
    'confirmed_drift': 3,
    'confirmed': 3,
    'severe_drift': 3,
    'severe': 3,
}

def get_warning_level_from_state(cognitive_state):
    """Map cognitive state to warning level."""
    state_lower = cognitive_state.lower() if cognitive_state else 'normal'
    return DRIFT_LEVEL_MAPPING.get(state_lower, 0)

def get_warning_info(level):
    """Get warning info dictionary for a given level."""
    level_key = f'level_{level}' if level > 0 else None
    if level_key and level_key in WARNING_MESSAGES:
        return WARNING_MESSAGES[level_key]
    return None

def should_show_popup(level):
    """Determine if popup should be shown for this level."""
    return level >= 2

def get_badge_class(level):
    """Get Bootstrap badge class for warning level."""
    if level == 1:
        return 'bg-info'
    elif level == 2:
        return 'bg-warning text-dark'
    elif level == 3:
        return 'bg-danger'
    elif level >= 4:
        return 'bg-dark'
    return 'bg-secondary'

def get_level_display_name(level):
    """Get display name for warning level."""
    if level == 1:
        return 'Level 1'
    elif level == 2:
        return 'Level 2'
    elif level == 3:
        return 'Level 3'
    elif level >= 4:
        return 'Level 4'
    return 'Info'