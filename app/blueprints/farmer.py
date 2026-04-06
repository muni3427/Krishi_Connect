from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import FarmerProfile, MarketPrice
from app.services.market_prices import get_prices_for_commodity
from flask import send_file
import io
from app.services.sarvam_voice import speech_to_text, text_to_speech
from app.services.market_prices import get_prices_for_commodity
from app.services.sarvam_voice import (
    speech_to_text,
    text_to_speech,
    get_language,
    analyse_price_fairness,
    rank_dealers,
)
from app.models import DealerProfile, User

farmer_bp = Blueprint("farmer", __name__, url_prefix="/farmer")


@farmer_bp.route("/dashboard")
@login_required
def dashboard():
    profile = FarmerProfile.query.filter_by(farmer_id=current_user.id).first()
    # Pull mandi prices for farmer's crop type
    prices = []
    if profile and profile.crop_type:
        prices = get_prices_for_commodity(profile.crop_type)
    return render_template("farmer/dashboard.html", profile=profile, prices=prices)


@farmer_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    profile = FarmerProfile.query.filter_by(farmer_id=current_user.id).first_or_404()
    if request.method == "POST":
        profile.crop_type = request.form.get("crop_type", profile.crop_type)
        profile.quantity = float(request.form.get("quantity", profile.quantity) or 0)
        profile.price_per_quintal = float(
            request.form.get("price_per_quintal", profile.price_per_quintal) or 0
        )
        profile.quality = request.form.get("quality", profile.quality)
        profile.has_transport = request.form.get("has_transport") == "on"
        db.session.commit()
        flash("Profile updated!", "success")
        return redirect(url_for("farmer.dashboard"))
    return render_template("farmer/edit_profile.html", profile=profile)


@farmer_bp.route("/prices/<crop>")
@login_required
def crop_prices(crop):
    """AJAX endpoint — returns JSON mandi prices for a crop."""
    rows = get_prices_for_commodity(crop)
    return jsonify([
        {
            "market": r.market,
            "district": r.district,
            "modal_price": r.modal_price,
            "min_price": r.min_price,
            "max_price": r.max_price,
            "arrival_date": r.arrival_date,
        }
        for r in rows
    ])

@farmer_bp.route("/voice/stt", methods=["POST"])
@login_required
def voice_stt():
    """Receive audio from browser mic, return crop name as text."""
    profile = FarmerProfile.query.filter_by(farmer_id=current_user.id).first_or_404()
    audio_bytes = request.files["audio"].read()

    try:
        crop_name = speech_to_text(audio_bytes, profile.state)
        return jsonify({"crop": crop_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@farmer_bp.route("/voice/prices", methods=["POST"])
@login_required
def voice_prices():
    """
    Receive crop name as JSON, look up mandi price,
    return audio of price read aloud in farmer's language.
    """
    profile = FarmerProfile.query.filter_by(farmer_id=current_user.id).first_or_404()
    crop = request.json.get("crop", "").strip()

    if not crop:
        return jsonify({"error": "No crop provided"}), 400

    prices = get_prices_for_commodity(crop)

    if not prices:
        text = f"{crop} ke liye aaj koi mandi price nahi mili."
    else:
        top = prices[0]
        text = (
            f"{crop} ka aaj ka mandi price: "
            f"minimum {int(top.min_price)} rupaye, "
            f"maximum {int(top.max_price)} rupaye, "
            f"modal price {int(top.modal_price)} rupaye per quintal. "
            f"Market: {top.market}, {top.district}."
        )
        # Sarvam will translate+speak this in farmer's language automatically

    try:
        audio_bytes = text_to_speech(text, profile.state)
        return send_file(
            io.BytesIO(audio_bytes),
            mimetype="audio/wav",
            as_attachment=False,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@farmer_bp.route("/analyse/price", methods=["POST"])
@login_required
def analyse_price():
    """
    Farmer taps Analyse button.
    Compares dealer's offered price vs mandi modal price.
    Returns text analysis + audio.
    """
    profile = FarmerProfile.query.filter_by(farmer_id=current_user.id).first_or_404()
    data = request.json

    offered_price = float(data.get("offered_price", 0))
    crop = data.get("crop") or profile.crop_type

    if not crop or not offered_price:
        return jsonify({"error": "Crop and offered price are required"}), 400

    # Get mandi prices
    prices = get_prices_for_commodity(crop)
    if not prices:
        return jsonify({"error": f"No mandi data found for {crop}"}), 404

    top = prices[0]
    language = get_language(profile.state)

    # Get LLM analysis text
    try:
        analysis_text = analyse_price_fairness(
            crop=crop,
            offered_price=offered_price,
            modal_price=top.modal_price,
            min_price=top.min_price,
            max_price=top.max_price,
            language=language,
        )
    except Exception as e:
        return jsonify({"error": f"Sarvam LLM failed: {str(e)}"}), 500

    # Convert analysis to audio
    try:
        audio_bytes = text_to_speech(analysis_text, profile.state)
        audio_b64 = __import__("base64").b64encode(audio_bytes).decode("utf-8")
    except Exception as e:
        audio_b64 = None  # text still works even if TTS fails

    return jsonify({
        "analysis": analysis_text,
        "audio_b64": audio_b64,          # frontend plays this
        "mandi_modal": top.modal_price,
        "mandi_min": top.min_price,
        "mandi_max": top.max_price,
        "market": top.market,
        "district": top.district,
    })


@farmer_bp.route("/analyse/dealers", methods=["POST"])
@login_required
def analyse_dealers():
    """
    Farmer taps Analyse button on dealer list.
    Sarvam LLM ranks top 3 dealers and explains why.
    Returns text ranking + audio.
    """
    profile = FarmerProfile.query.filter_by(farmer_id=current_user.id).first_or_404()
    crop = profile.crop_type

    if not crop:
        return jsonify({"error": "Update your crop type in profile first"}), 400

    # Fetch matching dealers from DB
    dealer_profiles = (
        DealerProfile.query
        .filter(DealerProfile.crop_type.ilike(f"%{crop}%"))
        .limit(10)
        .all()
    )

    if not dealer_profiles:
        return jsonify({"error": f"No dealers found for {crop}"}), 404

    # Build dealer list for LLM
    dealers = []
    for dp in dealer_profiles:
        user = User.query.get(dp.dealer_id)
        dealers.append({
            "name": user.name if user else "Unknown",
            "price_per_quintal": dp.price_per_quintal,
            "city": dp.address,
            "rating": dp.rating,
            "payment_terms": dp.payment_terms,
        })

    # Get mandi modal price
    prices = get_prices_for_commodity(crop)
    modal_price = prices[0].modal_price if prices else 0

    language = get_language(profile.state)

    # Get LLM ranking
    try:
        ranking_text = rank_dealers(
            crop=crop,
            farmer_city=profile.city,
            dealers=dealers,
            modal_price=modal_price,
            language=language,
        )
    except Exception as e:
        return jsonify({"error": f"Sarvam LLM failed: {str(e)}"}), 500

    # Convert to audio
    try:
        audio_bytes = text_to_speech(ranking_text, profile.state)
        audio_b64 = __import__("base64").b64encode(audio_bytes).decode("utf-8")
    except Exception as e:
        audio_b64 = None

    return jsonify({
        "ranking": ranking_text,
        "audio_b64": audio_b64,
        "dealers_analysed": len(dealers),
        "modal_price": modal_price,
    })