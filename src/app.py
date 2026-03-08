from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from db import get_conn
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

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id FROM speakers WHERE email = %s", (email,))
    if cur.fetchone():
        cur.close(); conn.close()
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

    cur.close(); conn.close()
    return jsonify({"ok": True}), 201


@app.post("/api/login")
def api_login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, email, full_name, school, password_hash FROM speakers WHERE email = %s",
        (email,),
    )
    user = cur.fetchone()
    cur.close(); conn.close()

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
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, school, title, body, leg_order, status FROM legislation ORDER BY leg_order")
    rows = cur.fetchall()
    cur.close(); conn.close()
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

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT COALESCE(MAX(leg_order), 0) + 1 AS next_order FROM legislation")
    next_order = cur.fetchone()["next_order"]
    cur.execute(
        "INSERT INTO legislation (school, title, body, leg_order) VALUES (%s, %s, %s, %s)",
        (school, title, body, next_order),
    )
    conn.commit()
    lid = cur.lastrowid
    cur.close(); conn.close()
    return jsonify({"ok": True, "id": lid}), 201


@app.put("/api/legislation/<int:leg_id>")
def api_legislation_update(leg_id):
    err = po_api_guard()
    if err:
        return err
    data = request.get_json(silent=True) or {}

    conn = get_conn()
    cur = conn.cursor()
    fields, values = [], []
    for col in ("title", "school", "body"):
        if col in data:
            fields.append(f"{col} = %s")
            values.append(data[col])
    if not fields:
        conn.close()
        return jsonify({"error": "No fields to update"}), 400
    values.append(leg_id)
    cur.execute(f"UPDATE legislation SET {', '.join(fields)} WHERE id = %s", values)
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok": True})


@app.delete("/api/legislation/<int:leg_id>")
def api_legislation_delete(leg_id):
    err = po_api_guard()
    if err:
        return err
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM legislation WHERE id = %s", (leg_id,))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok": True})


@app.post("/api/legislation/reorder")
def api_legislation_reorder():
    err = po_api_guard()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    order = data.get("order", [])

    conn = get_conn()
    cur = conn.cursor()
    for i, lid in enumerate(order, 1):
        cur.execute("UPDATE legislation SET leg_order = %s WHERE id = %s", (i, int(lid)))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Session / debate control API
# ---------------------------------------------------------------------------

def _iso(dt):
    return dt.isoformat() if dt else None


@app.get("/api/session/state")
def api_session_state():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

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
    }

    if not state or not state["active_legislation_id"]:
        cur.close(); conn.close()
        return jsonify(result)

    leg_id = state["active_legislation_id"]

    # Active legislation
    cur.execute("SELECT id, school, title, body, leg_order, status FROM legislation WHERE id = %s", (leg_id,))
    result["active_legislation"] = cur.fetchone()

    # Speeches on this legislation
    cur.execute("""
        SELECT s.id, s.legislation_id, s.speaker_id, s.is_affirmative,
               s.speech_type, s.created_at, sp.full_name, sp.school
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
                   s.speech_type, s.created_at, sp.full_name, sp.school
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

    cur.close(); conn.close()
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

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE session_state SET active_legislation_id = %s, current_speech_id = NULL, phase = 'speech_queue' WHERE id = 1",
        (leg_id,),
    )
    cur.execute("UPDATE legislation SET status = 'active' WHERE id = %s", (leg_id,))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok": True})


@app.post("/api/session/close-debate")
def api_session_close_debate():
    err = po_api_guard()
    if err:
        return err

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT active_legislation_id FROM session_state WHERE id = 1")
    state = cur.fetchone()

    if state and state["active_legislation_id"]:
        lid = state["active_legislation_id"]
        cur.execute("UPDATE legislation SET status = 'completed' WHERE id = %s", (lid,))
        cur.execute("UPDATE speech_queue SET status = 'cancelled' WHERE legislation_id = %s AND status = 'waiting'", (lid,))
    cur.execute(
        "UPDATE session_state SET active_legislation_id = NULL, current_speech_id = NULL, phase = 'idle' WHERE id = 1"
    )
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok": True})


@app.post("/api/session/reset")
def api_session_reset():
    """Full reset: clear all speeches, queues, and legislation statuses."""
    err = po_api_guard()
    if err:
        return err
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM question_queue")
    cur.execute("DELETE FROM speech_queue")
    cur.execute("DELETE FROM speeches")
    cur.execute("UPDATE session_state SET active_legislation_id = NULL, current_speech_id = NULL, phase = 'idle' WHERE id = 1")
    cur.execute("UPDATE legislation SET status = 'pending'")
    conn.commit()
    cur.close(); conn.close()
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

    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT active_legislation_id, phase FROM session_state WHERE id = 1")
    state = cur.fetchone()
    if not state or not state["active_legislation_id"]:
        cur.close(); conn.close()
        return jsonify({"error": "No active legislation"}), 400

    leg_id = state["active_legislation_id"]

    # Already in queue?
    cur.execute(
        "SELECT id FROM speech_queue WHERE legislation_id = %s AND speaker_id = %s AND status = 'waiting'",
        (leg_id, uid),
    )
    if cur.fetchone():
        cur.close(); conn.close()
        return jsonify({"error": "Already in queue"}), 400

    cur.execute(
        "INSERT INTO speech_queue (legislation_id, speaker_id, is_affirmative) VALUES (%s, %s, %s)",
        (leg_id, uid, bool(is_aff)),
    )
    conn.commit()
    qid = cur.lastrowid
    cur.close(); conn.close()
    return jsonify({"ok": True, "queue_id": qid}), 201


@app.post("/api/speech/cancel")
def api_speech_cancel():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Login required"}), 401

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE speech_queue SET status = 'cancelled' WHERE speaker_id = %s AND status = 'waiting'",
        (uid,),
    )
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok": True})


@app.post("/api/speech/select/<int:queue_id>")
def api_speech_select(queue_id):
    err = po_api_guard()
    if err:
        return err

    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT * FROM speech_queue WHERE id = %s AND status = 'waiting'", (queue_id,))
    entry = cur.fetchone()
    if not entry:
        cur.close(); conn.close()
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
        "INSERT INTO speeches (legislation_id, speaker_id, is_affirmative, speech_type) VALUES (%s, %s, %s, %s)",
        (entry["legislation_id"], entry["speaker_id"], entry["is_affirmative"], stype),
    )
    speech_id = cur.lastrowid
    cur.execute("UPDATE speech_queue SET status = 'speaking' WHERE id = %s", (queue_id,))
    cur.execute(
        "UPDATE session_state SET current_speech_id = %s, phase = 'speech_in_progress' WHERE id = 1",
        (speech_id,),
    )
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok": True, "speech_id": speech_id})


@app.post("/api/speech/complete")
def api_speech_complete():
    err = po_api_guard()
    if err:
        return err

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT current_speech_id FROM session_state WHERE id = 1")
    state = cur.fetchone()
    if not state or not state["current_speech_id"]:
        cur.close(); conn.close()
        return jsonify({"error": "No speech in progress"}), 400

    cur.execute(
        "UPDATE speech_queue SET status = 'done' WHERE speaker_id = "
        "(SELECT speaker_id FROM speeches WHERE id = %s) AND status = 'speaking'",
        (state["current_speech_id"],),
    )
    cur.execute("UPDATE session_state SET phase = 'questioning' WHERE id = 1")
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok": True})


@app.post("/api/speech/end-questioning")
def api_speech_end_questioning():
    err = po_api_guard()
    if err:
        return err

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT current_speech_id FROM session_state WHERE id = 1")
    state = cur.fetchone()

    if state and state["current_speech_id"]:
        cur.execute(
            "UPDATE question_queue SET status = 'cancelled' WHERE speech_id = %s AND status IN ('waiting','asking')",
            (state["current_speech_id"],),
        )

    cur.execute("UPDATE session_state SET current_speech_id = NULL, phase = 'speech_queue' WHERE id = 1")
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Question queue API
# ---------------------------------------------------------------------------

@app.post("/api/question/request")
def api_question_request():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Login required"}), 401

    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT current_speech_id, phase FROM session_state WHERE id = 1")
    state = cur.fetchone()
    if not state or state["phase"] != "questioning" or not state["current_speech_id"]:
        cur.close(); conn.close()
        return jsonify({"error": "Not in questioning phase"}), 400

    sid = state["current_speech_id"]

    # Can't question your own speech
    cur.execute("SELECT speaker_id FROM speeches WHERE id = %s", (sid,))
    speech = cur.fetchone()
    if speech and speech["speaker_id"] == uid:
        cur.close(); conn.close()
        return jsonify({"error": "Cannot question your own speech"}), 400

    # Already in queue?
    cur.execute(
        "SELECT id FROM question_queue WHERE speech_id = %s AND speaker_id = %s AND status = 'waiting'",
        (sid, uid),
    )
    if cur.fetchone():
        cur.close(); conn.close()
        return jsonify({"error": "Already in question queue"}), 400

    cur.execute(
        "INSERT INTO question_queue (speech_id, speaker_id) VALUES (%s, %s)",
        (sid, uid),
    )
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok": True}), 201


@app.post("/api/question/select/<int:queue_id>")
def api_question_select(queue_id):
    err = po_api_guard()
    if err:
        return err
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE question_queue SET status = 'asking' WHERE id = %s AND status = 'waiting'", (queue_id,))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok": True})


@app.post("/api/question/done/<int:queue_id>")
def api_question_done(queue_id):
    err = po_api_guard()
    if err:
        return err
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE question_queue SET status = 'done' WHERE id = %s", (queue_id,))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
