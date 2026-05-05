INDUSTRIES = {
    "hvac": {
        "name": "HVAC",
        "pain_points": [
            "Seasonal peaks mean empty pipelines in the off-season",
            "Customers call whoever shows up first on Google — not who's best",
            "No website means no trust, no callbacks from Google Maps",
            "Competitors with websites are winning jobs you should be getting",
        ],
        "roi_hook": "One new AC install or furnace replacement pays for a website 3–5x over.",
        "urgency": "Summer/winter seasons are peak — customers are searching right now.",
        "avg_job_value": "$3,000–$8,000 per install",
        "keywords": ["hvac", "heating", "cooling", "air conditioning", "furnace", "heat pump", "ac"],
    },
    "plumbing": {
        "name": "Plumbing",
        "pain_points": [
            "Emergency calls go to whoever ranks on Google — you're invisible without a site",
            "Customers won't call a business they can't find online at 2am",
            "Word of mouth has a ceiling — your website works 24/7",
            "No reviews page means losing trust to competitors who have one",
        ],
        "roi_hook": "One water heater replacement or pipe reroute covers the website cost entirely.",
        "urgency": "Plumbing emergencies happen daily — if you're not ranking, you're not getting the call.",
        "avg_job_value": "$500–$5,000 per job",
        "keywords": ["plumb", "pipe", "drain", "water heater", "sewer", "leak"],
    },
    "electrician": {
        "name": "Electrical",
        "pain_points": [
            "Panel upgrades and rewires are high-ticket — customers research before they call",
            "No website = no credibility for a licensed trade business",
            "Homebuyers need inspections fast — they Google first",
            "EV charger installs are booming and customers are searching online right now",
        ],
        "roi_hook": "One panel upgrade or EV charger install more than pays for the entire site.",
        "urgency": "EV adoption is surging — businesses ranking now are locking in that traffic.",
        "avg_job_value": "$1,000–$10,000 per job",
        "keywords": ["electric", "wiring", "panel", "outlet", "ev charger", "generator"],
    },
    "repair": {
        "name": "Repair Shop",
        "pain_points": [
            "Customers compare shops online before walking in — no site means no comparison",
            "Yelp and Google Reviews drive walk-ins; your own site amplifies that",
            "Repeat customers forget your number — a site keeps you top of mind",
            "Shops with websites look more established and charge higher rates",
        ],
        "roi_hook": "Even 3–4 extra repair tickets a month more than pays for itself.",
        "urgency": "People search 'phone repair near me' or 'auto shop near me' every day in your area.",
        "avg_job_value": "$150–$1,200 per ticket",
        "keywords": ["repair", "fix", "shop", "mechanic", "phone", "appliance", "auto"],
    },
}


def detect_industry(text: str):
    text = text.lower()
    for key, data in INDUSTRIES.items():
        if any(kw in text for kw in data["keywords"]):
            return data
    return None


def get_industry_context(industry) -> str:
    if not industry:
        return ""
    return f"""
Industry: {industry['name']}
Key pain points to surface naturally:
{chr(10).join(f'- {p}' for p in industry['pain_points'])}
ROI hook: {industry['roi_hook']}
Urgency angle: {industry['urgency']}
Average job value: {industry['avg_job_value']}
""".strip()
