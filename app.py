#!/usr/bin/env python3
import os
import uuid
import json
from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO, emit, join_room

from agent import JoshAgent
from crm import init_db, upsert_lead, get_all_leads, get_leads_csv, get_stats, get_lead_by_id

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "josh-sales-secret")
socketio = SocketIO(app, cors_allowed_origins="*")

init_db()

# Active sessions: session_id -> JoshAgent
sessions: dict = {}


def get_api_key():
    return os.environ.get("ANTHROPIC_API_KEY", "")


def _sync_crm(session_id: str, agent: JoshAgent, outcome: str = None):
    conversation_text = "\n".join(
        f"{'Josh' if m['role'] == 'assistant' else 'Prospect'}: {m['content']}"
        for m in agent.conversation
        if m["role"] in ("assistant", "user") and not m["content"].startswith("[CALL")
    )
    upsert_lead(session_id, {
        "name": agent.prospect_name,
        "email": agent.prospect_email,
        "phone": agent.prospect_phone,
        "business": agent.prospect_business,
        "city": agent.prospect_city,
        "industry": agent.industry["name"] if agent.industry else None,
        "outcome": outcome or agent.outcome,
        "score": agent.call_score,
        "stage": agent.stage,
        "conversation": conversation_text,
    })


# ── REST ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/leads")
def api_leads():
    return jsonify(get_all_leads())


@app.route("/api/leads/<int:lead_id>")
def api_lead_detail(lead_id: int):
    lead = get_lead_by_id(lead_id)
    if not lead:
        return jsonify({"error": "Not found"}), 404
    return jsonify(lead)


@app.route("/api/leads/<int:lead_id>/notes", methods=["POST"])
def api_lead_notes(lead_id: int):
    from crm import update_lead_notes
    data = request.get_json(force=True, silent=True) or {}
    notes = data.get("notes", "")
    update_lead_notes(lead_id, notes)
    return jsonify({"ok": True})


@app.route("/api/leads/export")
def api_leads_export():
    csv_data = get_leads_csv()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"}
    )


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


# ── Socket.IO ─────────────────────────────────────────────────────────────────

@socketio.on("start_call")
def handle_start_call(data):
    api_key = get_api_key() or data.get("api_key", "")
    if not api_key:
        emit("error", {"message": "No API key configured."})
        return

    session_id = data.get("session_id") or str(uuid.uuid4())
    join_room(session_id)

    agent = JoshAgent(api_key=api_key)
    sessions[session_id] = agent

    opening = agent.opening_line()
    _sync_crm(session_id, agent)

    emit("josh_message", {
        "text": opening,
        "session_id": session_id,
        "score": agent.call_score,
        "stage": agent.stage,
    })


@socketio.on("prospect_message")
def handle_prospect_message(data):
    session_id = data.get("session_id")
    text = data.get("text", "").strip()

    if not session_id or session_id not in sessions:
        emit("error", {"message": "Session not found. Start a new call."})
        return

    agent = sessions[session_id]
    response = agent.chat(text)

    _sync_crm(session_id, agent)

    emit("josh_message", {
        "text": response,
        "session_id": session_id,
        "industry": agent.industry["name"] if agent.industry else None,
        "prospect_name": agent.prospect_name,
        "score": agent.call_score,
        "stage": agent.stage,
        "outcome": agent.outcome,
    })


@socketio.on("end_call")
def handle_end_call(data):
    session_id = data.get("session_id")
    outcome = data.get("outcome", "no_answer")
    if session_id in sessions:
        _sync_crm(session_id, sessions[session_id], outcome)
        del sessions[session_id]
    emit("call_ended", {"session_id": session_id})


@socketio.on("update_lead_info")
def handle_update_lead(data):
    session_id = data.get("session_id")
    if session_id not in sessions:
        return
    agent = sessions[session_id]
    if data.get("name"):
        agent.prospect_name = data["name"]
    if data.get("email"):
        agent.prospect_email = data["email"]
    if data.get("business"):
        agent.prospect_business = data["business"]
    _sync_crm(session_id, agent, "closed")
    emit("lead_saved", {"session_id": session_id})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n Josh is live at http://localhost:{port}\n")
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
