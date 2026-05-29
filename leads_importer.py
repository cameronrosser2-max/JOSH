"""
Lead importer — handles CSV uploads and live Google Sheets sync.
Cleans phone numbers, detects industry, and loads into the dial queue.
"""
import re
import csv
import sqlite3
import time
from pathlib import Path
from industries import detect_industry

DB_PATH = "leads.db"


# ── Phone Number Cleaner ───────────────────────────────────────────────────────
def clean_phone(raw: str):
    """Convert any US phone format to E.164 (+1XXXXXXXXXX)."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw.strip())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None  # invalid


# ── Industry Detector ─────────────────────────────────────────────────────────
def detect_industry_from_name(business_name: str):
    """Detect industry from business name string."""
    name = business_name.lower()

    checks = [
        ("hvac",             ["hvac", "heating", "cooling", "air condition", "furnace", "heat pump"]),
        ("electrician",      ["electric", "wiring", "electrical"]),
        ("plumbing",         ["plumb", "pipe", "drain", "sewer", "water heater"]),
        ("roofing",          ["roof", "roofing", "shingle", "gutter", "siding"]),
        ("landscaping",      ["landscap", "lawn", "mowing", "irrigation", "sprinkler", "hardscape"]),
        ("painting",         ["paint", "painting", "painter"]),
        ("pest_control",     ["pest", "exterminator", "termite", "bed bug", "rodent"]),
        ("pressure_washing", ["pressure wash", "power wash", "soft wash"]),
        ("cleaning",         ["cleaning service", "maid", "janitorial", "housekeeping"]),
        ("concrete",         ["concrete", "paving", "asphalt", "masonry"]),
        ("fencing",          ["fencing", "fence", "railing"]),
        ("garage_door",      ["garage door", "overhead door"]),
        ("pool",             ["pool service", "pool clean", "pool repair", "pool build", "spa service"]),
        ("tree_service",     ["tree service", "tree removal", "tree trimming", "arborist", "stump"]),
        ("repair",           ["repair", "mechanic", "auto shop", "appliance", "handyman"]),
    ]

    for industry, keywords in checks:
        for kw in keywords:
            if kw in name:
                return industry
    return "general"


# ── DB Setup ──────────────────────────────────────────────────────────────────
def init_queue_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS dial_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT,
            phone TEXT UNIQUE,
            address TEXT,
            industry TEXT,
            status TEXT DEFAULT 'pending',
            raw_status TEXT,
            called_at TEXT,
            outcome TEXT,
            imported_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def upsert_queue_lead(business_name: str, phone: str, address: str = None,
                       industry: str = None, raw_status: str = None):
    """Insert a lead into the dial queue. Skip duplicates by phone."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Map raw sheet status to queue status
    status = "pending"
    if raw_status:
        low = raw_status.strip().lower()
        if "red" in low or "no go" in low:
            status = "skip"
        elif "yellow" in low or "maybe" in low:
            status = "maybe"
        elif "green" in low or "go" in low:
            status = "ready"

    c.execute("""
        INSERT OR IGNORE INTO dial_queue
            (business_name, phone, address, industry, status, raw_status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (business_name, phone, address, industry or "general", status, raw_status))

    conn.commit()
    conn.close()
    return c.lastrowid


def get_queue(filter_status: str = None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if filter_status:
        c.execute("SELECT * FROM dial_queue WHERE status = ? ORDER BY id", (filter_status,))
    else:
        c.execute("SELECT * FROM dial_queue ORDER BY id")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_next_pending():
    """Get the next lead to call (ready first, then pending)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM dial_queue
        WHERE status IN ('ready', 'pending')
        ORDER BY CASE status WHEN 'ready' THEN 0 ELSE 1 END, id
        LIMIT 1
    """)
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def mark_called(phone: str, outcome: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE dial_queue SET status = 'called', outcome = ?, called_at = datetime('now')
        WHERE phone = ?
    """, (outcome, phone))
    conn.commit()
    conn.close()


def get_queue_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT status, COUNT(*) FROM dial_queue GROUP BY status")
    stats = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return stats


# ── CSV Import ────────────────────────────────────────────────────────────────
def import_csv(filepath: str) -> dict:
    """Import leads from a CSV file. Returns count summary."""
    init_queue_table()
    imported = 0
    skipped = 0
    invalid = 0

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        # Normalize column names (strip whitespace)
        reader.fieldnames = [h.strip() for h in reader.fieldnames]

        for row in reader:
            # Try to find business name and phone from common column names
            business = (
                row.get("Business Name") or row.get("business_name") or
                row.get("Business") or row.get("Name") or ""
            ).strip()

            phone_raw = (
                row.get("Phone Number") or row.get("phone") or
                row.get("Phone") or row.get("phone_number") or ""
            ).strip()

            address = (
                row.get("Address") or row.get("address") or ""
            ).strip()

            raw_status = (
                row.get("Red-No Go Green-Go Yellow-Maybe") or
                row.get("Status") or row.get("status") or ""
            ).strip()

            phone = clean_phone(phone_raw)

            if not phone:
                invalid += 1
                continue

            industry = detect_industry_from_name(business)
            result = upsert_queue_lead(business, phone, address, industry, raw_status)

            if result:
                imported += 1
            else:
                skipped += 1

    return {"imported": imported, "skipped_duplicates": skipped, "invalid_phone": invalid}


# ── Google Sheets Sync ────────────────────────────────────────────────────────
def _extract_sheet_id(sheet_id_or_url: str) -> str:
    """Accept either a raw sheet ID or a full Google Sheets URL and return just the ID."""
    import re as _re
    # Match /d/<ID>/ pattern from any Google Sheets URL
    m = _re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", sheet_id_or_url)
    if m:
        return m.group(1)
    return sheet_id_or_url.strip()


def sync_google_sheet(sheet_id: str, credentials_path: str = "google_credentials.json",
                       tab_name: str = None) -> dict:
    """
    Pull leads from a Google Sheet and upsert into the dial queue.
    Requires google_credentials.json (service account) in project root.
    """
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return {"error": "google-api-python-client not installed"}

    if not Path(credentials_path).exists():
        return {"error": f"Google credentials file not found: {credentials_path}"}

    sheet_id = _extract_sheet_id(sheet_id)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    service = build("sheets", "v4", credentials=creds)

    range_name = f"{tab_name}!A:Z" if tab_name else "A:Z"
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=range_name
    ).execute()

    rows = result.get("values", [])
    if not rows:
        return {"imported": 0, "error": "Sheet is empty"}

    headers = [h.strip() for h in rows[0]]
    imported = skipped = invalid = 0

    for row_data in rows[1:]:
        row = dict(zip(headers, row_data + [""] * (len(headers) - len(row_data))))

        business = (
            row.get("Business Name") or row.get("Business") or row.get("Name") or ""
        ).strip()

        phone_raw = (
            row.get("Phone Number") or row.get("Phone") or row.get("phone") or ""
        ).strip()

        address = (row.get("Address") or "").strip()
        raw_status = (
            row.get("Red-No Go Green-Go Yellow-Maybe") or
            row.get("Status") or ""
        ).strip()

        phone = clean_phone(phone_raw)
        if not phone:
            invalid += 1
            continue

        industry = detect_industry_from_name(business)
        result_id = upsert_queue_lead(business, phone, address, industry, raw_status)
        if result_id:
            imported += 1
        else:
            skipped += 1

    return {"imported": imported, "skipped_duplicates": skipped, "invalid_phone": invalid}


# ── CLI Test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    init_queue_table()
    if len(sys.argv) > 1:
        result = import_csv(sys.argv[1])
        print(f"Import result: {result}")
        stats = get_queue_stats()
        print(f"Queue stats: {stats}")
