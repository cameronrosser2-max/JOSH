"""
SQLite storage for the standalone lead finder.
"""
import sqlite3
import csv
import io
import os

DB_PATH = os.environ.get("DB_PATH", "leads.db")


def init():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT,
            phone TEXT UNIQUE,
            address TEXT,
            industry TEXT,
            status TEXT DEFAULT 'new',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def upsert(business_name, phone, address, industry):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO leads (business_name, phone, address, industry)
        VALUES (?, ?, ?, ?)
    """, (business_name, phone, address or "", industry or "general"))
    inserted = c.lastrowid if c.rowcount else None
    conn.commit()
    conn.close()
    return inserted


def get_all(status=None, industry=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    clauses, params = [], []
    if status:
        clauses.append("status = ?"); params.append(status)
    if industry:
        clauses.append("industry = ?"); params.append(industry)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    c.execute(f"SELECT * FROM leads {where} ORDER BY id DESC", params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT status, COUNT(*) FROM leads GROUP BY status")
    stats = {row[0]: row[1] for row in c.fetchall()}
    c.execute("SELECT COUNT(*) FROM leads")
    stats["total"] = c.fetchone()[0]
    conn.close()
    return stats


def update_status(lead_id, status):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE leads SET status=? WHERE id=?", (status, lead_id))
    conn.commit()
    conn.close()


def update_notes(lead_id, notes):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE leads SET notes=? WHERE id=?", (notes, lead_id))
    conn.commit()
    conn.close()


def delete_lead(lead_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM leads WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()


def to_csv():
    rows = get_all()
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=["id","business_name","phone","address","industry","status","notes","created_at"])
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


def import_csv_file(filepath):
    imported, skipped = 0, 0
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize headers
            r = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items()}
            biz = r.get("business_name") or r.get("business") or r.get("name", "")
            phone = r.get("phone") or r.get("phone_number", "")
            if not biz or not phone:
                skipped += 1
                continue
            result = upsert(biz, phone, r.get("address", ""), r.get("industry", "general"))
            if result:
                imported += 1
            else:
                skipped += 1
    return {"imported": imported, "skipped": skipped}
