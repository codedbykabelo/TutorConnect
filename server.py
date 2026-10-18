from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
DB = ROOT / "tutorconnect.db"
MAX_LEARNERS_PER_TUTOR = 5
SESSIONS: dict[str, int] = {}

DEMO_TUTORS = (
    ("Aisha Patel", "Python", "Python, Data Analysis", "Aisha helps students build confidence with Python fundamentals, problem solving and practical data projects."),
    ("Ethan Morgan", "Java", "Java, Object-Oriented Programming", "Ethan makes object-oriented programming easier to understand, from classes and inheritance to clean Java projects."),
    ("Lerato Mokoena", "Mathematics", "Mathematics, Statistics", "Lerato supports students with algebra, calculus and statistics through patient, step-by-step explanations."),
    ("Noah Williams", "HTML", "HTML, CSS", "Noah helps beginners turn design ideas into accessible, responsive pages with modern HTML and CSS."),
    ("Thandiwe Nkosi", "SQL", "SQL, Database Systems", "Thandiwe teaches relational database design, SQL queries and practical data modelling."),
    ("Liam Chen", "JavaScript", "JavaScript, HTML, CSS", "Liam guides learners through JavaScript fundamentals and interactive web application development."),
    ("Amara Okafor", "Operating Systems", "Operating Systems, Computer Networks", "Amara explains operating system concepts and computer networking with clear diagrams and examples."),
    ("Sofia Martinez", "Accounting", "Accounting, Business Management", "Sofia helps students master accounting principles, financial statements and business decision-making."),
    ("Jayden Smith", "Physics", "Physics, Mathematics", "Jayden makes mechanics, electricity and mathematical problem solving approachable and engaging."),
    ("Priya Nair", "Software Engineering", "Software Engineering, Java", "Priya shares practical techniques for requirements, testing, teamwork and maintainable software."),
    ("Daniel Kim", "Python", "Python, SQL", "Daniel helps students combine Python programming and SQL to solve useful real-world problems."),
    ("Naledi Dlamini", "Statistics", "Statistics, Mathematics", "Naledi teaches probability, statistical inference and data interpretation with confidence-building practice."),
    ("Miguel Santos", "HTML", "HTML, CSS, JavaScript", "Miguel supports aspiring web developers from their first semantic page to polished interactive interfaces."),
    ("Chloe Bennett", "Computer Networks", "Computer Networks, Operating Systems", "Chloe breaks down networking protocols, systems concepts and the foundations of the internet."),
    ("Kamo Tshabalala", "Business Management", "Business Management, Accounting", "Kamo helps learners connect management theory with practical business and accounting scenarios."),
    ("Oliver Brown", "Database Systems", "Database Systems, SQL", "Oliver teaches database normalisation, relational modelling and writing reliable SQL queries."),
    ("Zanele Khumalo", "CSS", "CSS, HTML, User Interface Design", "Zanele helps students create responsive layouts and accessible, thoughtful user interfaces."),
    ("Arjun Desai", "Java", "Java, Algorithms", "Arjun works through Java programming, data structures and algorithms one clear step at a time."),
    ("Grace Wilson", "Physics", "Physics, Statistics", "Grace supports students with physics fundamentals, experimental data and statistical reasoning."),
    ("Refiloe Molefe", "Software Engineering", "Software Engineering, Business Management", "Refiloe brings software projects to life with practical guidance on planning, collaboration and delivery."),
)

AVATAR_BACKGROUNDS = ("#ede9fe", "#fce7f3", "#dbeafe", "#dcfce7", "#ffedd5", "#cffafe")
AVATAR_SKIN = ("#f2c6a0", "#d9a17b", "#8d5b43", "#eac09a", "#b97b5b", "#f3d2b2")
AVATAR_HAIR = ("#38251e", "#241a17", "#493324", "#292d3d", "#633d30", "#30221d")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=15000")
    return connection


def hashpass(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 180000).hex()
    return f"{salt}:{digest}"


def checkpass(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split(":")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 180000).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False


def backup_database(connection: sqlite3.Connection) -> Path:
    backup = ROOT / f"tutorconnect.db.pre-upgrade-{dt.datetime.now():%Y%m%d-%H%M%S-%f}.bak"
    target = sqlite3.connect(backup)
    try:
        connection.backup(target)
    finally:
        target.close()
    return backup


def init() -> None:
    with connect() as connection:
        existing = {row["name"] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "users" in existing:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
            missing_columns = {"specialties", "is_demo"} - columns
            if missing_columns:
                backup_database(connection)

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student','tutor','admin')),
                subject TEXT NOT NULL DEFAULT '',
                bio TEXT NOT NULL DEFAULT '',
                specialties TEXT NOT NULL DEFAULT '',
                is_demo INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS slots (
                id INTEGER PRIMARY KEY,
                tutor_id INTEGER NOT NULL REFERENCES users(id),
                start TEXT NOT NULL,
                UNIQUE(tutor_id,start)
            );
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY,
                slot_id INTEGER NOT NULL REFERENCES slots(id),
                student_id INTEGER NOT NULL REFERENCES users(id),
                status TEXT NOT NULL DEFAULT 'confirmed',
                created_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_slot
                ON bookings(slot_id) WHERE status='confirmed';
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
        if "specialties" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN specialties TEXT NOT NULL DEFAULT ''")
        if "is_demo" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")

        if not connection.execute("SELECT id FROM users WHERE role='admin'").fetchone():
            connection.execute(
                "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                ("Administrator", "admin@tutorconnect.local", hashpass("Admin123!"), "admin"),
            )
        seed_demo_tutors(connection)


def seed_demo_tutors(connection: sqlite3.Connection) -> None:
    for index, (name, subject, specialties, bio) in enumerate(DEMO_TUTORS, start=1):
        email = f"tutor{index:02d}@demo.tutorconnect.local"
        existing = connection.execute(
            "SELECT id FROM users WHERE email=? AND role='tutor' AND is_demo=1", (email,)
        ).fetchone()
        if not existing:
            connection.execute(
                """
                INSERT OR IGNORE INTO users(name,email,password,role,subject,bio,specialties,is_demo)
                VALUES(?,?,?,?,?,?,?,1)
                """,
                (name, email, hashpass(secrets.token_urlsafe(32)), "tutor", subject, bio, specialties),
            )
        tutor = connection.execute(
            "SELECT id,role,is_demo FROM users WHERE email=?", (email,)
        ).fetchone()
        if not tutor or tutor["role"] != "tutor" or not tutor["is_demo"]:
            continue
        for day_offset, hour in ((1, 10), (2, 14), (4, 16)):
            start = (dt.datetime.now() + dt.timedelta(days=day_offset)).replace(
                hour=hour, minute=0, second=0, microsecond=0
            )
            if start <= dt.datetime.now():
                start += dt.timedelta(days=1)
            connection.execute(
                "INSERT OR IGNORE INTO slots(tutor_id,start) VALUES(?,?)",
                (tutor["id"], start.isoformat(timespec="minutes")),
            )


def learner_count(connection: sqlite3.Connection, tutor_id: int) -> int:
    row = connection.execute(
        """
        SELECT COUNT(DISTINCT b.student_id) AS learners
        FROM bookings b JOIN slots s ON s.id=b.slot_id
        WHERE s.tutor_id=? AND b.status='confirmed'
        """,
        (tutor_id,),
    ).fetchone()
    return int(row["learners"])


def capacity_details(connection: sqlite3.Connection, tutor_id: int) -> dict[str, int]:
    learners = learner_count(connection, tutor_id)
    return {
        "learner_count": learners,
        "capacity": MAX_LEARNERS_PER_TUTOR,
        "spaces_remaining": max(0, MAX_LEARNERS_PER_TUTOR - learners),
    }


def avatar_path(user_id: int) -> str:
    return f"/avatars/{user_id}.svg"


def public_user(connection: sqlite3.Connection, user: sqlite3.Row) -> dict[str, object]:
    details: dict[str, object] = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "subject": user["subject"],
        "bio": user["bio"],
        "specialties": user["specialties"],
        "avatar": avatar_path(user["id"]),
    }
    if user["role"] == "tutor":
        details.update(capacity_details(connection, user["id"]))
    return details


def tutor_rows(
    connection: sqlite3.Connection, query: str = "", module: str = "", available: bool = False
) -> list[dict[str, object]]:
    query_like = f"%{query.strip().lower()}%"
    module_pattern = f"%,{module.strip().lower()},%"
    sql = """
        SELECT u.id,u.name,u.subject,u.bio,u.specialties,
            COUNT(DISTINCT CASE WHEN b.status='confirmed' THEN b.student_id END) learner_count,
            MAX(0, ? - COUNT(DISTINCT CASE WHEN b.status='confirmed' THEN b.student_id END)) spaces_remaining,
            (SELECT COUNT(*) FROM slots sl
             WHERE sl.tutor_id=u.id AND sl.start>?
               AND NOT EXISTS (
                   SELECT 1 FROM bookings active
                   WHERE active.slot_id=sl.id AND active.status='confirmed'
               )) AS available_slots,
            (SELECT MIN(sl.start) FROM slots sl
             WHERE sl.tutor_id=u.id AND sl.start>?
               AND NOT EXISTS (
                   SELECT 1 FROM bookings active
                   WHERE active.slot_id=sl.id AND active.status='confirmed'
               )) AS next_available
        FROM users u
        LEFT JOIN slots s ON s.tutor_id=u.id
        LEFT JOIN bookings b ON b.slot_id=s.id
        WHERE u.role='tutor'
          AND (lower(u.name) LIKE ? OR lower(u.subject) LIKE ?
               OR lower(u.specialties) LIKE ? OR lower(u.bio) LIKE ?)
    """
    params: list[object] = [
        MAX_LEARNERS_PER_TUTOR,
        dt.datetime.now().isoformat(timespec="minutes"),
        dt.datetime.now().isoformat(timespec="minutes"),
        query_like, query_like, query_like, query_like,
    ]
    if module:
        sql += """
          AND (lower(u.subject)=? OR lower(u.specialties) LIKE ?
               OR lower(u.specialties) LIKE ? OR lower(u.specialties) LIKE ?)
        """
        module_lower = module.strip().lower()
        params.extend([
            module_lower,
            module_pattern,
            f"{module_lower},%",
            f"%,{module_lower}",
        ])
    sql += " GROUP BY u.id ORDER BY u.is_demo ASC,u.name COLLATE NOCASE"
    rows = [dict(row) for row in connection.execute(sql, params).fetchall()]
    for row in rows:
        row["capacity"] = MAX_LEARNERS_PER_TUTOR
        row["fully_booked"] = row["spaces_remaining"] == 0
        row["avatar"] = avatar_path(int(row["id"]))
    if available:
        rows = [row for row in rows if row["available_slots"] and not row["fully_booked"]]
    return rows


def calendar_events(connection: sqlite3.Connection, user: sqlite3.Row | None) -> list[dict[str, object]]:
    now = dt.datetime.now().isoformat(timespec="minutes")
    events = [
        dict(row) for row in connection.execute(
            """
            SELECT s.id,s.start,u.name tutor,u.subject,1 available
            FROM slots s JOIN users u ON u.id=s.tutor_id
            WHERE s.start>? AND NOT EXISTS (
                SELECT 1 FROM bookings b WHERE b.slot_id=s.id AND b.status='confirmed'
            ) AND (SELECT COUNT(DISTINCT b.student_id) FROM bookings b
                   JOIN slots existing ON existing.id=b.slot_id
                   WHERE existing.tutor_id=u.id AND b.status='confirmed')<?
            ORDER BY s.start LIMIT 150
            """,
            (now, MAX_LEARNERS_PER_TUTOR),
        ).fetchall()
    ]
    if user:
        if user["role"] == "student":
            bookings = connection.execute(
                """
                SELECT b.id,s.id slot_id,s.start,t.name tutor,t.subject,0 available,b.status
                FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN users t ON t.id=s.tutor_id
                WHERE b.student_id=? AND b.status='confirmed' AND s.start>?
                ORDER BY s.start
                """,
                (user["id"], now),
            ).fetchall()
        elif user["role"] == "tutor":
            bookings = connection.execute(
                """
                SELECT b.id,s.id slot_id,s.start,l.name student,t.subject,0 available,b.status
                FROM bookings b JOIN slots s ON s.id=b.slot_id JOIN users l ON l.id=b.student_id
                WHERE s.tutor_id=? AND b.status='confirmed' AND s.start>?
                ORDER BY s.start
                """,
                (user["id"], now),
            ).fetchall()
        else:
            bookings = []
        for row in bookings:
            event = dict(row)
            event["id"] = event.pop("slot_id")
            event["available"] = 0
            events.append(event)
    return sorted(events, key=lambda event: str(event["start"]))


def dashboard_stats(connection: sqlite3.Connection, user: sqlite3.Row) -> dict[str, object]:
    now = dt.datetime.now().isoformat(timespec="minutes")
    if user["role"] == "student":
        available = connection.execute(
            """
            SELECT COUNT(*) FROM users u WHERE u.role='tutor'
            AND (SELECT COUNT(DISTINCT b.student_id) FROM bookings b JOIN slots s ON s.id=b.slot_id
                 WHERE s.tutor_id=u.id AND b.status='confirmed')<?
            AND EXISTS (
                SELECT 1 FROM slots s WHERE s.tutor_id=u.id AND s.start>?
                AND NOT EXISTS (
                    SELECT 1 FROM bookings b WHERE b.slot_id=s.id AND b.status='confirmed'
                )
            )
            """,
            (MAX_LEARNERS_PER_TUTOR, now),
        ).fetchone()[0]
        upcoming = connection.execute(
            """
            SELECT COUNT(*) FROM bookings b JOIN slots s ON s.id=b.slot_id
            WHERE b.student_id=? AND b.status='confirmed' AND s.start>?
            """,
            (user["id"], now),
        ).fetchone()[0]
        total = connection.execute(
            "SELECT COUNT(*) FROM bookings WHERE student_id=? AND status='confirmed'",
            (user["id"],),
        ).fetchone()[0]
        history = connection.execute(
            """
            SELECT COUNT(*) FROM bookings b JOIN slots s ON s.id=b.slot_id
            WHERE b.student_id=? AND (b.status!='confirmed' OR s.start<=?)
            """,
            (user["id"], now),
        ).fetchone()[0]
        return {
            "available_tutors": available, "upcoming_sessions": upcoming,
            "active_bookings": total, "booking_history": history,
        }
    if user["role"] == "tutor":
        upcoming = connection.execute(
            """
            SELECT COUNT(*) FROM bookings b JOIN slots s ON s.id=b.slot_id
            WHERE s.tutor_id=? AND b.status='confirmed' AND s.start>?
            """,
            (user["id"], now),
        ).fetchone()[0]
        active_learners = learner_count(connection, user["id"])
        slots = connection.execute(
            """
            SELECT COUNT(*) FROM slots s WHERE s.tutor_id=? AND s.start>?
            AND NOT EXISTS (SELECT 1 FROM bookings b WHERE b.slot_id=s.id AND b.status='confirmed')
            """,
            (user["id"], now),
        ).fetchone()[0]
        return {
            **capacity_details(connection, user["id"]),
            "upcoming_sessions": upcoming,
            "available_slots": slots,
            "assigned_modules": [item.strip() for item in user["specialties"].split(",") if item.strip()]
            or ([user["subject"]] if user["subject"] else []),
            "active_learners": active_learners,
        }
    students = connection.execute(
        "SELECT COUNT(*) FROM users WHERE role='student' AND is_demo=0"
    ).fetchone()[0]
    tutors = connection.execute(
        "SELECT COUNT(*) FROM users WHERE role='tutor' AND is_demo=0"
    ).fetchone()[0]
    bookings = connection.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    full = connection.execute(
        """
        SELECT COUNT(*) FROM users u WHERE u.role='tutor'
          AND (SELECT COUNT(DISTINCT b.student_id) FROM bookings b
               JOIN slots s ON s.id=b.slot_id
               WHERE s.tutor_id=u.id AND b.status='confirmed')>=?
        """,
        (MAX_LEARNERS_PER_TUTOR,),
    ).fetchone()[0]
    capacities = [
        {
            "id": row["id"], "name": row["name"], "subject": row["subject"],
            "is_demo": bool(row["is_demo"]),
            **capacity_details(connection, row["id"]),
        }
        for row in connection.execute(
            "SELECT id,name,subject,is_demo FROM users WHERE role='tutor' ORDER BY is_demo,name"
        ).fetchall()
    ]
    return {
        "registered_students": students, "registered_tutors": tutors,
        "all_bookings": bookings, "full_capacity_tutors": full,
        "tutor_capacities": capacities,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def respond(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 20000:
            raise ValueError("Request too large")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object")
        return value

    def auth(self) -> sqlite3.Row | None:
        token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        user_id = SESSIONS.get(token)
        if not user_id:
            return None
        with connect() as connection:
            return connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    def need(self, role: str | None = None) -> sqlite3.Row:
        user = self.auth()
        if not user:
            raise PermissionError("Please log in")
        if role and user["role"] != role:
            raise PermissionError("This action is not allowed for your role")
        return user

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/health":
                return self.respond({"status": "ok"})
            if path == "/api/me":
                user = self.auth()
                if not user:
                    return self.respond({"user": None})
                with connect() as connection:
                    return self.respond({"user": public_user(connection, user)})
            if path == "/api/tutors":
                params = parse_qs(parsed.query)
                query = params.get("q", [""])[0]
                module = params.get("module", [""])[0]
                available = params.get("available", [""])[0].lower() in ("1", "true", "yes")
                with connect() as connection:
                    return self.respond({
                        "tutors": tutor_rows(connection, query, module, available),
                        "modules": sorted({
                            subject.strip()
                            for row in connection.execute(
                                "SELECT subject,specialties FROM users WHERE role='tutor'"
                            )
                            for subject in ([row["subject"]] + row["specialties"].split(","))
                            if subject.strip()
                        }, key=str.casefold),
                    })
            if path == "/api/slots":
                tutor = int(parse_qs(parsed.query).get("tutor", ["0"])[0])
                now = dt.datetime.now().isoformat(timespec="minutes")
                with connect() as connection:
                    user = connection.execute(
                        "SELECT id,name,subject FROM users WHERE id=? AND role='tutor'", (tutor,)
                    ).fetchone()
                    if not user:
                        return self.respond({"error": "Tutor not found"}, 404)
                    slots = connection.execute(
                        """
                        SELECT s.id,s.tutor_id,s.start FROM slots s
                        WHERE s.tutor_id=? AND s.start>? AND NOT EXISTS (
                            SELECT 1 FROM bookings b
                            WHERE b.slot_id=s.id AND b.status='confirmed'
                        ) ORDER BY s.start
                        """,
                        (tutor, now),
                    ).fetchall()
                    capacity = capacity_details(connection, tutor)
                    return self.respond({
                        "tutor": dict(user), "slots": [dict(row) for row in slots],
                        **capacity, "fully_booked": capacity["spaces_remaining"] == 0,
                    })
            if path == "/api/my-slots":
                user = self.need("tutor")
                with connect() as connection:
                    slots = connection.execute(
                        """
                        SELECT s.id,s.start,
                            CASE WHEN b.id IS NULL THEN 'Available' ELSE 'Booked' END status,
                            b.student_id,l.name student
                        FROM slots s
                        LEFT JOIN bookings b ON b.slot_id=s.id AND b.status='confirmed'
                        LEFT JOIN users l ON l.id=b.student_id
                        WHERE s.tutor_id=? ORDER BY s.start
                        """,
                        (user["id"],),
                    ).fetchall()
                    return self.respond({"slots": [dict(row) for row in slots]})
            if path == "/api/bookings":
                user = self.need()
                with connect() as connection:
                    if user["role"] == "student":
                        rows = connection.execute(
                            """
                            SELECT b.id,b.status,s.start,t.id tutor_id,t.name tutor,t.subject,
                                CASE WHEN b.status='confirmed' AND s.start<=? THEN 1 ELSE 0 END completed
                            FROM bookings b JOIN slots s ON s.id=b.slot_id
                            JOIN users t ON t.id=s.tutor_id
                            WHERE b.student_id=? ORDER BY s.start DESC
                            """,
                            (dt.datetime.now().isoformat(timespec="minutes"), user["id"]),
                        ).fetchall()
                    elif user["role"] == "tutor":
                        rows = connection.execute(
                            """
                            SELECT b.id,b.status,s.start,l.id student_id,l.name student,t.name tutor,t.subject,
                                CASE WHEN b.status='confirmed' AND s.start<=? THEN 1 ELSE 0 END completed
                            FROM bookings b JOIN slots s ON s.id=b.slot_id
                            JOIN users l ON l.id=b.student_id JOIN users t ON t.id=s.tutor_id
                            WHERE s.tutor_id=? ORDER BY s.start DESC
                            """,
                            (dt.datetime.now().isoformat(timespec="minutes"), user["id"]),
                        ).fetchall()
                    else:
                        rows = connection.execute(
                            """
                            SELECT b.id,b.status,s.start,l.name student,t.name tutor,t.subject,
                                CASE WHEN b.status='confirmed' AND s.start<=? THEN 1 ELSE 0 END completed
                            FROM bookings b JOIN slots s ON s.id=b.slot_id
                            JOIN users l ON l.id=b.student_id JOIN users t ON t.id=s.tutor_id
                            ORDER BY s.start DESC
                            """,
                            (dt.datetime.now().isoformat(timespec="minutes"),),
                        ).fetchall()
                    return self.respond({"bookings": [dict(row) for row in rows]})
            if path == "/api/calendar":
                user = self.auth()
                with connect() as connection:
                    return self.respond({"events": calendar_events(connection, user)})
            if path == "/api/stats":
                user = self.need()
                with connect() as connection:
                    return self.respond(dashboard_stats(connection, user))
            if path == "/api/admin/users":
                self.need("admin")
                with connect() as connection:
                    rows = connection.execute(
                        """
                        SELECT id,name,email,role,subject,specialties,is_demo
                        FROM users ORDER BY is_demo ASC,id DESC
                        """
                    ).fetchall()
                    users = []
                    for row in rows:
                        item = dict(row)
                        if item["role"] == "tutor":
                            item.update(capacity_details(connection, item["id"]))
                        users.append(item)
                    return self.respond({"users": users})
            if path.startswith("/avatars/") and path.endswith(".svg"):
                user_id = int(Path(unquote(path)).stem)
                with connect() as connection:
                    user = connection.execute(
                        "SELECT id,name FROM users WHERE id=?", (user_id,)
                    ).fetchone()
                if not user:
                    return self.respond({"error": "Avatar not found"}, 404)
                index = user_id % len(AVATAR_BACKGROUNDS)
                initial = user["name"].strip()[:1].upper()
                svg = (
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">'
                    f'<rect width="128" height="128" rx="64" fill="{AVATAR_BACKGROUNDS[index]}"/>'
                    f'<ellipse cx="64" cy="121" rx="43" ry="34" fill="{AVATAR_HAIR[index]}"/>'
                    f'<path d="M42 92h44v22a22 22 0 0 1-44 0z" fill="{AVATAR_SKIN[index]}"/>'
                    f'<ellipse cx="64" cy="58" rx="30" ry="36" fill="{AVATAR_SKIN[index]}"/>'
                    f'<path d="M34 56Q31 20 64 20q34 0 31 38-5-21-22-25-15 15-38 13z" fill="{AVATAR_HAIR[index]}"/>'
                    '<circle cx="53" cy="60" r="2.5" fill="#33241f"/>'
                    '<circle cx="75" cy="60" r="2.5" fill="#33241f"/>'
                    '<path d="M56 75q8 7 16 0" fill="none" stroke="#8b5148" stroke-width="3" stroke-linecap="round"/>'
                    f'<text x="100" y="112" font-family="sans-serif" font-size="20" font-weight="700" fill="#5b21b6">{initial}</text>'
                    '</svg>'
                )
                body = svg.encode()
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/":
                path = "/index.html"
            file_path = (ROOT / path.lstrip("/")).resolve()
            if not file_path.is_relative_to(ROOT) or not file_path.is_file():
                return self.respond({"error": "Not found"}, 404)
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(str(file_path))[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except PermissionError as error:
            self.respond({"error": str(error)}, 403)
        except (ValueError, sqlite3.Error, OSError, json.JSONDecodeError) as error:
            self.respond({"error": str(error)}, 400)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            data = self.body()
            if path == "/api/register":
                name = str(data.get("name", "")).strip()
                email = str(data.get("email", "")).strip().lower()
                password = str(data.get("password", ""))
                role = data.get("role")
                subject = str(data.get("subject", "")).strip()
                specialties = str(data.get("specialties", subject)).strip()
                bio = str(data.get("bio", "")).strip()
                if not name or "@" not in email or len(password) < 8 or role not in ("student", "tutor"):
                    raise ValueError("Enter a name, valid email, password of 8+ characters, and role")
                if role == "tutor" and not subject:
                    raise ValueError("Tutors must provide a subject")
                with connect() as connection:
                    try:
                        connection.execute(
                            """
                            INSERT INTO users(name,email,password,role,subject,bio,specialties)
                            VALUES(?,?,?,?,?,?,?)
                            """,
                            (name, email, hashpass(password), role, subject, bio, specialties),
                        )
                    except sqlite3.IntegrityError as error:
                        raise ValueError("Email is already registered") from error
                return self.respond({"message": "Account created. Please log in."}, 201)
            if path == "/api/login":
                with connect() as connection:
                    user = connection.execute(
                        "SELECT * FROM users WHERE email=?",
                        (str(data.get("email", "")).strip().lower(),),
                    ).fetchone()
                    if not user or not checkpass(str(data.get("password", "")), user["password"]):
                        return self.respond({"error": "Invalid email or password"}, 401)
                    token = secrets.token_urlsafe(32)
                    SESSIONS[token] = user["id"]
                    return self.respond({"token": token, "user": public_user(connection, user)})
            if path == "/api/logout":
                token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
                SESSIONS.pop(token, None)
                return self.respond({"message": "Logged out"})
            if path == "/api/slots":
                user = self.need("tutor")
                start = str(data.get("start", ""))
                try:
                    start_time = dt.datetime.fromisoformat(start)
                except ValueError as error:
                    raise ValueError("Choose a valid date and time") from error
                if start_time.tzinfo is not None:
                    start_time = start_time.astimezone().replace(tzinfo=None)
                if start_time <= dt.datetime.now():
                    raise ValueError("Choose a future time")
                with connect() as connection:
                    try:
                        connection.execute(
                            "INSERT INTO slots(tutor_id,start) VALUES(?,?)",
                            (user["id"], start_time.isoformat(timespec="minutes")),
                        )
                    except sqlite3.IntegrityError as error:
                        raise ValueError("This slot already exists") from error
                return self.respond({"message": "Availability added"}, 201)
            if path == "/api/bookings":
                user = self.need("student")
                try:
                    slot_id = int(data.get("slot_id", 0))
                except (TypeError, ValueError) as error:
                    raise ValueError("Choose a valid time slot") from error
                with connect() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    slot = connection.execute("SELECT * FROM slots WHERE id=?", (slot_id,)).fetchone()
                    now = dt.datetime.now().isoformat(timespec="minutes")
                    if not slot or slot["start"] <= now:
                        raise ValueError("This slot is not available")
                    if slot["tutor_id"] == user["id"]:
                        raise ValueError("You cannot book your own tutoring session")
                    if connection.execute(
                        "SELECT id FROM bookings WHERE slot_id=? AND status='confirmed'",
                        (slot_id,),
                    ).fetchone():
                        raise ValueError("This time has already been booked")
                    current_learners = learner_count(connection, slot["tutor_id"])
                    already_active = connection.execute(
                        """
                        SELECT 1 FROM bookings b JOIN slots s ON s.id=b.slot_id
                        WHERE s.tutor_id=? AND b.student_id=? AND b.status='confirmed' LIMIT 1
                        """,
                        (slot["tutor_id"], user["id"]),
                    ).fetchone()
                    if current_learners >= MAX_LEARNERS_PER_TUTOR and not already_active:
                        raise ValueError("This tutor is fully booked and has no learner spaces remaining")
                    try:
                        connection.execute(
                            "INSERT INTO bookings(slot_id,student_id,created_at) VALUES(?,?,?)",
                            (slot_id, user["id"], dt.datetime.now().isoformat(timespec="seconds")),
                        )
                    except sqlite3.IntegrityError as error:
                        raise ValueError("This time has already been booked") from error
                return self.respond({"message": "Session booked successfully"}, 201)
            if path == "/api/cancel":
                user = self.need()
                try:
                    booking_id = int(data.get("id", 0))
                except (TypeError, ValueError) as error:
                    raise ValueError("Choose a valid booking") from error
                with connect() as connection:
                    booking = connection.execute(
                        """
                        SELECT b.*,s.tutor_id,s.start FROM bookings b
                        JOIN slots s ON s.id=b.slot_id WHERE b.id=?
                        """,
                        (booking_id,),
                    ).fetchone()
                    if (
                        not booking or booking["status"] != "confirmed"
                        or (user["role"] == "student" and booking["student_id"] != user["id"])
                        or (user["role"] == "tutor" and booking["tutor_id"] != user["id"])
                        or user["role"] == "admin"
                    ):
                        raise PermissionError("Cannot cancel this booking")
                    connection.execute(
                        "UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,)
                    )
                return self.respond({"message": "Booking cancelled"})
            return self.respond({"error": "Not found"}, 404)
        except PermissionError as error:
            self.respond({"error": str(error)}, 403)
        except (ValueError, sqlite3.Error, OSError, json.JSONDecodeError) as error:
            self.respond({"error": str(error)}, 400)


if __name__ == "__main__":
    init()
    port = int(os.environ.get("PORT", 8000))
    print(f"TutorConnect running at http://localhost:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
