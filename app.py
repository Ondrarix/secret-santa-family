"""
Secret Santa Hosted App
Multi-user Secret Santa with grouped draws and per-group assignments.
"""

import os
import secrets
import string
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
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            year INTEGER NOT NULL,
            description TEXT DEFAULT '',
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
    """)
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
def generate_password(length=10):
    """Generate a secure random password."""
    chars = string.ascii_letters + string.digits + "!@"
    while True:
        pw = ''.join(secrets.choice(chars) for _ in range(length))
        if (any(c.isupper() for c in pw) and
            any(c.islower() for c in pw) and
            any(c.isdigit() for c in pw)):
            return pw


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
    conn.close()
    if not user:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "id": user["id"],
        "username": user["username"],
        "name": user["display_name"],
        "is_admin": bool(user["is_admin"]),
        "group_id": user["group_id"]
    })


# ── Admin: Group Management ──────────────────────────────────────────
@app.route("/api/admin/groups", methods=["GET"])
@login_required
def api_admin_groups():
    if not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    conn = get_db()
    groups = conn.execute(
        "SELECT id, name, year, description, created_at FROM groups ORDER BY year DESC, name"
    ).fetchall()
    data = []
    for g in groups:
        user_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE group_id = ?", (g["id"],)
        ).fetchone()["cnt"]
        draw_count = conn.execute(
            "SELECT COUNT(DISTINCT drawn_at) as cnt FROM assignments WHERE group_id = ?", (g["id"],)
        ).fetchone()["cnt"]
        data.append({
            "id": g["id"],
            "name": g["name"],
            "year": g["year"],
            "description": g["description"],
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
    year = data.get("year", 2024)
    description = data.get("description", "").strip()
    if not name:
        return jsonify({"error": "group name required"}), 400
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO groups (name, year, description) VALUES (?, ?, ?)",
            (name, year, description)
        )
        conn.commit()
        group_id = cur.lastrowid
    except sqlite3.IntegrityError as e:
        conn.close()
        return jsonify({"error": str(e)}), 409
    conn.close()
    return jsonify({"id": group_id, "name": name, "year": year})


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
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"deleted": user_id, "name": user["display_name"]})


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
    exclusions = conn.execute("""
        SELECT e.id, u1.display_name as user_name, u2.display_name as excluded_name
        FROM exclusions e
        JOIN users u1 ON e.user_id = u1.id
        JOIN users u2 ON e.excluded_user_id = u2.id
        WHERE u1.group_id = ?
        ORDER BY u1.display_name, u2.display_name
    """, (group_id,)).fetchall()
    conn.close()
    return jsonify([{
        "id": e["id"],
        "user": e["user_name"],
        "excluded": e["excluded_name"]
    } for e in exclusions])


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

    for name in FAMILY_USERS:
        pw = generate_password(10)
        username = sanitize_username(name)
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, group_id) VALUES (?, ?, ?, ?)",
            (username, generate_password_hash(pw), name, group_id)
        )
    conn.commit()
    conn.close()
    print(f"Created family group 'Rodina 2024' with {len(FAMILY_USERS)} users")
    print("\nUser credentials:")
    for name in FAMILY_USERS:
        username = sanitize_username(name)
        pw = generate_password(10)
        print(f"  {name:12s}  →  {username:12s}  /  {pw}")


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
    # Seed family group (must come after admin creates group_id=1)
    seed_family_group()
    app.run(host=host, port=port, debug=debug)
