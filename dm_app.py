#!/usr/bin/env python3
"""
Josh — Instagram DM Outreach Web App
Deploy on Railway. Open the dashboard, click Send, watch it run.
"""

import csv
import json
import os
import random
import sys
import threading
import time
import logging
from datetime import date, datetime
from pathlib import Path

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

from industries import INDUSTRIES

# ── Config ────────────────────────────────────────────────────────────────
IG_USERNAME      = os.environ.get("IG_USERNAME", "")
IG_PASSWORD      = os.environ.get("IG_PASSWORD", "")
DAILY_DM_LIMIT   = int(os.environ.get("DAILY_DM_LIMIT", 50))
TARGET_TOTAL     = int(os.environ.get("TARGET_TOTAL", 1000))
WAIT_MIN_SECS    = int(os.environ.get("WAIT_MIN_SECS", 45))
WAIT_MAX_SECS    = int(os.environ.get("WAIT_MAX_SECS", 120))
SESSION_FILE     = "ig_session.json"
LOG_FILE         = "dm_log.csv"
COUNTER_FILE     = "dm_counter.json"
PORT             = int(os.environ.get("PORT", 5000))

HASHTAGS = {
    "hvac":            ["hvaclife", "hvactechnician", "hvacbusiness", "hvaccontractor", "heatingandcooling"],
    "plumbing":        ["plumbinglife", "plumber", "plumbingbusiness", "plumbingcontractor"],
    "electrician":     ["electrician", "electricalbusiness", "electricianlife", "sparky"],
    "roofing":         ["roofingcontractor", "roofinglife", "roofer", "roofingbusiness"],
    "landscaping":     ["landscapingbusiness", "lawncare", "landscaper", "landscapinglife"],
    "painting":        ["paintingcontractor", "paintingbusiness", "painterlife", "housepainter"],
    "pest_control":    ["pestcontrol", "pestcontrolbusiness", "exterminator"],
    "pressure_washing":["pressurewashing", "pressurewashingbusiness", "softwash"],
    "cleaning":        ["cleaningbusiness", "cleaningservice", "maidservice", "janitorial"],
    "concrete":        ["concretework", "concretecontractor", "masonrywork"],
    "fencing":         ["fencingcontractor", "fenceinstall", "fencingbusiness"],
    "garage_door":     ["garagedoorrepair", "garagedoor", "garagedoorbusiness"],
    "pool":            ["poolservice", "poolcleaning", "poolbuilder"],
    "tree_service":    ["treeservice", "treeremoval", "arborist"],
    "repair":          ["autorepairshop", "appliancerepair", "repairshop"],
}

# ── App setup ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "josh-dm-secret")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("josh.dm")

# ── Global state ──────────────────────────────────────────────────────────
state = {
    "running":    False,
    "sent":       0,
    "failed":     0,
    "skipped":    0,
    "target":     TARGET_TOTAL,
    "log":        [],          # list of recent activity lines
    "started_at": None,
    "stopped":    False,
}
_stop_flag = threading.Event()


# ── Helpers ───────────────────────────────────────────────────────────────

def push(msg: str, kind: str = "info"):
    """Send a log line to the dashboard in real time."""
    entry = {"t": datetime.now().strftime("%H:%M:%S"), "msg": msg, "kind": kind}
    state["log"].append(entry)
    if len(state["log"]) > 500:
        state["log"] = state["log"][-500:]
    socketio.emit("log", entry)
    socketio.emit("stats", get_stats())


def get_stats() -> dict:
    return {
        "running":  state["running"],
        "sent":     state["sent"],
        "failed":   state["failed"],
        "skipped":  state["skipped"],
        "target":   state["target"],
        "log":      state["log"][-100:],
    }


def load_contacted() -> set:
    contacted = set()
    if not Path(LOG_FILE).exists():
        return contacted
    with open(LOG_FILE, newline="") as f:
        for row in csv.DictReader(f):
            contacted.add(row.get("username", "").lower())
    return contacted


def log_contact(username, full_name, industry, message, status):
    file_exists = Path(LOG_FILE).exists()
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["date", "username", "full_name", "industry", "status", "message"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
            "username":  username,
            "full_name": full_name,
            "industry":  industry,
            "status":    status,
            "message":   message.replace("\n", " "),
        })


def build_message(industry_key: str, business_name: str) -> str:
    ind     = INDUSTRIES.get(industry_key, {})
    name    = ind.get("name", "your business")
    pain    = random.choice(ind.get("pain_points", ["getting found online is tough"]))
    roi     = ind.get("roi_hook", "a website pays for itself fast.")
    avg_job = ind.get("avg_job_value", "high-ticket jobs")

    templates = [
        (
            f"Hey {business_name}! 👋 Quick question — do you have a website yet?\n\n"
            f"A lot of {name} companies say {pain.lower()}. "
            f"We build done-for-you websites for {name} businesses — {roi} "
            f"Mind if I show you a quick example?"
        ),
        (
            f"Hi {business_name}! I help {name} businesses get more leads online. "
            f"{pain} — sound familiar? "
            f"We handle design, hosting, and SEO. {roi} "
            f"Can I send you a free mockup?"
        ),
        (
            f"Hey! Love seeing {name} businesses on here. 🔧\n\n"
            f"With {avg_job} per job, even 2–3 extra calls a month from Google "
            f"makes a huge difference. We build sites that do exactly that. "
            f"Want a free sample page for your business?"
        ),
    ]
    return random.choice(templates)


# ── DM worker (runs in background thread) ─────────────────────────────────

def dm_worker():
    try:
        from instagrapi import Client
        from instagrapi.exceptions import RateLimitError, ClientError
    except ImportError:
        push("ERROR: instagrapi not installed. Run: pip install instagrapi Pillow", "error")
        state["running"] = False
        socketio.emit("stats", get_stats())
        return

    if not IG_USERNAME or not IG_PASSWORD:
        push("ERROR: IG_USERNAME or IG_PASSWORD not set in Railway environment variables.", "error")
        state["running"] = False
        socketio.emit("stats", get_stats())
        return

    push(f"Logging in as @{IG_USERNAME}…", "info")

    cl = Client()
    cl.delay_range = [2, 5]
    try:
        if Path(SESSION_FILE).exists():
            cl.load_settings(SESSION_FILE)
        cl.login(IG_USERNAME, IG_PASSWORD)
        cl.dump_settings(SESSION_FILE)
        push(f"✓ Logged in as @{IG_USERNAME}", "success")
    except Exception as e:
        push(f"Login failed: {e}", "error")
        state["running"] = False
        socketio.emit("stats", get_stats())
        return

    contacted = load_contacted()
    push(f"Already contacted {len(contacted)} accounts. Targeting {state['target']} new DMs.", "info")

    industry_keys = list(HASHTAGS.keys())

    while state["sent"] < state["target"] and not _stop_flag.is_set():
        random.shuffle(industry_keys)

        for industry_key in industry_keys:
            if state["sent"] >= state["target"] or _stop_flag.is_set():
                break

            ind_name = INDUSTRIES.get(industry_key, {}).get("name", industry_key)
            push(f"── Scraping {ind_name} accounts…", "info")

            tags = HASHTAGS.get(industry_key, [])
            random.shuffle(tags)
            batch = {}

            for tag in tags:
                if _stop_flag.is_set():
                    break
                try:
                    medias = cl.hashtag_medias_recent_v1(tag, amount=50)
                    for media in medias:
                        u = media.user
                        uname = u.username.lower()
                        if uname not in batch and uname not in contacted:
                            batch[uname] = {
                                "username":  u.username,
                                "full_name": u.full_name or u.username,
                                "user_id":   u.pk,
                            }
                    push(f"  #{tag}: found {len(batch)} prospects", "info")
                    time.sleep(random.uniform(2, 5))
                except Exception as e:
                    push(f"  #{tag} scrape error: {e}", "warn")

            accounts = list(batch.values())
            random.shuffle(accounts)

            for acct in accounts:
                if state["sent"] >= state["target"] or _stop_flag.is_set():
                    break

                uname = acct["username"].lower()
                if uname in contacted:
                    state["skipped"] += 1
                    continue

                first_name = acct["full_name"].split()[0] if acct["full_name"] else uname
                message    = build_message(industry_key, first_name)

                try:
                    cl.direct_send(message, user_ids=[acct["user_id"]])
                    state["sent"] += 1
                    contacted.add(uname)
                    log_contact(uname, acct["full_name"], industry_key, message, "sent")
                    push(f"✓ Sent to @{uname} ({ind_name})  [{state['sent']}/{state['target']}]", "success")
                except Exception as e:
                    state["failed"] += 1
                    log_contact(uname, acct["full_name"], industry_key, message, "failed")
                    push(f"✗ @{uname} failed: {e}", "error")

                socketio.emit("stats", get_stats())

                wait = random.uniform(WAIT_MIN_SECS, WAIT_MAX_SECS)
                push(f"  Waiting {wait:.0f}s before next DM…", "info")

                # Interruptible sleep
                for _ in range(int(wait)):
                    if _stop_flag.is_set():
                        break
                    time.sleep(1)

    if _stop_flag.is_set():
        push(f"⏹ Stopped. Sent {state['sent']} DMs total.", "warn")
    else:
        push(f"🎉 Done! Sent {state['sent']} DMs to {state['sent']} businesses.", "success")

    state["running"] = False
    socketio.emit("stats", get_stats())


# ── Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("dm_dashboard.html")


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/api/start", methods=["POST"])
def api_start():
    if state["running"]:
        return jsonify({"ok": False, "msg": "Already running"})

    data = request.get_json(silent=True) or {}
    state["target"]     = int(data.get("target", TARGET_TOTAL))
    state["sent"]       = 0
    state["failed"]     = 0
    state["skipped"]    = 0
    state["log"]        = []
    state["running"]    = True
    state["started_at"] = datetime.now().isoformat()
    _stop_flag.clear()

    t = threading.Thread(target=dm_worker, daemon=True)
    t.start()

    return jsonify({"ok": True, "msg": f"Started — targeting {state['target']} DMs"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    _stop_flag.set()
    return jsonify({"ok": True, "msg": "Stop signal sent"})


@app.route("/api/log")
def api_log():
    """Download dm_log.csv"""
    if not Path(LOG_FILE).exists():
        return "No log yet.", 404
    from flask import send_file
    return send_file(LOG_FILE, as_attachment=True, download_name="dm_log.csv")


@socketio.on("connect")
def on_connect():
    emit("stats", get_stats())


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=PORT)
