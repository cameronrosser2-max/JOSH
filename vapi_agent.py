"""
Vapi integration for Josh.
Handles assistant updates and outbound call placement.
Vapi manages the full call — STT, LLM, TTS, phone connection.
"""
import requests
from config import VAPI_API_KEY, VAPI_ASSISTANT_ID, VAPI_PHONE_NUMBER_ID, PUBLIC_URL

VAPI_BASE = "https://api.vapi.ai"


def _headers():
    return {
        "Authorization": f"Bearer {VAPI_API_KEY}",
        "Content-Type": "application/json",
    }


def update_assistant(system_prompt: str, webhook_url: str = None):
    """Push updated system prompt and webhook URL to Josh on Vapi."""
    payload = {
        "model": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "temperature": 0.7,
            "maxTokens": 180,
            "messages": [
                {"role": "system", "content": system_prompt}
            ],
        },
        "voice": {
            "provider": "vapi",
            "voiceId": "Elliot",
        },
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-3",
            "language": "en",
        },
        "firstMessageMode": "assistant-speaks-first",
        "endCallFunctionEnabled": True,
        "endCallMessage": "No problem at all — take care!",
        "silenceTimeoutSeconds": 20,
        "maxDurationSeconds": 600,
        "backgroundSound": "off",
        "backchannelingEnabled": False,
    }

    if webhook_url:
        payload["serverUrl"] = webhook_url

    resp = requests.patch(
        f"{VAPI_BASE}/assistant/{VAPI_ASSISTANT_ID}",
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    data = resp.json()
    if resp.status_code not in (200, 201):
        raise Exception(f"Failed to update assistant: {data}")
    print(f"[VAPI] Assistant updated — ID: {VAPI_ASSISTANT_ID}")
    return data


def make_call(to: str, business_name: str = None, industry: str = None,
              address: str = None, system_prompt: str = None) -> str:
    """
    Place an outbound call via Vapi.
    Returns the Vapi call ID.
    """
    city = _extract_city(address)

    # Personalized opening line per lead
    first_message = _build_opening(business_name, industry, city)

    # Per-call assistant overrides — inject lead intel into the prompt
    overrides = {"firstMessage": first_message}

    if system_prompt:
        # Inject lead-specific intel into the system prompt for this call
        intel = ""
        if business_name or city or industry:
            intel = "\n\nPROSPECT INTEL — use naturally throughout the call:\n"
            if business_name:
                intel += f"- Business name: {business_name}\n"
            if city:
                intel += f"- City: {city}\n"
            if industry:
                intel += f"- Industry: {industry}\n"
            intel += "Open with their business name and city. Do NOT read this list — weave it in naturally.\n"

        overrides["model"] = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "temperature": 0.7,
            "maxTokens": 180,
            "messages": [
                {"role": "system", "content": system_prompt + intel}
            ],
        }

    voicemail_msg = (
        f"Hey{', this is Josh' if not business_name else ''} — "
        f"{'I was calling for ' + business_name + ' — ' if business_name else ''}"
        f"I help {'trade' if not industry else industry} businesses get more booked jobs from Google. "
        f"If your phone isn't ringing as much as you want, give me a call back or I'll try you again. "
        f"Talk soon."
    )

    payload = {
        "assistantId": VAPI_ASSISTANT_ID,
        "phoneNumberId": VAPI_PHONE_NUMBER_ID,
        "customer": {"number": to},
        "assistantOverrides": overrides,
        "phoneCallProviderDetails": {
            "voicemailMessage": voicemail_msg,
        },
    }
    if business_name:
        payload["customer"]["name"] = business_name

    resp = requests.post(
        f"{VAPI_BASE}/call",
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    data = resp.json()
    if resp.status_code not in (200, 201) or "id" not in data:
        raise Exception(f"Vapi call failed ({resp.status_code}): {data}")

    call_id = data["id"]
    print(f"[VAPI] Call started → {to} | {business_name} | ID: {call_id}")
    return call_id


def get_call(call_id: str) -> dict:
    resp = requests.get(f"{VAPI_BASE}/call/{call_id}", headers=_headers(), timeout=10)
    return resp.json()


def end_call(call_id: str) -> dict:
    """Hang up an active Vapi call."""
    resp = requests.delete(
        f"{VAPI_BASE}/call/{call_id}",
        headers=_headers(),
        timeout=10,
    )
    if resp.status_code not in (200, 204):
        raise Exception(f"Vapi end_call failed ({resp.status_code}): {resp.text}")
    return {"ok": True}


def _extract_city(address: str) -> str:
    if not address:
        return ""
    parts = address.split(",")
    return parts[1].strip() if len(parts) >= 2 else ""


def _build_opening(business_name: str, industry: str, city: str) -> str:
    if business_name and city:
        return (
            f"Hey, is this the owner over at {business_name}? "
            f"I was just pulling up your Google listing in {city} — "
            f"quick question, is your phone ringing as much as you want it to right now?"
        )
    elif business_name:
        return (
            f"Hey, is this the owner over at {business_name}? "
            f"This is Josh — I help {industry or 'trade'} businesses get more booked jobs from Google. "
            f"Quick question — is your phone ringing as much as you want it to right now?"
        )
    else:
        return (
            "Hey, this is Josh — I help trade businesses get more booked jobs from Google. "
            "Quick question — is your phone ringing as much as you want it to right now?"
        )
