from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from db import get_db
from datetime import datetime
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

PO_PIN = "1234"  # Simple admin PIN — change for production


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return {
        "id": uid,
        "name": session.get("user_name"),
        "email": session.get("user_email"),
        "school": session.get("user_school"),
    }


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("page_login"))
        return f(*args, **kwargs)
    return decorated


def po_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_po"):
            return redirect(url_for("page_po_login"))
        return f(*args, **kwargs)
    return decorated


def po_api_guard():
    if not session.get("is_po"):
        return jsonify({"error": "PO access required"}), 403
    return None


@app.context_processor
def inject_globals():
    return {"current_user": get_current_user(), "is_po": session.get("is_po", False)}


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.get("/")
def page_index():
    return render_template("index.html")


@app.get("/register")
def page_register():
    return render_template("register.html")


@app.get("/login")
def page_login():
    return render_template("login.html")


@app.get("/po/login")
def page_po_login():
    return render_template("po_login.html")


@app.get("/po")
@po_required
def page_po():
    return render_template("po.html")


# ---------------------------------------------------------------------------
# Auth API
# ---------------------------------------------------------------------------

@app.post("/api/register")
def api_register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()
    school = (data.get("school") or "").strip()

    if not email or not password or not name or not school:
        return jsonify({"error": "All fields are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    with get_db() as (conn, cur):
        cur.execute("SELECT id FROM speakers WHERE email = %s", (email,))
        if cur.fetchone():
            return jsonify({"error": "Email already registered"}), 409

        pw_hash = generate_password_hash(password)
        cur.execute(
            "INSERT INTO speakers (email, password_hash, full_name, school) VALUES (%s, %s, %s, %s)",
            (email, pw_hash, name, school),
        )
        conn.commit()
        uid = cur.lastrowid

        session["user_id"] = uid
        session["user_name"] = name
        session["user_email"] = email
        session["user_school"] = school

    return jsonify({"ok": True}), 201


@app.post("/api/login")
def api_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    with get_db() as (conn, cur):
        cur.execute(
            "SELECT id, email, full_name, school, password_hash FROM speakers WHERE email = %s",
            (email,),
        )
        user = cur.fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    session["user_id"] = user["id"]
    session["user_name"] = user["full_name"]
    session["user_email"] = user["email"]
    session["user_school"] = user["school"]
    return jsonify({"ok": True})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.post("/api/po/login")
def api_po_login():
    data = request.get_json(silent=True) or {}
    pin = data.get("pin") or ""
    if not secrets.compare_digest(pin, PO_PIN):
        return jsonify({"error": "Invalid PIN"}), 401
    session["is_po"] = True
    return jsonify({"ok": True})


@app.post("/api/po/logout")
def api_po_logout():
    session.pop("is_po", None)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Legislation API
# ---------------------------------------------------------------------------

@app.get("/api/legislation")
def api_legislation_list():
    with get_db() as (conn, cur):
        cur.execute("SELECT id, school, title, body, leg_order, status, vote_result FROM legislation ORDER BY leg_order")
        rows = cur.fetchall()
    return jsonify({"legislation": rows})


@app.post("/api/legislation")
def api_legislation_create():
    err = po_api_guard()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    school = (data.get("school") or "").strip()
    body = (data.get("body") or "").strip()

    if not title or not school:
        return jsonify({"error": "Title and school are required"}), 400

    with get_db() as (conn, cur):
        cur.execute("SELECT COALESCE(MAX(leg_order), 0) + 1 AS next_order FROM legislation")
        next_order = cur.fetchone()["next_order"]
        cur.execute(
            "INSERT INTO legislation (school, title, body, leg_order) VALUES (%s, %s, %s, %s)",
            (school, title, body, next_order),
        )
        conn.commit()
        lid = cur.lastrowid
    return jsonify({"ok": True, "id": lid}), 201


@app.put("/api/legislation/<int:leg_id>")
def api_legislation_update(leg_id):
    err = po_api_guard()
    if err:
        return err
    data = request.get_json(silent=True) or {}

    fields, values = [], []
    for col in ("title", "school", "body"):
        if col in data:
            fields.append(f"{col} = %s")
            values.append(data[col])
    if not fields:
        return jsonify({"error": "No fields to update"}), 400
    values.append(leg_id)
    with get_db(dictionary=False) as (conn, cur):
        cur.execute(f"UPDATE legislation SET {', '.join(fields)} WHERE id = %s", values)
        conn.commit()
    return jsonify({"ok": True})


@app.delete("/api/legislation/<int:leg_id>")
def api_legislation_delete(leg_id):
    err = po_api_guard()
    if err:
        return err
    with get_db(dictionary=False) as (conn, cur):
        cur.execute("DELETE FROM legislation WHERE id = %s", (leg_id,))
        conn.commit()
    return jsonify({"ok": True})


@app.post("/api/legislation/reorder")
def api_legislation_reorder():
    err = po_api_guard()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    order = data.get("order", [])

    with get_db(dictionary=False) as (conn, cur):
        for i, lid in enumerate(order, 1):
            cur.execute("UPDATE legislation SET leg_order = %s WHERE id = %s", (i, int(lid)))
        conn.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Session / debate control API
# ---------------------------------------------------------------------------

def _iso(dt):
    return dt.isoformat() if dt else None


def _timer_elapsed_seconds(state, now=None):
    if not state:
        return 0

    elapsed = int(state.get("timer_elapsed_seconds") or 0)
    status = state.get("timer_status") or "idle"
    started_at = state.get("timer_started_at")

    if status == "running" and started_at:
        now = now or datetime.now()
        elapsed += max(0, int((now - started_at).total_seconds()))

    return elapsed


def _timer_payload(state, now=None):
    if not state:
        return {"status": "idle", "elapsed_seconds": 0, "started_at": None}

    return {
        "status": state.get("timer_status") or "idle",
        "elapsed_seconds": _timer_elapsed_seconds(state, now=now),
        "started_at": _iso(state.get("timer_started_at")),
    }


def _reset_timer_state(cur, status="idle", elapsed_seconds=0, started_at=None):
    cur.execute(
        "UPDATE session_state SET timer_status = %s, timer_elapsed_seconds = %s, timer_started_at = %s WHERE id = 1",
        (status, elapsed_seconds, started_at),
    )


def _finalize_active_speech_timer(cur):
    cur.execute("SELECT * FROM session_state WHERE id = 1")
    state = cur.fetchone()
    if not state or not state.get("current_speech_id"):
        return 0

    final_elapsed = _timer_elapsed_seconds(state)
    cur.execute(
        "UPDATE speeches SET duration_seconds = %s WHERE id = %s",
        (final_elapsed, state["current_speech_id"]),
    )
    _reset_timer_state(cur, status="stopped", elapsed_seconds=final_elapsed, started_at=None)
    return final_elapsed


def _vote_summary(cur, leg_id, user_id=None):
    cur.execute("SELECT COUNT(*) AS total FROM speakers")
    total = cur.fetchone()["total"]

    cur.execute(
        """
        SELECT
            SUM(CASE WHEN vote_choice = 'for' THEN 1 ELSE 0 END) AS for_count,
            SUM(CASE WHEN vote_choice = 'against' THEN 1 ELSE 0 END) AS against_count
        FROM legislation_votes
        WHERE legislation_id = %s
        """,
        (leg_id,),
    )
    row = cur.fetchone() or {}
    for_count = int(row.get("for_count") or 0)
    against_count = int(row.get("against_count") or 0)
    cast_total = for_count + against_count

    user_vote = None
    if user_id:
        cur.execute(
            "SELECT vote_choice FROM legislation_votes WHERE legislation_id = %s AND speaker_id = %s",
            (leg_id, user_id),
        )
        uv = cur.fetchone()
        user_vote = uv["vote_choice"] if uv else None

    return {
        "for_count": for_count,
        "against_count": against_count,
        "abstain_count": max(0, int(total) - cast_total),
        "total_speakers": int(total),
        "cast_count": cast_total,
        "user_vote": user_vote,
    }


def _speaker_stats(cur, leg_id):
    cur.execute(
        """
        SELECT DISTINCT speaker_id
        FROM (
            SELECT speaker_id FROM speech_queue WHERE legislation_id = %s
            UNION
            SELECT speaker_id FROM speeches WHERE legislation_id = %s
            UNION
            SELECT qq.speaker_id
            FROM question_queue qq
            JOIN speeches s ON s.id = qq.speech_id
            WHERE s.legislation_id = %s
        ) AS session_speakers
        ORDER BY speaker_id
        """,
        (leg_id, leg_id, leg_id),
    )
    speaker_ids = [row["speaker_id"] for row in cur.fetchall()]
    if not speaker_ids:
        return []

    stats = []
    for speaker_id in speaker_ids:
        cur.execute(
            "SELECT id, full_name, school FROM speakers WHERE id = %s",
            (speaker_id,),
        )
        speaker = cur.fetchone()
        if not speaker:
            continue

        cur.execute(
            "SELECT COUNT(*) AS speeches_count, COALESCE(AVG(duration_seconds), 0) AS avg_seconds FROM speeches WHERE legislation_id = %s AND speaker_id = %s",
            (leg_id, speaker_id),
        )
        speech_row = cur.fetchone() or {}

        cur.execute(
            """
            SELECT COUNT(*) AS questions_count
            FROM question_queue qq
            JOIN speeches s ON s.id = qq.speech_id
            WHERE s.legislation_id = %s AND qq.speaker_id = %s
            """,
            (leg_id, speaker_id),
        )
        question_row = cur.fetchone() or {}

        stats.append(
            {
                "id": speaker["id"],
                "full_name": speaker["full_name"],
                "school": speaker["school"],
                "speeches_count": int((speech_row.get("speeches_count") if speech_row else 0) or 0),
                "questions_count": int((question_row.get("questions_count") if question_row else 0) or 0),
                "avg_speaking_seconds": int(round(float((speech_row.get("avg_seconds") if speech_row else 0) or 0))),
            }
        )

    stats.sort(key=lambda row: (-row["speeches_count"], -row["questions_count"], row["full_name"].lower()))
    return stats


def ensure_timer_schema():
    with get_db() as (conn, cur):
        cur.execute("SHOW COLUMNS FROM session_state LIKE 'phase'")
        phase_col = cur.fetchone()
        phase_type = (phase_col or {}).get("Type", "")
        if "'voting'" not in phase_type:
            cur.execute("ALTER TABLE session_state MODIFY COLUMN phase ENUM('idle', 'speech_queue', 'speech_in_progress', 'questioning', 'voting') NOT NULL DEFAULT 'idle'")

        cur.execute("SHOW COLUMNS FROM session_state LIKE 'timer_status'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE session_state ADD COLUMN timer_status ENUM('idle', 'running', 'paused', 'stopped') NOT NULL DEFAULT 'idle'")

        cur.execute("SHOW COLUMNS FROM session_state LIKE 'timer_elapsed_seconds'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE session_state ADD COLUMN timer_elapsed_seconds INT NOT NULL DEFAULT 0")

        cur.execute("SHOW COLUMNS FROM session_state LIKE 'timer_started_at'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE session_state ADD COLUMN timer_started_at DATETIME DEFAULT NULL")

        cur.execute("SHOW COLUMNS FROM speeches LIKE 'duration_seconds'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE speeches ADD COLUMN duration_seconds INT NOT NULL DEFAULT 0")

        cur.execute("SHOW COLUMNS FROM legislation LIKE 'vote_result'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE legislation ADD COLUMN vote_result ENUM('pending', 'passed', 'failed') NOT NULL DEFAULT 'pending'")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS legislation_votes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                legislation_id INT NOT NULL,
                speaker_id INT NOT NULL,
                vote_choice ENUM('for', 'against') NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_leg_speaker_vote (legislation_id, speaker_id),
                FOREIGN KEY (legislation_id) REFERENCES legislation(id),
                FOREIGN KEY (speaker_id) REFERENCES speakers(id)
            )
            """
        )

        cur.execute("UPDATE session_state SET timer_status = COALESCE(timer_status, 'idle'), timer_elapsed_seconds = COALESCE(timer_elapsed_seconds, 0) WHERE id = 1")
        conn.commit()


@app.get("/api/session/state")
def api_session_state():
    with get_db() as (conn, cur):
        cur.execute("SELECT * FROM session_state WHERE id = 1")
        state = cur.fetchone()

        result = {
            "phase": state["phase"] if state else "idle",
            "active_legislation": None,
            "current_speech": None,
            "speeches": [],
            "speech_queue": [],
            "question_queue": [],
            "next_side": None,
            "timer": _timer_payload(state),
            "voting": None,
            "speaker_stats": [],
        }

        if not state or not state["active_legislation_id"]:
            return jsonify(result)

        leg_id = state["active_legislation_id"]

        # Active legislation
        cur.execute("SELECT id, school, title, body, leg_order, status, vote_result FROM legislation WHERE id = %s", (leg_id,))
        result["active_legislation"] = cur.fetchone()

        # Speeches on this legislation
        cur.execute("""
             SELECT s.id, s.legislation_id, s.speaker_id, s.is_affirmative,
                 s.speech_type, s.duration_seconds, s.created_at, sp.full_name, sp.school
            FROM speeches s JOIN speakers sp ON sp.id = s.speaker_id
            WHERE s.legislation_id = %s ORDER BY s.created_at
        """, (leg_id,))
        speeches = cur.fetchall()
        for r in speeches:
            r["created_at"] = _iso(r["created_at"])
        result["speeches"] = speeches

        # Determine next side needed
        if len(speeches) == 0:
            result["next_side"] = True   # authorship — affirmative
        elif len(speeches) == 1:
            result["next_side"] = False  # first negative
        else:
            result["next_side"] = not speeches[-1]["is_affirmative"]

        # Speech queue with precedence/recency info
        cur.execute("""
            SELECT sq.id, sq.legislation_id, sq.speaker_id, sq.is_affirmative,
                   sq.status, sq.created_at,
                   sp.full_name, sp.school,
                   (SELECT COUNT(*) FROM speeches WHERE speaker_id = sq.speaker_id) AS total_speeches,
                   (SELECT MAX(created_at) FROM speeches WHERE speaker_id = sq.speaker_id) AS last_speech_time
            FROM speech_queue sq
            JOIN speakers sp ON sp.id = sq.speaker_id
            WHERE sq.legislation_id = %s AND sq.status = 'waiting'
            ORDER BY total_speeches ASC, last_speech_time ASC, sq.created_at ASC
        """, (leg_id,))
        queue = cur.fetchall()
        for r in queue:
            r["created_at"] = _iso(r["created_at"])
            r["last_speech_time"] = _iso(r["last_speech_time"])
        result["speech_queue"] = queue

        # Current speech & question queue
        if state["current_speech_id"]:
            cur.execute("""
                SELECT s.id, s.legislation_id, s.speaker_id, s.is_affirmative,
                       s.speech_type, s.duration_seconds, s.created_at, sp.full_name, sp.school
                FROM speeches s JOIN speakers sp ON sp.id = s.speaker_id
                WHERE s.id = %s
            """, (state["current_speech_id"],))
            cs = cur.fetchone()
            if cs:
                cs["created_at"] = _iso(cs["created_at"])
            result["current_speech"] = cs

            cur.execute("""
                SELECT qq.id, qq.speech_id, qq.speaker_id, qq.status, qq.created_at,
                       sp.full_name, sp.school
                FROM question_queue qq
                JOIN speakers sp ON sp.id = qq.speaker_id
                WHERE qq.speech_id = %s AND qq.status IN ('waiting', 'asking')
                ORDER BY qq.created_at ASC
            """, (state["current_speech_id"],))
            qqueue = cur.fetchall()
            for r in qqueue:
                r["created_at"] = _iso(r["created_at"])
            result["question_queue"] = qqueue

        result["timer"] = _timer_payload(state)
        result["voting"] = _vote_summary(cur, leg_id, user_id=session.get("user_id"))
        result["speaker_stats"] = _speaker_stats(cur, leg_id)

    return jsonify(result)


@app.post("/api/session/open-debate")
def api_session_open_debate():
    err = po_api_guard()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    leg_id = data.get("legislation_id")
    if not leg_id:
        return jsonify({"error": "legislation_id required"}), 400

    with get_db(dictionary=False) as (conn, cur):
        cur.execute(
            "UPDATE session_state SET active_legislation_id = %s, current_speech_id = NULL, phase = 'speech_queue', timer_status = 'idle', timer_elapsed_seconds = 0, timer_started_at = NULL WHERE id = 1",
            (leg_id,),
        )
        cur.execute("UPDATE legislation SET status = 'active', vote_result = 'pending' WHERE id = %s", (leg_id,))
        cur.execute("DELETE FROM legislation_votes WHERE legislation_id = %s", (leg_id,))
        conn.commit()
    return jsonify({"ok": True})


@app.post("/api/session/close-debate")
def api_session_close_debate():
    err = po_api_guard()
    if err:
        return err

    with get_db() as (conn, cur):
        cur.execute("SELECT active_legislation_id, current_speech_id FROM session_state WHERE id = 1")
        state = cur.fetchone()

        if not state or not state["active_legislation_id"]:
            return jsonify({"error": "No active legislation"}), 400

        lid = state["active_legislation_id"]
        _finalize_active_speech_timer(cur)
        cur.execute("UPDATE speech_queue SET status = 'cancelled' WHERE legislation_id = %s AND status = 'waiting'", (lid,))
        if state.get("current_speech_id"):
            cur.execute(
                "UPDATE question_queue SET status = 'cancelled' WHERE speech_id = %s AND status IN ('waiting','asking')",
                (state["current_speech_id"],),
            )
        cur.execute("DELETE FROM legislation_votes WHERE legislation_id = %s", (lid,))
        cur.execute(
            "UPDATE session_state SET current_speech_id = NULL, phase = 'voting', timer_status = 'idle', timer_elapsed_seconds = 0, timer_started_at = NULL WHERE id = 1"
        )
        conn.commit()
    return jsonify({"ok": True})


@app.post("/api/session/reset")
def api_session_reset():
    """Full reset: clear all speeches, queues, and legislation statuses."""
    err = po_api_guard()
    if err:
        return err
    with get_db(dictionary=False) as (conn, cur):
        cur.execute("DELETE FROM legislation_votes")
        cur.execute("DELETE FROM question_queue")
        cur.execute("DELETE FROM speech_queue")
        cur.execute("DELETE FROM speeches")
        cur.execute("UPDATE session_state SET active_legislation_id = NULL, current_speech_id = NULL, phase = 'idle', timer_status = 'idle', timer_elapsed_seconds = 0, timer_started_at = NULL WHERE id = 1")
        cur.execute("UPDATE legislation SET status = 'pending', vote_result = 'pending'")
        conn.commit()
    return jsonify({"ok": True})


@app.post("/api/vote")
def api_vote_submit():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Login required"}), 401

    data = request.get_json(silent=True) or {}
    vote_choice = (data.get("vote_choice") or "").strip().lower()
    if vote_choice not in ("for", "against"):
        return jsonify({"error": "vote_choice must be 'for' or 'against'"}), 400

    with get_db() as (conn, cur):
        cur.execute("SELECT active_legislation_id, phase FROM session_state WHERE id = 1")
        state = cur.fetchone()
        if not state or not state.get("active_legislation_id"):
            return jsonify({"error": "No active legislation"}), 400
        if state.get("phase") != "voting":
            return jsonify({"error": "Voting is not open"}), 400

        leg_id = state["active_legislation_id"]
        cur.execute(
            """
            INSERT INTO legislation_votes (legislation_id, speaker_id, vote_choice)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE vote_choice = VALUES(vote_choice)
            """,
            (leg_id, uid, vote_choice),
        )
        conn.commit()

        voting = _vote_summary(cur, leg_id, user_id=uid)
    return jsonify({"ok": True, "voting": voting})


@app.post("/api/session/finalize-vote")
def api_session_finalize_vote():
    err = po_api_guard()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    result = (data.get("result") or "").strip().lower()
    if result not in ("passed", "failed"):
        return jsonify({"error": "result must be 'passed' or 'failed'"}), 400

    with get_db() as (conn, cur):
        cur.execute("SELECT active_legislation_id, phase FROM session_state WHERE id = 1")
        state = cur.fetchone()
        if not state or not state.get("active_legislation_id"):
            return jsonify({"error": "No active legislation"}), 400
        if state.get("phase") != "voting":
            return jsonify({"error": "Not in voting phase"}), 400

        lid = state["active_legislation_id"]
        cur.execute("UPDATE legislation SET status = 'completed', vote_result = %s WHERE id = %s", (result, lid))
        cur.execute(
            "UPDATE session_state SET active_legislation_id = NULL, current_speech_id = NULL, phase = 'idle', timer_status = 'idle', timer_elapsed_seconds = 0, timer_started_at = NULL WHERE id = 1"
        )
        conn.commit()

    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Speech queue API
# ---------------------------------------------------------------------------

@app.post("/api/speech/request")
def api_speech_request():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Login required"}), 401

    data = request.get_json(silent=True) or {}
    is_aff = data.get("is_affirmative")
    if is_aff is None:
        return jsonify({"error": "is_affirmative required"}), 400

    with get_db() as (conn, cur):
        cur.execute("SELECT active_legislation_id, phase FROM session_state WHERE id = 1")
        state = cur.fetchone()
        if not state or not state["active_legislation_id"]:
            return jsonify({"error": "No active legislation"}), 400
        if state["phase"] not in ("speech_queue", "speech_in_progress"):
            return jsonify({"error": "Debate is not accepting speech requests"}), 400

        leg_id = state["active_legislation_id"]

        # Already in queue?
        cur.execute(
            "SELECT id FROM speech_queue WHERE legislation_id = %s AND speaker_id = %s AND status = 'waiting'",
            (leg_id, uid),
        )
        if cur.fetchone():
            return jsonify({"error": "Already in queue"}), 400

        cur.execute(
            "INSERT INTO speech_queue (legislation_id, speaker_id, is_affirmative) VALUES (%s, %s, %s)",
            (leg_id, uid, bool(is_aff)),
        )
        conn.commit()
        qid = cur.lastrowid
    return jsonify({"ok": True, "queue_id": qid}), 201


@app.post("/api/speech/cancel")
def api_speech_cancel():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Login required"}), 401

    with get_db(dictionary=False) as (conn, cur):
        cur.execute(
            "UPDATE speech_queue SET status = 'cancelled' WHERE speaker_id = %s AND status = 'waiting'",
            (uid,),
        )
        conn.commit()
    return jsonify({"ok": True})


@app.post("/api/speech/select/<int:queue_id>")
def api_speech_select(queue_id):
    err = po_api_guard()
    if err:
        return err

    with get_db() as (conn, cur):
        cur.execute("SELECT * FROM speech_queue WHERE id = %s AND status = 'waiting'", (queue_id,))
        entry = cur.fetchone()
        if not entry:
            return jsonify({"error": "Queue entry not found"}), 404

        # Determine speech type
        cur.execute("SELECT COUNT(*) AS cnt FROM speeches WHERE legislation_id = %s", (entry["legislation_id"],))
        cnt = cur.fetchone()["cnt"]
        if cnt == 0:
            stype = "authorship"
        elif cnt == 1:
            stype = "first_negative"
        else:
            stype = "regular"

        cur.execute(
            "INSERT INTO speeches (legislation_id, speaker_id, is_affirmative, speech_type, duration_seconds) VALUES (%s, %s, %s, %s, 0)",
            (entry["legislation_id"], entry["speaker_id"], entry["is_affirmative"], stype),
        )
        speech_id = cur.lastrowid
        cur.execute("UPDATE speech_queue SET status = 'speaking' WHERE id = %s", (queue_id,))
        cur.execute(
            "UPDATE session_state SET current_speech_id = %s, phase = 'speech_in_progress', timer_status = 'running', timer_elapsed_seconds = 0, timer_started_at = NOW() WHERE id = 1",
            (speech_id,),
        )
        conn.commit()
    return jsonify({"ok": True, "speech_id": speech_id})


@app.post("/api/speech/complete")
def api_speech_complete():
    err = po_api_guard()
    if err:
        return err

    with get_db() as (conn, cur):
        cur.execute("SELECT current_speech_id FROM session_state WHERE id = 1")
        state = cur.fetchone()
        if not state or not state["current_speech_id"]:
            return jsonify({"error": "No speech in progress"}), 400

        _finalize_active_speech_timer(cur)
        cur.execute(
            "UPDATE speech_queue SET status = 'done' WHERE speaker_id = "
            "(SELECT speaker_id FROM speeches WHERE id = %s) AND status = 'speaking'",
            (state["current_speech_id"],),
        )
        cur.execute("UPDATE session_state SET phase = 'questioning' WHERE id = 1")
        conn.commit()
    return jsonify({"ok": True})


@app.post("/api/speech/timer/pause")
def api_speech_timer_pause():
    err = po_api_guard()
    if err:
        return err

    with get_db() as (conn, cur):
        cur.execute("SELECT * FROM session_state WHERE id = 1")
        state = cur.fetchone()
        if not state or not state.get("current_speech_id"):
            return jsonify({"error": "No speech in progress"}), 400
        if state.get("timer_status") != "running":
            return jsonify({"error": "Timer is not running"}), 400

        elapsed = _timer_elapsed_seconds(state)
        _reset_timer_state(cur, status="paused", elapsed_seconds=elapsed, started_at=None)
        conn.commit()
    return jsonify({"ok": True, "timer": {"status": "paused", "elapsed_seconds": elapsed}})


@app.post("/api/speech/timer/resume")
def api_speech_timer_resume():
    err = po_api_guard()
    if err:
        return err

    with get_db() as (conn, cur):
        cur.execute("SELECT * FROM session_state WHERE id = 1")
        state = cur.fetchone()
        if not state or not state.get("current_speech_id"):
            return jsonify({"error": "No speech in progress"}), 400
        if state.get("timer_status") != "paused":
            return jsonify({"error": "Timer is not paused"}), 400

        cur.execute("UPDATE session_state SET timer_status = 'running', timer_started_at = NOW() WHERE id = 1")
        conn.commit()
        elapsed = _timer_elapsed_seconds(state)
    return jsonify({"ok": True, "timer": {"status": "running", "elapsed_seconds": elapsed}})


@app.post("/api/speech/timer/reset")
def api_speech_timer_reset():
    err = po_api_guard()
    if err:
        return err

    with get_db() as (conn, cur):
        cur.execute("SELECT * FROM session_state WHERE id = 1")
        state = cur.fetchone()
        if not state or not state.get("current_speech_id"):
            return jsonify({"error": "No speech in progress"}), 400

        _reset_timer_state(cur, status="paused", elapsed_seconds=0, started_at=None)
        conn.commit()
    return jsonify({"ok": True, "timer": {"status": "paused", "elapsed_seconds": 0}})


@app.post("/api/speech/end-questioning")
def api_speech_end_questioning():
    err = po_api_guard()
    if err:
        return err

    with get_db() as (conn, cur):
        cur.execute("SELECT current_speech_id FROM session_state WHERE id = 1")
        state = cur.fetchone()

        if state and state["current_speech_id"]:
            cur.execute(
                "UPDATE question_queue SET status = 'cancelled' WHERE speech_id = %s AND status IN ('waiting','asking')",
                (state["current_speech_id"],),
            )

        cur.execute("UPDATE session_state SET current_speech_id = NULL, phase = 'speech_queue', timer_status = 'idle', timer_elapsed_seconds = 0, timer_started_at = NULL WHERE id = 1")
        conn.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Question queue API
# ---------------------------------------------------------------------------

@app.post("/api/question/request")
def api_question_request():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Login required"}), 401

    with get_db() as (conn, cur):
        cur.execute("SELECT current_speech_id, phase FROM session_state WHERE id = 1")
        state = cur.fetchone()
        if not state or state["phase"] != "questioning" or not state["current_speech_id"]:
            return jsonify({"error": "Not in questioning phase"}), 400

        sid = state["current_speech_id"]

        # Can't question your own speech
        cur.execute("SELECT speaker_id FROM speeches WHERE id = %s", (sid,))
        speech = cur.fetchone()
        if speech and speech["speaker_id"] == uid:
            return jsonify({"error": "Cannot question your own speech"}), 400

        # Already in queue?
        cur.execute(
            "SELECT id FROM question_queue WHERE speech_id = %s AND speaker_id = %s AND status = 'waiting'",
            (sid, uid),
        )
        if cur.fetchone():
            return jsonify({"error": "Already in question queue"}), 400

        cur.execute(
            "INSERT INTO question_queue (speech_id, speaker_id) VALUES (%s, %s)",
            (sid, uid),
        )
        conn.commit()
    return jsonify({"ok": True}), 201


@app.post("/api/question/select/<int:queue_id>")
def api_question_select(queue_id):
    err = po_api_guard()
    if err:
        return err
    with get_db(dictionary=False) as (conn, cur):
        cur.execute("UPDATE question_queue SET status = 'asking' WHERE id = %s AND status = 'waiting'", (queue_id,))
        conn.commit()
    return jsonify({"ok": True})


@app.post("/api/question/done/<int:queue_id>")
def api_question_done(queue_id):
    err = po_api_guard()
    if err:
        return err
    with get_db(dictionary=False) as (conn, cur):
        cur.execute("UPDATE question_queue SET status = 'done' WHERE id = %s", (queue_id,))
        conn.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ensure_timer_schema()
    app.run(debug=True, port=5000)
