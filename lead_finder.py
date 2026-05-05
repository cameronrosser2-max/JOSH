"""
Automatic Lead Finder
Searches Google Places API for HVAC, Plumbing, Electrical & Repair shops
and loads them directly into the dial queue.
"""
import re
import time
import requests
from leads_importer import init_queue_table, upsert_queue_lead, get_queue_stats

# ── Target industries & search terms ─────────────────────────────────────────
SEARCH_TERMS = [
    "HVAC company",
    "heating and cooling",
    "air conditioning repair",
    "plumbing company",
    "plumber",
    "electrician",
    "electrical contractor",
    "appliance repair shop",
    "auto repair shop",
    "barbershop",
]

INDUSTRY_MAP = {
    "hvac": "hvac", "heating": "hvac", "cooling": "hvac", "air condition": "hvac",
    "plumb": "plumbing", "pipe": "plumbing",
    "electric": "electrician", "wiring": "electrician",
    "repair": "repair", "barber": "repair", "auto": "repair", "appliance": "repair",
}

# Default cities to search — can be overridden from the UI
DEFAULT_CITIES = [
    "Dallas TX", "Houston TX", "Austin TX", "San Antonio TX",
    "Miami FL", "Orlando FL", "Tampa FL",
    "Los Angeles CA", "Phoenix AZ", "Chicago IL",
]


def _detect_industry(name: str, types: list) -> str:
    text = (name + " ".join(types)).lower()
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


def search_google_places(api_key: str, query: str, city: str, max_results: int = 20) -> list:
    """Search Google Places API for businesses."""
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    results = []
    next_token = None

    while len(results) < max_results:
        params = {
            "query": f"{query} in {city}",
            "key": api_key,
            "type": "establishment",
        }
        if next_token:
            params = {"pagetoken": next_token, "key": api_key}
            time.sleep(2)  # Google requires delay before using page token

        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            break

        for place in data.get("results", []):
            name = place.get("name", "")
            address = place.get("formatted_address", "")
            place_id = place.get("place_id", "")
            types = place.get("types", [])

            # Get phone number via Place Details
            phone = _get_phone(api_key, place_id)
            if not phone:
                continue

            results.append({
                "business_name": name,
                "phone": phone,
                "address": address,
                "industry": _detect_industry(name, types),
            })

            if len(results) >= max_results:
                break

        next_token = data.get("next_page_token")
        if not next_token:
            break

    return results


def _get_phone(api_key: str, place_id: str) -> str:
    """Get phone number from Google Place Details."""
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "formatted_phone_number",
        "key": api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=8)
        data = resp.json()
        raw = data.get("result", {}).get("formatted_phone_number", "")
        return _clean_phone(raw)
    except:
        return None


def find_and_queue_leads(
    api_key: str,
    cities: list = None,
    industries: list = None,
    max_per_search: int = 10,
    progress_callback=None,
) -> dict:
    """
    Main function: search Google Places and load leads into dial queue.
    progress_callback(message) is called with status updates.
    """
    init_queue_table()
    cities = cities or DEFAULT_CITIES
    search_terms = industries or SEARCH_TERMS

    total_imported = 0
    total_skipped = 0
    total_searched = 0

    def log(msg):
        print(f"[FINDER] {msg}")
        if progress_callback:
            progress_callback(msg)

    for city in cities:
        for term in search_terms:
            log(f"Searching: {term} in {city}...")
            try:
                leads = search_google_places(api_key, term, city, max_per_search)
                for lead in leads:
                    result = upsert_queue_lead(
                        lead["business_name"],
                        lead["phone"],
                        lead["address"],
                        lead["industry"],
                    )
                    if result:
                        total_imported += 1
                    else:
                        total_skipped += 1
                total_searched += 1
                log(f"  Found {len(leads)} leads — queue total: {total_imported}")
            except Exception as e:
                log(f"  Error: {e}")
            time.sleep(0.5)

    stats = get_queue_stats()
    log(f"Done! {total_imported} new leads added. Queue: {stats}")
    return {
        "imported": total_imported,
        "skipped_duplicates": total_skipped,
        "searches_run": total_searched,
        "queue_stats": stats,
    }
