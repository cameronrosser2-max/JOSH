#!/usr/bin/env python3
"""
Josh — Instagram DM Outreach System
Production-ready Railway app. One dashboard, full control.
"""

import csv
import json
import os
import random
import threading
import time
import logging
import schedule
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, render_template, jsonify, request, session, redirect, send_file
from flask_socketio import SocketIO, emit

from industries import INDUSTRIES

# ── Environment config ────────────────────────────────────────────────────
IG_USERNAME    = os.environ.get("IG_USERNAME", "").strip()
IG_PASSWORD    = os.environ.get("IG_PASSWORD", "").strip()
DASHBOARD_PIN  = os.environ.get("DASHBOARD_PIN", "").strip()       # optional PIN lock
WAIT_MIN       = int(os.environ.get("WAIT_MIN_SECS", 40))
WAIT_MAX       = int(os.environ.get("WAIT_MAX_SECS", 110))
DEFAULT_TARGET = int(os.environ.get("TARGET_TOTAL", 1000))
PORT           = int(os.environ.get("PORT", 5000))

SESSION_FILE  = "ig_session.json"
LOG_FILE      = "dm_log.csv"
COUNTER_FILE  = "dm_counter.json"
SCHEDULE_FILE = "dm_schedule.json"

HASHTAGS = {
    "hvac":            ["hvaclife", "hvactechnician", "hvacbusiness", "hvaccontractor", "heatingandcooling", "hvactech"],
    "plumbing":        ["plumbinglife", "plumber", "plumbingbusiness", "plumbingcontractor", "plumbingpros"],
    "electrician":     ["electrician", "electricalbusiness", "electricianlife", "sparky", "electricalcontractor"],
    "roofing":         ["roofingcontractor", "roofinglife", "roofer", "roofingbusiness", "roofingcompany"],
    "landscaping":     ["landscapingbusiness", "lawncare", "landscaper", "landscapinglife", "lawncarepros"],
    "painting":        ["paintingcontractor", "paintingbusiness", "painterlife", "housepainter", "paintingpros"],
    "pest_control":    ["pestcontrol", "pestcontrolbusiness", "exterminator", "pestmanagement"],
    "pressure_washing":["pressurewashing", "pressurewashingbusiness", "softwash", "powerwashing"],
    "cleaning":        ["cleaningbusiness", "cleaningservice", "maidservice", "janitorial", "cleaningpros"],
    "concrete":        ["concretework", "concretecontractor", "masonrywork", "concretelife"],
    "fencing":         ["fencingcontractor", "fenceinstall", "fencingbusiness", "fencecompany"],
    "garage_door":     ["garagedoorrepair", "garagedoor", "garagedoorbusiness", "garagedoorpros"],
    "pool":            ["poolservice", "poolcleaning", "poolbuilder", "poolmaintenance"],
    "tree_service":    ["treeservice", "treeremoval", "arborist", "treecare", "treepros"],
    "repair":          ["autorepairshop", "appliancerepair", "repairshop", "mechaniclife"],
}

# ── Flask setup ───────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "josh-outreach-2024")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("josh")

# ── Shared state ──────────────────────────────────────────────────────────
state = {
    "running":      False,
    "sent":         0,
    "failed":       0,
    "skipped":      0,
    "target":       DEFAULT_TARGET,
    "log":          [],
    "started_at":   None,
    "industry_stats": {k: 0 for k in HASHTAGS},
    "speed":        0.0,   # DMs per hour
    "eta_mins":     None,
}
_stop_flag = threading.Event()
_state_lock = threading.Lock()


# ── Utilities ─────────────────────────────────────────────────────────────

def push(msg: str, kind: str = "info"):
    entry = {"t": datetime.now().strftime("%H:%M:%S"), "msg": msg, "kind": kind}
    with _state_lock:
        state["log"].append(entry)
        if len(state["log"]) > 1000:
            state["log"] = state["log"][-1000:]
    socketio.emit("log", entry)
    socketio.emit("stats", _get_stats())


def _get_stats() -> dict:
    elapsed = 0
    if state["started_at"]:
        elapsed = (datetime.now() - datetime.fromisoformat(state["started_at"])).total_seconds()

    speed = round(state["sent"] / (elapsed / 3600), 1) if elapsed > 60 else 0
    remaining = state["target"] - state["sent"]
    eta = round((remaining / speed) * 60) if speed > 0 else None

    return {
        "running":         state["running"],
        "sent":            state["sent"],
        "failed":          state["failed"],
        "skipped":         state["skipped"],
        "target":          state["target"],
        "log":             state["log"][-150:],
        "industry_stats":  state["industry_stats"],
        "speed":           speed,
        "eta_mins":        eta,
        "credentials_set": bool(IG_USERNAME and IG_PASSWORD),
    }


def load_contacted() -> set:
    if not Path(LOG_FILE).exists():
        return set()
    with open(LOG_FILE, newline="", encoding="utf-8") as f:
        return {row.get("username", "").lower() for row in csv.DictReader(f) if row.get("username")}


def append_log(username, full_name, industry, message, status):
    exists = Path(LOG_FILE).exists()
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "username", "full_name", "industry", "status", "message"])
        if not exists:
            w.writeheader()
        w.writerow({
            "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
            "username":  username,
            "full_name": full_name,
            "industry":  industry,
            "status":    status,
            "message":   message.replace("\n", " "),
        })


def load_counter() -> dict:
    if Path(COUNTER_FILE).exists():
        try:
            return json.loads(Path(COUNTER_FILE).read_text())
        except Exception:
            pass
    return {}


def save_counter(counters: dict):
    Path(COUNTER_FILE).write_text(json.dumps(counters))


def build_message(industry_key: str, name: str) -> str:
    ind     = INDUSTRIES.get(industry_key, {})
    iname   = ind.get("name", "your business")
    pain    = random.choice(ind.get("pain_points", ["getting found online is tough"]))
    roi     = ind.get("roi_hook", "a website pays for itself fast.")
    avg_job = ind.get("avg_job_value", "high-ticket jobs")

    return random.choice([
        (
            f"Hey {name}! 👋 Quick question — do you have a website yet?\n\n"
            f"A lot of {iname} companies say \"{pain.lower()}\" "
            f"We build done-for-you sites specifically for {iname} businesses — {roi} "
            f"Mind if I show you a quick example?"
        ),
        (
            f"Hi {name}! I help {iname} businesses get more calls from Google. "
            f"{pain} — sound familiar? "
            f"We handle everything: design, hosting, SEO. {roi} "
            f"Can I send over a free mockup for your business?"
        ),
        (
            f"Hey {name}! Love seeing {iname} businesses on here. 🔧\n\n"
            f"With {avg_job} per job, even 2–3 extra Google calls a month is huge. "
            f"We build websites that do exactly that for {iname} companies. "
            f"Want a free sample page? No strings."
        ),
        (
            f"Hey {name}, noticed you're in {iname} — are you currently getting leads online? "
            f"Most {iname} businesses miss out because {pain.lower()} "
            f"We fix that with a professional website. {roi} "
            f"Happy to send you a free demo, just say the word!"
        ),
    ])


# ── Instagram DM worker ───────────────────────────────────────────────────

def dm_worker(target: int):
    try:
        from instagrapi import Client
        from instagrapi.exceptions import RateLimitError, ClientError, LoginRequired
    except ImportError:
        push("ERROR: instagrapi not installed — check requirements.txt", "error")
        state["running"] = False
        socketio.emit("stats", _get_stats())
        return

    if not IG_USERNAME or not IG_PASSWORD:
        push("ERROR: IG_USERNAME / IG_PASSWORD not set in Railway Variables tab.", "error")
        state["running"] = False
        socketio.emit("stats", _get_stats())
        return

    # Login
    push(f"Connecting to Instagram as @{IG_USERNAME}…", "info")
    cl = Client()
    cl.delay_range = [1, 3]
    try:
        if Path(SESSION_FILE).exists():
            try:
                cl.load_settings(SESSION_FILE)
                cl.login(IG_USERNAME, IG_PASSWORD)
                push(f"✓ Session restored for @{IG_USERNAME}", "success")
            except (LoginRequired, Exception):
                push("Session expired — logging in fresh…", "warn")
                cl = Client()
                cl.delay_range = [1, 3]
                cl.login(IG_USERNAME, IG_PASSWORD)
                cl.dump_settings(SESSION_FILE)
                push(f"✓ Logged in as @{IG_USERNAME}", "success")
        else:
            cl.login(IG_USERNAME, IG_PASSWORD)
            cl.dump_settings(SESSION_FILE)
            push(f"✓ Logged in as @{IG_USERNAME}", "success")
    except Exception as e:
        push(f"Login failed: {e}", "error")
        state["running"] = False
        socketio.emit("stats", _get_stats())
        return

    contacted = load_contacted()
    push(f"Already contacted {len(contacted)} accounts. Targeting {target} new DMs.", "info")

    counters     = load_counter()
    today        = date.today().isoformat()
    sent_today   = counters.get(today, 0)
    industry_keys = list(HASHTAGS.keys())
    state["started_at"] = datetime.now().isoformat()

    while state["sent"] < target and not _stop_flag.is_set():
        random.shuffle(industry_keys)

        for industry_key in industry_keys:
            if state["sent"] >= target or _stop_flag.is_set():
                break

            ind_name = INDUSTRIES.get(industry_key, {}).get("name", industry_key)
            push(f"── Searching {ind_name} accounts…", "info")

            tags  = list(HASHTAGS[industry_key])
            random.shuffle(tags)
            batch = {}

            for tag in tags:
                if _stop_flag.is_set() or len(batch) >= 200:
                    break
                try:
                    medias = cl.hashtag_medias_recent_v1(tag, amount=50)
                    new = 0
                    for media in medias:
                        u = media.user
                        uname = u.username.lower()
                        if uname not in batch and uname not in contacted:
                            batch[uname] = {
                                "username":  u.username,
                                "full_name": (u.full_name or u.username).strip(),
                                "user_id":   u.pk,
                            }
                            new += 1
                    if new:
                        push(f"  #{tag}: +{new} new prospects ({len(batch)} total)", "info")
                    time.sleep(random.uniform(1.5, 4))
                except RateLimitError:
                    push(f"  Rate limited on #{tag} — pausing 6 min…", "warn")
                    for _ in range(360):
                        if _stop_flag.is_set():
                            break
                        time.sleep(1)
                except Exception as e:
                    push(f"  #{tag}: {e}", "warn")

            accounts = list(batch.values())
            random.shuffle(accounts)

            for acct in accounts:
                if state["sent"] >= target or _stop_flag.is_set():
                    break

                uname = acct["username"].lower()
                if uname in contacted:
                    state["skipped"] += 1
                    continue

                first = acct["full_name"].split()[0] if acct["full_name"] else uname
                msg   = build_message(industry_key, first)

                try:
                    cl.direct_send(msg, user_ids=[acct["user_id"]])
                    state["sent"]                        += 1
                    state["industry_stats"][industry_key] += 1
                    sent_today                           += 1
                    contacted.add(uname)
                    counters[today] = sent_today
                    save_counter(counters)
                    append_log(uname, acct["full_name"], industry_key, msg, "sent")
                    push(
                        f"✓ @{uname} ({ind_name})  [{state['sent']}/{target}]",
                        "success"
                    )
                except RateLimitError:
                    push("Rate limited — pausing 10 min…", "warn")
                    for _ in range(600):
                        if _stop_flag.is_set():
                            break
                        time.sleep(1)
                    continue
                except Exception as e:
                    state["failed"] += 1
                    append_log(uname, acct["full_name"], industry_key, msg, "failed")
                    push(f"✗ @{uname}: {e}", "error")

                socketio.emit("stats", _get_stats())

                # Human-like delay between messages
                wait = random.uniform(WAIT_MIN, WAIT_MAX)
                push(f"  Next DM in {wait:.0f}s…", "info")
                for _ in range(int(wait)):
                    if _stop_flag.is_set():
                        break
                    time.sleep(1)

    if _stop_flag.is_set():
        push(f"⏹ Stopped manually. Sent {state['sent']} DMs this session.", "warn")
    else:
        push(f"🎉 Campaign complete! Sent {state['sent']} DMs across {len(HASHTAGS)} industries.", "success")

    state["running"] = False
    socketio.emit("stats", _get_stats())


# ── Scheduler ─────────────────────────────────────────────────────────────

_scheduler_thread = None

def _run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(30)

def load_schedule() -> dict:
    if Path(SCHEDULE_FILE).exists():
        try:
            return json.loads(Path(SCHEDULE_FILE).read_text())
        except Exception:
            pass
    return {"enabled": False, "time": "09:00", "target": DEFAULT_TARGET}

def save_schedule(data: dict):
    Path(SCHEDULE_FILE).write_text(json.dumps(data))

def apply_schedule():
    global _scheduler_thread
    schedule.clear()
    cfg = load_schedule()
    if cfg.get("enabled") and cfg.get("time"):
        schedule.every().day.at(cfg["time"]).do(
            lambda: start_campaign(cfg.get("target", DEFAULT_TARGET))
        )
        log.info(f"Scheduled daily run at {cfg['time']}")
    if _scheduler_thread is None or not _scheduler_thread.is_alive():
        _scheduler_thread = threading.Thread(target=_run_scheduler, daemon=True)
        _scheduler_thread.start()

def start_campaign(target: int):
    if state["running"]:
        return
    state.update({
        "running": True, "sent": 0, "failed": 0, "skipped": 0,
        "target": target, "log": [], "started_at": datetime.now().isoformat(),
        "industry_stats": {k: 0 for k in HASHTAGS},
    })
    _stop_flag.clear()
    threading.Thread(target=dm_worker, args=(target,), daemon=True).start()


# ── Auth ──────────────────────────────────────────────────────────────────

def requires_pin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if DASHBOARD_PIN and not session.get("authed"):
            if request.is_json:
                return jsonify({"ok": False, "msg": "Not authenticated"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated


# ── Routes ────────────────────────────────────────────────────────────────

@app.route("/")
@requires_pin
def index():
    return render_template("dm_dashboard.html",
                           credentials_set=bool(IG_USERNAME and IG_PASSWORD),
                           ig_username=IG_USERNAME)

@app.route("/login", methods=["GET", "POST"])
def login():
    if not DASHBOARD_PIN:
        session["authed"] = True
        return redirect("/")
    if request.method == "POST":
        if request.form.get("pin") == DASHBOARD_PIN:
            session["authed"] = True
            return redirect("/")
        return render_template("login.html", error="Wrong PIN")
    return render_template("login.html", error=None)

@app.route("/api/stats")
@requires_pin
def api_stats():
    return jsonify(_get_stats())

@app.route("/api/start", methods=["POST"])
@requires_pin
def api_start():
    if state["running"]:
        return jsonify({"ok": False, "msg": "Already running"})
    data   = request.get_json(silent=True) or {}
    target = int(data.get("target", DEFAULT_TARGET))
    start_campaign(target)
    return jsonify({"ok": True, "msg": f"Campaign started — targeting {target} DMs"})

@app.route("/api/stop", methods=["POST"])
@requires_pin
def api_stop():
    _stop_flag.set()
    return jsonify({"ok": True, "msg": "Stop signal sent"})

@app.route("/api/schedule", methods=["GET", "POST"])
@requires_pin
def api_schedule():
    if request.method == "POST":
        cfg = request.get_json(silent=True) or {}
        save_schedule(cfg)
        apply_schedule()
        return jsonify({"ok": True})
    return jsonify(load_schedule())

@app.route("/api/log")
@requires_pin
def api_log_download():
    if not Path(LOG_FILE).exists():
        return "No log yet.", 404
    return send_file(LOG_FILE, as_attachment=True, download_name=f"dm_log_{date.today()}.csv")

@app.route("/api/log/clear", methods=["POST"])
@requires_pin
def api_log_clear():
    Path(LOG_FILE).unlink(missing_ok=True)
    Path(COUNTER_FILE).unlink(missing_ok=True)
    return jsonify({"ok": True})

@socketio.on("connect")
def on_connect():
    emit("stats", _get_stats())

# ── Boot ──────────────────────────────────────────────────────────────────

apply_schedule()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=PORT)
