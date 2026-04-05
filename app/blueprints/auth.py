from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import User, FarmerProfile, DealerProfile

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# ─── User Loader (Flask-Login needs this) ───────────────────────────────────
from app import login_manager

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─── Root redirect ───────────────────────────────────────────────────────────
from flask import Blueprint as _BP
root_bp = _BP("root", __name__)

@root_bp.route("/")
def index():
    return redirect(url_for("auth.login_page"))

@root_bp.route("/test")
def test():
    return {"status": "ok", "message": "AgriConnect is running"}


# ─── Login ───────────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET"])
def login_page():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user.role)
    return render_template("auth/login.html")


@auth_bp.route("/login", methods=["POST"])
def login():
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "").strip()

    # Normalize phone — strip spaces and leading country code variations
    phone = phone.replace(" ", "").replace("+91", "").lstrip("0")

    user = User.query.filter_by(phone=phone).first()

    if not user or not check_password_hash(user.password, password):
        flash("Invalid phone number or password.", "error")
        return redirect(url_for("auth.login_page"))

    login_user(user)
    return _redirect_by_role(user.role)


# ─── Register ────────────────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["POST"])
def register():
    role = request.form.get("role", "farmer").strip()
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    phone = request.form.get("phone", "").strip()
    district = request.form.get("district", "").strip()
    language_pref = request.form.get("language_pref", "en").strip()
    password = request.form.get("password", "").strip()

    # Normalize phone
    phone = phone.replace(" ", "").replace("+91", "").lstrip("0")

    # Validate
    if not all([first_name, phone, password, role]):
        flash("Please fill in all required fields.", "error")
        return redirect(url_for("auth.login_page") + "#register")

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return redirect(url_for("auth.login_page") + "#register")

    if User.query.filter_by(phone=phone).first():
        flash("This phone number is already registered. Please login.", "error")
        return redirect(url_for("auth.login_page"))

    if role not in ("farmer", "dealer"):
        flash("Invalid role selected.", "error")
        return redirect(url_for("auth.login_page") + "#register")

    # Build full name
    name = f"{first_name} {last_name}".strip()

    # Create user
    user = User(
        name=name,
        phone=phone,
        role=role,
        password=generate_password_hash(password),
        is_verified=False,
    )
    db.session.add(user)
    db.session.flush()  # get user.id before committing

    # Create profile
    if role == "farmer":
        profile = FarmerProfile(
            farmer_id=user.id,
            village="",
            city=district,       # district maps to city for now
            state=_district_to_state(district),
            crop_type="",
            quantity=0.0,
            price_per_quintal=0.0,
            quality="",
            has_transport=False,
        )
        db.session.add(profile)

    elif role == "dealer":
        profile = DealerProfile(
            dealer_id=user.id,
            type="general",
            address=district,
            crop_type="",
            quantity=0.0,
            price_per_quintal=0.0,
            rating=0.0,
            years_in_business=0,
            payment_terms="cash",
            quality_requirements="",
        )
        db.session.add(profile)

    db.session.commit()

    flash("Account created! Please login.", "success")
    return redirect(url_for("auth.login_page"))


# ─── Logout ──────────────────────────────────────────────────────────────────
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login_page"))


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _redirect_by_role(role):
    if role == "farmer":
        return redirect(url_for("farmer.dashboard"))
    elif role == "dealer":
        return redirect(url_for("dealer.dashboard"))
    elif role == "admin":
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("auth.login_page"))


def _district_to_state(district: str) -> str:
    """
    Best-guess state from district name.
    Farmers can update their full profile after login.
    """
    karnataka = [
        "bengaluru", "bangalore", "mysuru", "mysore", "kolar", "hassan",
        "tumkur", "tumakuru", "mandya", "raichur", "ballari", "bellary",
        "kalaburagi", "gulbarga", "dharwad", "belagavi", "belgaum",
        "shivamogga", "shimoga", "udupi", "mangaluru", "mangalore",
        "vijayapura", "bijapur", "bagalkot", "gadag", "haveri", "koppal",
        "chitradurga", "davanagere", "chikkamagaluru", "kodagu", "coorg",
        "chikkaballapur", "ramanagara", "chamarajanagar", "yadgir", "bidar"
    ]
    tamil_nadu = [
        "chennai", "coimbatore", "madurai", "salem", "tiruchirappalli",
        "trichy", "tirunelveli", "vellore", "erode", "tiruppur", "theni",
        "dindigul", "thanjavur", "kanchipuram", "namakkal", "nilgiris",
        "ooty", "pudukkottai", "ramanathapuram", "sivaganga", "virudhunagar",
        "thoothukudi", "tuticorin", "nagapattinam", "cuddalore", "villupuram"
    ]
    andhra = [
        "visakhapatnam", "vizag", "vijayawada", "guntur", "nellore",
        "kurnool", "kadapa", "tirupati", "anantapur", "kakinada",
        "rajahmundry", "eluru", "ongole", "srikakulam", "vizianagaram",
        "chittoor", "krishna", "west godavari", "east godavari"
    ]
    telangana = [
        "hyderabad", "warangal", "nizamabad", "karimnagar", "khammam",
        "mahbubnagar", "nalgonda", "adilabad", "rangareddy", "medak",
        "sangareddy", "siddipet", "suryapet", "yadadri", "jayashankar",
        "bhadradri", "mulugu", "narayanpet", "wanaparthy", "nagarkurnool"
    ]
    kerala = [
        "thiruvananthapuram", "trivandrum", "kochi", "cochin", "kozhikode",
        "calicut", "thrissur", "kollam", "palakkad", "alappuzha", "alleppey",
        "malappuram", "kannur", "kasaragod", "idukki", "wayanad",
        "ernakulam", "pathanamthitta", "kottayam"
    ]

    d = district.lower().strip()
    if any(k in d for k in karnataka):
        return "Karnataka"
    if any(t in d for t in tamil_nadu):
        return "Tamil Nadu"
    if any(a in d for a in andhra):
        return "Andhra Pradesh"
    if any(t in d for t in telangana):
        return "Telangana"
    if any(k in d for k in kerala):
        return "Kerala"
    return "Karnataka"  # default fallback

from flask import Blueprint, redirect, url_for

root_bp = Blueprint('root', __name__)

@root_bp.route('/')
def index():
    return redirect(url_for('auth.login'))