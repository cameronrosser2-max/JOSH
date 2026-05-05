"""
Auto Dialer — works through the lead queue automatically.
Calls one lead at a time, waits for completion, moves to the next.
"""
import time
import threading
from leads_importer import get_next_pending, mark_called

# Dialer state
_state = {
    "running": False,
    "paused": False,
    "current_lead": None,
    "calls_made": 0,
    "calls_connected": 0,
    "log": [],
    "thread": None,
}

# Injected at runtime from voice_agent
_make_call_fn = None
_call_sessions = None

DELAY_BETWEEN_CALLS = 30  # seconds to wait between calls (default)
MAX_CALLS_PER_RUN = 200   # safety cap


def init(make_call_fn, call_sessions: dict):
    global _make_call_fn, _call_sessions
    _make_call_fn = make_call_fn
    _call_sessions = call_sessions


def set_delay(seconds: int):
    global DELAY_BETWEEN_CALLS
    DELAY_BETWEEN_CALLS = max(5, int(seconds))
    return {"delay": DELAY_BETWEEN_CALLS}


def _log(msg: str):
    print(f"[DIALER] {msg}")
    _state["log"].append({"time": time.strftime("%H:%M:%S"), "msg": msg})
    if len(_state["log"]) > 200:
        _state["log"] = _state["log"][-200:]


def _run_loop(test_number: str = None):
    _log("Auto-dialer started")
    calls_this_run = 0

    while _state["running"] and calls_this_run < MAX_CALLS_PER_RUN:
        # Pause support
        while _state["paused"] and _state["running"]:
            time.sleep(1)

        if not _state["running"]:
            break

        lead = get_next_pending()
        if not lead:
            _log("No more pending leads — dialer complete")
            break

        dial_to = test_number if test_number else lead["phone"]
        _state["current_lead"] = lead
        _log(f"Calling {lead['business_name']} at {dial_to}...")

        try:
            call_sid = _make_call_fn(
                to=dial_to,
                business_name=lead.get("business_name"),
                industry=lead.get("industry"),
                address=lead.get("address"),
            )
            mark_called(lead["phone"], "calling")
            _state["calls_made"] += 1
            calls_this_run += 1
            _log(f"  Connected | SID: {call_sid}")

            # Wait for call to finish before dialing next
            wait_start = time.time()
            while time.time() - wait_start < 180:  # max 3 min wait
                if call_sid not in (_call_sessions or {}):
                    break
                time.sleep(2)

            _log(f"  Call ended | waiting {DELAY_BETWEEN_CALLS}s before next...")
            time.sleep(DELAY_BETWEEN_CALLS)

        except Exception as e:
            _log(f"  Error calling {lead['phone']}: {e}")
            mark_called(lead["phone"], "error")
            time.sleep(3)

    _state["running"] = False
    _state["current_lead"] = None
    _log(f"Dialer stopped. Total calls this run: {calls_this_run}")


def start(test_number: str = None):
    if _state["running"]:
        return {"error": "Dialer already running"}
    _state["running"] = True
    _state["paused"] = False
    _state["log"] = []
    t = threading.Thread(target=_run_loop, args=(test_number,), daemon=True)
    _state["thread"] = t
    t.start()
    return {"status": "started"}


def pause():
    _state["paused"] = not _state["paused"]
    return {"paused": _state["paused"]}


def stop():
    _state["running"] = False
    _state["paused"] = False
    _state["current_lead"] = None
    return {"status": "stopped"}


def get_status():
    return {
        "running": _state["running"],
        "paused": _state["paused"],
        "current_lead": _state["current_lead"],
        "calls_made": _state["calls_made"],
        "log": _state["log"][-20:],
    }
