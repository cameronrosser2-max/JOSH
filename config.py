import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (works locally); Railway injects env vars directly
load_dotenv(Path(__file__).parent / ".env")


def _get(key, default=""):
    return os.environ.get(key, default)


ANTHROPIC_API_KEY    = _get("ANTHROPIC_API_KEY")
TWILIO_ACCOUNT_SID   = _get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN    = _get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER  = _get("TWILIO_PHONE_NUMBER")
ELEVENLABS_API_KEY   = _get("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID  = _get("ELEVENLABS_VOICE_ID") or "TxGEqnHWrfWFTfGW9XjX"
VAPI_API_KEY         = _get("VAPI_API_KEY")
VAPI_ASSISTANT_ID    = _get("VAPI_ASSISTANT_ID")
VAPI_PHONE_NUMBER_ID = _get("VAPI_PHONE_NUMBER_ID")
PUBLIC_URL           = _get("PUBLIC_URL") or "http://localhost:5000"
PORT                 = int(_get("PORT") or 5000)
DASHBOARD_PASSWORD   = _get("DASHBOARD_PASSWORD")
