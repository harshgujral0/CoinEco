import os
import sqlite3
import random
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g, send_from_directory, flash
from werkzeug.utils import secure_filename
import bcrypt
from datetime import datetime
import base64

# SendGrid imports
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# ---------------- CONFIG ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ecocoin.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("ECO_SECRET", "supersecretkey")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config['TEMPLATES_AUTO_RELOAD'] = True

# ---------------- SENDGRID CONFIG ----------------
# Make sure to set these environment variables locally and on Render:
# SENDGRID_API_KEY and FROM_EMAIL
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")  # now uses environment variable
FROM_EMAIL = os.environ.get("FROM_EMAIL", "project.ecocoin@gmail.com")
otp_storage = {}

# ---------------- DATABASE ----------------
def get_db():
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        photo TEXT,
        balance INTEGER DEFAULT 0,
        username TEXT,
        gender TEXT,
        address TEXT,
        joined TEXT,
        secret_pin TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        material TEXT,
        weight REAL,
        points INTEGER,
        time TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------- STATIC FILE SERVING ----------------
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ---------------- CONTEXT ----------------
@app.context_processor
def inject_now():
    return {"current_year": datetime.utcnow().year}

# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return render_template("index.html")

# -------- OTP SENDING ROUTE (SendGrid) --------
@app.route('/send_otp', methods=['POST'])
def send_otp():
    email = request.form.get('email')
    if not email:
        return jsonify({"error": "Please enter your email first."}), 400

    otp = str(random.randint(100000, 999999))
    otp_storage[email] = otp

    # Build the SendGrid message
    html_content = f"""
        <h2>Welcome to EcoCoin!</h2>
        <p>Your One-Time Password (OTP) is: <strong>{otp}</strong></p>
        <p>Please do not share this code with anyone. The OTP will expire in 10 minutes.</p>
        <p>— Team EcoCoin 🌱</p>
    """

    try:
        if not SENDGRID_API_KEY:
            raise RuntimeError("SENDGRID_API_KEY environment variable is not set")

        message = Mail(
            from_email=FROM_EMAIL,
            to_emails=email,
            subject="EcoCoin Email Verification - OTP Inside 🌿",
            html_content=html_content
        )
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        # optional: you can check response.status_code
        return jsonify({"success": True, "message": "OTP sent successfully!"}), 200
    except Exception as e:
        print("SendGrid Error:", e)
        return jsonify({"error": "Failed to send OTP"}), 500


# -------- USER REGISTRATION --------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        otp_entered = request.form.get("otp", "")
        photo_data = request.form.get("photo_data")

        if not (name and email and password and photo_data):
            flash("All fields are required including photo capture.", "danger")
            return render_template("register.html", email=email)

        # OTP validation
        if email not in otp_storage or otp_storage[email] != otp_entered:
            flash("Invalid or missing OTP. Please verify your email.", "danger")
            return render_template("register.html", email=email)

        # Hash password
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Save photo
        try:
            imgdata = base64.b64decode(photo_data.split(",")[1])
            filename = f"user_{int(datetime.utcnow().timestamp())}.jpg"
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(filename))
            with open(filepath, "wb") as f:
                f.write(imgdata)
        except Exception as e:
            return f"Error processing photo: {e}", 400

        # Insert into DB
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (name,email,password,photo) VALUES (?,?,?,?)",
                (name, email, hashed, filename),
            )
            conn.commit()
            # Generate 6-digit PIN
            pin = str(random.randint(100000, 999999))
            cur.execute("UPDATE users SET secret_pin=? WHERE id=?", (pin, cur.lastrowid))
            conn.commit()
        except sqlite3.IntegrityError:
            flash("Email already exists!", "warning")
            return render_template("register.html", email=email)

        del otp_storage[email]
        flash("Registration successful! You can now login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

# -------- LOGIN --------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cur.fetchone()

        if user and bcrypt.checkpw(password.encode(), user["password"].encode()):
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        elif email == "ecocoin011@gmail.com" and password == "iuceeproject":
            session["admin"] = True
            return redirect(url_for("admin"))
        else:
            flash("Invalid login!", "danger")
            return redirect(url_for("login"))
    return render_template("login.html")

# -------- DASHBOARD --------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    uid = session["user_id"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (uid,))
    user = cur.fetchone()
    cur.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC", (uid,))
    txs = cur.fetchall()
    return render_template("dashboard.html", user=user, transactions=txs)

# -------- PROFILE --------
@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))
    uid = session["user_id"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (uid,))
    user = cur.fetchone()
    return render_template("profile.html", user=user)

# -------- LOGOUT --------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# -------- EDIT PROFILE --------
@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    uid = session["user_id"]
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE id=?", (uid,))
    user = cur.fetchone()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        gender = request.form.get("gender", "").strip()
        address = request.form.get("address", "").strip()
        joined = request.form.get("member_since", "").strip()

        cur.execute("""
            UPDATE users 
            SET username=?, gender=?, address=?, joined=? 
            WHERE id=?
        """, (username, gender, address, joined, uid))
        conn.commit()
        return redirect(url_for("profile"))

    return render_template("edit_profile.html", user=user)

# -------- API FOR POINT UPDATES --------
@app.route("/api/update-points", methods=["POST"])
def api_update_points():
    data = request.json or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "user_id required"}), 400
    material = data.get("material", "Unknown")
    weight = float(data.get("weight", 0))
    points = int(data.get("points", 0))

    now = datetime.utcnow().isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO transactions (user_id,material,weight,points,time) VALUES (?,?,?,?,?)",
        (user_id, material, weight, points, now),
    )
    cur.execute("UPDATE users SET balance = balance + ? WHERE id=?", (points, user_id))
    conn.commit()
    cur.execute("SELECT balance FROM users WHERE id=?", (user_id,))
    row = cur.fetchone()
    newbal = row["balance"] if row else 0
    return jsonify({"success": True, "new_balance": newbal})

# -------- OTHER PAGES --------
@app.route("/credit")
def credit():
    return render_template("credit.html")

@app.route("/support")
def support():
    return redirect("https://docs.google.com/forms/d/e/1FAIpQLSc4DSK0gDw2Tg807pK1K0IyWyI6rMXp0JFHJYVVqOXIBRULkw/viewform?usp=sf_link")

@app.route("/leaderboard")
def leaderboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, photo, COALESCE(balance,0) as balance FROM users ORDER BY balance DESC LIMIT 50")
    users = [dict(row) for row in cur.fetchall()]

    cur.execute("SELECT material, SUM(points) as total_points FROM transactions GROUP BY material")
    community_rows = cur.fetchall()
    community = {row["material"]: row["total_points"] for row in community_rows} if community_rows else {}

    user_breakdowns = {}
    for u in users:
        uid = u["id"]
        cur.execute("SELECT material, SUM(points) as pts FROM transactions WHERE user_id=? GROUP BY material", (uid,))
        rows = cur.fetchall()
        breakdown = {r["material"]: r["pts"] for r in rows} if rows else {}
        user_breakdowns[str(uid)] = breakdown

    return render_template("leaderboard.html",
                            users=users,
                            community=community,
                            user_breakdowns=user_breakdowns)

# -------- ADMIN DASHBOARD --------
@app.route("/admin")
def admin():
    if "admin" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, balance, username, gender, address, joined, secret_pin FROM users")
    users = cur.fetchall()
    return render_template("admin.html", users=users)

@app.route("/admin/delete/<int:user_id>", methods=["POST"])
def admin_delete(user_id):
    if "admin" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    flash("User deleted successfully.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/edit/<int:user_id>", methods=["GET", "POST"])
def admin_edit(user_id):
    if "admin" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        balance = int(request.form.get("balance", 0))
        username = request.form.get("username", "").strip()
        gender = request.form.get("gender", "").strip()
        address = request.form.get("address", "").strip()
        joined = request.form.get("joined", "").strip()
        secret_pin = request.form.get("secret_pin", "").strip()

        try:
            cur.execute("""
                UPDATE users SET name=?, email=?, balance=?, username=?, gender=?, address=?, joined=?, secret_pin=?
                WHERE id=?
            """, (name, email, balance, username, gender, address, joined, secret_pin, user_id))
            conn.commit()
            flash("User updated successfully.", "success")
            return redirect(url_for("admin"))
        except sqlite3.IntegrityError:
            flash("Email already exists.", "danger")
            return redirect(url_for("admin_edit", user_id=user_id))

    cur.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = cur.fetchone()
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin"))

    return render_template("admin_edit.html", user=user)

@app.route("/api/get_user_by_pin", methods=["GET"])
def get_user_by_pin():
    pin = request.args.get("pin", "").strip()

    if not pin:
        return jsonify({"success": False, "error": "PIN required"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, balance FROM users WHERE secret_pin=?", (pin,))
    user = cur.fetchone()

    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    return jsonify({
        "success": True,
        "user_id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "balance": user["balance"]
    })
@app.route("/api/update_points_by_pin", methods=["POST"])
def update_points_by_pin():
    data = request.json or {}

    pin = data.get("pin")
    if not pin:
        return jsonify({"success": False, "error": "PIN required"}), 400

    conn = get_db()
    cur = conn.cursor()

    # find user
    cur.execute("SELECT id FROM users WHERE secret_pin=?", (pin,))
    user = cur.fetchone()

    if not user:
        return jsonify({"success": False, "error": "Invalid PIN"}), 404

    user_id = user["id"]

    # data
    material = data.get("material", "Unknown")
    weight = float(data.get("weight", 0))
    points = int(data.get("points", 0))
    now = datetime.utcnow().isoformat()

    # insert transaction
    cur.execute("""
        INSERT INTO transactions (user_id, material, weight, points, time)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, material, weight, points, now))

    cur.execute("UPDATE users SET balance = balance + ? WHERE id=?", (points, user_id))
    conn.commit()

    cur.execute("SELECT balance FROM users WHERE id=?", (user_id,))
    newbal = cur.fetchone()["balance"]

    return jsonify({"success": True, "new_balance": newbal})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

