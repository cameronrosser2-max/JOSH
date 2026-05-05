import sqlite3
import csv
import io
import json
from datetime import datetime


DB_PATH = "leads.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            name TEXT,
            email TEXT,
            business TEXT,
            industry TEXT,
            outcome TEXT DEFAULT 'in_progress',
            conversation TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def upsert_lead(session_id: str, data: dict):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()

    c.execute("SELECT id FROM leads WHERE session_id = ?", (session_id,))
    row = c.fetchone()

    if row:
        c.execute("""
            UPDATE leads SET
                name = COALESCE(?, name),
                email = COALESCE(?, email),
                business = COALESCE(?, business),
                industry = COALESCE(?, industry),
                outcome = COALESCE(?, outcome),
                conversation = ?,
                updated_at = ?
            WHERE session_id = ?
        """, (
            data.get("name"),
            data.get("email"),
            data.get("business"),
            data.get("industry"),
            data.get("outcome"),
            data.get("conversation"),
            now,
            session_id
        ))
    else:
        c.execute("""
            INSERT INTO leads (session_id, name, email, business, industry, outcome, conversation, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            data.get("name"),
            data.get("email"),
            data.get("business"),
            data.get("industry"),
            data.get("outcome", "in_progress"),
            data.get("conversation"),
            now,
            now
        ))

    conn.commit()
    conn.close()


def get_all_leads():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM leads ORDER BY created_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_leads_csv():
    leads = get_all_leads()
    output = io.StringIO()
    fields = ["id", "name", "email", "business", "industry", "outcome", "created_at", "updated_at"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(leads)
    return output.getvalue()


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM leads")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM leads WHERE outcome = 'closed'")
    closed = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM leads WHERE outcome = 'interested'")
    interested = c.fetchone()[0]
    c.execute("SELECT industry, COUNT(*) as cnt FROM leads GROUP BY industry ORDER BY cnt DESC")
    by_industry = [{"industry": r[0] or "Unknown", "count": r[1]} for r in c.fetchall()]
    conn.close()
    return {
        "total": total,
        "closed": closed,
        "interested": interested,
        "by_industry": by_industry,
    }
