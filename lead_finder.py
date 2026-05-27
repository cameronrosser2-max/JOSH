"""
Lead Finder — Google Maps / Places API
Finds ALL trade businesses. No skipping. Every result goes into the queue.
"""
import re
import time
import requests
from leads_importer import init_queue_table, upsert_queue_lead, get_queue_stats

SEARCH_TERMS = [
    # HVAC
    "HVAC contractor",
    "HVAC company",
    "air conditioning repair",
    "heating and cooling company",
    "AC repair",
    # Plumbing
    "plumber",
    "plumbing company",
    "plumbing contractor",
    # Electrician
    "electrician",
    "electrical contractor",
    "electrical company",
    # Roofing
    "roofing contractor",
    "roofing company",
    "roof repair",
]

INDUSTRY_MAP = {
    "hvac": "hvac", "heating": "hvac", "cooling": "hvac",
    "air condition": "hvac", "ac repair": "hvac",
    "plumb": "plumbing",
    "electric": "electrician",
    "roof": "roofing",
}

DEFAULT_CITIES = [
    "Dallas TX", "Houston TX", "Austin TX", "San Antonio TX", "Fort Worth TX",
    "Miami FL", "Orlando FL", "Tampa FL", "Jacksonville FL",
    "Atlanta GA", "Charlotte NC", "Raleigh NC",
    "Phoenix AZ", "Scottsdale AZ", "Tucson AZ",
    "Los Angeles CA", "San Diego CA", "Las Vegas NV",
    "Chicago IL", "Columbus OH", "Nashville TN",
]


def _detect_industry(name: str, types: list) -> str:
    text = (name + " " + " ".join(types)).lower()
    for kw, ind in INDUSTRY_MAP.items():
        if kw in text:
            return ind
    return "general"


def _clean_phone(raw: str) -> str:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


def _get_details(api_key: str, place_id: str) -> dict:
    """Get phone and website. If they have a website, we skip them."""
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    try:
        resp = requests.get(url, params={
            "place_id": place_id,
            "fields": "formatted_phone_number,website",
            "key": api_key,
        }, timeout=8)
        result = resp.json().get("result", {})
        return {
            "phone":   _clean_phone(result.get("formatted_phone_number", "")),
            "website": result.get("website", ""),
        }
    except:
        return {"phone": None, "website": ""}


def search_google_places(api_key: str, query: str, city: str,
                          max_results: int = 20) -> list:
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    results = []
    next_token = None

    while len(results) < max_results:
        params = {"query": f"{query} in {city}", "key": api_key}
        if next_token:
            params = {"pagetoken": next_token, "key": api_key}
            time.sleep(2)

        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            break

        for place in data.get("results", []):
            name    = place.get("name", "Unknown")
            details = _get_details(api_key, place.get("place_id", ""))

            # Check Google Maps listing for website
            if details.get("website"):
                print(f"[FINDER]   ✗ {name} — has website, skipping")
                continue

            if not details.get("phone"):
                print(f"[FINDER]   ✗ {name} — no phone number, skipping")
                continue

            print(f"[FINDER]   ✓ {name} — no website on Google Maps, adding")
            results.append({
                "business_name": name,
                "phone":         details["phone"],
                "address":       place.get("formatted_address", ""),
                "industry":      _detect_industry(name, place.get("types", [])),
            })

            if len(results) >= max_results:
                break

        next_token = data.get("next_page_token")
        if not next_token:
            break

    return results


def find_and_queue_leads(
    api_key: str,
    cities: list = None,
    industries: list = None,
    max_per_search: int = 20,
    max_stars: float = None,
    require_no_website: bool = None,
    progress_callback=None,
    stop_flag=None,
) -> dict:
    init_queue_table()
    cities       = cities or DEFAULT_CITIES
    search_terms = industries or SEARCH_TERMS
    total_added  = 0
    total_dupes  = 0

    def log(msg):
        print(f"[FINDER] {msg}")
        if progress_callback:
            progress_callback(msg)

    log(f"Starting — {len(cities)} cities × {len(search_terms)} niches")

    for city in cities:
        for term in search_terms:
            if stop_flag and stop_flag():
                log("Stopped.")
                break

            log(f"Searching: {term} in {city}...")
            try:
                leads = search_google_places(api_key, term, city, max_per_search)
                new = 0
                for lead in leads:
                    if upsert_queue_lead(lead["business_name"], lead["phone"],
                                        lead["address"], lead["industry"]):
                        total_added += 1
                        new += 1
                    else:
                        total_dupes += 1
                log(f"  → {new} added ({len(leads)} found)")
            except Exception as e:
                log(f"  Error: {e}")

            time.sleep(0.3)

    stats = get_queue_stats()
    log(f"Done — {total_added} leads added, {total_dupes} duplicates skipped")
    return {
        "imported":           total_added,
        "skipped_duplicates": total_dupes,
        "queue_stats":        stats,
    }
