from flask import Flask, render_template, request, g, session, redirect, url_for, flash, jsonify
import sqlite3
import os
from functools import wraps

# ==================================================
# CONFIG
# ==================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "leads.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "leadforge_dev_secret_2026")

# ==================================================
# DATABASE
# ==================================================
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        g._database = db
    return db


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            business TEXT NOT NULL,
            score TEXT NOT NULL,
            is_paid INTEGER DEFAULT 0,
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
# AUTH
# ==================================================
def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("user") != "admin":
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

# ==================================================
# LEAD SCORING (SIMULATED AI ENGINE)
# ==================================================
def score_lead(business: str):
    if not business:
        return "COLD"

    b = business.lower()

    if any(k in b for k in ["ai", "software", "tech", "saas", "startup", "automation"]):
        return "HOT"

    if any(k in b for k in ["business", "service", "agency", "shop", "retail"]):
        return "WARM"

    return "COLD"

# ==================================================
# HOME
# ==================================================
@app.route("/")
def home():
    return render_template("index.html")

# ==================================================
# LEAD CAPTURE (FULL FIXED — NO CRASHES)
# ==================================================
@app.route("/capture", methods=["POST"])
def capture():
    try:
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        business = request.form.get("business", "").strip()

        if not name or not email or not business:
            flash("All fields are required.")
            return redirect(url_for("home"))

        db = get_db()

        # prevent duplicates safely
        existing = db.execute(
            "SELECT id FROM leads WHERE email = ?",
            (email,)
        ).fetchone()

        if existing:
            flash("Lead already exists. Try another email.")
            return redirect(url_for("home"))

        score = score_lead(business)

        db.execute("""
            INSERT INTO leads (name, email, business, score, is_paid)
            VALUES (?, ?, ?, ?, 0)
        """, (name, email, business, score))

        db.commit()

        session["lead_email"] = email

        return redirect(url_for("paywall"))

    except Exception as e:
        print("CAPTURE ERROR:", str(e))
        flash("Something went wrong while processing your lead.")
        return redirect(url_for("home"))

# ==================================================
# PAYWALL
# ==================================================
@app.route("/paywall")
def paywall():
    return render_template("paywall.html")

# ==================================================
# UPGRADE
# ==================================================
@app.route("/upgrade")
def upgrade():
    return render_template("upgrade.html")

# ==================================================
# PAYMENT SUCCESS (SAFE MVP LOGIC)
# ==================================================
@app.route("/payment-success")
def payment_success():
    db = get_db()
    email = session.get("lead_email")

    if email:
        db.execute("""
            UPDATE leads
            SET is_paid = 1
            WHERE email = ?
        """, (email,))
        db.commit()

    return render_template("payment_success.html")

# ==================================================
# ADMIN DASHBOARD
# ==================================================
@app.route("/admin")
@require_login
def admin():
    db = get_db()
    leads = db.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()

    stats = {
        "total": len(leads),
        "hot": sum(1 for l in leads if l["score"] == "HOT"),
        "warm": sum(1 for l in leads if l["score"] == "WARM"),
        "cold": sum(1 for l in leads if l["score"] == "COLD"),
    }

    return render_template("admin.html", leads=leads, stats=stats)

# ==================================================
# DELETE LEAD
# ==================================================
@app.route("/delete/<int:lead_id>")
@require_login
def delete(lead_id):
    db = get_db()
    db.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    db.commit()
    return redirect(url_for("admin"))

# ==================================================
# LOGIN
# ==================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == "admin" and request.form.get("password") == "admin123":
            session["user"] = "admin"
            return redirect(url_for("admin"))

        flash("Invalid credentials")

    return render_template("login.html")

# ==================================================
# LOGOUT
# ==================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

# ==================================================
# COPILOT (SIMULATED AI — SAFE)
# ==================================================
@app.route("/copilot", methods=["POST"])
def copilot():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").lower()

    if "lead" in message:
        reply = "HOT leads convert fastest — focus there first."
    elif "sales" in message:
        reply = "Follow up within 24 hours for best conversion rates."
    elif "revenue" in message:
        reply = "Target SaaS, tech, and service-based businesses."
    else:
        reply = "Ask me about leads, sales, or revenue strategy."

    return jsonify({"reply": reply})

# ==================================================
# START
# ==================================================
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)