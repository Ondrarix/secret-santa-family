"""
Secret Santa Hosted App
Multi-user Secret Santa with grouped draws and per-group assignments.
"""

import os
import secrets
import string
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, abort
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect, generate_csrf
import sqlite3

# ── App ──────────────────────────────────────────────────────────────
app = Flask(__name__)

# SECRET_KEY must be stable across restarts, or every restart logs users out.
# In production (SECRET_KEY unset) we fail loudly rather than silently rotating keys.
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    if os.environ.get("FLASK_DEBUG", "1") == "1":
        # Dev convenience: stable-per-process ephemeral key.
        _secret = secrets.token_hex(32)
        print("⚠️  SECRET_KEY not set — using an ephemeral dev key (sessions reset on restart).")
    else:
        raise RuntimeError(
            "SECRET_KEY environment variable must be set in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
app.secret_key = _secret

# Secure session cookies. SESSION_COOKIE_SECURE is on unless explicitly disabled
# (set INSECURE_COOKIES=1 for plain-HTTP local testing).
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("INSECURE_COOKIES", "0") != "1",
)

# CSRF protection for all state-changing requests.
csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@app.after_request
def set_csrf_cookie(response):
    """Expose a readable CSRF token cookie so the fetch wrapper can send it back."""
    response.set_cookie(
        "csrf_token", generate_csrf(),
        samesite="Lax",
        secure=os.environ.get("INSECURE_COOKIES", "0") != "1",
    )
    return response

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secret_santa.db")


# ── Database Helpers ─────────────────────────────────────────────────
def get_db():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            year INTEGER NOT NULL,
            description TEXT DEFAULT '',
            budget REAL,
            currency TEXT DEFAULT 'Kč',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            group_id INTEGER,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES groups(id)
        );
        CREATE TABLE IF NOT EXISTS exclusions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            excluded_user_id INTEGER NOT NULL,
            UNIQUE(user_id, excluded_user_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (excluded_user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            giver_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            drawn_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, giver_id, receiver_id),
            FOREIGN KEY (group_id) REFERENCES groups(id),
            FOREIGN KEY (giver_id) REFERENCES users(id),
            FOREIGN KEY (receiver_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS wishes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            wish_text TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            giver_id INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT,
            asked_at TEXT DEFAULT CURRENT_TIMESTAMP,
            answered_at TEXT,
            FOREIGN KEY (group_id) REFERENCES groups(id),
            FOREIGN KEY (giver_id) REFERENCES users(id),
            FOREIGN KEY (recipient_id) REFERENCES users(id)
        );
    """)
    conn.commit()

    # ── Lightweight migrations for pre-existing databases ──
    existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(groups)").fetchall()}
    if "budget" not in existing_cols:
        conn.execute("ALTER TABLE groups ADD COLUMN budget REAL")
    if "currency" not in existing_cols:
        conn.execute("ALTER TABLE groups ADD COLUMN currency TEXT DEFAULT 'Kč'")
    conn.commit()
    conn.close()


# ── User Model (Flask-Login) ─────────────────────────────────────────
class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.name = row["display_name"]
        self.is_admin = bool(row["is_admin"])
        self.group_id = row["group_id"]

    @staticmethod
    def get(user_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        return User(row) if row else None


@login_manager.user_loader
def load_user(user_id):
    return User.get(int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for("login"))


# ── Helpers ──────────────────────────────────────────────────────────
# Simple in-memory login rate limiter (per IP). Adequate for a single-process
# family app; resets on restart. Not for horizontally-scaled deployments.
_login_attempts = {}  # ip -> [timestamps]
_LOGIN_MAX_ATTEMPTS = 10
_LOGIN_WINDOW_SECONDS = 300  # 5 minutes


def _login_rate_limited(ip):
    """Return True if this IP has exceeded the login attempt budget."""
    import time
    now = time.time()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < _LOGIN_WINDOW_SECONDS]
    _login_attempts[ip] = attempts
    return len(attempts) >= _LOGIN_MAX_ATTEMPTS


def _record_login_attempt(ip):
    import time
    _login_attempts.setdefault(ip, []).append(time.time())


def generate_password(length=10):
    """Generate a secure random password."""
    chars = string.ascii_letters + string.digits + "!@"
    while True:
        pw = ''.join(secrets.choice(chars) for _ in range(length))
        if (any(c.isupper() for c in pw) and
            any(c.islower() for c in pw) and
            any(c.isdigit() for c in pw)):
            return pw


def _parse_budget(data):
    """Extract (budget, currency) from a request payload. budget is a float or None."""
    raw = data.get("budget")
    if raw is None or raw == "":
        budget = None
    else:
        try:
            budget = float(raw)
            if budget < 0:
                budget = None
        except (ValueError, TypeError):
            budget = None
    currency = (data.get("currency") or "Kč").strip()[:8] or "Kč"
    return budget, currency


def sanitize_username(name):
    """Convert a display name to a URL-safe username."""
    return (name.lower()
            .replace(" ", "_")
            .replace("'", "")
            .replace("í", "i").replace("á", "a").replace("é", "e")
            .replace("ú", "u").replace("ů", "u").replace("ó", "o")
            .replace("ě", "e").replace("š", "s").replace("č", "c")
            .replace("ř", "r").replace("ž", "z").replace("ý", "y")
            .replace("ď", "d").replace("ť", "t"))


# ── Routes: Pages ────────────────────────────────────────────────────
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
        if _login_rate_limited(ip):
            return render_template(
                "login.html",
                error="Too many login attempts. Please wait a few minutes and try again."
            ), 429
        _record_login_attempt(ip)
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = None
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            user = User(row)
            login_user(user)
        conn.close()
        if user:
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Wrong username or password")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/admin")
@login_required
def admin_panel():
    if not current_user.is_admin:
        return redirect(url_for("dashboard"))
    return render_template("admin.html")


# ── User: Dashboard ──────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    # Admin has no group — send them to the admin panel instead of a broken dashboard.
    if current_user.is_admin and not current_user.group_id:
        return redirect(url_for("admin_panel"))
    conn = get_db()
    group = conn.execute("SELECT * FROM groups WHERE id = ?", (current_user.group_id,)).fetchone()
    conn.close()
    return render_template("dashboard.html", group=group)


# ── Routes: API ──────────────────────────────────────────────────────
@app.route("/api/me")
@login_required
def api_me():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (current_user.id,)).fetchone()
    group = None
    if user and user["group_id"]:
        group = conn.execute(
            "SELECT name, year, budget, currency FROM groups WHERE id = ?", (user["group_id"],)
        ).fetchone()
    conn.close()
    if not user:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "id": user["id"],
        "username": user["username"],
        "name": user["display_name"],
        "is_admin": bool(user["is_admin"]),
        "group_id": user["group_id"],
        "group_name": group["name"] if group else None,
        "budget": group["budget"] if group else None,
        "currency": (group["currency"] if group else None) or "Kč"
    })


# ── Admin: Group Management ──────────────────────────────────────────
@app.route("/api/admin/groups", methods=["GET"])
@login_required
def api_admin_groups():
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    groups = conn.execute(
        "SELECT id, name, year, description, budget, currency, created_at FROM groups ORDER BY year DESC, name"
    ).fetchall()
    data = []
    for g in groups:
        user_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE group_id = ?", (g["id"],)
        ).fetchone()["cnt"]
        draw_count = conn.execute(
            "SELECT CASE WHEN EXISTS(SELECT 1 FROM assignments WHERE group_id = ?) THEN 1 ELSE 0 END as cnt",
            (g["id"],)
        ).fetchone()["cnt"]
        data.append({
            "id": g["id"],
            "name": g["name"],
            "year": g["year"],
            "description": g["description"],
            "budget": g["budget"],
            "currency": g["currency"] or "Kč",
            "user_count": user_count,
            "draw_count": draw_count,
            "created_at": g["created_at"]
        })
    conn.close()
    return jsonify(data)


@app.route("/api/admin/groups", methods=["POST"])
@login_required
def api_admin_create_group():
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json()
    name = data.get("name", "").strip()
    year = data.get("year", datetime.now().year)
    description = data.get("description", "").strip()
    budget, currency = _parse_budget(data)
    if not name:
        return jsonify({"error": "group name required"}), 400
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO groups (name, year, description, budget, currency) VALUES (?, ?, ?, ?, ?)",
            (name, year, description, budget, currency)
        )
        conn.commit()
        group_id = cur.lastrowid
    except sqlite3.IntegrityError as e:
        conn.close()
        return jsonify({"error": str(e)}), 409
    conn.close()
    return jsonify({"id": group_id, "name": name, "year": year})


@app.route("/api/admin/groups/<int:group_id>", methods=["PUT"])
@login_required
def api_admin_edit_group(group_id):
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json()
    name = data.get("name", "").strip()
    year = data.get("year")
    description = data.get("description", "").strip()
    budget, currency = _parse_budget(data)
    if not name:
        return jsonify({"error": "group name required"}), 400
    conn = get_db()
    try:
        conn.execute(
            "UPDATE groups SET name = ?, year = ?, description = ?, budget = ?, currency = ? WHERE id = ?",
            (name, year, description, budget, currency, group_id)
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.close()
        return jsonify({"error": str(e)}), 409
    conn.close()
    return jsonify({"edited": group_id, "name": name, "year": year})


@app.route("/api/admin/groups/<int:group_id>", methods=["DELETE"])
@login_required
def api_admin_delete_group(group_id):
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    has_users = conn.execute(
        "SELECT COUNT(*) as cnt FROM users WHERE group_id = ?", (group_id,)
    ).fetchone()["cnt"]
    if has_users > 0:
        conn.close()
        return jsonify({"error": "delete users first"}), 400
    conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    conn.commit()
    conn.close()
    return jsonify({"deleted": group_id})


# ── Admin: User Management (per group) ───────────────────────────────
@app.route("/api/admin/groups/<int:group_id>/users", methods=["GET"])
@login_required
def api_admin_group_users(group_id):
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    users = conn.execute(
        "SELECT id, username, display_name, is_admin, created_at FROM users WHERE group_id = ? ORDER BY display_name",
        (group_id,)
    ).fetchall()
    data = []
    for u in users:
        assignments = conn.execute(
            "SELECT COUNT(*) as cnt FROM assignments WHERE giver_id = ? AND group_id = ?",
            (u["id"], group_id)
        ).fetchone()["cnt"]
        exclusions = conn.execute(
            "SELECT COUNT(*) as cnt FROM exclusions WHERE user_id = ?", (u["id"],)
        ).fetchone()["cnt"]
        data.append({
            "id": u["id"],
            "username": u["username"],
            "display_name": u["display_name"],
            "is_admin": bool(u["is_admin"]),
            "assignments": assignments,
            "exclusions": exclusions,
            "created_at": u["created_at"]
        })
    conn.close()
    return jsonify(data)


@app.route("/api/admin/groups/<int:group_id>/users", methods=["POST"])
@login_required
def api_admin_add_user(group_id):
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json()
    display_name = data.get("display_name", "").strip()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    auto_creds = data.get("auto_credentials", False)

    if not display_name:
        return jsonify({"error": "display name required"}), 400

    conn = get_db()
    group = conn.execute("SELECT id FROM groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        conn.close()
        return jsonify({"error": "group not found"}), 404

    # Generate username if not provided
    if not username:
        username = sanitize_username(display_name)
        base = username
        counter = 1
        while conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            username = f"{base}_{counter}"
            counter += 1

    # Generate password if auto or empty
    if auto_creds or not password:
        password = generate_password(10)

    if len(password) < 4:
        conn.close()
        return jsonify({"error": "password must be at least 4 characters"}), 400

    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, group_id) VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(password), display_name, group_id)
        )
        conn.commit()
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": f"Username '{username}' already exists"}), 409

    conn.close()
    return jsonify({
        "id": user_id,
        "username": username,
        "display_name": display_name,
        "password": password if (auto_creds or not data.get("password")) else "******"
    })


@app.route("/api/admin/groups/<int:group_id>/users/<int:user_id>", methods=["DELETE"])
@login_required
def api_admin_delete_user(group_id, user_id):
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    user = conn.execute(
        "SELECT id, display_name, is_admin FROM users WHERE id = ? AND group_id = ?",
        (user_id, group_id)
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "user not found in this group"}), 404
    if user_id == current_user.id:
        conn.close()
        return jsonify({"error": "can't delete yourself"}), 400

    conn.execute("DELETE FROM assignments WHERE giver_id = ? OR receiver_id = ?", (user_id, user_id))
    conn.execute("DELETE FROM exclusions WHERE user_id = ? OR excluded_user_id = ?", (user_id, user_id))
    conn.execute("DELETE FROM questions WHERE giver_id = ? OR recipient_id = ?", (user_id, user_id))
    conn.execute("DELETE FROM wishes WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"deleted": user_id, "name": user["display_name"]})


@app.route("/api/admin/groups/<int:group_id>/users/<int:user_id>", methods=["PUT"])
@login_required
def api_admin_edit_user(group_id, user_id):
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json()
    display_name = data.get("display_name", "").strip()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()  # optional; if provided, set new password

    if not display_name:
        return jsonify({"error": "display name required"}), 400

    conn = get_db()
    # Verify user belongs to this group
    user = conn.execute(
        "SELECT id, display_name, username, is_admin FROM users WHERE id = ? AND group_id = ?",
        (user_id, group_id)
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "user not found in this group"}), 404

    # Check username uniqueness if changed
    if username and username != user["username"]:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ? AND id != ?", (username, user_id)
        ).fetchone()
        if existing:
            conn.close()
            return jsonify({"error": f"Username '{username}' already taken"}), 409

    # Build update
    updates = []
    params = []
    if username:
        updates.append("username = ?")
        params.append(username)
    if password:
        updates.append("password_hash = ?")
        params.append(generate_password_hash(password))
    if display_name != user["display_name"]:
        updates.append("display_name = ?")
        params.append(display_name)

    if updates:
        params.append(user_id)
        conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params
        )
        conn.commit()

    conn.close()
    return jsonify({"edited": user_id, "display_name": display_name, "username": username or user["username"]})


@app.route("/api/admin/users/<int:user_id>/credentials", methods=["GET"])
@login_required
def api_admin_user_credentials(user_id):
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    user = conn.execute("SELECT id, username, display_name FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not user:
        return jsonify({"error": "user not found"}), 404
    return jsonify({"username": user["username"], "display_name": user["display_name"]})


@app.route("/api/admin/groups/<int:group_id>/generate-credentials", methods=["POST"])
@login_required
def api_admin_generate_credentials(group_id):
    """Regenerate passwords for all users in a group."""
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    users = conn.execute(
        "SELECT id, display_name, username FROM users WHERE group_id = ? ORDER BY display_name",
        (group_id,)
    ).fetchall()

    results = []
    for u in users:
        new_pw = generate_password(10)
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_pw), u["id"])
        )
        results.append({
            "username": u["username"],
            "display_name": u["display_name"],
            "password": new_pw
        })
    conn.commit()
    conn.close()
    return jsonify({"credentials": results})


# ── Admin: Exclusions (per group) ────────────────────────────────────
@app.route("/api/admin/groups/<int:group_id>/exclusions", methods=["GET"])
@login_required
def api_admin_group_exclusions(group_id):
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    rows = conn.execute("""
        SELECT e.id, u1.id as user_id, u1.display_name as user_name,
               u2.id as excluded_id, u2.display_name as excluded_name
        FROM exclusions e
        JOIN users u1 ON e.user_id = u1.id
        JOIN users u2 ON e.excluded_user_id = u2.id
        WHERE u1.group_id = ?
        ORDER BY u1.display_name, u2.display_name
    """, (group_id,)).fetchall()

    # Group bidirectional exclusions: if A→B and B→A both exist, show as mutual
    seen_pairs = set()
    result = []
    for r in rows:
        pair_key = tuple(sorted([r["user_id"], r["excluded_id"]]))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        # Check if the reverse direction also exists
        rev = conn.execute(
            "SELECT id FROM exclusions WHERE user_id = ? AND excluded_user_id = ?",
            (r["excluded_id"], r["user_id"])
        ).fetchone()
        is_mutual = rev is not None

        result.append({
            "user_id": r["user_id"],
            "excluded_id": r["excluded_id"],
            "user": r["user_name"],
            "excluded": r["excluded_name"],
            "mutual": is_mutual,
            "id": r["id"],
            "reverse_id": rev["id"] if rev else None
        })
    conn.close()
    return jsonify(result)


@app.route("/api/admin/groups/<int:group_id>/exclusions", methods=["POST"])
@login_required
def api_admin_add_exclusion(group_id):
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json()
    user_id = data.get("user_id")
    excluded_user_id = data.get("excluded_user_id")
    if not user_id or not excluded_user_id or user_id == excluded_user_id:
        return jsonify({"error": "need two different users"}), 400
    conn = get_db()
    user1 = conn.execute(
        "SELECT id FROM users WHERE id = ? AND group_id = ?",
        (user_id, group_id)
    ).fetchone()
    user2 = conn.execute(
        "SELECT id FROM users WHERE id = ? AND group_id = ?",
        (excluded_user_id, group_id)
    ).fetchone()
    if not user1 or not user2:
        conn.close()
        return jsonify({"error": "both users must be in this group"}), 400
    try:
        conn.execute(
            "INSERT INTO exclusions (user_id, excluded_user_id) VALUES (?, ?)",
            (user_id, excluded_user_id)
        )
        conn.execute(
            "INSERT INTO exclusions (user_id, excluded_user_id) VALUES (?, ?)",
            (excluded_user_id, user_id)
        )
        conn.commit()
        e_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "exclusion already exists"}), 409
    conn.close()
    return jsonify({"id": e_id})


@app.route("/api/admin/exclusions/<int:exclusion_id>", methods=["DELETE"])
@login_required
def api_admin_delete_exclusion(exclusion_id):
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    # Get the direction of this exclusion to also delete the reverse
    row = conn.execute("SELECT user_id, excluded_user_id FROM exclusions WHERE id = ?", (exclusion_id,)).fetchone()
    if row:
        conn.execute("DELETE FROM exclusions WHERE id = ?", (exclusion_id,))
        conn.execute("DELETE FROM exclusions WHERE user_id = ? AND excluded_user_id = ?", (row["excluded_user_id"], row["user_id"]))
        conn.commit()
    conn.close()
    return jsonify({"deleted": exclusion_id})


@app.route("/api/admin/groups/<int:group_id>/users-list", methods=["GET"])
@login_required
def api_admin_group_users_list(group_id):
    """Flat list of users in group for exclusion selects."""
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    users = conn.execute(
        "SELECT id, display_name FROM users WHERE group_id = ? ORDER BY display_name",
        (group_id,)
    ).fetchall()
    conn.close()
    return [{"id": u["id"], "name": u["display_name"]} for u in users]


# ── Admin: Trigger Draw (per group) ──────────────────────────────────
@app.route("/api/admin/groups/<int:group_id>/draw", methods=["POST"])
@login_required
def api_admin_draw(group_id):
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    group = conn.execute("SELECT id FROM groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        conn.close()
        return jsonify({"error": "group not found"}), 404

    users = conn.execute(
        "SELECT id, display_name FROM users WHERE group_id = ? ORDER BY id", (group_id,)
    ).fetchall()
    n = len(users)

    if n < 2:
        conn.close()
        return jsonify({"error": "need at least 2 users in the group"}), 400

    # Build exclusion lookup
    user_ids = [u["id"] for u in users]
    user_map = {u["id"]: u["display_name"] for u in users}
    exclusion_pairs = set()
    for u in users:
        rows = conn.execute(
            "SELECT excluded_user_id FROM exclusions WHERE user_id = ?", (u["id"],)
        ).fetchall()
        for r in rows:
            exclusion_pairs.add((u["id"], r["excluded_user_id"]))

    # Clear old assignments for this group
    conn.execute("DELETE FROM assignments WHERE group_id = ?", (group_id,))

    # Generate derangement respecting exclusions — use CSPRNG
    import secrets as sec
    rng = sec.SystemRandom()
    assignments = None
    for attempt in range(10000):
        shuffled = list(user_ids)
        for i in range(n - 1, 0, -1):
            j = rng.randint(0, i)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]

        valid = True
        for i in range(n):
            giver = user_ids[i]
            receiver = shuffled[i]
            if giver == receiver:
                valid = False
                break
            if (giver, receiver) in exclusion_pairs:
                valid = False
                break

        if valid:
            assignments = [{"giver_id": user_ids[i], "receiver_id": shuffled[i]}
                          for i in range(n)]
            break

    if not assignments:
        conn.close()
        return jsonify({"error": "No valid assignment found. Check exclusion constraints."}), 400

    for a in assignments:
        conn.execute(
            "INSERT INTO assignments (group_id, giver_id, receiver_id) VALUES (?, ?, ?)",
            (group_id, a["giver_id"], a["receiver_id"])
        )
    conn.commit()
    conn.close()

    result = []
    for a in assignments:
        result.append({
            "giver": user_map[a["giver_id"]],
            "receiver": user_map[a["receiver_id"]]
        })
    result.sort(key=lambda x: x["giver"].lower())

    return jsonify({"assignments": result, "message": f"Draw completed! {n} assignments made."})


@app.route("/api/admin/groups/<int:group_id>/reset", methods=["POST"])
@login_required
def api_admin_reset(group_id):
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    conn.execute("DELETE FROM assignments WHERE group_id = ?", (group_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Assignments cleared"})


@app.route("/api/admin/groups/<int:group_id>/assignments", methods=["GET"])
@login_required
def api_admin_group_assignments(group_id):
    """Get current assignments for a group (used by admin reveal)."""
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    assignments = conn.execute("""
        SELECT u1.display_name as giver, u2.display_name as receiver
        FROM assignments a
        JOIN users u1 ON a.giver_id = u1.id
        JOIN users u2 ON a.receiver_id = u2.id
        WHERE a.group_id = ?
        ORDER BY u1.display_name
    """, (group_id,)).fetchall()
    conn.close()
    if not assignments:
        return jsonify({"assignments": [], "message": "No assignments found."})
    return jsonify({"assignments": [{"giver": a["giver"], "receiver": a["receiver"]} for a in assignments]})


# ── User: Self Exclusions ────────────────────────────────────────────
@app.route("/api/user/exclusions", methods=["GET"])
@login_required
def api_user_exclusions():
    conn = get_db()
    my_exclusions = conn.execute(
        "SELECT e.id, u2.display_name FROM exclusions e JOIN users u2 ON e.excluded_user_id = u2.id WHERE e.user_id = ?",
        (current_user.id,)
    ).fetchall()
    others = conn.execute(
        "SELECT id, display_name FROM users WHERE group_id = ? AND id != ? ORDER BY display_name",
        (current_user.group_id, current_user.id)
    ).fetchall()
    conn.close()
    return jsonify({
        "excluded": [{"id": e["id"], "name": e["display_name"]} for e in my_exclusions],
        "others": [{"id": o["id"], "name": o["display_name"]} for o in others]
    })


@app.route("/api/user/exclusions", methods=["POST"])
@login_required
def api_user_add_exclusion():
    data = request.get_json()
    excluded_user_id = data.get("excluded_user_id")
    if not excluded_user_id or excluded_user_id == current_user.id:
        return jsonify({"error": "invalid"}), 400
    conn = get_db()
    same_group = conn.execute(
        "SELECT id FROM users WHERE id = ? AND group_id = ?",
        (excluded_user_id, current_user.group_id)
    ).fetchone()
    if not same_group:
        conn.close()
        return jsonify({"error": "user must be in your group"}), 400
    try:
        conn.execute(
            "INSERT INTO exclusions (user_id, excluded_user_id) VALUES (?, ?)",
            (current_user.id, excluded_user_id)
        )
        conn.execute(
            "INSERT INTO exclusions (user_id, excluded_user_id) VALUES (?, ?)",
            (excluded_user_id, current_user.id)
        )
        conn.commit()
        name = conn.execute(
            "SELECT display_name FROM users WHERE id = ?", (excluded_user_id,)
        ).fetchone()["display_name"]
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "already excluded"}), 409
    conn.close()
    return jsonify({"excluded": name})


@app.route("/api/user/exclusions/<int:exclusion_id>", methods=["DELETE"])
@login_required
def api_user_delete_exclusion(exclusion_id):
    conn = get_db()
    conn.execute("DELETE FROM exclusions WHERE id = ? AND user_id = ?", (exclusion_id, current_user.id))
    conn.commit()
    conn.close()
    return jsonify({"deleted": exclusion_id})


# ── User: My Assignment ──────────────────────────────────────────────
@app.route("/api/me/assignment")
@login_required
def api_my_assignment():
    conn = get_db()
    row = conn.execute(
        "SELECT u.display_name FROM assignments a JOIN users u ON a.receiver_id = u.id "
        "WHERE a.giver_id = ? AND a.group_id = ?",
        (current_user.id, current_user.group_id)
    ).fetchone()
    conn.close()
    if row:
        return jsonify({"name": row["display_name"]})
    return jsonify({"name": None, "message": "No assignment yet. Ask the admin to draw!"})


# ── User: Change Password ────────────────────────────────────────────
@app.route("/api/me/password", methods=["POST"])
@login_required
def api_change_password():
    data = request.get_json()
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")
    if not old_password or not new_password:
        return jsonify({"error": "both fields required"}), 400
    if len(new_password) < 4:
        return jsonify({"error": "password must be at least 4 characters"}), 400
    conn = get_db()
    row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (current_user.id,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], old_password):
        conn.close()
        return jsonify({"error": "current password is wrong"}), 401
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), current_user.id)
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Password changed"})


# ── User: Wishes ─────────────────────────────────────────────────────
@app.route("/api/me/wish", methods=["GET", "POST"])
@login_required
def api_user_wish():
    conn = get_db()
    if request.method == "POST":
        data = request.get_json()
        wish_text = (data.get("wish_text", "") or "").strip()[:500]
        if not wish_text:
            conn.close()
            return jsonify({"error": "wish text required"}), 400
        # Upsert: insert or update
        try:
            conn.execute(
                "INSERT INTO wishes (user_id, wish_text) VALUES (?, ?)",
                (current_user.id, wish_text)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.execute(
                "UPDATE wishes SET wish_text = ? WHERE user_id = ?",
                (wish_text, current_user.id)
            )
            conn.commit()
        conn.close()
        return jsonify({"message": "Wish saved"})

    # GET: return my wish
    row = conn.execute(
        "SELECT wish_text FROM wishes WHERE user_id = ?", (current_user.id,)
    ).fetchone()
    conn.close()
    return jsonify({"wish": row["wish_text"] if row else ""})


@app.route("/api/me/recipient-wish", methods=["GET"])
@login_required
def api_my_recipient_wish():
    """Get the wish of the person I drew."""
    conn = get_db()
    # Find who I drew
    receiver_id = conn.execute(
        "SELECT receiver_id FROM assignments WHERE giver_id = ? AND group_id = ?",
        (current_user.id, current_user.group_id)
    ).fetchone()
    if not receiver_id:
        conn.close()
        return jsonify({"wish": None, "name": None})
    receiver_id = receiver_id["receiver_id"]
    # Get their wish
    wish_row = conn.execute(
        "SELECT w.wish_text, u.display_name FROM wishes w JOIN users u ON w.user_id = u.id WHERE w.user_id = ?",
        (receiver_id,)
    ).fetchone()
    conn.close()
    if wish_row and wish_row["wish_text"]:
        return jsonify({"wish": wish_row["wish_text"], "name": wish_row["display_name"]})
    return jsonify({"wish": None, "name": None})


# ── User: Anonymous Q&A ──────────────────────────────────────────────
def _my_recipient_id(conn):
    """Return the user_id I (current_user) am giving to in my group, or None."""
    row = conn.execute(
        "SELECT receiver_id FROM assignments WHERE giver_id = ? AND group_id = ?",
        (current_user.id, current_user.group_id)
    ).fetchone()
    return row["receiver_id"] if row else None


@app.route("/api/me/questions", methods=["GET"])
@login_required
def api_my_questions():
    """Questions I (as giver) have asked my recipient — with answers if given.
    The recipient's identity IS known to the giver (it's who they drew), so we
    return their name here; anonymity only protects the giver's identity."""
    conn = get_db()
    recipient_id = _my_recipient_id(conn)
    if not recipient_id:
        conn.close()
        return jsonify({"recipient": None, "questions": []})
    recipient = conn.execute(
        "SELECT display_name FROM users WHERE id = ?", (recipient_id,)
    ).fetchone()
    rows = conn.execute(
        "SELECT id, question, answer, asked_at, answered_at FROM questions "
        "WHERE giver_id = ? AND recipient_id = ? AND group_id = ? ORDER BY asked_at",
        (current_user.id, recipient_id, current_user.group_id)
    ).fetchall()
    conn.close()
    return jsonify({
        "recipient": recipient["display_name"] if recipient else None,
        "questions": [{
            "id": r["id"], "question": r["question"], "answer": r["answer"],
            "asked_at": r["asked_at"], "answered_at": r["answered_at"]
        } for r in rows]
    })


@app.route("/api/me/questions", methods=["POST"])
@login_required
def api_ask_question():
    """Giver asks their recipient a question."""
    data = request.get_json()
    question = (data.get("question", "") or "").strip()[:500]
    if not question:
        return jsonify({"error": "question text required"}), 400
    conn = get_db()
    recipient_id = _my_recipient_id(conn)
    if not recipient_id:
        conn.close()
        return jsonify({"error": "You don't have an assignment yet."}), 400
    # Cap at 20 open/total questions per giver→recipient to prevent abuse.
    count = conn.execute(
        "SELECT COUNT(*) as c FROM questions WHERE giver_id = ? AND recipient_id = ? AND group_id = ?",
        (current_user.id, recipient_id, current_user.group_id)
    ).fetchone()["c"]
    if count >= 20:
        conn.close()
        return jsonify({"error": "Question limit reached for this recipient."}), 400
    conn.execute(
        "INSERT INTO questions (group_id, giver_id, recipient_id, question) VALUES (?, ?, ?, ?)",
        (current_user.group_id, current_user.id, recipient_id, question)
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Question sent"})


@app.route("/api/me/incoming-questions", methods=["GET"])
@login_required
def api_incoming_questions():
    """Questions asked about MY gift (I am the recipient). Asker stays anonymous."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, question, answer, asked_at, answered_at FROM questions "
        "WHERE recipient_id = ? AND group_id = ? ORDER BY asked_at",
        (current_user.id, current_user.group_id)
    ).fetchall()
    conn.close()
    # Deliberately omit giver_id — the asker is anonymous to the recipient.
    return jsonify({"questions": [{
        "id": r["id"], "question": r["question"], "answer": r["answer"],
        "asked_at": r["asked_at"], "answered_at": r["answered_at"]
    } for r in rows]})


@app.route("/api/me/incoming-questions/<int:question_id>", methods=["POST"])
@login_required
def api_answer_question(question_id):
    """Recipient answers a question about their gift."""
    data = request.get_json()
    answer = (data.get("answer", "") or "").strip()[:500]
    if not answer:
        return jsonify({"error": "answer text required"}), 400
    conn = get_db()
    # Only the recipient of this question may answer it.
    q = conn.execute(
        "SELECT id FROM questions WHERE id = ? AND recipient_id = ?",
        (question_id, current_user.id)
    ).fetchone()
    if not q:
        conn.close()
        return jsonify({"error": "question not found"}), 404
    conn.execute(
        "UPDATE questions SET answer = ?, answered_at = CURRENT_TIMESTAMP WHERE id = ?",
        (answer, question_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Answer saved"})


# ── Seed: Admin ──────────────────────────────────────────────────────
def seed_admin():
    """Create default admin if no users exist."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    if count == 0:
        conn = get_db()
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, group_id, is_admin) VALUES (?, ?, ?, NULL, 1)",
            ("admin", generate_password_hash("secret"), "Admin")
        )
        conn.commit()
        conn.close()
        print("Created default admin account: admin / secret")


# ── Seed: Family Group ───────────────────────────────────────────────
FAMILY_USERS = ["Maminka", "Tatínek", "Danuška", "Káčí", "Óňa", "Nezuš"]


def seed_family_group():
    """Create the 2024 family group with pre-registered users."""
    conn = get_db()
    group = conn.execute(
        "SELECT id FROM groups WHERE name = ? AND year = ?",
        ("Rodina", 2024)
    ).fetchone()
    if group:
        conn.close()
        return

    cur = conn.execute(
        "INSERT INTO groups (name, year, description) VALUES (?, ?, ?)",
        ("Rodina", 2024, "Family Secret Santa 2024")
    )
    group_id = cur.lastrowid

    created = []
    for name in FAMILY_USERS:
        pw = generate_password(10)
        username = sanitize_username(name)
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, group_id) VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(pw), name, group_id)
        )
        created.append((name, username, pw))
    conn.commit()
    conn.close()
    print(f"Created family group 'Rodina 2024' with {len(FAMILY_USERS)} users")
    print("\nUser credentials (save these — they are not recoverable later):")
    for name, username, pw in created:
        print(f"  {name:12s}  →  {username:12s}  /  {pw}")


# ── Bootstrap ────────────────────────────────────────────────────────
# Runs on import (dev server AND gunicorn) so the DB and admin always exist.
init_db()
seed_admin()
seed_family_group()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # Debug defaults OFF — must be explicitly enabled. The Werkzeug debugger
    # is a remote-code-execution risk if ever exposed in production.
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"🎅 Secret Santa running at http://{host}:{port}")
    if debug:
        print("   Default admin: admin / secret  (change the password after first login!)")
    app.run(host=host, port=port, debug=debug)
