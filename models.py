# models.py
import sqlite3
from datetime import datetime, timedelta
import os
import secrets

def _row_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = _row_factory
    return conn

def _columns_for_table(conn, table):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info('{table}')")
    return [r['name'] for r in cur.fetchall()]

def _table_exists(conn, table):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,))
    return cur.fetchone() is not None

def _ensure_table(conn, create_sql):
    cur = conn.cursor()
    cur.execute(create_sql)
    conn.commit()

def _add_column_if_missing(conn, table, column_def):  # column_def example: "is_banned INTEGER NOT NULL DEFAULT 0"
    col_name = column_def.split()[0]
    existing = _columns_for_table(conn, table)
    if col_name not in existing:
        cur = conn.cursor()
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        conn.commit()
        return True
    return False

def init_db(db_path):
    # Ensure DB directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    conn = get_connection(db_path)

    # Create tables if missing (CREATE TABLE IF NOT EXISTS)
    _ensure_table(
        conn,
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'candidate',
            is_banned INTEGER NOT NULL DEFAULT 0,
            banned_until TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    )

    _ensure_table(
        conn,
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employer_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            location_text TEXT,
            lat REAL,
            lng REAL,
            salary TEXT,
            tags TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employer_id) REFERENCES users(id)
        )
    """,
    )

    _ensure_table(
        conn,
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            cover_letter TEXT,
            resume_text TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """,
    )

    _ensure_table(
        conn,
        """
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            rater_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
            comment TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (rater_id) REFERENCES users(id)
        )
    """,
    )

    _ensure_table(
        conn,
        """
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            purpose TEXT NOT NULL,
            expires_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """,
    )

    # Add newer columns if the table schema is older (non-destructive)
    try:
        # applications: store uploaded file paths for cover letter and resume (pdfs)
        _add_column_if_missing(conn, "applications", "cover_letter_path TEXT")
        _add_column_if_missing(conn, "applications", "resume_path TEXT")
    except sqlite3.OperationalError as e:
        # Log but continue
        print("models.init_db: failed to add application file columns:", e)

    conn.close()

# ---- helper functions for app logic below ----

# Users
def create_user(db_path, email, password_hash, role="candidate", username=None, first_name=None, last_name=None, verified=0):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO users
           (email,password_hash,role,username,first_name,last_name,verified,created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (email, password_hash, role, username, first_name, last_name, verified, datetime.utcnow().isoformat()),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return get_user_by_id(db_path, user_id)

def get_user_by_email(db_path, email):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, email, password_hash, role, is_banned, banned_until, created_at, username, first_name, last_name, verified FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    return row

def get_user_by_username(db_path, username):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, email, role, is_banned, banned_until, created_at, username, first_name, last_name, verified FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row

def get_user_by_id(db_path, id):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, email, role, is_banned, banned_until, created_at, username, first_name, last_name, verified FROM users WHERE id = ?", (id,))
    row = cur.fetchone()
    conn.close()
    return row

def set_user_verified(db_path, email):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE users SET verified = 1 WHERE email = ?", (email,))
    conn.commit()
    updated = cur.rowcount
    conn.close()
    return updated > 0

def update_user_password(db_path, email, password_hash):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash = ? WHERE email = ?", (password_hash, email))
    conn.commit()
    updated = cur.rowcount
    conn.close()
    return updated > 0

def get_all_users(db_path):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, email, role, is_banned, banned_until, created_at, username, first_name, last_name, verified FROM users ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return rows

def set_user_ban(db_path, user_id, banned_until_iso=None):
    conn = get_connection(db_path)
    cur = conn.cursor()
    if banned_until_iso:
        cur.execute("UPDATE users SET is_banned=1, banned_until=? WHERE id = ?", (banned_until_iso, user_id))
    else:
        cur.execute("UPDATE users SET is_banned=1, banned_until=NULL WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True

def unset_user_ban(db_path, user_id):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_banned=0, banned_until=NULL WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True

def delete_user(db_path, user_id):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM applications WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM ratings WHERE rater_id = ? OR (target_type='user' AND target_id=?)", (user_id, user_id))
    cur.execute("SELECT id FROM jobs WHERE employer_id = ?", (user_id,))
    job_ids = [r['id'] for r in cur.fetchall()]
    for jid in job_ids:
        cur.execute("DELETE FROM applications WHERE job_id = ?", (jid,))
        cur.execute("DELETE FROM ratings WHERE target_type='job' AND target_id = ?", (jid,))
    cur.execute("DELETE FROM jobs WHERE employer_id = ?", (user_id,))
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True

# Tokens: DB-backed hex tokens for email verification and password reset
def create_token(db_path, email, purpose, expires_seconds=3600):
    conn = get_connection(db_path)
    cur = conn.cursor()
    token = secrets.token_hex(24)  # 48 hex chars (~192 bits)
    expires_at = (datetime.utcnow() + timedelta(seconds=expires_seconds)).isoformat()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            purpose TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
    cur.execute(
        "INSERT INTO tokens (token, email, purpose, expires_at) VALUES (?, ?, ?, ?)",
        (token, email, purpose, expires_at),
    )
    conn.commit()
    conn.close()
    return token

def consume_token(db_path, token, purpose):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT email, expires_at FROM tokens WHERE token = ? AND purpose = ?",
        (token, purpose),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    email = row["email"]
    expires_at = row.get("expires_at")
    try:
        if expires_at:
            exp_dt = datetime.fromisoformat(expires_at)
            if exp_dt < datetime.utcnow():
                cur.execute("DELETE FROM tokens WHERE token = ?", (token,))
                conn.commit()
                conn.close()
                return None
    except Exception:
        cur.execute("DELETE FROM tokens WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return None
    cur.execute("DELETE FROM tokens WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    return email

def get_token_info(db_path, token, purpose):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT token, email, purpose, expires_at, created_at FROM tokens WHERE token = ? AND purpose = ?", (token, purpose))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    expires_at = row.get("expires_at")
    try:
        if expires_at:
            exp_dt = datetime.fromisoformat(expires_at)
            if exp_dt < datetime.utcnow():
                return None
    except Exception:
        return None
    return row

def purge_expired_tokens(db_path):
    conn = get_connection(db_path)
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("DELETE FROM tokens WHERE expires_at <= ?", (now,))
    conn.commit()
    conn.close()

# Jobs
def create_job(db_path, employer_id, title, description, location_text=None, lat=None, lng=None, salary="", tags=None):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO jobs
           (employer_id, title, description, location_text, lat, lng, salary, tags, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (employer_id, title, description, location_text, lat, lng, salary, tags, datetime.utcnow().isoformat()),
    )
    conn.commit()
    job_id = cur.lastrowid
    conn.close()
    return get_job_by_id(db_path, job_id)

def update_job(db_path, job_id, title=None, description=None, location_text=None, lat=None, lng=None, salary=None, tags=None):
    conn = get_connection(db_path)
    cur = conn.cursor()
    fields = []
    params = []
    if title is not None:
        fields.append("title = ?"); params.append(title)
    if description is not None:
        fields.append("description = ?"); params.append(description)
    if location_text is not None:
        fields.append("location_text = ?"); params.append(location_text)
    if lat is not None:
        fields.append("lat = ?"); params.append(lat)
    if lng is not None:
        fields.append("lng = ?"); params.append(lng)
    if salary is not None:
        fields.append("salary = ?"); params.append(salary)
    if tags is not None:
        fields.append("tags = ?"); params.append(tags)
    if not fields:
        conn.close()
        return get_job_by_id(db_path, job_id)
    params.append(job_id)
    sql = "UPDATE jobs SET " + ", ".join(fields) + " WHERE id = ?"
    cur.execute(sql, params)
    conn.commit()
    conn.close()
    return get_job_by_id(db_path, job_id)

def delete_job(db_path, job_id):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM applications WHERE job_id = ?", (job_id,))
    cur.execute("DELETE FROM ratings WHERE target_type='job' AND target_id = ?", (job_id,))
    cur.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return True

def get_jobs(db_path, limit=None):
    conn = get_connection(db_path)
    cur = conn.cursor()
    sql = "SELECT id, employer_id, title, description, location_text, lat, lng, salary, tags, created_at FROM jobs ORDER BY created_at DESC"
    if limit:
        sql += " LIMIT ?"
        cur.execute(sql, (limit,))
    else:
        cur.execute(sql)
    rows = cur.fetchall()
    conn.close()
    return rows

def get_job_by_id(db_path, job_id):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, employer_id, title, description, location_text, lat, lng, salary, tags, created_at FROM jobs WHERE id = ?", (job_id,))
    row = cur.fetchone()
    conn.close()
    return row

def get_jobs_by_employer(db_path, employer_id):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, employer_id, title, description, location_text, lat, lng, salary, tags, created_at FROM jobs WHERE employer_id = ? ORDER BY created_at DESC",
        (employer_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows

# Applications
def create_application(db_path, job_id, user_id, cover_letter="", resume_text="", cover_letter_path=None, resume_path=None):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO applications (job_id, user_id, cover_letter, resume_text, cover_letter_path, resume_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (job_id, user_id, cover_letter, resume_text, cover_letter_path, resume_path, datetime.utcnow().isoformat()),
    )
    conn.commit()
    app_id = cur.lastrowid
    conn.close()
    return {"id": app_id, "job_id": job_id, "user_id": user_id, "cover_letter_path": cover_letter_path, "resume_path": resume_path}

# and update get_applications_by_job to include the filename columns:
def get_applications_by_job(db_path, job_id):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT a.id, a.job_id, a.user_id, a.cover_letter, a.resume_text, a.cover_letter_path, a.resume_path, a.created_at, u.email as applicant_email FROM applications a JOIN users u ON u.id = a.user_id WHERE a.job_id = ? ORDER BY a.created_at DESC",
        (job_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_applications_by_user(db_path, user_id):
    """
    Returns applications for a given user. Each row includes cover_letter_path and resume_path where present.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, job_id, user_id, cover_letter, resume_text, cover_letter_path, resume_path, created_at FROM applications WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows

# Ratings
def create_rating(db_path, target_type, target_id, rater_id, rating, comment=""):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ratings (target_type, target_id, rater_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (target_type, target_id, rater_id, rating, comment, datetime.utcnow().isoformat()),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return {"id": rid, "target_type": target_type, "target_id": target_id, "rater_id": rater_id, "rating": rating}

def get_ratings_for_target(db_path, target_type, target_id):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT r.id, r.target_type, r.target_id, r.rater_id, r.rating, r.comment, r.created_at, u.email as rater_email FROM ratings r JOIN users u ON u.id = r.rater_id WHERE r.target_type = ? AND r.target_id = ? ORDER BY r.created_at DESC",
        (target_type, target_id),
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def get_average_rating_for_target(db_path, target_type, target_id):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT AVG(rating) as avg_rating, COUNT(*) as count FROM ratings WHERE target_type = ? AND target_id = ?",
        (target_type, target_id),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"avg": None, "count": 0}
    return {"avg": row.get("avg_rating"), "count": row.get("count")}

def get_rating_by_id(db_path, rating_id):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, target_type, target_id, rater_id, rating, comment, created_at FROM ratings WHERE id = ?", (rating_id,))
    row = cur.fetchone()
    conn.close()
    return row

def delete_rating(db_path, rating_id):
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM ratings WHERE id = ?", (rating_id,))
    conn.commit()
    conn.close()
    return True
