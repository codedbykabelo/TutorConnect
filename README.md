# TutorConnect

A responsive peer-tutoring platform with a Python standard-library backend, SQLite storage, and an installable Progressive Web App.

## Run locally

Requires Python 3.10 or newer; no pip packages or Node.js are required.

1. Open a terminal in `tutorconnect_app`.
2. Run `python server.py` (or `python3 server.py`).
3. Visit **http://localhost:8000**.

SQLite creates `tutorconnect.db` on first start. When a later startup needs to migrate an existing database, the application saves a timestamped `tutorconnect.db.pre-upgrade-*.bak` copy before changing the schema. Keep the database and backup together when moving the project.

## Explore the platform

- Browse 20 included demonstration tutor profiles, their module specialisations and automatically generated local portraits.
- Search by tutor name, module or skill; filter for tutors with open availability.
- Register as a student or tutor. Tutor accounts can add future availability; students can book and cancel sessions.
- Each tutor can have up to five distinct learners with active confirmed bookings across all of their modules. Multiple sessions for the same learner count once. Booking and capacity checks run inside a serialized database transaction.
- Student, tutor and administrator dashboards show relevant sessions and platform statistics. The calendar displays upcoming available slots and confirmed sessions.
- The demonstration administrator account is `admin@tutorconnect.local` / `Admin123!`. Change or disable these credentials before hosting the application publicly.

Demo tutor accounts are browseable and bookable, but are not login accounts. They are created automatically when the database is initialized. Demo profiles do not inflate the administrator's registered-student or registered-tutor totals.

## Install the app

The web manifest includes 192 px and 512 px app icons. In a compatible browser, use **Install app** or **Add to Home Screen**. Local installation is supported on `localhost`; public hosting should use HTTPS. The service worker caches the interface and avatars for offline loading. Authentication, searching and booking still require a running backend connection.

## Technology and deployment notes

- Frontend: HTML, CSS, vanilla JavaScript.
- Backend and persistence: Python `http.server`, JSON endpoints and SQLite.
- Passwords: salted PBKDF2-SHA256 hashes.
- Sessions: stored in server memory and cleared on restart.
- Development server: intended for local development and demonstration. Before public deployment, configure a production WSGI/ASGI server, HTTPS, persistent sessions, rate limits, CSRF protection, account recovery, credential management, backups and monitoring.
- There is no payment processing, messaging, video calling or external profile-image service.
