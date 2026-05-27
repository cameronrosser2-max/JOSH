import sqlite3
import csv
import io
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
            phone TEXT,
            business TEXT,
            city TEXT,
            industry TEXT,
            outcome TEXT DEFAULT 'in_progress',
            score INTEGER DEFAULT 50,
            stage TEXT,
            notes TEXT,
            follow_up_date TEXT,
            conversation TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    # Migrate existing databases gracefully
    new_cols = [
        ("phone", "TEXT"),
        ("city", "TEXT"),
        ("score", "INTEGER DEFAULT 50"),
        ("stage", "TEXT"),
        ("notes", "TEXT"),
        ("follow_up_date", "TEXT"),
    ]
    for col, defn in new_cols:
        try:
            c.execute(f"ALTER TABLE leads ADD COLUMN {col} {defn}")
        except Exception:
            pass
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
                phone = COALESCE(?, phone),
                business = COALESCE(?, business),
                city = COALESCE(?, city),
                industry = COALESCE(?, industry),
                outcome = COALESCE(?, outcome),
                score = COALESCE(?, score),
                stage = COALESCE(?, stage),
                notes = COALESCE(?, notes),
                conversation = ?,
                updated_at = ?
            WHERE session_id = ?
        """, (
            data.get("name"),
            data.get("email"),
            data.get("phone"),
            data.get("business"),
            data.get("city"),
            data.get("industry"),
            data.get("outcome"),
            data.get("score"),
            data.get("stage"),
            data.get("notes"),
            data.get("conversation"),
            now,
            session_id
        ))
    else:
        c.execute("""
            INSERT INTO leads
                (session_id, name, email, phone, business, city, industry,
                 outcome, score, stage, notes, conversation, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id,
            data.get("name"),
            data.get("email"),
            data.get("phone"),
            data.get("business"),
            data.get("city"),
            data.get("industry"),
            data.get("outcome", "in_progress"),
            data.get("score", 50),
            data.get("stage"),
            data.get("notes"),
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


def get_lead_by_id(lead_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_leads_csv():
    leads = get_all_leads()
    output = io.StringIO()
    fields = ["id", "name", "email", "phone", "business", "city", "industry",
              "outcome", "score", "stage", "created_at", "updated_at"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(leads)
    return output.getvalue()


def update_lead_notes(lead_id: int, notes: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE leads SET notes = ?, updated_at = ? WHERE id = ?",
        (notes, datetime.utcnow().isoformat(), lead_id)
    )
    conn.commit()
    conn.close()


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM leads")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM leads WHERE outcome = 'closed'")
    closed = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM leads WHERE outcome = 'interested'")
    interested = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM leads WHERE outcome = 'no_answer'")
    no_answer = c.fetchone()[0]

    c.execute("SELECT AVG(score) FROM leads WHERE score IS NOT NULL")
    avg_score_row = c.fetchone()[0]
    avg_score = round(avg_score_row) if avg_score_row else 0

    c.execute("""
        SELECT industry, COUNT(*) as cnt
        FROM leads
        WHERE industry IS NOT NULL
        GROUP BY industry
        ORDER BY cnt DESC
        LIMIT 8
    """)
    by_industry = [{"industry": r[0] or "Unknown", "count": r[1]} for r in c.fetchall()]

    c.execute("""
        SELECT city, COUNT(*) as cnt
        FROM leads
        WHERE city IS NOT NULL AND city != ''
        GROUP BY city
        ORDER BY cnt DESC
        LIMIT 5
    """)
    by_city = [{"city": r[0], "count": r[1]} for r in c.fetchall()]

    conversion_rate = round((closed / total * 100), 1) if total > 0 else 0
    hot_rate = round(((closed + interested) / total * 100), 1) if total > 0 else 0

    conn.close()
    return {
        "total": total,
        "closed": closed,
        "interested": interested,
        "no_answer": no_answer,
        "avg_score": avg_score,
        "conversion_rate": conversion_rate,
        "hot_rate": hot_rate,
        "by_industry": by_industry,
        "by_city": by_city,
    }
