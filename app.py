from flask import (
    Flask, render_template, request, g, jsonify,
    session, redirect, url_for, flash
)

import sqlite3
import csv
import os
import traceback
from functools import wraps

# =========================
# AI IMPORT (SAFE)
# =========================
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False


# ==================================================
# APP CONFIG
# ==================================================
app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "leadforge_dev_secret_2026")
DB_NAME = "leads.db"


# ==================================================
# DATABASE LAYER
# ==================================================
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_NAME)
        db.row_factory = sqlite3.Row
    return db


def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            business TEXT NOT NULL,
            score TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()


@app.teardown_appcontext
def close_db(_):
    db = getattr(g, "_database", None)
    if db:
        db.close()


# ==================================================
# AUTH SYSTEM
# ==================================================
def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("user") != "admin":
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ==================================================
# LEAD SCORING ENGINE (B1 CORE)
# ==================================================
def score_lead(business: str):
    if not business:
        return "COLD"

    b = business.lower()

    hot = ["ai", "software", "tech", "startup", "marketing", "agency", "consulting", "finance"]
    warm = ["business", "service", "ecommerce", "shop", "retail"]

    if any(k in b for k in hot):
        return "HOT"
    if any(k in b for k in warm):
        return "WARM"
    return "COLD"


# ==================================================
# ANALYTICS ENGINE
# ==================================================
def get_dashboard_stats(leads):
    return {
        "total": len(leads),
        "hot": sum(1 for l in leads if l["score"] == "HOT"),
        "warm": sum(1 for l in leads if l["score"] == "WARM"),
        "cold": sum(1 for l in leads if l["score"] == "COLD"),
    }


# ==================================================
# ROUTES
# ==================================================
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/admin")
@require_login
def admin():
    db = get_db()
    leads = db.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()
    stats = get_dashboard_stats(leads)
    return render_template("admin.html", leads=leads, stats=stats)


# ==================================================
# LEAD CAPTURE
# ==================================================
@app.route("/capture", methods=["POST"])
def capture():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    business = request.form.get("business", "").strip()

    if not all([name, email, business]):
        flash("All fields required.")
        return redirect(url_for("home"))

    score = score_lead(business)

    db = get_db()
    db.execute(
        "INSERT INTO leads (name, email, business, score) VALUES (?, ?, ?, ?)",
        (name, email, business, score)
    )
    db.commit()

    return redirect(url_for("admin"))


# ==================================================
# LOGIN
# ==================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username")
        pwd = request.form.get("password")

        if user == os.getenv("ADMIN_USERNAME", "admin") and \
           pwd == os.getenv("ADMIN_PASSWORD", "admin123"):

            session["user"] = "admin"
            return redirect(url_for("admin"))

        flash("Invalid credentials")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ==================================================
# DELETE LEAD
# ==================================================
@app.route("/delete/<int:lead_id>")
@require_login
def delete_lead(lead_id):
    db = get_db()
    db.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    db.commit()
    return redirect(url_for("admin"))


# ==================================================
# API
# ==================================================
@app.route("/api/leads")
@require_login
def api_leads():
    db = get_db()
    leads = db.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()

    return jsonify({
        "success": True,
        "total": len(leads),
        "leads": [dict(l) for l in leads]
    })


# ==================================================
# EXPORT CSV
# ==================================================
@app.route("/export")
@require_login
def export_csv():
    db = get_db()
    leads = db.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()

    with open("leads_export.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Name", "Email", "Business", "Score", "Created At"])

        for l in leads:
            writer.writerow([l["id"], l["name"], l["email"], l["business"], l["score"], l["created_at"]])

    flash("Export complete.")
    return redirect(url_for("admin"))


# ==================================================
# 🧠 B1 AI ACTION ENGINE (PRODUCTION VERSION)
# ==================================================
@app.route("/copilot", methods=["POST"])
@require_login
def copilot():
    try:
        data = request.get_json()
        message = (data.get("message") or "").strip().lower()

        db = get_db()
        leads = db.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()
        lead_context = [dict(l) for l in leads]

        # =========================
        # FALLBACK MODE (ALWAYS WORKS)
        # =========================
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key or not OPENAI_AVAILABLE:

            if "hot" in message:
                return jsonify({"reply": "Focus HOT leads first — highest conversion probability."})

            if "lead" in message:
                return jsonify({"reply": f"You have {len(leads)} total leads."})

            if "score" in message:
                return jsonify({"reply": "Scoring system: HOT → WARM → COLD."})

            return jsonify({
                "reply": "Copilot Offline Mode: ask about leads, scoring, or HOT leads."
            })

        # =========================
        # AI MODE
        # =========================
        client = OpenAI(api_key=api_key)

        system_prompt = f"""
You are B1 AI ACTION ENGINE.

You are a SALES OPERATIONS SYSTEM.

TASKS:
- Rank leads
- Suggest actions
- Write outreach messages
- Prioritize revenue opportunities

LEADS:
{lead_context}

FORMAT:
1. Priority Leads
2. Actions
3. Messages
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ]
        )

        return jsonify({"reply": response.choices[0].message.content})

    except Exception:
        print("COPILOT ERROR:")
        traceback.print_exc()

        return jsonify({
            "reply": "System error. Fallback mode active."
        })


# ==================================================
# START APP
# ==================================================
if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="127.0.0.1", port=5000)