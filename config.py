import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (works locally); Railway injects env vars directly
load_dotenv(Path(__file__).parent / ".env")


def _get(key, default=""):
    return os.environ.get(key, default)


ANTHROPIC_API_KEY    =_get("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")
TWILIO_ACCOUNT_SID   = _get("TSK6137f89965337b0b480865291f557f12")
TWILIO_AUTH_TOKEN    = _get("0033a76298cf19a63b46866afd4e816d")
TWILIO_PHONE_NUMBER  = _get("+16823985182")
ELEVENLABS_API_KEY   = 
_get("dfe170f13fbc18bb50c85dba234b2095868b62a3e95c2c2bea818411aa07ac1b")
ELEVENLABS_VOICE_ID  = _get("7EzWGsX10sAS4c9m9cPf")
PUBLIC_URL           = _get(""http://localhost:5000”")
PORT                 = int(_get("5000") or 5000)
DASHBOARD_PASSWORD   = _get("Josh123")
