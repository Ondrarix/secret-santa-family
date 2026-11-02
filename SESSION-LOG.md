# Session Log — 2026-11-02

## Summary

Built and deployed **Secret Santa Family Edition** — a multi-user web app for running Secret Santa draws with partner exclusions.

## What was built

### Core app (single project, `secret-santa-hosted/`)

| File | Purpose |
|------|---------|
| `app.py` | Flask backend with SQLite, user auth, assignment logic |
| `templates/base.html` | Shared layout with navbar |
| `templates/login.html` | Login form |
| `templates/dashboard.html` | User dashboard — see assignment, manage exclusions, change password |
| `templates/admin.html` | Admin panel — user management, exclusion management, draw trigger |
| `static/style.css` | Dark festive theme, mobile responsive |
| `requirements.txt` | Python deps: flask, flask-login, werkzeug, python-dotenv |
| `start.bat` | Windows launcher |

### Features implemented

- **User auth** — Flask-Login, password hashing via werkzeug
- **Private assignments** — each user sees only their own gift recipient
- **Partner exclusions** — users can set exclusions on their dashboard; admin can set any exclusion
- **Draw algorithm** — Fisher-Yates derangement respecting all exclusion constraints
- **Confetti animation** on successful draw
- **Password change** — per-user password change from dashboard
- **Mobile responsive** — works on phones/tablets

### Bug fixes applied

1. Missing `/dashboard` route → added `@app.route("/dashboard")` rendering `dashboard.html`
2. User exclusion deletion broken (no ID in API response) → updated `api_user_exclusions()` to return exclusion IDs, fixed frontend to use IDs for DELETE

## Deployment

- **GitHub repo:** https://github.com/Ondrarix/secret-santa-family
- **Cloud host:** Render (free tier) — `https://<your-app>.onrender.com`
- **Auto-deploy:** pushed code to GitHub, Render auto-deploys on new commits

## Credentials

- **Default admin:** `admin / secret`
- **User:** Ondrarix (GitHub)
- **Git config:** Ondrarix <matatko.o@gmail.com>

## How it works

### User flow
1. Admin logs in → adds participants with name + password
2. Users log in → see their dashboard
3. Users set exclusions (e.g., "I don't want to draw my partner")
4. Admin reviews exclusions → clicks "Draw Now!"
5. Each user sees only their own assignment

### Data model (SQLite)
- `users` — id, name, password_hash, is_admin
- `exclusions` — user_id, excluded_user_id (one-to-many per user)
- `assignments` — giver_id, receiver_id (many-to-one, unique pair)

### API endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /api/me | required | Current user info |
| GET | /api/me/assignment | required | User's assignment |
| POST | /api/me/password | required | Change password |
| GET | /api/user/exclusions | required | User's exclusions + available users |
| POST | /api/user/exclusions | required | Add self exclusion |
| DELETE | /api/user/exclusions/:id | required | Remove self exclusion |
| GET | /api/admin/users | admin only | List all users |
| POST | /api/admin/users | admin only | Add user |
| DELETE | /api/admin/users/:id | admin only | Delete user |
| GET | /api/admin/exclusions | admin only | List all exclusions |
| POST | /api/admin/exclusions | admin only | Add exclusion |
| DELETE | /api/admin/exclusions/:id | admin only | Delete exclusion |
| POST | /api/admin/draw | admin only | Trigger draw |
| POST | /api/admin/reset | admin only | Clear assignments |

## Status

- [x] App built and tested locally
- [x] Code pushed to GitHub
- [x] Deployed on Render
- [x] Bug fix for missing /dashboard route deployed
- [x] Password change UI + API added
- [x] Session documented
- [ ] Family accounts created (pending user action)
- [ ] First draw conducted (pending user action)

## Planned for next session

1. Add family member accounts via admin panel
2. Test the full flow (login → exclusions → draw → reveal)
3. Verify exclusions are respected in the draw
4. Address any bugs or UX issues
