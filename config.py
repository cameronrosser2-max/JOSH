import os
from dotenv import dotenv_values

# Load .env locally; on Railway env vars are injected automatically
_env = dotenv_values("/Users/cameronrosser/ai-sales-agent/.env")

def _get(key, default=""):
    # Railway injects env vars directly into os.environ — check both
    return _env.get(key) or os.environ.get(key, default)

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
