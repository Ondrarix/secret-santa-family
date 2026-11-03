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
1. Push the code to a GitHub repo
2. Go to https://render.com
3. Create a new **Web Service**
4. Connect your repo, set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python app.py`
5. Deploy — you get a `https://your-app.onrender.com` URL

### Option B: Railway
1. Go to https://railway.app
2. New project → deploy from GitHub
3. Set build/start commands same as Render
4. Free tier gives you a live URL

## Security Notes

- Passwords are hashed with Werkzeug's security module
- Flask-Login handles session management
- Draw uses cryptographic randomness (`secrets.SystemRandom`)
- For production hosting, use HTTPS (both Render and Railway provide it automatically)
- The SQLite database file contains all data — back it up if needed
- Keep the `SECRET_KEY` as a random string in production

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
