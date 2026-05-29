"""
SMS follow-up module — sends a closing text after hot calls via Twilio.
Fires automatically when a call ends with outcome 'interested' or 'closed'.
"""
from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER


def send_followup(to: str, business_name: str = None, prospect_name: str = None,
                  industry: str = None) -> dict:
    """
    Send a post-call follow-up SMS to a hot lead.
    Returns dict with ok/error.
    """
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        return {"ok": False, "error": "Twilio not configured"}

    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        name_part = f" {prospect_name}" if prospect_name else ""
        biz_part  = f" for {business_name}" if business_name else ""
        trade     = industry or "your trade business"

        body = (
            f"Hey{name_part}, it's Josh — great talking just now. "
            f"I'm putting together your project brief{biz_part} right now. "
            f"Your build slot is held for 24 hrs. "
            f"Reply YES to confirm and I'll send over everything to get started. "
            f"One job from the site covers the whole thing."
        )

        msg = client.messages.create(
            body=body,
            from_=TWILIO_PHONE_NUMBER,
            to=to,
        )
        print(f"[SMS] Follow-up sent → {to} | SID: {msg.sid}")
        return {"ok": True, "sid": msg.sid}

    except Exception as e:
        print(f"[SMS] Failed → {to}: {e}")
        return {"ok": False, "error": str(e)}


def send_voicemail_followup(to: str, business_name: str = None) -> dict:
    """
    Send an SMS after a no-answer call so they know who called.
    """
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        return {"ok": False, "error": "Twilio not configured"}

    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        biz_part = f" at {business_name}" if business_name else ""

        body = (
            f"Hey{biz_part}, this is Josh — I tried reaching you about getting your business "
            f"ranking on Google and bringing in more calls. "
            f"Quick question: is your lead flow where you want it to be right now? "
            f"Reply back or call me — takes 2 minutes."
        )

        msg = client.messages.create(
            body=body,
            from_=TWILIO_PHONE_NUMBER,
            to=to,
        )
        print(f"[SMS] Voicemail follow-up → {to} | SID: {msg.sid}")
        return {"ok": True, "sid": msg.sid}

    except Exception as e:
        print(f"[SMS] Failed → {to}: {e}")
        return {"ok": False, "error": str(e)}
