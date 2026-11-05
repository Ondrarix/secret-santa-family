# 🎅 Secret Santa — Family Edition

A multi-user Secret Santa app with **grouped draws**, private assignments, and per-group exclusions.

## Features

- **Grouped draws** — create multiple Secret Santa groups (e.g. Office 2024, Family 2024)
- **Private assignments** — each person only sees their own gift recipient
- **Pre-registered users** — admin creates accounts; users log in with username + password (no self-registration)
- **Partner exclusions** — family members can exclude themselves from drawing their partner
- **Admin panel** — manage groups, participants, exclusions, and trigger draws
- **Auto-generated credentials** — admin can generate random usernames/passwords for users
- **Secure draw** — cryptographic randomness (secrets.SystemRandom)
- **Festive UI** — dark theme with confetti animations
- **Runs locally** — no external services needed, everything stores in a local SQLite database

## Quick Start (Local Network)

### 1. Install Python

Download from: https://www.python.org/downloads/

During install, check **"Add Python to PATH"**.

### 2. Install Dependencies

Open Command Prompt in the app folder and run:

```
pip install -r requirements.txt
```

### 3. Start the Server

**Option A — Double-click:**
```
start.bat
```

**Option B — Command line:**
```
python app.py
```

The server starts at `http://localhost:5000`

### 4. Access from Your Network

On your Windows machine, find your local IP:
```
ipconfig
```

Look for **IPv4 Address** under your active network (e.g., `192.168.1.42`).

Family members can access the app from any device on your WiFi by going to:
```
http://192.168.1.42:5000
```

### 5. First Login

Default admin account:
- **Username:** `admin`
- **Password:** `secret`

⚠️ **Change the admin password after first login!**

## Default Family Group (2024)

On first run, the app creates:
- **Group:** "Rodina 2024" (Family Secret Santa 2024)
- **6 pre-registered users:** Maminka, Tatínek, Danuška, Káčí, Óňa, Nezuš

Each user gets a random 10-character password. Share these credentials with your family members.

## How It Works

### Admin Panel (`/admin`)

1. **Create groups** — give each group a name and year (e.g. "Office 2024", "Rodina 2024")
2. **Add participants** — add people to a specific group (auto-generate username + password, or set manually)
3. **View credentials** — click "View" next to a user to see their login username
4. **Regenerate passwords** — click "Regenerate All Passwords" to give everyone new passwords
5. **Set exclusions** — pick two people in the same group to exclude each other
6. **Draw assignments** — click "Draw Now!" to generate a draw for the selected group
7. **Reset** — clear assignments without deleting users

### User Dashboard

1. **Log in** with username and password
2. **See only your own assignment** — you never see who others drew
3. **Set your own exclusions** — people in your group you don't want to draw
4. **Change password** — update your password anytime

### Draw Algorithm

- Fisher-Yates shuffle with CSPRNG (`secrets.SystemRandom`)
- No self-assignments (derangement)
- Respects all exclusion constraints
- Up to 10,000 attempts per draw before failing
- Admin can retry if the algorithm can't find a valid assignment

## File Structure

```
secret-santa-hosted/
├── app.py                 # Flask backend + SQLite database
├── requirements.txt       # Python dependencies
├── start.bat              # Windows launcher
├── README.md              # This file
├── templates/
│   ├── base.html          # Base layout
│   ├── login.html         # Login page (username + password)
│   ├── dashboard.html     # User dashboard
│   └── admin.html         # Admin panel (groups, users, draws)
├── static/
│   └── style.css          # All styling
└── secret_santa.db        # SQLite database (auto-created)
```

## Cloud Deployment (Optional)

### Option A: Render (Recommended)

This repo includes a `render.yaml` blueprint and a `Procfile`, so Render can
configure everything automatically.

1. Push the code to a GitHub repo
2. Go to https://render.com → **New → Blueprint**, connect the repo
3. Render reads `render.yaml`:
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `gunicorn app:app --bind 0.0.0.0:$PORT`
   - **SECRET_KEY** is auto-generated and kept stable (sessions survive restarts)
   - **FLASK_DEBUG** is set to `0` (debugger OFF in production)
4. Deploy — you get a `https://your-app.onrender.com` URL

> ⚠️ **Data persistence:** Render's free tier has an *ephemeral* filesystem —
> the SQLite database resets on every deploy/restart. For data that must
> survive, attach a **Render Disk** or migrate to Postgres.

### Manual setup (any host)

Set these environment variables, then run the start command:

| Variable | Purpose | Example |
|----------|---------|---------|
| `SECRET_KEY` | **Required in production.** Stable session key. | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FLASK_DEBUG` | Leave unset or `0` in production. | `0` |
| `PORT` | Port to bind. | `5000` |

```
pip install -r requirements.txt
gunicorn app:app --bind 0.0.0.0:$PORT
```

### Option B: Railway
1. Go to https://railway.app
2. New project → deploy from GitHub
3. Railway uses the included `Procfile` automatically
4. Set `SECRET_KEY` (and `FLASK_DEBUG=0`) in the service's variables

## Security Notes

- Passwords are hashed with Werkzeug's security module (scrypt)
- Flask-Login handles session management; cookies are `HttpOnly` + `SameSite=Lax`,
  and `Secure` in production (set `INSECURE_COOKIES=1` only for local HTTP testing)
- **CSRF protection** (Flask-WTF) guards every state-changing request
- **Login rate limiting** — 10 attempts per IP per 5 minutes
- Draw uses cryptographic randomness (`secrets.SystemRandom`)
- Debugger is OFF by default (`FLASK_DEBUG` must be explicitly `1` to enable)
- `SECRET_KEY` **must** be set in production — the app refuses to start without it
- For production hosting, use HTTPS (both Render and Railway provide it automatically)
- The SQLite database file contains all data — back it up if needed

## Troubleshooting

**"Port 5000 already in use"**
- Change the port: `set PORT=8080 && python app.py`
- Or close the other program using port 5000

**Firewall blocks access**
- Windows Defender Firewall → Allow an app → Allow Flask/Python through private and public networks
- Or create an inbound rule for port 5000

**Can't find local IP**
- Run `ipconfig` in Command Prompt
- Look for "IPv4 Address" under Wi-Fi or Ethernet adapter
- Family must be on the same WiFi network

**Database corrupted**
- Delete `secret_santa.db` (you'll lose data)
- Restart the app — fresh database is created automatically

## Customization

Edit `static/style.css` to change colors. Key variables:
- `--primary`: Main green (#2ecc71)
- `--danger`: Red for actions (#e74c3c)
- `--info`: Blue (#3498db)
- `--admin`: Gold (#f1c40f)
