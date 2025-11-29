```markdown
# Jobsite (Flask + Server-rendered HTML)

This version replaces the Node/React scaffold with a simple Flask application that serves HTML templates and uses SQLite for account storage. It includes signup, signin, session-based auth, role support (candidate / employer), and a protected profile page.

Requirements
- Python 3.8+
- pip

Install
1. Create a virtual environment (recommended)
   - python -m venv venv
   - source venv/bin/activate  # on Windows: venv\Scripts\activate

2. Install dependencies
   - pip install -r requirements.txt

Run
- python app.py
- By default the app runs on http://127.0.0.1:5000

Environment
- FLASK_SECRET_KEY (optional) — set a secure secret for sessions. If not set, a default 'change-me-to-a-random-secret' will be used (not for production).

Files
- app.py: Flask app and routes (signup, signin, logout, profile)
- models.py: SQLite helper functions and DB initialization
- templates/: Jinja2 templates (layout, index, signup, signin, profile, employer dashboard)
- static/: CSS file
- data.db: created automatically on first run

Notes & next steps
- Passwords are hashed with Werkzeug generate_password_hash.
- Sessions are cookie-based via Flask-Login.
- Roles are stored on the users table; you can protect endpoints using the require_roles decorator in app.py.
- This is a simple, easy-to-extend starting point for a server-rendered site. For production use: set a strong FLASK_SECRET_KEY, enable HTTPS, and consider additional security (CSRF protection via Flask-WTF, input validation, rate limiting).
```