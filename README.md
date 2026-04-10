# Cognitive Drift Detection System

## Early Cognitive Drift Detection using Behavioural, Physiological Signals and Computer Vision

**MCA Final Year Project - Phase 1**

---

## Project Overview

This is Phase 1 of a Django-based student focus monitoring system. Phase 1 establishes the core web foundation, authentication, database models, and dashboard infrastructure. Future phases will integrate ML models, OpenCV for eye tracking, and IoT sensors for HRV monitoring.

### Key Features (Phase 1)

- User authentication (signup, login, logout)
- User profile with study preferences
- 9 database models for cognitive drift tracking
- Dashboard with real-time data visualization
- REST API endpoints for future module integration
- AJAX auto-refresh framework
- Customizable Django admin panel

---

## Technology Stack

- **Backend**: Django 4.2+ (Python 3.10+)
- **Database**: SQLite
- **Frontend**: HTML5, CSS3, Bootstrap 5.3
- **Charts**: Chart.js 4.4
- **Authentication**: Django built-in auth system
- **JavaScript**: Vanilla JS with fetch API

---

## Project Structure

```
cognitive_drift_monitor/
├── cognitive_drift_monitor/    # Django project settings
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── manage.py
├── core/                        # Main application
│   ├── models.py               # 9 database models
│   ├── views.py                # All views and API endpoints
│   ├── urls.py                 # URL routing
│   ├── forms.py                # Form classes
│   ├── admin.py                # Customized admin
│   ├── signals.py              # Auto profile creation
│   ├── apps.py
│   ├── management/commands/     # Sample data command
│   │   └── create_sample_data.py
│   ├── migrations/
│   └── templates/core/         # HTML templates
│       ├── home.html
│       ├── login.html
│       ├── signup.html
│       ├── dashboard.html
│       ├── profile.html
│       └── history.html
├── static/                     # Static files
│   ├── css/style.css
│   └── js/dashboard.js
├── templates/                  # Base template
│   └── base.html
├── media/                      # User uploads (created if needed)
├── db.sqlite3                   # Database (created after migration)
└── README.md
```

---

## Setup Instructions

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)

### Step 1: Create Virtual Environment

```bash
cd cognitive_drift_monitor
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

### Step 2: Install Dependencies

```bash
pip install django
```

### Step 3: Run Migrations

```bash
cd cognitive_drift_monitor
python manage.py makemigrations core
python manage.py migrate
```

### Step 4: Create Superuser (Admin)

```bash
python manage.py createsuperuser
# Follow prompts to create admin account
```

### Step 5: Create Sample Data (Optional but Recommended)

```bash
# Create demo user with sample data
python manage.py create_sample_data

# Options:
# --user username    Specify username (default: demo_user)
# --days 14          Number of days of data (default: 7)
# --clear            Clear existing data before creating new
```

### Step 6: Run Development Server

```bash
python manage.py runserver
```

The server will start at: **http://127.0.0.1:8000/**

---

## Testing the Application

### Login Credentials

**Demo User (created with sample data):**
- Username: `demo_user`
- Password: `demo123`

**Admin User (created with createsuperuser):**
- Username: (your choice)
- Password: (your choice)

### Test URLs

| URL | Description |
|-----|-------------|
| `/` | Landing page |
| `/signup/` | User registration |
| `/login/` | User login |
| `/logout/` | User logout |
| `/dashboard/` | Main dashboard (requires login) |
| `/profile/` | User settings (requires login) |
| `/history/` | Records history (requires login) |
| `/admin/` | Django admin panel |

### Test API Endpoints

All API endpoints require authentication. Use browser dev tools or curl:

```bash
# Get dashboard summary (logged in)
curl http://127.0.0.1:8000/api/dashboard-summary/

# Get drift records
curl http://127.0.0.1:8000/api/drift-records/

# Get chart data
curl http://127.0.0.1:8000/api/chart-data/?days=7

# Get warnings
curl http://127.0.0.1:8000/api/warnings/

# Get reaction records
curl http://127.0.0.1:8000/api/reaction-records/

# Get eye records
curl http://127.0.0.1:8000/api/eye-records/

# Get HRV records
curl http://127.0.0.1:8000/api/hrv-records/
```

### Testing POST Endpoints (Placeholder)

```bash
# Test saving reaction data (placeholder for Phase 2)
curl -X POST http://127.0.0.1:8000/api/save-reaction/ \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: YOUR_CSRF_TOKEN" \
  -d '{
    "mean_rt": 320.5,
    "std_rt": 45.2,
    "variability": 0.25,
    "z_score": 0.5,
    "valid_trials": 20,
    "total_trials": 25,
    "false_starts": 2,
    "anticipations": 1,
    "drift_status": "stable"
  }'
```

---

## Database Models

### A. UserProfile
Extended user profile with study preferences and settings.

### B. DriftRecord
Cognitive drift analysis combining reaction, eye, and HRV scores.

### C. ReactionSession
Reaction time test session data.

### D. EyeRecord
Eye tracking data from computer vision (future).

### E. HRVRecord
Heart rate variability data from sensors (future).

### F. WarningLog
Cognitive drift warnings and alerts.

### G. GoalRecord
Daily study goals and completion tracking.

### H. PomodoroSession
Pomodoro technique session data.

### I. DistractionRecord
Distractions encountered during study.

---

## Future Phases

### Phase 2: Reaction Time Module
- Interactive reaction time test
- Real-time score calculation
- Sensor integration

### Phase 3: Computer Vision Module
- Eye tracking with OpenCV
- Drowsiness detection
- Looking-away detection

### Phase 4: IoT/Physiological Module
- HRV sensor integration
- Real-time stress monitoring
- Bluetooth/wifi connectivity

### Phase 5: ML Integration
- Machine learning model for drift prediction
- Personal baseline comparison
- Alert system

---

## API Documentation

### GET Endpoints

| Endpoint | Description | Parameters |
|----------|-------------|------------|
| `/api/dashboard-summary/` | Summary data for dashboard | None |
| `/api/drift-records/` | List of drift records | `limit` (default 20) |
| `/api/reaction-records/` | List of reaction sessions | `limit` (default 20) |
| `/api/eye-records/` | List of eye records | `limit` (default 20) |
| `/api/hrv-records/` | List of HRV records | `limit` (default 20) |
| `/api/warnings/` | List of warnings | `limit`, `unacknowledged` |
| `/api/chart-data/` | Chart data for graphs | `days` (default 7) |

### POST Endpoints (Placeholders)

| Endpoint | Description |
|----------|-------------|
| `/api/save-reaction/` | Save reaction test results |
| `/api/save-eye/` | Save eye tracking data |
| `/api/save-hrv/` | Save HRV sensor data |

---

## Extending the Project

### Adding New Pages

1. Add view function in `views.py`
2. Add URL pattern in `urls.py`
3. Create template in `templates/core/`
4. Add link to navigation in `base.html`

### Adding New Models

1. Add model class in `models.py`
2. Register in `admin.py`
3. Run `makemigrations` and `migrate`
4. Add API endpoints in `views.py`

### Customizing the Dashboard

Edit `dashboard.html` and `dashboard.js` to add new charts or cards.

---

## Troubleshooting

### Common Issues

1. **Migration errors**: Delete `db.sqlite3` and `core/migrations/` except `__init__.py`, then re-migrate.

2. **Static files not loading**: Run `python manage.py collectstatic` in production.

3. **Template errors**: Ensure all templates are in the correct directories.

4. **CSRF errors**: Ensure CSRF tokens are included in forms and AJAX requests.

### Reset Database

```bash
rm db.sqlite3
python manage.py makemigrations core
python manage.py migrate
python manage.py createsuperuser
python manage.py create_sample_data --clear
```

---

## Development Notes

- All user data is automatically linked to the logged-in user
- Signals automatically create UserProfile on user creation
- AJAX auto-refresh runs every 5 seconds on dashboard
- Charts use Chart.js with placeholder data
- API endpoints return JSON responses
- Forms include CSRF protection

---

## License

This project is for educational purposes as part of MCA Final Year Project.

---

## Author

MCA Final Year Student
Cognitive Drift Detection System - Phase 1
