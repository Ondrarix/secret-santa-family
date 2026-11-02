# 🎅 Secret Santa — Hosted Family Edition

A multi-user Secret Santa app with private assignments and partner exclusions.

## Features

- **Private assignments** — each person only sees their own gift recipient
- **Partner exclusions** — family members can exclude themselves from drawing their partner
- **Admin panel** — manage participants, exclusions, and trigger the draw
- **Snowflake animation & confetti** — festive UI
- **Runs locally** — no external services needed, everything stores in a local SQLite database

## Quick Start (Local Network)

### 1. Install Python

Download from: https://www.python.org/downloads/

During install, check **"Add Python to PATH"**.

### 2. Install Dependencies

Open Command Prompt in the app folder and run:

```
pip install flask flask-login werkzeug python-dotenv
```

Or run the included script (if pip is available):

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
- **Name:** `admin`
- **Password:** `secret`

⚠️ **Change the admin password after first login!** Create your own admin account via the API or SQL, then delete the default.

## How It Works

### Admin Panel (`/admin`)
- Add participants (name + password for each person)
- Set exclusions (e.g., "Alice doesn't want to draw Bob")
- Click "Draw Now!" to generate all assignments
- Reset assignments without deleting users

### User Dashboard (`/`)
- Log in with your name and password
- See only your own assignment (click to reveal)
- Set your own exclusions (partner you don't want to draw)
- Admin can override individual exclusions from the admin panel

### Draw Algorithm
- Fisher-Yates shuffle with derangement (no self-assignments)
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
│   ├── login.html         # Login page
│   ├── dashboard.html     # User dashboard
│   └── admin.html         # Admin panel
├── static/
│   └── style.css          # All styling
└── secret_santa.db        # SQLite database (auto-created)
```

## Cloud Deployment (Optional)

If you want remote access (outside your home network), deploy to a free service:

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

### Option C: PythonAnywhere
1. Go to https://www.pythonanywhere.com
2. Free tier → Web tab → Flask
3. Upload the files
4. Set WSGI config to point to `app.py`

## Security Notes

- Passwords are hashed with Werkzeug's security module
- Flask-Login handles session management
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
