#!/usr/bin/env python3
"""
Josh — Instagram DM Outreach Automation
Finds HVAC, plumbing, electrical, and other trade businesses on Instagram
and sends personalized cold DMs selling website services.
"""

# ─────────── OPTIONAL OVERRIDES (leave blank to use saved credentials) ──────
# You can also just run the script — it will ask you on first launch.

IG_USERNAME   = ""   # leave blank to use saved login
IG_PASSWORD   = ""   # leave blank to use saved login

DAILY_DM_LIMIT   = 30     # max DMs per day (keep ≤ 40 to avoid bans)
SESSION_FILE     = "ig_session.json"
LOG_FILE         = "dm_log.csv"
CREDS_FILE       = "ig_creds.json"
WAIT_MIN_SECS    = 45
WAIT_MAX_SECS    = 120

# Hashtags to scrape per industry — add/remove as needed
HASHTAGS = {
    "hvac":            ["hvaclife", "hvactechnician", "hvacbusiness", "hvaccontractor", "heatingandcooling"],
    "plumbing":        ["plumbinglife", "plumber", "plumbingbusiness", "plumbingcontractor"],
    "electrician":     ["electrician", "electricalbusiness", "electricianlife", "sparky"],
    "roofing":         ["roofingcontractor", "roofinglife", "roofer", "roofingbusiness"],
    "landscaping":     ["landscapingbusiness", "lawncare", "landscaper", "landscapinglife"],
    "painting":        ["paintingcontractor", "paintingbusiness", "painterlife", "housepainter"],
    "pest_control":    ["pestcontrol", "pestcontrolbusiness", "exterminator"],
    "pressure_washing":["pressurewashing", "pressurewashingbusiness", "softwash"],
    "cleaning":        ["cleaningbusiness", "cleaningservice", "maidservice", "janitorial"],
    "concrete":        ["concretework", "concretecontractor", "masonrywork"],
    "fencing":         ["fencingcontractor", "fenceinstall", "fencingbusiness"],
    "garage_door":     ["garagedoorrepair", "garagedoor", "garagedoorbusiness"],
    "pool":            ["poolservice", "poolcleaning", "poolbuilder"],
    "tree_service":    ["treeservice", "treeremoval", "arborist"],
    "repair":          ["autorepairshop", "appliancerepair", "repairshop"],
}

# How many accounts to pull per hashtag (Instagram limits ~50 reliably)
ACCOUNTS_PER_HASHTAG = 50

# ───────────────────────────────────────────────────────────────────────────

import csv
import json
import os
import random
import time
import logging
from datetime import date, datetime
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired, RateLimitError, ClientError, UserNotFound
)

from industries import INDUSTRIES, detect_industry, get_industry_context

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("josh.ig")


# ── Message templates ── one is chosen at random per send ─────────────────

def build_message(industry_key: str, business_name: str) -> str:
    """Return a short, personalized cold DM for the given industry."""
    ind = INDUSTRIES.get(industry_key, {})
    name    = ind.get("name", "your business")
    pain    = random.choice(ind.get("pain_points", ["getting found online is tough"]))
    roi     = ind.get("roi_hook", "a website pays for itself fast.")
    avg_job = ind.get("avg_job_value", "high-ticket jobs")

    templates = [
        (
            f"Hey {business_name}! 👋 Quick question — do you have a website yet?\n\n"
            f"A lot of {name} companies I talk to say {pain.lower()}. "
            f"We build done-for-you websites specifically for {name} businesses — "
            f"{roi} Mind if I show you a quick example?"
        ),
        (
            f"Hi {business_name}! I work with {name} businesses on getting more leads online. "
            f"{pain} — sound familiar? "
            f"We handle everything: design, hosting, SEO. {roi} "
            f"Would it be okay if I sent over a free mockup for your business?"
        ),
        (
            f"Hey! Love seeing {name} businesses on here. 🔧\n\n"
            f"Quick thought — with {avg_job} per job, even 2–3 extra calls a month from Google "
            f"makes a huge difference. We build websites that do exactly that for {name} companies. "
            f"Want me to put together a free sample page for you?"
        ),
    ]
    return random.choice(templates)


# ── CSV log helpers ────────────────────────────────────────────────────────

def load_contacted() -> set:
    """Return set of usernames already messaged (from log file)."""
    contacted = set()
    if not Path(LOG_FILE).exists():
        return contacted
    with open(LOG_FILE, newline="") as f:
        for row in csv.DictReader(f):
            contacted.add(row.get("username", "").lower())
    return contacted


def log_contact(username: str, full_name: str, industry: str, message: str, status: str):
    file_exists = Path(LOG_FILE).exists()
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["date", "username", "full_name", "industry", "status", "message"],
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
            "username":  username,
            "full_name": full_name,
            "industry":  industry,
            "status":    status,
            "message":   message.replace("\n", " "),
        })


# ── First-run wizard ──────────────────────────────────────────────────────

def get_credentials() -> tuple[str, str]:
    """Return (username, password) — from env vars, code, saved file, or interactive prompt."""
    # 1. Environment variables (used by GitHub Actions)
    env_user = os.environ.get("IG_USERNAME", "")
    env_pass = os.environ.get("IG_PASSWORD", "")
    if env_user and env_pass:
        return env_user, env_pass

    # 2. Hard-coded in the script
    if IG_USERNAME and IG_PASSWORD:
        return IG_USERNAME, IG_PASSWORD

    # 3. Previously saved locally
    if Path(CREDS_FILE).exists():
        creds = json.loads(Path(CREDS_FILE).read_text())
        return creds["username"], creds["password"]

    # 4. First-run wizard (local only)
    print("\n" + "="*50)
    print("  JOSH — First Time Setup")
    print("="*50)
    print("\nEnter your Instagram login details.")
    print("(These are saved locally so you won't be asked again.)\n")

    username = input("  Instagram username: ").strip()
    import getpass
    password = getpass.getpass("  Instagram password: ").strip()

    save = input("\n  Save credentials for future runs? (y/n): ").strip().lower()
    if save == "y":
        Path(CREDS_FILE).write_text(json.dumps({"username": username, "password": password}))
        print("  Saved to ig_creds.json\n")

    return username, password


# ── Instagram client helpers ───────────────────────────────────────────────

def get_client() -> Client:
    username, password = get_credentials()

    cl = Client()
    cl.delay_range = [2, 5]

    if Path(SESSION_FILE).exists():
        try:
            cl.load_settings(SESSION_FILE)
            cl.login(username, password)
            log.info("Resumed existing session.")
            return cl
        except Exception:
            log.warning("Session invalid — logging in fresh.")

    cl.login(username, password)
    cl.dump_settings(SESSION_FILE)
    log.info("Logged in and session saved.")
    return cl


def scrape_accounts(cl: Client, industry_key: str) -> list[dict]:
    """
    Scrape accounts from hashtags for one industry.
    Returns list of dicts: {username, full_name, user_id, industry}.
    """
    tags    = HASHTAGS.get(industry_key, [])
    results = {}   # username → info dict (deduped)

    for tag in tags:
        try:
            medias = cl.hashtag_medias_recent_v1(tag, amount=ACCOUNTS_PER_HASHTAG)
            for media in medias:
                u = media.user
                uname = u.username.lower()
                if uname not in results:
                    results[uname] = {
                        "username":  u.username,
                        "full_name": u.full_name or u.username,
                        "user_id":   u.pk,
                        "industry":  industry_key,
                    }
            log.info(f"  #{tag}: scraped {len(medias)} posts → {len(results)} unique so far")
            time.sleep(random.uniform(3, 7))
        except RateLimitError:
            log.warning(f"  Rate-limited on #{tag} — sleeping 5 min")
            time.sleep(300)
        except Exception as e:
            log.warning(f"  Skipped #{tag}: {e}")

    return list(results.values())


def send_dm(cl: Client, user_id: int, message: str) -> bool:
    try:
        cl.direct_send(message, user_ids=[user_id])
        return True
    except RateLimitError:
        log.warning("Rate-limited — sleeping 10 min")
        time.sleep(600)
        return False
    except (ClientError, Exception) as e:
        log.warning(f"DM failed: {e}")
        return False


# ── Main loop ─────────────────────────────────────────────────────────────

def run():
    log.info("Josh Instagram DM Outreach starting…")

    # Guard: don't exceed daily limit across runs
    today       = date.today().isoformat()
    counter_file = Path("dm_counter.json")
    counters    = json.loads(counter_file.read_text()) if counter_file.exists() else {}
    sent_today  = counters.get(today, 0)

    if sent_today >= DAILY_DM_LIMIT:
        log.info(f"Daily limit ({DAILY_DM_LIMIT}) already reached for {today}. Run again tomorrow.")
        return

    contacted = load_contacted()
    log.info(f"Already contacted {len(contacted)} accounts total. Sent today: {sent_today}/{DAILY_DM_LIMIT}")

    cl = get_client()

    # Shuffle industries so we don't always hit the same ones first
    industry_keys = list(HASHTAGS.keys())
    random.shuffle(industry_keys)

    for industry_key in industry_keys:
        if sent_today >= DAILY_DM_LIMIT:
            break

        log.info(f"\n── Scraping: {INDUSTRIES.get(industry_key, {}).get('name', industry_key)} ──")
        accounts = scrape_accounts(cl, industry_key)
        random.shuffle(accounts)

        for acct in accounts:
            if sent_today >= DAILY_DM_LIMIT:
                break

            uname = acct["username"].lower()
            if uname in contacted:
                continue

            message = build_message(industry_key, acct["full_name"].split()[0] if acct["full_name"] else uname)

            log.info(f"  → DM to @{uname} ({industry_key})")
            success = send_dm(cl, acct["user_id"], message)
            status  = "sent" if success else "failed"

            log_contact(uname, acct["full_name"], industry_key, message, status)
            contacted.add(uname)

            if success:
                sent_today += 1
                # Save counter after every successful send
                counters[today] = sent_today
                counter_file.write_text(json.dumps(counters))
                log.info(f"  ✓ Sent ({sent_today}/{DAILY_DM_LIMIT})")
            else:
                log.info(f"  ✗ Failed — skipping")

            # Human-like delay between DMs
            wait = random.uniform(WAIT_MIN_SECS, WAIT_MAX_SECS)
            log.info(f"  Waiting {wait:.0f}s…")
            time.sleep(wait)

    log.info(f"\nDone. Sent {sent_today} DMs today. Log: {LOG_FILE}")


if __name__ == "__main__":
    run()
