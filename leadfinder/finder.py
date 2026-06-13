"""
Lead Finder — searches Google Places for trade businesses with no website.
"""
import re
import time
import requests

SEARCH_TERMS = [
    "HVAC contractor", "HVAC company", "air conditioning repair",
    "plumber", "plumbing company",
    "electrician", "electrical contractor",
    "roofing contractor", "roof repair",
    "landscaping company", "lawn care service",
    "painting contractor", "house painter",
    "pest control company", "exterminator",
    "pressure washing service", "power washing company",
    "house cleaning service", "maid service",
    "concrete contractor", "driveway paving",
    "fence installation company", "fencing contractor",
    "garage door repair",
    "pool service company", "pool cleaning service",
    "tree removal service", "tree trimming company",
    "handyman service", "appliance repair",
]

INDUSTRY_MAP = {
    "hvac": "hvac", "heating": "hvac", "cooling": "hvac", "air condition": "hvac", "ac repair": "hvac",
    "plumb": "plumbing",
    "electric": "electrician",
    "roof": "roofing",
    "landscap": "landscaping", "lawn": "landscaping",
    "paint": "painting",
    "pest": "pest_control", "exterminator": "pest_control",
    "pressure wash": "pressure_washing", "power wash": "pressure_washing",
    "cleaning service": "cleaning", "maid": "cleaning",
    "concrete": "concrete", "paving": "concrete", "masonry": "concrete",
    "fenc": "fencing",
    "garage door": "garage_door",
    "pool": "pool",
    "tree": "tree_service",
    "handyman": "repair", "appliance": "repair",
}

DEFAULT_CITIES = [
    "Dallas TX", "Houston TX", "Austin TX", "San Antonio TX",
    "Miami FL", "Orlando FL", "Tampa FL",
    "Atlanta GA", "Charlotte NC",
    "Phoenix AZ", "Scottsdale AZ",
    "Los Angeles CA", "San Diego CA", "Las Vegas NV",
    "Chicago IL", "Nashville TN", "Denver CO",
]


def detect_industry(name: str, types: list) -> str:
    text = (name + " " + " ".join(types)).lower()
    for kw, ind in INDUSTRY_MAP.items():
        if kw in text:
            return ind
    return "general"


def clean_phone(raw: str) -> str:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


def get_place_details(api_key: str, place_id: str) -> dict:
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={"place_id": place_id, "fields": "formatted_phone_number,website", "key": api_key},
            timeout=8,
        )
        result = resp.json().get("result", {})
        return {
            "phone": clean_phone(result.get("formatted_phone_number", "")),
            "website": result.get("website", ""),
        }
    except Exception:
        return {"phone": None, "website": ""}


def search_places(api_key: str, query: str, city: str, max_results: int = 20) -> list:
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
            name = place.get("name", "Unknown")
            details = get_place_details(api_key, place.get("place_id", ""))

            if details.get("website") or not details.get("phone"):
                continue

            results.append({
                "business_name": name,
                "phone": details["phone"],
                "address": place.get("formatted_address", ""),
                "industry": detect_industry(name, place.get("types", [])),
            })

            if len(results) >= max_results:
                break

        next_token = data.get("next_page_token")
        if not next_token:
            break

    return results


def run_search(api_key: str, cities: list, search_terms: list,
               max_per_search: int, progress_cb=None, stop_flag=None) -> list:
    all_leads = []
    seen_phones = set()

    def log(msg):
        if progress_cb:
            progress_cb(msg)

    log(f"Starting — {len(cities)} cities × {len(search_terms)} searches")

    for city in cities:
        for term in search_terms:
            if stop_flag and stop_flag():
                log("Stopped.")
                return all_leads

            log(f"Searching: {term} in {city}...")
            try:
                leads = search_places(api_key, term, city, max_per_search)
                new = 0
                for lead in leads:
                    if lead["phone"] not in seen_phones:
                        seen_phones.add(lead["phone"])
                        all_leads.append(lead)
                        new += 1
                log(f"  → {new} new leads ({len(leads)} found)")
            except Exception as e:
                log(f"  Error: {e}")

            time.sleep(0.3)

    log(f"Done — {len(all_leads)} total leads found")
    return all_leads
