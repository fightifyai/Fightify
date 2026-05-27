from flask import Flask, render_template, request, redirect, session, jsonify, send_from_directory
import os
import json
import stripe
from flask import redirect, request, session
from datetime import datetime, date, timedelta
import cv2
import mediapipe as mp
import math
import random
stripe.api_key = "sk_test_51TaAp7LzWytRkK8sJ11gsOrmdvXbtEIeudQO7nqgRu7U7tyzU2PCfiGYA4dCasibrCGbcbVKRizyDN5EkCnVSiqx003gt6RPiZ"

user_data = {}

app = Flask(__name__)
app.secret_key = "boxing-ai-key"

UPLOAD_FOLDER = "uploads"
DATA_FILE = "sessions.json"
USERS_FILE = "users.json"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

mp_pose = mp.solutions.pose

app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_DOMAIN=None
)

# -------------------------
# USERS
# -------------------------
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_users(data):
    with open(USERS_FILE, "w") as f:
        json.dump(data, f, indent=2)

# -------------------------
# DATA SYSTEM
# -------------------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def require_payment():
    if "user" not in session:
        return redirect("/")
    if not session.get("paid", False):
        return redirect("/paywall")
    return None

# -------------------------
# DAILY PLAN
# -------------------------
def generate_daily_plan(logs, drills):
    if not drills:
        return []

    offense = [d for d in drills if d["focus"] == "offense"]
    defense = [d for d in drills if d["focus"] == "defense"]
    conditioning = [d for d in drills if d["focus"] == "conditioning"]

    plan = []
    if offense: plan.append(random.choice(offense))
    if defense: plan.append(random.choice(defense))
    if conditioning: plan.append(random.choice(conditioning))

    return plan

def get_daily_plan(username):
    data = load_data()
    sessions = data.get(username, [])

    with open("data/drills.json", "r") as f:
        drills = json.load(f)

    return generate_daily_plan(sessions, drills)

# -------------------------
# PROGRESS SYSTEM (FIXED)
# -------------------------
from datetime import date, timedelta

def update_progress(username, completed=False):
    users = load_users()

    if username not in users:
        return

    user = users[username]

    today = str(date.today())

    user.setdefault("xp", 0)
    user.setdefault("streak", 0)
    user.setdefault("last_active", None)
    user.setdefault("last_completed", None)

    # base xp
    user["xp"] += 10

    if completed:

        # completion bonus
        user["xp"] += 40

        if user["last_completed"] != today:

            yesterday = str(date.today() - timedelta(days=1))

            if user["last_completed"] == yesterday:
                user["streak"] += 1
            else:
                user["streak"] = 1

            user["last_completed"] = today

    user["last_active"] = today

    save_users(users)

# -------------------------
# RECOMMENDER
# -------------------------
def recommend_drills(logs, drills):
    if not logs:
        return drills[:2]  # fallback

    def normalize(t):
        t = t.lower()

        if "defense" in t:
            return "defense"
        if "offense" in t or "jab" in t or "combo" in t or "drill" in t:
            return "offense"
        if "conditioning" in t or "timed" in t or "round" in t:
            return "conditioning"

        return "offense"

    types = {}

    for l in logs:
        t = normalize(l.get("type", ""))
        types[t] = types.get(t, 0) + 1

    weakest_area = min(types, key=types.get)

    recommendations = [
        d for d in drills
        if d.get("focus") == weakest_area
    ]

    return recommendations[:2]
# -------------------------
# BOXING ANALYSIS ENGINE
# -------------------------
def analyze_fight(video_path):
    cap = cv2.VideoCapture(video_path)
    pose = mp_pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        min_detection_confidence=0.5
    )

    frames = 0
    guard_up_frames = 0
    punch_count = 0
    prev_left = None
    prev_right = None
    movement_list = []
    last_punch_frame = -999

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frames += 1
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb)

        if results.pose_landmarks:
            lm = results.pose_landmarks.landmark

            lw, rw = lm[15], lm[16]
            ls, rs = lm[11], lm[12]

            if prev_left is not None:
                lw.x = lw.x * 0.7 + prev_left.x * 0.3
            if prev_right is not None:
                rw.x = rw.x * 0.7 + prev_right.x * 0.3

            if lw.y < ls.y and rw.y < rs.y:
                guard_up_frames += 1

            if prev_left and prev_right:
                if abs(lw.x - prev_left.x) > 0.04 or abs(rw.x - prev_right.x) > 0.04:
                    if frames - last_punch_frame > 6:
                        punch_count += 1
                        last_punch_frame = frames

                movement = (abs(lw.x - prev_left.x) + abs(rw.x - prev_right.x)) / 2
                movement_list.append(movement)

            prev_left = lw
            prev_right = rw

    cap.release()

    if frames == 0:
        return {"offense":0,"defense":0,"output":0,"overall":0}

    video_time = max(frames/30,1)
    punch_rate = punch_count / video_time
    guard_ratio = guard_up_frames / frames

    offense = min(100, max(0, (punch_rate*12)+38))
    defense = min(100, 40+(guard_ratio*400))
    output = min(100, max(0, 32+(punch_rate*11)))

    overall = int((offense*0.3 + defense*0.3 + output*0.4))

    # -------------------------
    # COACH SYSTEM (ADD THIS)
    # -------------------------
    if defense < 50:
        coach = {
            "title": "Defense Breakdown",
            "mistake": "Guard is not consistent during exchanges",
            "fix": "Keep hands returning to face after every punch",
            "drills": [
                "3 rounds shadowboxing (guard reset after every punch)",
                "Slip + cover drill for 2 minutes",
                "Light sparring focusing only on defense"
            ]
        }
    elif offense < 50:
        coach = {
            "title": "Offense Breakdown",
            "mistake": "Low output and passive engagement",
            "fix": "Increase controlled punch frequency without losing form",
            "drills": [
                "1-2 combo repetition rounds",
                "Jab-only round",
                "Heavy bag steady rhythm"
            ]
        }
    elif output < 50:
        coach = {
            "title": "Output Breakdown",
            "mistake": "Not enough work rate or activity",
            "fix": "Increase punch volume while staying relaxed",
            "drills": [
                "High-volume jab rounds",
                "30s burst intervals",
                "Nonstop shadowboxing"
            ]
        }
    else:
        coach = {
            "title": "Strong Performance",
            "mistake": "Minor timing issues",
            "fix": "Refine rhythm and accuracy",
            "drills": [
                "Technical sparring",
                "Counter timing drill",
                "Fast jab + reset"
            ]
        }


    return {
        "offense": int(offense),
        "defense": int(defense),
        "output": int(output),
        "overall": int(overall),
        "coach": coach   # 🔥 REQUIRED FIX
    }
# -------------------------
# ROUTES
# -------------------------
@app.route("/", methods=["GET","POST"])
def login():
    users = load_users()

    if request.method == "POST":
        email = request.form.get("email","").strip().lower()

        if not email:
            return redirect("/")

        # create account if it doesn't exist
        if email not in users:
            users[email] = {
                "paid": False,
                "xp": 0,
                "streak": 0,
                "last_active": ""
            }
            save_users(users)

        session["user"] = email
        return redirect("/dashboard")

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    username = session["user"]
    users = load_users()

    if not users.get(username, {}).get("paid", False):
        return redirect("/paywall")

    data = load_data()
    sessions = data.get(username, [])
    latest = sessions[0] if sessions else None

    try:
        with open("data/drills.json") as f:
            drills = json.load(f)
    except:
        drills = []

    daily_plan = get_daily_plan(username)

    user = users.get(username, {})
    completed_today = user.get("last_completed") == str(date.today())

    return render_template("dashboard.html",
        sessions=sessions,
        latest=latest,
        drills=drills,
        daily_plan=daily_plan,
        user=user,
        completed_today=completed_today
    )

@app.route("/paywall")
def paywall():
    return render_template("paywall.html")

@app.route("/complete-session", methods=["POST"])
def complete_session():
    if "user" not in session:
        return jsonify({"error": "not logged in"})

    username = session["user"]

    update_progress(username, completed=True)

    return jsonify({"success": True})

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():

    email = session.get("user")

    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=email,
        line_items=[{
            "price": "price_1TbUpDLzWytRkK8smwIZzjNF",
            "quantity": 1,
        }],
        success_url="http://127.0.0.1:5000/success",
        cancel_url="http://127.0.0.1:5000/paywall",
    )

    return redirect(checkout_session.url)


@app.route("/success")
def success():
    email = session.get("user")

    if email:
        users = load_users()
        if email in users:
            users[email]["paid"] = True
            save_users(users)

    return redirect("/dashboard")

@app.route("/coach-reply", methods=["POST"])
def coach_reply():
    msg = request.json.get("message", "").lower()

    responses = {
        "offense": {
            "title": "Offense Breakdown",
            "mistake": "You are predictable with single-paced attacks.",
            "why": "Opponents can time counters when rhythm never changes.",
            "fix": "Mix short bursts (2–4 punches) with resets.",
            "drill": "3x rounds: 1–2–3 combos + step-out after each.",
            "cue": "Break rhythm, then exit"
        },
        "defense": {
            "title": "Defense Breakdown",
            "mistake": "You stay in range after punching or drop guard.",
            "why": "Most counters land right after your attack.",
            "fix": "Always return to guard and exit at an angle.",
            "drill": "Shadowboxing: every combo ends with slip or pivot.",
            "cue": "Hit → move → reset"
        },
        "default": {
            "title": "Fundamentals",
            "mistake": "Inconsistent structure.",
            "why": "Basics break under pressure.",
            "fix": "Slow down and rebuild clean form.",
            "drill": "3 shadow rounds at 50% speed.",
            "cue": "Clean first, fast later"
        }
    }

    r = responses.get(msg, responses["default"])

    return jsonify(r)

@app.route("/today-session")
def today_session():

    if "user" not in session:
        return redirect("/")

    # generate daily drills
    daily_plan = get_daily_plan(session["user"])

    # only 2 drills max
    daily_plan = daily_plan[:2]

    return render_template(
        "today_session.html",
        drills=daily_plan
    )

@app.route("/start-drill", methods=["GET", "POST"])
def start_drill():
    if "user" not in session:
        return redirect("/")

    with open("data/drills.json") as f:
        drills = json.load(f)

    return render_template("today_session.html", drills=drills)

@app.route("/upload", methods=["POST"])
def upload():
    if "user" not in session:
        return redirect("/")

    file = request.files["video"]
    filepath = os.path.join(UPLOAD_FOLDER, "video.mp4")
    file.save(filepath)

    try:
        result = analyze_fight(filepath)
    except Exception as e:
        return f"Analysis failed: {str(e)}"

    data = load_data()
    user = session["user"]

    history = data.get(user, [])
    history.insert(0, {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "result": result
    })

    data[user] = history[:20]
    save_data(data)

    return render_template("result.html", session=history[0])

@app.route("/weekly-plan")
def weekly_plan():
    if "user" not in session:
        return redirect("/")

    import datetime
    import json

    with open("data/weekly_plan.json") as f:
        plan = json.load(f)

    day = datetime.datetime.now().strftime("%A").lower()
    today_focus = plan.get(day, [])

    return render_template(
        "weekly_plan.html",
        day=day,
        focus=today_focus
    )

@app.route("/training-logs")
def training_logs():
    if "user" not in session:
        return redirect("/")

    username = session["user"]

    # LOAD USERS (for streak + xp)
    users = load_users()
    user = users.get(username, {})

    # LOAD LOGS
    try:
        with open("data/training_logs.json") as f:
            logs = json.load(f)
    except:
        logs = []

    # LOAD DRILLS
    try:
        with open("data/drills.json") as f:
            drills = json.load(f)
    except:
        drills = []

    import random

    # 🔥 RANDOM 5 DRILLS
    safe_drills = drills[:]
    random.shuffle(safe_drills)
    selected_drills = safe_drills[:2]

    total_sessions = len(logs)



    # WEEKLY SESSIONS
    weekly_sessions = user.get("streak", 0)
        
    # SAFE INTENSITY CALC
    avg_intensity = (
        sum(int(l.get("intensity", 0)) for l in logs) / total_sessions
        if total_sessions else 0
    )

    # TYPES COUNT
    types = {}
    for l in logs:
        t = l.get("type", "unknown")
        types[t] = types.get(t, 0) + 1

    return render_template(
        "training_logs.html",
        logs=logs,
        drills=selected_drills,   # ✅ FIXED
        total_sessions=total_sessions,
        avg_intensity=round(avg_intensity, 1),
        types=types,
        user=user,
        weekly_sessions=weekly_sessions,
    )

@app.route("/coach-chat")
def coach_chat():
    return render_template("coach_chat.html")

@app.route("/drills")
def drills():
    with open("data/drills.json") as f:
        drills = json.load(f)
    return render_template("drills.html", drills=drills)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
