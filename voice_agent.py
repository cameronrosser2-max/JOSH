"""
Josh — Voice AI Agent using
Deepgram + ElevenLabs + Claude
"""
import os
import uuid
import json
import base64
import time
import re
from typing import Optional

from flask import Flask, request, Response
from flask_socketio import SocketIO
from twilio.twiml.voice_response import VoiceResponse, Gather, Connect, Stream
from twilio.rest import Client as TwilioClient

import anthropic
from elevenlabs.client import ElevenLabs as ElevenLabsClient

from config import (
    ANTHROPIC_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER, ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID, PUBLIC_URL, PORT
)
from industries import detect_industry, get_industry_context
from crm import init_db, upsert_lead
from leads_importer import (
    init_queue_table, import_csv, sync_google_sheet,
    get_queue, get_next_pending, mark_called, get_queue_stats
)
import auto_dialer
import lead_finder as lead_finder_module
import vapi_agent
import threading

# ── App Setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "josh-voice-secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

init_db()
init_queue_table()

# Active call sessions
call_sessions: dict = {}

# Map call_sid → lead context for outbound calls (declared here for auto_dialer)
outbound_context: dict = {}


# ── Josh System Prompt ────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are Josh, an elite sales closer on a LIVE PHONE CALL. You sell high-converting websites to trade businesses — HVAC, plumbing, electricians, and repair shops. You have 10 years of sales experience and close 40% of your calls.

══ VOICE RULES — NON-NEGOTIABLE ══
- This is a REAL phone call. Max 2 sentences per response. Never more.
- Zero markdown, zero lists, zero asterisks. Pure spoken English only.
- Never say: "Great!", "Absolutely!", "Certainly!", "Of course!", "I understand" — these sound robotic.
- Never repeat anything you already said.
- Speak like a confident human being, not a sales bot.
- Use the business name and city naturally when you know them.
- Always end your turn with either a question or a statement that creates tension.

══ WHO YOU ARE ══
You're not a vendor. You're a specialist who helps trade businesses stop losing money to competitors who rank higher on Google. You've helped hundreds of HVAC companies, plumbers, electricians and repair shops in their exact situation. You don't need this deal — you're doing them a favor by calling.

══ SALES PSYCHOLOGY YOU USE ══
- NEPQ (Neuro-Emotional Persuasion): Ask questions that make them feel the pain themselves. Don't tell them they have a problem — make them admit it.
- PATTERN INTERRUPT: Open in a way they've never heard. Reference their specific business.
- FUTURE PACE: Paint the picture of what life looks like WITH the website working.
- TAKEAWAY: You're not desperate. If they're not a fit, you move on. This creates desire.
- ASSUMPTIVE LANGUAGE: Say "when we build your site" not "if you decide to move forward."
- SOCIAL PROOF: Mention similar businesses you've helped (HVAC in Dallas, plumber in Miami, etc.)

══ CONVERSATION STAGES ══

STAGE 1 — PATTERN INTERRUPT OPEN:
Don't ask if they have 30 seconds. Just go. Reference their business specifically.
Example: "Hey, I was just looking at [Business Name] online — quick question for you. How are you getting most of your new customers right now?"
Or: "Hey, this is Josh — I specialize in helping [industry] businesses in [city] get more booked jobs from Google. Quick question — is your phone ringing as much as you want it to?"

STAGE 2 — DISCOVERY (ask ONE question at a time, listen hard):
- "How are most new customers finding you right now?"
- "And when someone searches for [HVAC/plumbing/electrical] in [their city] on Google — do you show up?"
- "Do you have a website right now?" → If yes: "And is it actually generating calls and booked jobs for you, or is it more just sitting there?"
- "What does a typical job run you — ballpark?" (Get their average job value — critical for ROI close)

STAGE 3 — AGITATION (make the pain real using THEIR words):
Reflect exactly what they said back at them with the financial cost attached.
Example: "So if I heard you right — you're getting most of your work from word of mouth, your site isn't really bringing in calls, and meanwhile someone's searching 'HVAC repair in [city]' right now and calling one of your competitors instead of you. That's real money walking out the door every single day."
Then pause. Let it land. Then ask: "How long has that been going on?"

STAGE 4 — SOLUTION PITCH (30 seconds max, outcome-focused):
"What we do is build websites specifically engineered to rank on Google and turn visitors into calls and booked jobs — not just something that looks nice. We've done this for [similar business] in [nearby city] and they went from getting zero online leads to booking 8 to 12 new jobs a month from their site alone."

STAGE 5 — TRIAL CLOSE before price:
"Based on what you've told me — does having a website that actually drives calls make sense for where you're trying to take the business?"
Wait for yes. If yes → go to price. If hesitation → handle it first.

STAGE 6 — PRICE WITH ROI ANCHOR:
"Investment is between $500 and $1,500 depending on what we build. And look — you told me a typical [job type] runs you [their number]. That means one job covers the entire thing. Everything after that is pure profit."
Then immediately: "The way we work is we get started today, build it out over the next week, and you're live and getting traffic within 10 days."

STAGE 7 — ASSUMPTIVE CLOSE:
Don't ask "would you like to move forward?" — that invites hesitation.
Instead: "So to get this rolling — what's the best email to send your project brief to?"
Or: "I just need your name, best email, and we'll lock in your build slot for this week."

STAGE 8 — OBJECTION HANDLING:
Use the FEEL/FELT/FOUND framework + a specific redirect, then re-close immediately.

- "Too expensive / can't afford it":
  "I get that — a lot of the [industry] owners I work with felt the same way before we started. What they found was one extra job a month from the site paid for everything. What does a slow month look like for you right now?"

- "Not interested":
  "Fair enough. Before I let you go — is your lead flow where you want it to be, or is that something you're actively trying to improve?"

- "I already have a website":
  "Good. Is it ranking on the first page of Google when someone searches [their service] in [their city]? Because if not, it's essentially invisible."

- "Send me some information / email me":
  "I can do that — but honestly everything I'd send you we can cover in two minutes right now. What's the main thing you'd want to know?"

- "I need to think about it":
  "Totally fair. What specifically is making you hesitate — is it the timing, the investment, or something else?"

- "I'm too busy":
  "That's actually why this works for you — we handle every single part of it. You just answer a few questions and we build the whole thing. Takes you about 15 minutes total."

- "I don't trust this / is this a scam":
  "Smart to be skeptical — there's a lot of garbage out there. Here's what I'd say: we don't take payment until you've seen and approved a full mockup of your site. You literally see it before you pay a dollar."

- "I use a guy / I have someone":
  "Good — is he actively getting you new customers from Google right now, or more just maintaining what's already there?"

══ CLOSING RULES ══
- Always re-close after handling an objection — never let an objection end the conversation.
- If you get 3 hard no's, exit gracefully: "No problem at all — if things change down the road, we'd be happy to help. Take care."
- If they're ready, move to intake FAST. Don't keep selling once they say yes.

══ INTAKE (when they agree) ══
"Perfect. I just need three things — your name, your best email address, and we'll get your build slot locked in for this week."
Collect: first name → email → confirm business name → tell them next steps ("You'll get a project brief in your inbox within the hour. We'll have a mockup ready in 3 to 5 days.")

{industry_context}
""".strip()


# ── Call Session ──────────────────────────────────────────────────────────────
class CallSession:
    def __init__(self, call_sid: str, business_name: str = None,
                 industry_key: str = None, address: str = None):
        self.call_sid = call_sid
        self.session_id = str(uuid.uuid4())
        self.conversation = []
        self.prospect_name = None
        self.prospect_email = None
        self.prospect_business = business_name
        self.prospect_address = address
        self.outcome = "in_progress"
        self.anthropic = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.xi_client = ElevenLabsClient(api_key=ELEVENLABS_API_KEY) if ELEVENLABS_API_KEY else None
        self.created_at = time.time()

        # Pre-load industry from queue data
        from industries import INDUSTRIES
        self.industry = INDUSTRIES.get(industry_key) if industry_key else None

    def _city_from_address(self) -> str:
        """Extract city from address string."""
        if not self.prospect_address:
            return ""
        parts = self.prospect_address.split(",")
        return parts[1].strip() if len(parts) >= 2 else ""

    def build_system(self) -> str:
        context = get_industry_context(self.industry) if self.industry else ""
        if context:
            context = f"\n\nINDUSTRY CONTEXT (weave in naturally):\n{context}"

        # Inject prospect-specific intel so Josh opens with personalization
        intel = ""
        if self.prospect_business or self.prospect_address:
            city = self._city_from_address()
            intel = "\n\nPROSPECT INTEL (use this to personalize — don't read it robotically):\n"
            if self.prospect_business:
                intel += f"- Business name: {self.prospect_business}\n"
            if city:
                intel += f"- City: {city}\n"
            if self.industry:
                intel += f"- Industry: {self.industry['name']}\n"
            intel += "Use the business name and city naturally in your opening and throughout the call.\n"

        return SYSTEM_PROMPT.replace("{industry_context}", context + intel)

    def extract_info(self, text: str):
        # Only detect industry if we don't already have it
        if not self.industry:
            self.industry = detect_industry(text)

        if not self.prospect_email:
            m = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
            if m:
                self.prospect_email = m.group()

        if not self.prospect_name:
            m = re.search(r"(?:i'?m|my name is|this is|name'?s)\s+([A-Z][a-z]+)", text, re.IGNORECASE)
            if m:
                self.prospect_name = m.group(1)

    def think(self, user_text: str) -> str:
        self.extract_info(user_text)
        self.conversation.append({"role": "user", "content": user_text})

        resp = self.anthropic.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=180,
            system=self.build_system(),
            messages=self.conversation,
        )
        reply = resp.content[0].text.strip()
        self.conversation.append({"role": "assistant", "content": reply})
        return reply

    def opening_line(self) -> str:
        city = self._city_from_address()
        context_hint = ""
        if self.prospect_business:
            context_hint += f" You are calling {self.prospect_business}."
        if city:
            context_hint += f" They are located in {city}."
        if self.industry:
            context_hint += f" They are in the {self.industry['name']} industry."

        self.conversation.append({
            "role": "user",
            "content": f"[Prospect just answered the phone.{context_hint} Open with a personalized pattern interrupt — use their business name and city. Do NOT ask if they have 30 seconds. Just go straight into your opener.]"
        })
        resp = self.anthropic.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=120,
            system=self.build_system(),
            messages=self.conversation,
        )
        reply = resp.content[0].text.strip()
        self.conversation.append({"role": "assistant", "content": reply})
        return reply

    def text_to_speech(self, text: str) -> Optional[bytes]:
        """Convert text to speech via ElevenLabs. Returns raw MP3 bytes."""
        if not self.xi_client:
            return None
        try:
            audio = self.xi_client.text_to_speech.convert(
                voice_id=ELEVENLABS_VOICE_ID,
                text=text,
                model_id="eleven_turbo_v2_5",
                output_format="mp3_44100_128",
                voice_settings={
                    "stability": 0.45,
                    "similarity_boost": 0.80,
                    "style": 0.20,
                    "use_speaker_boost": True,
                }
            )
            chunks = b"".join(audio)
            return chunks
        except Exception as e:
            print(f"[ElevenLabs error] {e}")
            return None

    def save_to_crm(self, outcome: str = None):
        transcript = "\n".join(
            f"{'Josh' if m['role'] == 'assistant' else 'Caller'}: {m['content']}"
            for m in self.conversation
            if m["role"] in ("user", "assistant") and not m["content"].startswith("[")
        )
        upsert_lead(self.session_id, {
            "name": self.prospect_name,
            "email": self.prospect_email,
            "business": self.prospect_business,
            "industry": self.industry["name"] if self.industry else None,
            "outcome": outcome or self.outcome,
            "conversation": transcript,
        })


# ── TwiML Helpers ─────────────────────────────────────────────────────────────
def twiml_say(text: str, gather_action: str = None) -> str:
    """Build TwiML that speaks text, then listens for a response."""
    resp = VoiceResponse()

    if gather_action:
        gather = Gather(
            input="speech",
            action=gather_action,
            method="POST",
            speech_timeout="auto",
            speech_model="phone_call",
            enhanced=True,
            language="en-US",
        )
        gather.say(text, voice="Polly.Matthew-Neural")
        resp.append(gather)
        # Fallback if no speech detected
        resp.say("I didn't catch that. Let me try again.", voice="Polly.Matthew-Neural")
        resp.redirect(gather_action, method="POST")
    else:
        resp.say(text, voice="Polly.Matthew-Neural")

    return str(resp)


def twiml_play_and_gather(audio_url: str, gather_action: str) -> str:
    """Play ElevenLabs audio then gather speech."""
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action=gather_action,
        method="POST",
        speech_timeout="auto",
        speech_model="phone_call",
        enhanced=True,
        language="en-US",
    )
    gather.play(audio_url)
    resp.append(gather)
    resp.say("I didn't catch that.", voice="Polly.Matthew-Neural")
    resp.redirect(gather_action, method="POST")
    return str(resp)


# ── Vapi init ─────────────────────────────────────────────────────────────────
def _init_vapi():
    """Push Josh's system prompt and webhook URL to Vapi on startup."""
    try:
        base_prompt = SYSTEM_PROMPT.replace("{industry_context}", "").strip()
        vapi_agent.update_assistant(
            system_prompt=base_prompt,
            webhook_url=f"{PUBLIC_URL}/vapi/webhook",
        )
    except Exception as e:
        print(f"[VAPI] Warning — could not update assistant: {e}")

threading.Thread(target=_init_vapi, daemon=True).start()


# ── Auto-dialer init ──────────────────────────────────────────────────────────
def _make_call(to: str, business_name=None, industry=None, address=None) -> str:
    """Called by auto_dialer to place a call via Vapi. Returns call ID."""
    base_prompt = SYSTEM_PROMPT.replace("{industry_context}", "").strip()
    call_id = vapi_agent.make_call(
        to=to,
        business_name=business_name,
        industry=industry,
        address=address,
        system_prompt=base_prompt,
    )
    # Track in call_sessions so auto_dialer knows the call is active
    call_sessions[call_id] = {"vapi": True, "business_name": business_name}
    return call_id

auto_dialer.init(_make_call, call_sessions)

# ── Flask Routes ──────────────────────────────────────────────────────────────


@app.route("/incoming", methods=["POST"])
def incoming_call():
    """Twilio hits this when someone calls Josh's number."""
    call_sid = request.form.get("CallSid", str(uuid.uuid4()))
    from_number = request.form.get("From", "Unknown")

    # Pull pre-loaded lead context for outbound calls
    ctx = outbound_context.pop(call_sid, {})
    session = CallSession(
        call_sid,
        business_name=ctx.get("business_name"),
        industry_key=ctx.get("industry"),
        address=ctx.get("address"),
    )
    call_sessions[call_sid] = session

    print(f"\n[CALL] {'Outbound' if ctx else 'Inbound'} | {ctx.get('business_name', from_number)} | SID: {call_sid}")

    opening = session.opening_line()
    print(f"[JOSH] {opening}")

    # Try ElevenLabs first, fall back to Polly
    audio_bytes = session.text_to_speech(opening)
    if audio_bytes:
        audio_url = _store_audio(call_sid, "opening", audio_bytes)
        twiml = twiml_play_and_gather(audio_url, f"{PUBLIC_URL}/respond/{call_sid}")
    else:
        twiml = twiml_say(opening, gather_action=f"{PUBLIC_URL}/respond/{call_sid}")

    return Response(twiml, mimetype="text/xml")


@app.route("/respond/<call_sid>", methods=["POST"])
def respond(call_sid: str):
    """Called after Twilio transcribes the prospect's speech."""
    session = call_sessions.get(call_sid)
    if not session:
        resp = VoiceResponse()
        resp.say("Sorry, something went wrong. Goodbye.", voice="Polly.Matthew-Neural")
        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    speech_result = request.form.get("SpeechResult", "").strip()
    confidence = float(request.form.get("Confidence", 0))

    print(f"[CALLER] {speech_result} (confidence: {confidence:.2f})")

    if not speech_result:
        twiml = twiml_say(
            "Sorry, I didn't catch that — could you say that again?",
            gather_action=f"{PUBLIC_URL}/respond/{call_sid}"
        )
        return Response(twiml, mimetype="text/xml")

    # Detect hang-up intent
    lower = speech_result.lower()
    if any(w in lower for w in ["goodbye", "bye", "hang up", "not interested, goodbye"]):
        session.outcome = "no_answer"
        session.save_to_crm("no_answer")
        del call_sessions[call_sid]
        resp = VoiceResponse()
        resp.say("No problem — take care!", voice="Polly.Matthew-Neural")
        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    # Detect closed deal
    if any(w in lower for w in ["yes", "sounds good", "let's do it", "i'm in", "go ahead"]):
        if len(session.conversation) > 6:  # Only treat as close if deep enough in convo
            session.outcome = "interested"

    josh_reply = session.think(speech_result)
    print(f"[JOSH] {josh_reply}")

    # Detect intake stage — save as closed if collecting info
    if any(w in josh_reply.lower() for w in ["name", "email", "lock in", "get started"]):
        session.outcome = "interested"

    session.save_to_crm()

    audio_bytes = session.text_to_speech(josh_reply)
    if audio_bytes:
        audio_url = _store_audio(call_sid, str(len(session.conversation)), audio_bytes)
        twiml = twiml_play_and_gather(audio_url, f"{PUBLIC_URL}/respond/{call_sid}")
    else:
        twiml = twiml_say(josh_reply, gather_action=f"{PUBLIC_URL}/respond/{call_sid}")

    return Response(twiml, mimetype="text/xml")


@app.route("/status", methods=["POST"])
def call_status():
    """Twilio status callback — fires when call ends."""
    call_sid = request.form.get("CallSid")
    status = request.form.get("CallStatus")
    print(f"[STATUS] {call_sid} → {status}")

    if call_sid in call_sessions:
        session = call_sessions[call_sid]
        if status in ("completed", "busy", "no-answer", "failed", "canceled"):
            if session.outcome == "in_progress":
                session.outcome = "no_answer" if status != "completed" else "in_progress"
            session.save_to_crm()
            del call_sessions[call_sid]
    return "", 204


@app.route("/make-call", methods=["POST"])
def make_outbound_call():
    """API endpoint to trigger Josh to call a prospect."""
    data = request.get_json(force=True)
    to_number = data.get("to")
    if not to_number:
        return {"error": "Missing 'to' phone number"}, 400

    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        return {"error": "Twilio credentials not configured"}, 500

    client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    call = client.calls.create(
        to=to_number,
        from_=TWILIO_PHONE_NUMBER,
        url=f"{PUBLIC_URL}/incoming",
        status_callback=f"{PUBLIC_URL}/status",
        status_callback_method="POST",
    )
    print(f"[OUTBOUND] Calling {to_number} | SID: {call.sid}")
    return {"call_sid": call.sid, "status": call.status}


# ── Audio Storage (temp files served back to Twilio) ──────────────────────────
import tempfile
from pathlib import Path

AUDIO_DIR = Path("static/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def _store_audio(call_sid: str, turn: str, mp3_bytes: bytes) -> str:
    """Save MP3 to static dir and return public URL."""
    filename = f"{call_sid}_{turn}.mp3"
    path = AUDIO_DIR / filename
    path.write_bytes(mp3_bytes)
    return f"{PUBLIC_URL}/static/audio/{filename}"


# ── Dashboard ─────────────────────────────────────────────────────────────────
from crm import get_all_leads, get_leads_csv, get_stats
from flask import jsonify, render_template


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/leads")
def api_leads():
    return jsonify(get_all_leads())


@app.route("/api/leads/export")
def api_export():
    from flask import Response as FlaskResponse
    return FlaskResponse(
        get_leads_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"}
    )


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/api/active-calls")
def api_active():
    return jsonify([
        {
            "call_sid": s.call_sid,
            "industry": s.industry["name"] if s.industry else None,
            "name": s.prospect_name,
            "turns": len([m for m in s.conversation if m["role"] == "user"]),
            "outcome": s.outcome,
        }
        for s in call_sessions.values()
    ])


# ── Vapi Webhook ─────────────────────────────────────────────────────────────

@app.route("/vapi/webhook", methods=["POST"])
def vapi_webhook():
    """Receives all Vapi call events."""
    data = request.get_json(force=True, silent=True) or {}
    msg = data.get("message", {})
    event = msg.get("type", "")
    call = msg.get("call", {})
    call_id = call.get("id", "")

    print(f"[VAPI EVENT] {event} | {call_id[:8] if call_id else '?'}...")

    if event == "end-of-call-report":
        # Pull transcript and analysis from the report
        transcript = msg.get("transcript", "")
        summary = msg.get("analysis", {}).get("summary", "")
        success = msg.get("analysis", {}).get("successEvaluation", "")
        ended_reason = msg.get("endedReason", "")

        # Determine outcome
        outcome = "no_answer"
        if success == "true" or success is True:
            outcome = "closed"
        elif any(w in transcript.lower() for w in ["email", "yes", "sounds good", "let's do it", "i'm in", "go ahead"]):
            outcome = "interested"
        elif ended_reason in ("customer-ended-call", "assistant-ended-call"):
            outcome = "no_answer"

        # Extract email from transcript
        email = None
        import re as _re
        m = _re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", transcript)
        if m:
            email = m.group()

        # Extract name from transcript
        name = None
        nm = _re.search(r"(?:i'?m|my name is|this is|name'?s)\s+([A-Z][a-z]+)", transcript)
        if nm:
            name = nm.group(1)

        # Pull lead context from call_sessions
        ctx = call_sessions.pop(call_id, {})
        business = ctx.get("business_name") or call.get("customer", {}).get("name", "")

        # Save to CRM
        session_id = str(uuid.uuid4())
        upsert_lead(session_id, {
            "name": name,
            "email": email,
            "business": business,
            "industry": None,
            "outcome": outcome,
            "conversation": transcript,
        })

        print(f"[VAPI] Call ended — {business} | outcome: {outcome} | reason: {ended_reason}")
        if summary:
            print(f"[VAPI] Summary: {summary}")

    elif event == "status-update":
        status = msg.get("status", "")
        if status in ("ended", "failed"):
            call_sessions.pop(call_id, None)

    return "", 200


# ── Lead Queue API ────────────────────────────────────────────────────────────

@app.route("/api/queue")
def api_queue():
    return jsonify(get_queue())


@app.route("/api/queue/stats")
def api_queue_stats():
    return jsonify(get_queue_stats())


@app.route("/api/queue/next")
def api_queue_next():
    lead = get_next_pending()
    return jsonify(lead or {})


@app.route("/api/queue/call-next", methods=["POST"])
def api_call_next():
    """Dial the next lead in the queue."""
    lead = get_next_pending()
    if not lead:
        return jsonify({"error": "No pending leads in queue"}), 404

    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        return jsonify({"error": "Twilio not configured — add credentials to .env"}), 500

    data = request.get_json(force=True, silent=True) or {}
    test_number = data.get("test_number", "").strip()
    dial_to = test_number if test_number else lead["phone"]

    try:
        base_prompt = SYSTEM_PROMPT.replace("{industry_context}", "").strip()
        call_id = vapi_agent.make_call(
            to=dial_to,
            business_name=lead.get("business_name"),
            industry=lead.get("industry"),
            address=lead.get("address"),
            system_prompt=base_prompt,
        )
        call_sessions[call_id] = {"vapi": True, "business_name": lead.get("business_name")}
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    mark_called(lead["phone"], "calling")
    print(f"[QUEUE] Dialing {lead['business_name']} at {dial_to} | Vapi ID: {call_id}")
    return jsonify({"call_id": call_id, "lead": lead})


@app.route("/api/queue/call-lead", methods=["POST"])
def api_call_specific_lead():
    """Dial a specific lead by ID."""
    data = request.get_json(force=True)
    phone = data.get("phone")
    business = data.get("business_name", "")

    if not phone:
        return jsonify({"error": "Missing phone"}), 400

    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        return jsonify({"error": "Twilio not configured — add credentials to .env"}), 500

    try:
        base_prompt = SYSTEM_PROMPT.replace("{industry_context}", "").strip()
        call_id = vapi_agent.make_call(
            to=phone,
            business_name=data.get("business_name"),
            industry=data.get("industry"),
            address=data.get("address"),
            system_prompt=base_prompt,
        )
        call_sessions[call_id] = {"vapi": True, "business_name": data.get("business_name")}
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    mark_called(phone, "calling")
    print(f"[QUEUE] Dialing {business} at {phone} | Vapi ID: {call_id}")
    return jsonify({"call_id": call_id, "status": "queued"})


@app.route("/api/queue/import-csv", methods=["POST"])
def api_import_csv():
    """Upload a CSV file and import into queue."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file.filename.endswith(".csv"):
        return jsonify({"error": "File must be a .csv"}), 400

    tmp_path = f"/tmp/josh_import_{uuid.uuid4()}.csv"
    file.save(tmp_path)
    result = import_csv(tmp_path)
    return jsonify(result)


@app.route("/api/queue/sync-sheets", methods=["POST"])
def api_sync_sheets():
    """Sync from Google Sheets using sheet ID from request body."""
    data = request.get_json(force=True)
    sheet_id = data.get("sheet_id", "").strip()
    tab_name = data.get("tab_name", "").strip() or None

    if not sheet_id:
        return jsonify({"error": "Missing sheet_id"}), 400

    result = sync_google_sheet(sheet_id, tab_name=tab_name)
    return jsonify(result)


@app.route("/api/queue/update-status", methods=["POST"])
def api_update_status():
    """Manually update a lead's status in the queue."""
    data = request.get_json(force=True)
    phone = data.get("phone")
    status = data.get("status")
    if not phone or not status:
        return jsonify({"error": "Missing phone or status"}), 400

    import sqlite3 as _sqlite3
    conn = _sqlite3.connect("leads.db")
    conn.execute("UPDATE dial_queue SET status = ? WHERE phone = ?", (status, phone))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── Auto-Dialer API ───────────────────────────────────────────────────────────

@app.route("/api/dialer/start", methods=["POST"])
def api_dialer_start():
    data = request.get_json(force=True, silent=True) or {}
    test_number = (data.get("test_number") or "").strip() or None
    result = auto_dialer.start(test_number=test_number)
    return jsonify(result)


@app.route("/api/dialer/stop", methods=["POST"])
def api_dialer_stop():
    return jsonify(auto_dialer.stop())


@app.route("/api/dialer/pause", methods=["POST"])
def api_dialer_pause():
    return jsonify(auto_dialer.pause())


@app.route("/api/dialer/delay", methods=["POST"])
def api_dialer_delay():
    data = request.get_json(force=True, silent=True) or {}
    seconds = data.get("seconds", 30)
    return jsonify(auto_dialer.set_delay(seconds))


@app.route("/api/dialer/status")
def api_dialer_status():
    return jsonify(auto_dialer.get_status())


# ── Lead Finder API ───────────────────────────────────────────────────────────

_finder_status = {"running": False, "log": [], "result": None}


@app.route("/api/finder/start", methods=["POST"])
def api_finder_start():
    if _finder_status["running"]:
        return jsonify({"error": "Finder already running"}), 400

    data = request.get_json(force=True, silent=True) or {}
    api_key = data.get("google_api_key", "").strip()
    cities = data.get("cities") or lead_finder_module.DEFAULT_CITIES
    industries = data.get("industries") or None
    max_stars = data.get("max_stars", 3.5)
    require_no_website = data.get("require_no_website", True)

    if not api_key:
        return jsonify({"error": "Google Places API key required"}), 400

    _finder_status["running"] = True
    _finder_status["log"] = []
    _finder_status["result"] = None

    def run():
        def log(msg):
            _finder_status["log"].append({"time": __import__("time").strftime("%H:%M:%S"), "msg": msg})
        def should_stop():
            return not _finder_status["running"]
        try:
            result = lead_finder_module.find_and_queue_leads(
                api_key=api_key,
                cities=cities,
                industries=industries,
                max_stars=max_stars,
                require_no_website=require_no_website,
                progress_callback=log,
                stop_flag=should_stop,
            )
            _finder_status["result"] = result
        except Exception as e:
            _finder_status["log"].append({"time": __import__("time").strftime("%H:%M:%S"), "msg": f"Error: {e}"})
        finally:
            _finder_status["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/finder/stop", methods=["POST"])
def api_finder_stop():
    _finder_status["running"] = False
    return jsonify({"status": "stopped"})


@app.route("/api/finder/status")
def api_finder_status():
    return jsonify({
        "running": _finder_status["running"],
        "log": _finder_status["log"][-30:],
        "result": _finder_status["result"],
    })


if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════════════╗
║      Josh — Voice AI Sales Agent  🎙️             ║
╠══════════════════════════════════════════════════╣
║  Dashboard : http://localhost:{PORT}
║  Public URL: {PUBLIC_URL}
╚══════════════════════════════════════════════════╝
""")
    socketio.run(app, host="0.0.0.0", port=PORT, debug=False)
