"""
Monitoring Process Manager for Cognitive Drift Detection System.
Manages subprocesses for eye_tracker.py and hrv_bridge.py.
"""

import subprocess
import os
import sys
import threading
import time
import secrets

_processes = {}
_process_lock = threading.Lock()


def get_project_root():
    """Get the project root directory."""
    # monitoring_manager.py is in core/, project root is parent
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def generate_token():
    """Generate a secure monitoring token."""
    return secrets.token_hex(32)


def get_or_create_token(user):
    """Get or create monitoring token for user."""
    from core.models import UserProfile
    
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    if not profile.monitoring_token:
        profile.monitoring_token = generate_token()
        profile.save()
    
    return profile.monitoring_token


def is_process_running(username, process_name):
    """Check if a user's process is currently running."""
    key = f"{username}_{process_name}"
    with _process_lock:
        proc = _processes.get(key)
        if proc is None:
            return False
        if proc.poll() is not None:
            del _processes[key]
            return False
        return True


def get_user_monitoring_status(username):
    """Get the status of a specific user's monitoring processes."""
    eye_running = is_process_running(username, 'eye_tracker')
    hrv_running = is_process_running(username, 'hrv_bridge')
    
    if eye_running and hrv_running:
        status = 'running'
    elif eye_running or hrv_running:
        status = 'partial'
    else:
        status = 'stopped'
    
    return {
        'status': status,
        'eye_tracker': 'running' if eye_running else 'stopped',
        'hrv_bridge': 'running' if hrv_running else 'stopped',
    }


def start_monitoring_for_user(user, show_window=False):
    """Start eye and HRV tracking for a specific user using token auth."""
    username = user.username
    token = get_or_create_token(user)
    
    project_root = get_project_root()
    eye_tracker_path = os.path.join(project_root, 'eye_tracker.py')
    hrv_bridge_path = os.path.join(project_root, 'hrv_bridge.py')
    
    results = {'eye_tracker': None, 'hrv_bridge': None}
    
    # Start eye tracker
    if not is_process_running(username, 'eye_tracker'):
        try:
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            
            # Build command with optional window flag
            cmd = [sys.executable, eye_tracker_path, '--username', username, '--token', token]
            if show_window:
                cmd.append('--use-window')
            
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=project_root,
                text=True,
                bufsize=1
            )
            
            key = f"{username}_eye_tracker"
            with _process_lock:
                _processes[key] = proc
            
            results['eye_tracker'] = {'success': True, 'message': 'Eye tracker started'}
            
        except Exception as e:
            results['eye_tracker'] = {'success': False, 'error': str(e)}
    else:
        results['eye_tracker'] = {'success': False, 'error': 'Eye tracker already running for this user'}
    
    # Start HRV bridge
    if not is_process_running(username, 'hrv_bridge'):
        try:
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            
            proc = subprocess.Popen(
                [sys.executable, hrv_bridge_path, '--username', username, '--token', token],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=project_root,
                text=True,
                bufsize=1
            )
            
            key = f"{username}_hrv_bridge"
            with _process_lock:
                _processes[key] = proc
            
            results['hrv_bridge'] = {'success': True, 'message': 'HRV bridge started'}
            
        except Exception as e:
            results['hrv_bridge'] = {'success': False, 'error': str(e)}
    else:
        results['hrv_bridge'] = {'success': False, 'error': 'HRV bridge already running for this user'}
    
    status = get_user_monitoring_status(username)
    
    return {
        'success': status['status'] != 'stopped',
        'status': status,
        'results': results,
    }


def stop_monitoring_for_user(username):
    """Stop all monitoring processes for a specific user."""
    results = {'eye_tracker': None, 'hrv_bridge': None}
    
    # Stop eye tracker
    key = f"{username}_eye_tracker"
    with _process_lock:
        proc = _processes.get(key)
    
    if proc:
        try:
            proc.terminate()
            time.sleep(0.5)
            if proc.poll() is None:
                proc.kill()
            with _process_lock:
                if key in _processes:
                    del _processes[key]
            results['eye_tracker'] = {'success': True, 'message': 'Eye tracker stopped'}
        except Exception as e:
            results['eye_tracker'] = {'success': False, 'error': str(e)}
    
    # Stop HRV bridge
    key = f"{username}_hrv_bridge"
    with _process_lock:
        proc = _processes.get(key)
    
    if proc:
        try:
            proc.terminate()
            time.sleep(0.5)
            if proc.poll() is None:
                proc.kill()
            with _process_lock:
                if key in _processes:
                    del _processes[key]
            results['hrv_bridge'] = {'success': True, 'message': 'HRV bridge stopped'}
        except Exception as e:
            results['hrv_bridge'] = {'success': False, 'error': str(e)}
    
    status = get_user_monitoring_status(username)
    
    return {
        'success': True,
        'status': status,
        'results': results,
    }


# Legacy functions for backward compatibility
def start_eye_tracker(username, password):
    """Legacy function - not used."""
    return {'success': False, 'error': 'Use start_monitoring_for_user instead'}


def start_hrv_bridge(username, password):
    """Legacy function - not used."""
    return {'success': False, 'error': 'Use start_monitoring_for_user instead'}


def start_monitoring(username, password):
    """Legacy function - not used."""
    return {'success': False, 'error': 'Use start_monitoring_for_user instead'}


def stop_monitoring():
    """Legacy function - not used."""
    return {'success': False, 'error': 'Use stop_monitoring_for_user instead'}


def stop_eye_tracker():
    """Legacy function - not used."""
    return {'success': False, 'error': 'Use stop_monitoring_for_user instead'}


def stop_hrv_bridge():
    """Legacy function - not used."""
    return {'success': False, 'error': 'Use stop_monitoring_for_user instead'}


def get_monitoring_status():
    """Legacy function - returns empty status."""
    return {'status': 'stopped', 'eye_tracker': 'stopped', 'hrv_bridge': 'stopped'}