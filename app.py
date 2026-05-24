from flask import Flask, render_template, request, g, session, redirect, url_for, flash
import sqlite3
import os
from functools import wraps

# ==================================================
# BASE PATH (PYTHONANYWHERE SAFE)
# ==================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "leads.db")

# ==================================================
# FLASK APP
# ==================================================
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "leadforge_dev_secret_2026")

# ==================================================
# DATABASE
# ==================================================
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
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
# LEAD SCORING ENGINE
# ==================================================
def score_lead(business: str):
    if not business:
        return "COLD"

    b = business.lower()

    if any(k in b for k in ["ai", "software", "tech", "saas", "startup"]):
        return "HOT"
    if any(k in b for k in ["business", "service", "shop", "retail"]):
        return "WARM"
    return "COLD"


# ==================================================
# HOME
# ==================================================
@app.route("/")
def home():
    return render_template("index.html")


# ==================================================
# ADMIN (SAAS PROTECTED)
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
# LEAD CAPTURE
# ==================================================
@app.route("/capture", methods=["POST"])
def capture():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    business = request.form.get("business", "").strip()

    if not name or not email or not business:
        flash("All fields required")
        return redirect(url_for("home"))

    score = score_lead(business)

    db = get_db()
    db.execute(
        "INSERT INTO leads (name, email, business, score, is_paid) VALUES (?, ?, ?, ?, 0)",
        (name, email, business, score)
    )
    db.commit()

    return redirect(url_for("paywall"))


# ==================================================
# 🔒 SAAS PAYWALL PAGE
# ==================================================
@app.route("/paywall")
def paywall():
    db = get_db()
    lead = db.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 1").fetchone()

    return render_template("paywall.html", lead=lead)


# ==================================================
# PAYMENT SUCCESS (MANUAL MARKING FOR NOW)
# ==================================================
@app.route("/unlock/<int:lead_id>")
def unlock(lead_id):
    db = get_db()
    db.execute("UPDATE leads SET is_paid = 1 WHERE id = ?", (lead_id,))
    db.commit()

    flash("Payment successful — SaaS unlocked 🚀")
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
# START APP
# ==================================================
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)