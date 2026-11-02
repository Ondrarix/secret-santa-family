"""
Secret Santa Hosted App
A multi-user Secret Santa app with partner exclusions.
"""

import os
import json
import secrets
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

# ── App ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

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
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
            giver_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            drawn_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(giver_id, receiver_id),
            FOREIGN KEY (giver_id) REFERENCES users(id),
            FOREIGN KEY (receiver_id) REFERENCES users(id)
        );
    """)
    conn.commit()
    conn.close()


# ── User Model (Flask-Login) ─────────────────────────────────────────
class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.is_admin = bool(row["is_admin"])

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


# ── Routes: Pages ────────────────────────────────────────────────────
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        user = None
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            user = User(row)
            login_user(user)
        conn.close()
        if user:
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Wrong name or password")
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


# ── Routes: API ──────────────────────────────────────────────────────
@app.route("/api/me")
@login_required
def api_me():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (current_user.id,)).fetchone()
    conn.close()
    if not user:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "id": user["id"],
        "name": user["name"],
        "is_admin": bool(user["is_admin"])
    })


# ── Admin: User Management ──────────────────────────────────────────
@app.route("/api/admin/users", methods=["GET"])
@login_required
def api_admin_users():
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    users = conn.execute("SELECT id, name, is_admin, created_at FROM users ORDER BY name").fetchall()
    # Count assignments per user
    data = []
    for u in users:
        assignments = conn.execute(
            "SELECT COUNT(*) as cnt FROM assignments WHERE giver_id = ?", (u["id"],)
        ).fetchone()["cnt"]
        exclusions = conn.execute(
            "SELECT COUNT(*) as cnt FROM exclusions WHERE user_id = ?", (u["id"],)
        ).fetchone()["cnt"]
        data.append({
            "id": u["id"],
            "name": u["name"],
            "is_admin": bool(u["is_admin"]),
            "assignments": assignments,
            "exclusions": exclusions,
            "created_at": u["created_at"]
        })
    conn.close()
    return jsonify(data)


@app.route("/api/admin/users", methods=["POST"])
@login_required
def api_admin_add_user():
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json()
    name = data.get("name", "").strip()
    password = data.get("password", "").strip()
    if not name or not password:
        return jsonify({"error": "name and password required"}), 400
    if len(password) < 4:
        return jsonify({"error": "password must be at least 4 characters"}), 400
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, password_hash) VALUES (?, ?)",
            (name, generate_password_hash(password))
        )
        conn.commit()
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": f"User '{name}' already exists"}), 409
    conn.close()
    return jsonify({"id": user_id, "name": name})


@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@login_required
def api_admin_delete_user(user_id):
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    # Prevent deleting yourself
    if user_id == current_user.id:
        return jsonify({"error": "can't delete yourself"}), 400
    conn = get_db()
    user = conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "user not found"}), 404
    # Delete related data
    conn.execute("DELETE FROM assignments WHERE giver_id = ? OR receiver_id = ?", (user_id, user_id))
    conn.execute("DELETE FROM exclusions WHERE user_id = ? OR excluded_user_id = ?", (user_id, user_id))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"deleted": user_id, "name": user["name"]})


# ── Admin: Exclusions ────────────────────────────────────────────────
@app.route("/api/admin/exclusions", methods=["GET"])
@login_required
def api_admin_exclusions():
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    exclusions = conn.execute("""
        SELECT e.id, u1.name as user_name, u2.name as excluded_name
        FROM exclusions e
        JOIN users u1 ON e.user_id = u1.id
        JOIN users u2 ON e.excluded_user_id = u2.id
        ORDER BY u1.name, u2.name
    """).fetchall()
    conn.close()
    return jsonify([{
        "id": e["id"],
        "user": e["user_name"],
        "excluded": e["excluded_name"]
    } for e in exclusions])


@app.route("/api/admin/exclusions", methods=["POST"])
@login_required
def api_admin_add_exclusion():
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json()
    user_id = data.get("user_id")
    excluded_user_id = data.get("excluded_user_id")
    if not user_id or not excluded_user_id or user_id == excluded_user_id:
        return jsonify({"error": "need two different users"}), 400
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO exclusions (user_id, excluded_user_id) VALUES (?, ?)",
            (user_id, excluded_user_id)
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
    conn.execute("DELETE FROM exclusions WHERE id = ?", (exclusion_id,))
    conn.commit()
    conn.close()
    return jsonify({"deleted": exclusion_id})


# ── Admin: Trigger Draw ──────────────────────────────────────────────
@app.route("/api/admin/draw", methods=["POST"])
@login_required
def api_admin_draw():
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    users = conn.execute("SELECT id, name FROM users ORDER BY id").fetchall()
    n = len(users)

    if n < 2:
        conn.close()
        return jsonify({"error": "need at least 2 users"}), 400

    # Build exclusion lookup
    user_ids = [u["id"] for u in users]
    user_map = {u["id"]: u["name"] for u in users}
    exclusion_pairs = set()
    for u in users:
        rows = conn.execute(
            "SELECT excluded_user_id FROM exclusions WHERE user_id = ?", (u["id"],)
        ).fetchall()
        for r in rows:
            exclusion_pairs.add((u["id"], r["excluded_user_id"]))

    # Clear old assignments
    conn.execute("DELETE FROM assignments")

    # Generate derangement respecting exclusions
    import random
    assignments = None
    for attempt in range(10000):
        shuffled = list(user_ids)
        # Fisher-Yates shuffle
        for i in range(n - 1, 0, -1):
            j = random.randint(0, i)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]

        valid = True
        for i in range(n):
            giver = user_ids[i]
            receiver = shuffled[i]
            # Can't draw self
            if giver == receiver:
                valid = False
                break
            # Can't draw someone they excluded
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

    # Insert assignments
    for a in assignments:
        conn.execute(
            "INSERT INTO assignments (giver_id, receiver_id) VALUES (?, ?)",
            (a["giver_id"], a["receiver_id"])
        )
    conn.commit()
    conn.close()

    # Build readable result
    result = []
    for a in assignments:
        result.append({
            "giver": user_map[a["giver_id"]],
            "receiver": user_map[a["receiver_id"]]
        })
    result.sort(key=lambda x: x["giver"].lower())

    return jsonify({"assignments": result, "message": f"Draw completed! {n} assignments made."})


@app.route("/api/admin/reset", methods=["POST"])
@login_required
def api_admin_reset():
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    conn.execute("DELETE FROM assignments")
    conn.commit()
    conn.close()
    return jsonify({"message": "Assignments cleared"})


# ── User: Self Exclusions ────────────────────────────────────────────
@app.route("/api/user/exclusions", methods=["GET"])
@login_required
def api_user_exclusions():
    conn = get_db()
    my_exclusions = conn.execute(
        "SELECT e.id, u2.name FROM exclusions e JOIN users u2 ON e.excluded_user_id = u2.id WHERE e.user_id = ?",
        (current_user.id,)
    ).fetchall()
    # All other users (excluding self)
    others = conn.execute(
        "SELECT id, name FROM users WHERE id != ? ORDER BY name", (current_user.id,)
    ).fetchall()
    conn.close()
    return jsonify({
        "excluded": [{"id": e["id"], "name": e["name"]} for e in my_exclusions],
        "others": [{"id": o["id"], "name": o["name"]} for o in others]
    })


@app.route("/api/user/exclusions", methods=["POST"])
@login_required
def api_user_add_exclusion():
    data = request.get_json()
    excluded_user_id = data.get("excluded_user_id")
    if not excluded_user_id or excluded_user_id == current_user.id:
        return jsonify({"error": "invalid"}), 400
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO exclusions (user_id, excluded_user_id) VALUES (?, ?)",
            (current_user.id, excluded_user_id)
        )
        conn.commit()
        name = conn.execute("SELECT name FROM users WHERE id = ?", (excluded_user_id,)).fetchone()["name"]
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
        "SELECT u.name FROM assignments a JOIN users u ON a.receiver_id = u.id WHERE a.giver_id = ?",
        (current_user.id,)
    ).fetchone()
    conn.close()
    if row:
        return jsonify({"name": row["name"]})
    return jsonify({"name": None, "message": "No assignment yet. Ask the admin to draw!"})


# ── Seed Admin Account ───────────────────────────────────────────────
def seed_admin():
    """Create default admin if no users exist."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    if count == 0:
        conn = get_db()
        conn.execute(
            "INSERT INTO users (name, password_hash, is_admin) VALUES (?, ?, 1)",
            ("admin", generate_password_hash("secret"))
        )
        conn.commit()
        conn.close()
        print("Created default admin account: admin / secret")


# ── Bootstrap ────────────────────────────────────────────────────────
init_db()
seed_admin()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"🎅 Secret Santa running at http://{host}:{port}")
    print(f"   Default admin: admin / secret")
    print(f"   Change password after first login!")
    app.run(host=host, port=port, debug=debug)
