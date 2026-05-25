# =========================
# LEADFORGE AI SAAS LEVEL 5
# MULTI-TENANT FUNDABLE ARCHITECTURE
# =========================

import sqlite3
import time
import hashlib
import secrets
from functools import wraps
from datetime import datetime
from contextlib import contextmanager

from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify

# =========================
# APP INITIALIZATION
# =========================
app = Flask(__name__)

# =========================
# CONFIGURATION
# =========================
app.config.update(
    SECRET_KEY="CHANGE_THIS_SUPER_SECRET_TO_A_RANDOM_VALUE",
    SESSION_TIMEOUT=3600,
    DATABASE="leadforge.db",
    MAX_REQUESTS=60,
    WINDOW_SECONDS=60,
    FREE_TIER_LIMIT=50,      # Free tier: 50 leads per month
    PRO_TIER_LIMIT=999999    # Pro tier: unlimited
)

# Rate limiting storage
RATE_LIMIT = {}

# =========================
# DATABASE HELPERS
# =========================
def get_db():
    """Get database connection for current request context"""
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    """Close database connection after request"""
    db = g.pop("db", None)
    if db is not None:
        db.close()

@contextmanager
def get_db_connection():
    """Context manager for database operations"""
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# =========================
# FLASH MESSAGE SYSTEM
# =========================
def flash(message, category="info"):
    """Store flash message in session"""
    if "flashes" not in session:
        session["flashes"] = []
    session["flashes"].append({"message": message, "category": category})

def get_flashes():
    """Retrieve and clear flash messages"""
    flashes = session.pop("flashes", [])
    return flashes

# Make flash available to templates
@app.context_processor
def utility_processor():
    return {
        "get_flashes": get_flashes,
        "now": datetime.now,
        "app_name": "LeadForge AI"
    }

# =========================
# COMPLETE DATABASE MIGRATION
# =========================
def migrate_database():
    """Add all missing columns to existing database tables"""
    with get_db_connection() as conn:
        # Fix users table - add org_id if missing
        cursor = conn.execute("PRAGMA table_info(users)")
        existing_columns = [col[1] for col in cursor.fetchall()]
        
        if 'org_id' not in existing_columns:
            print("Adding org_id column to users table...")
            conn.execute("ALTER TABLE users ADD COLUMN org_id INTEGER DEFAULT 1")
            conn.execute("UPDATE users SET org_id = 1 WHERE org_id IS NULL")
            print("✓ Added org_id to users table")
        
        # Fix leads table - add all missing columns
        cursor = conn.execute("PRAGMA table_info(leads)")
        existing_columns = [col[1] for col in cursor.fetchall()]
        
        if 'org_id' not in existing_columns:
            print("Adding org_id column to leads table...")
            conn.execute("ALTER TABLE leads ADD COLUMN org_id INTEGER DEFAULT 1")
            conn.execute("UPDATE leads SET org_id = 1 WHERE org_id IS NULL")
            print("✓ Added org_id to leads table")
        
        if 'user_id' not in existing_columns:
            print("Adding user_id column to leads table...")
            conn.execute("ALTER TABLE leads ADD COLUMN user_id INTEGER DEFAULT 1")
            conn.execute("UPDATE leads SET user_id = 1 WHERE user_id IS NULL")
            print("✓ Added user_id to leads table")
        
        if 'is_paid' not in existing_columns:
            print("Adding is_paid column to leads table...")
            conn.execute("ALTER TABLE leads ADD COLUMN is_paid INTEGER DEFAULT 0")
            print("✓ Added is_paid to leads table")
        
        if 'label' not in existing_columns:
            print("Adding label column to leads table...")
            conn.execute("ALTER TABLE leads ADD COLUMN label TEXT DEFAULT 'COLD'")
            print("✓ Added label to leads table")
        
        print("Database migration complete!")

# =========================
# DATABASE INITIALIZATION
# =========================
def init_db():
    """Initialize database with all required tables"""
    with get_db_connection() as conn:
        # ORGANIZATIONS TABLE
        conn.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                plan TEXT DEFAULT 'free',
                api_key TEXT UNIQUE NOT NULL,
                leads_this_month INTEGER DEFAULT 0,
                last_reset_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # USERS TABLE
        table_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
        
        if not table_check:
            conn.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER DEFAULT 1,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("✓ Created users table")
        else:
            cursor = conn.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'org_id' not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN org_id INTEGER DEFAULT 1")
                print("✓ Added org_id to existing users table")

        # LEADS TABLE
        table_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='leads'").fetchone()
        
        if not table_check:
            conn.execute("""
                CREATE TABLE leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    org_id INTEGER DEFAULT 1,
                    user_id INTEGER DEFAULT 1,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    business TEXT NOT NULL,
                    score INTEGER DEFAULT 0,
                    label TEXT DEFAULT 'COLD',
                    is_paid INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("✓ Created leads table")
        else:
            cursor = conn.execute("PRAGMA table_info(leads)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'org_id' not in columns:
                conn.execute("ALTER TABLE leads ADD COLUMN org_id INTEGER DEFAULT 1")
            if 'user_id' not in columns:
                conn.execute("ALTER TABLE leads ADD COLUMN user_id INTEGER DEFAULT 1")
            if 'is_paid' not in columns:
                conn.execute("ALTER TABLE leads ADD COLUMN is_paid INTEGER DEFAULT 0")
            if 'label' not in columns:
                conn.execute("ALTER TABLE leads ADD COLUMN label TEXT DEFAULT 'COLD'")

        # PAYMENTS TABLE
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                provider TEXT,
                status TEXT DEFAULT 'pending',
                amount REAL DEFAULT 0.00,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create default organization if none exists
        org_count = conn.execute("SELECT COUNT(*) as count FROM organizations").fetchone()["count"]
        if org_count == 0:
            default_api_key = generate_api_key()
            conn.execute("""
                INSERT INTO organizations (name, plan, api_key)
                VALUES (?, ?, ?)
            """, ("Default Organization", "free", default_api_key))
            print("✓ Created default organization")
            
            default_password = hash_password("admin123")
            conn.execute("""
                INSERT INTO users (org_id, username, password, role)
                VALUES (?, ?, ?, ?)
            """, (1, "admin", default_password, "admin"))
            print("✓ Created default admin user (username: admin, password: admin123)")

        # Create indexes
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_org_id ON leads(org_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email)")
        except Exception as e:
            print(f"Index creation note: {e}")

# =========================
# LEAD LIMIT HELPERS
# =========================
def get_user_plan(org_id):
    """Get the plan for an organization"""
    db = get_db()
    result = db.execute(
        "SELECT plan FROM organizations WHERE id = ?",
        (org_id,)
    ).fetchone()
    return result["plan"] if result else "free"

def get_lead_count_this_month(org_id):
    """Get number of leads captured this month for an organization"""
    db = get_db()
    current_month = datetime.now().strftime("%Y-%m")
    result = db.execute("""
        SELECT COUNT(*) as count FROM leads 
        WHERE org_id = ? AND strftime('%Y-%m', created_at) = ?
    """, (org_id, current_month)).fetchone()
    return result["count"]

def check_lead_limit(org_id):
    """Check if organization has reached its lead limit"""
    plan = get_user_plan(org_id)
    current_count = get_lead_count_this_month(org_id)
    
    if plan == "free":
        if current_count >= app.config["FREE_TIER_LIMIT"]:
            return False, current_count, app.config["FREE_TIER_LIMIT"]
    return True, current_count, app.config["PRO_TIER_LIMIT"] if plan == "pro" else app.config["FREE_TIER_LIMIT"]

def can_capture_lead(org_id):
    """Return (allowed, current_count, limit, plan)"""
    plan = get_user_plan(org_id)
    current_count = get_lead_count_this_month(org_id)
    
    if plan == "free":
        limit = app.config["FREE_TIER_LIMIT"]
        allowed = current_count < limit
    else:
        limit = app.config["PRO_TIER_LIMIT"]
        allowed = True
    
    return allowed, current_count, limit, plan

# =========================
# SECURITY HELPERS
# =========================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_api_key() -> str:
    return secrets.token_hex(24)

# =========================
# AUTHENTICATION DECORATORS
# =========================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please login to access this page", "warning")
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function

def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get("X-API-KEY")
        if not api_key:
            return jsonify({"error": "Missing API key"}), 401
        
        db = get_db()
        org = db.execute(
            "SELECT * FROM organizations WHERE api_key = ?",
            (api_key,)
        ).fetchone()
        
        if not org:
            return jsonify({"error": "Invalid API key"}), 403
        
        g.org = org
        return f(*args, **kwargs)
    return decorated_function

# =========================
# AI SCORING ENGINE
# =========================
def ai_engine_v4(text: str) -> dict:
    """Intelligent lead scoring based on keyword detection"""
    text_lower = text.lower()
    
    signals = {
        "enterprise": 35, "investment": 30, "saas": 25,
        "startup": 20, "agency": 10, "business": 10,
        "b2b": 25, "ecommerce": 15, "marketing": 10,
        "consulting": 10, "ai": 20, "machine learning": 20,
        "blockchain": 15, "cloud": 15, "scale": 15,
        "growth": 10, "software": 15, "platform": 10,
        "automation": 15, "data": 10, "analytics": 10
    }
    
    score = 40  # Base score
    detected_signals = []
    
    for keyword, weight in signals.items():
        if keyword in text_lower:
            score += weight
            detected_signals.append(keyword)
    
    score = min(100, max(0, score))
    
    if score >= 75:
        label = "HOT"
    elif score >= 55:
        label = "WARM"
    else:
        label = "COLD"
    
    return {"score": score, "label": label, "signals": detected_signals}

# =========================
# HELPER FUNCTIONS
# =========================
def get_lead_stats(org_id: int) -> dict:
    """Get lead statistics for dashboard"""
    db = get_db()
    
    total = db.execute("SELECT COUNT(*) as count FROM leads WHERE org_id = ?", (org_id,)).fetchone()["count"]
    hot = db.execute("SELECT COUNT(*) as count FROM leads WHERE org_id = ? AND label = 'HOT'", (org_id,)).fetchone()["count"]
    warm = db.execute("SELECT COUNT(*) as count FROM leads WHERE org_id = ? AND label = 'WARM'", (org_id,)).fetchone()["count"]
    cold = db.execute("SELECT COUNT(*) as count FROM leads WHERE org_id = ? AND label = 'COLD'", (org_id,)).fetchone()["count"]
    
    return {"total": total, "hot": hot, "warm": warm, "cold": cold}

# =========================
# PAGE ROUTES
# =========================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login")
def login_page():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/upgrade")
@login_required
def upgrade():
    """Upgrade page showing plan details"""
    db = get_db()
    org = db.execute(
        "SELECT plan FROM organizations WHERE id = ?",
        (session.get("org_id", 1),)
    ).fetchone()
    current_plan = org["plan"] if org else "free"
    
    return render_template("upgrade.html", current_plan=current_plan)

@app.route("/paywall")
def paywall():
    return redirect(url_for("upgrade"))

@app.route("/payment-success")
@login_required
def payment_success():
    """Handle successful payment"""
    db = get_db()
    db.execute(
        "UPDATE organizations SET plan = 'pro' WHERE id = ?",
        (session.get("org_id", 1),)
    )
    db.commit()
    
    # Record payment
    db.execute("""
        INSERT INTO payments (org_id, provider, status, amount)
        VALUES (?, ?, ?, ?)
    """, (session.get("org_id", 1), 'paypal', 'completed', 9.99))
    db.commit()
    
    flash("Payment successful! Your account has been upgraded to Pro. 🎉", "success")
    return redirect(url_for("dashboard"))

@app.route("/admin")
@login_required
def admin():
    return redirect(url_for("dashboard"))

# =========================
# AUTHENTICATION ROUTES
# =========================

@app.route("/login/submit", methods=["POST"])
def login_submit():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    
    if not username or not password:
        flash("Username and password are required", "error")
        return redirect(url_for("login_page"))
    
    db = get_db()
    hashed_password = hash_password(password)
    
    user = db.execute("""
        SELECT u.*, o.name as org_name, o.plan as org_plan
        FROM users u
        LEFT JOIN organizations o ON u.org_id = o.id
        WHERE u.username = ? AND u.password = ?
    """, (username, hashed_password)).fetchone()
    
    if not user:
        flash("Invalid username or password", "error")
        return redirect(url_for("login_page"))
    
    session["user_id"] = user["id"]
    session["org_id"] = user["org_id"] if user["org_id"] else 1
    session["username"] = user["username"]
    session["plan"] = user["org_plan"] if user["org_plan"] else "free"
    
    flash(f"Welcome back, {user['username']}! 👋", "success")
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "info")
    return redirect(url_for("home"))

# =========================
# DASHBOARD ROUTE
# =========================

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    
    # Get user's plan and lead usage
    org = db.execute(
        "SELECT plan FROM organizations WHERE id = ?",
        (session.get("org_id", 1),)
    ).fetchone()
    current_plan = org["plan"] if org else "free"
    
    allowed, current_count, limit, plan = can_capture_lead(session.get("org_id", 1))
    
    leads = db.execute("""
        SELECT * FROM leads 
        WHERE org_id = ? 
        ORDER BY created_at DESC
    """, (session.get("org_id", 1),)).fetchall()
    
    stats = get_lead_stats(session.get("org_id", 1))
    
    return render_template("admin.html", 
                         leads=leads, 
                         stats=stats,
                         current_plan=current_plan,
                         lead_count=current_count,
                         lead_limit=limit,
                         remaining=limit - current_count if current_plan == "free" else "Unlimited")

# =========================
# LEAD MANAGEMENT ROUTES
# =========================

@app.route("/capture", methods=["POST"])
@login_required
def capture():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    business = request.form.get("business", "").strip()
    
    if not all([name, email, business]):
        flash("All fields are required", "error")
        return redirect(url_for("dashboard"))
    
    # Email validation
    if "@" not in email or "." not in email:
        flash("Please enter a valid email address", "error")
        return redirect(url_for("dashboard"))
    
    # Check lead limit
    allowed, current_count, limit, plan = can_capture_lead(session.get("org_id", 1))
    
    if not allowed:
        flash(f"Free tier limit reached ({current_count}/{limit} leads this month). Upgrade to Pro for unlimited leads!", "warning")
        return redirect(url_for("upgrade"))
    
    # Analyze with AI
    result = ai_engine_v4(business)
    
    db = get_db()
    db.execute("""
        INSERT INTO leads (org_id, user_id, name, email, business, score, label, is_paid)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session.get("org_id", 1),
        session.get("user_id", 1),
        name,
        email,
        business,
        result["score"],
        result["label"],
        1 if session.get("plan") == "pro" else 0
    ))
    db.commit()
    
    remaining = limit - (current_count + 1)
    if remaining <= 5 and remaining > 0 and session.get("plan") == "free":
        flash(f"Lead analyzed! Status: {result['label']}. ⚠️ Only {remaining} lead(s) remaining this month. Upgrade to Pro for unlimited!", "warning")
    else:
        flash(f"Lead analyzed! Status: {result['label']} 🎯", "success")
    
    return redirect(url_for("dashboard"))

@app.route("/delete/<int:lead_id>")
@login_required
def delete(lead_id):
    db = get_db()
    
    lead = db.execute(
        "SELECT id FROM leads WHERE id = ? AND org_id = ?",
        (lead_id, session.get("org_id", 1))
    ).fetchone()
    
    if not lead:
        flash("Lead not found", "error")
        return redirect(url_for("dashboard"))
    
    db.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    db.commit()
    
    flash("Lead deleted successfully", "success")
    return redirect(url_for("dashboard"))

# =========================
# API ENDPOINTS
# =========================

@app.route("/api/score", methods=["POST"])
@api_key_required
def api_score():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400
    
    data = request.get_json()
    text = data.get("text", "")
    
    if not text:
        return jsonify({"error": "Text field is required"}), 400
    
    result = ai_engine_v4(text)
    return jsonify({
        "success": True,
        "score": result["score"],
        "label": result["label"],
        "signals": result["signals"]
    })

@app.route("/api/leads")
@api_key_required
def api_leads():
    db = get_db()
    
    leads = db.execute("""
        SELECT id, name, email, business, score, label, created_at
        FROM leads 
        WHERE org_id = ?
        ORDER BY created_at DESC
        LIMIT 100
    """, (g.org["id"],)).fetchall()
    
    return jsonify({
        "success": True,
        "count": len(leads),
        "leads": [dict(lead) for lead in leads]
    })

@app.route("/api/usage")
@api_key_required
def api_usage():
    """API endpoint to check current usage"""
    current_count = get_lead_count_this_month(g.org["id"])
    plan = g.org["plan"]
    limit = app.config["FREE_TIER_LIMIT"] if plan == "free" else app.config["PRO_TIER_LIMIT"]
    
    return jsonify({
        "success": True,
        "plan": plan,
        "leads_this_month": current_count,
        "monthly_limit": limit,
        "remaining": limit - current_count if plan == "free" else "unlimited"
    })

@app.route("/api/payment-webhook", methods=["POST"])
def payment_webhook():
    """Handle PayPal payment webhook"""
    try:
        data = request.get_json() or {}
        # Verify payment here (in production, verify with PayPal)
        
        # For demo, assume payment is valid
        org_id = data.get("org_id")
        if org_id:
            db = get_db()
            db.execute(
                "UPDATE organizations SET plan = 'pro' WHERE id = ?",
                (org_id,)
            )
            db.execute("""
                INSERT INTO payments (org_id, provider, status, amount)
                VALUES (?, ?, ?, ?)
            """, (org_id, 'paypal', 'completed', 9.99))
            db.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# =========================
# ERROR HANDLERS
# =========================

@app.errorhandler(404)
def not_found_error(error):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template("500.html"), 500

# =========================
# APPLICATION INITIALIZATION
# =========================

with app.app_context():
    init_db()
    migrate_database()

# =========================
# RUN APPLICATION
# =========================
if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)