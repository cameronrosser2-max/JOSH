"""
Lead Finder — standalone Flask app.
"""
import os
import uuid
import threading
import time
from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv
import db
import finder as finder_module

load_dotenv()

app = Flask(__name__)
db.init()

# ── Finder state ──────────────────────────────────────────────────────────────
_state = {"running": False, "log": [], "total": 0, "stop": False}


# ── Pages ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── Finder API ────────────────────────────────────────────────────────────────
@app.route("/api/finder/start", methods=["POST"])
def api_start():
    if _state["running"]:
        return jsonify({"error": "Already running"}), 400

    data = request.get_json(force=True, silent=True) or {}
    api_key = (data.get("google_api_key") or "").strip()
    if not api_key:
        return jsonify({"error": "Google Places API key required"}), 400

    cities = data.get("cities") or finder_module.DEFAULT_CITIES
    terms  = data.get("industries") or finder_module.SEARCH_TERMS
    max_r  = int(data.get("max_per_search") or 20)

    _state.update({"running": True, "log": [], "total": 0, "stop": False})

    def run():
        def log(msg):
            _state["log"].append({"t": time.strftime("%H:%M:%S"), "msg": msg})
        def should_stop():
            return _state["stop"]

        try:
            leads = finder_module.run_search(api_key, cities, terms, max_r, log, should_stop)
            added = 0
            for lead in leads:
                if db.upsert(lead["business_name"], lead["phone"], lead["address"], lead["industry"]):
                    added += 1
            _state["total"] = added
            log(f"✓ Done — {added} new leads saved")
        except Exception as e:
            log(f"Error: {e}")
        finally:
            _state["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/finder/stop", methods=["POST"])
def api_stop():
    _state["stop"] = True
    _state["running"] = False
    return jsonify({"status": "stopped"})


@app.route("/api/finder/status")
def api_status():
    return jsonify({
        "running": _state["running"],
        "log": _state["log"][-50:],
        "total": _state["total"],
    })


# ── Leads API ─────────────────────────────────────────────────────────────────
@app.route("/api/leads")
def api_leads():
    status   = request.args.get("status")
    industry = request.args.get("industry")
    return jsonify(db.get_all(status=status, industry=industry))


@app.route("/api/leads/stats")
def api_stats():
    return jsonify(db.get_stats())


@app.route("/api/leads/<int:lead_id>/status", methods=["POST"])
def api_update_status(lead_id):
    data = request.get_json(force=True, silent=True) or {}
    db.update_status(lead_id, data.get("status", "new"))
    return jsonify({"ok": True})


@app.route("/api/leads/<int:lead_id>/notes", methods=["POST"])
def api_update_notes(lead_id):
    data = request.get_json(force=True, silent=True) or {}
    db.update_notes(lead_id, data.get("notes", ""))
    return jsonify({"ok": True})


@app.route("/api/leads/<int:lead_id>", methods=["DELETE"])
def api_delete(lead_id):
    db.delete_lead(lead_id)
    return jsonify({"ok": True})


@app.route("/api/leads/export")
def api_export():
    return Response(
        db.to_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@app.route("/api/leads/import", methods=["POST"])
def api_import():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    tmp = f"/tmp/lf_{uuid.uuid4()}.csv"
    f.save(tmp)
    result = db.import_csv_file(tmp)
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n Lead Finder running at http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
