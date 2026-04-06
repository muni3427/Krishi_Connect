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
from app.models import DealerProfile, User, CropPool, PoolMember

farmer_bp = Blueprint("farmer", __name__, url_prefix="/farmer")

@farmer_bp.route("/pools")
@login_required
def view_pools():
    profile = FarmerProfile.query.filter_by(farmer_id=current_user.id).first()
    if not profile or not profile.crop_type:
        flash("Please set your Crop Type in profile to view local pools.", "warning")
        return redirect(url_for('farmer.dashboard'))

    # Fetch active pools in user's state for the same crop
    active_pools = CropPool.query.filter(
        CropPool.crop_type.ilike(f"%{profile.crop_type}%"),
        CropPool.state.ilike(f"%{profile.state}%"),
        CropPool.is_active == True
    ).order_by(CropPool.created_at.desc()).all()

    # Calculate total current quantity for each pool from PoolMember records
    pools_data = []
    for pool in active_pools:
        total_collected = sum(m.contributed_qty for m in pool.members)
        is_member = any(m.farmer_id == current_user.id for m in pool.members)
        pools_data.append({
            "pool": pool,
            "total_collected": total_collected,
            "is_member": is_member,
            "member_count": len(pool.members),
            "progress_percent": min(100, int((total_collected / pool.target_quantity) * 100)) if pool.target_quantity else 0
        })

    return render_template("farmer/pools.html", profile=profile, pools=pools_data)

@farmer_bp.route("/pools/create", methods=["POST"])
@login_required
def create_pool():
    profile = FarmerProfile.query.filter_by(farmer_id=current_user.id).first_or_404()
    
    target_qty = float(request.form.get("target_quantity", 0))
    min_price = float(request.form.get("min_price", 0))
    initial_qty = float(request.form.get("initial_quantity", 0))

    if initial_qty <= 0 or target_qty <= 0:
        flash("Quantities must be greater than zero.", "danger")
        return redirect(url_for('farmer.view_pools'))
        
    if initial_qty > target_qty:
        flash("Initial contribution cannot exceed target amount.", "danger")
        return redirect(url_for('farmer.view_pools'))

    # Create new Pool
    new_pool = CropPool(
        crop_type=profile.crop_type,
        state=profile.state,
        city=profile.city,
        target_quantity=target_qty,
        min_price=min_price
    )
    db.session.add(new_pool)
    db.session.flush() # get id

    # Add creator as first member
    member = PoolMember(
        pool_id=new_pool.id,
        farmer_id=current_user.id,
        contributed_qty=initial_qty
    )
    db.session.add(member)
    db.session.commit()

    flash(f"New pool for {profile.crop_type} created successfully!", "success")
    return redirect(url_for('farmer.view_pools'))

@farmer_bp.route("/pools/join", methods=["POST"])
@login_required
def join_pool():
    pool_id = request.form.get("pool_id")
    contributed_qty = float(request.form.get("contributed_qty", 0))

    if not pool_id or contributed_qty <= 0:
        flash("Invalid quantity to join pool.", "danger")
        return redirect(url_for('farmer.view_pools'))

    pool = CropPool.query.get_or_404(pool_id)
    
    # Check if user already in pool
    existing = PoolMember.query.filter_by(pool_id=pool.id, farmer_id=current_user.id).first()
    if existing:
        flash("You are already part of this pool.", "info")
        return redirect(url_for('farmer.view_pools'))

    member = PoolMember(
        pool_id=pool.id,
        farmer_id=current_user.id,
        contributed_qty=contributed_qty
    )
    db.session.add(member)
    db.session.commit()

    flash("Successfully joined the crop pool!", "success")
    return redirect(url_for('farmer.view_pools'))



@farmer_bp.route("/dashboard")
@login_required
def dashboard():
    profile = FarmerProfile.query.filter_by(farmer_id=current_user.id).first()
    prices = []
    dealers = []
    if profile and profile.crop_type:
        prices = get_prices_for_commodity(profile.crop_type, state=profile.state, district=profile.city)
        
        # Fetch dealers looking for this crop, prioritizing nearby dealers
        from sqlalchemy import case
        dealer_profiles = DealerProfile.query.filter(DealerProfile.crop_type.ilike(f"%{profile.crop_type}%"))\
            .order_by(case((DealerProfile.address.ilike(f"%{profile.city}%"), 1), else_=0).desc())\
            .limit(10).all()
        for dp in dealer_profiles:
            user = User.query.get(dp.dealer_id)
            if user:
                dealers.append({
                    "name": user.name,
                    "phone": user.phone,
                    "city": dp.address,
                    "quantity": dp.quantity,
                    "price_per_quintal": dp.price_per_quintal,
                    "rating": dp.rating,
                    "payment_terms": dp.payment_terms
                })

    return render_template("farmer/dashboard.html", profile=profile, prices=prices, dealers=dealers)


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
        profile.language_pref = request.form.get("language_pref", profile.language_pref or "hi-IN")
        profile.has_transport = request.form.get("has_transport") == "on"
        db.session.commit()
        flash("Profile updated!", "success")
        return redirect(url_for("farmer.dashboard"))
    return render_template("farmer/edit_profile.html", profile=profile)


@farmer_bp.route("/prices/<crop>")
@login_required
def crop_prices(crop):
    profile = FarmerProfile.query.filter_by(farmer_id=current_user.id).first()
    rows = get_prices_for_commodity(crop, state=profile.state if profile else None, district=profile.city if profile else None)
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
        lang = profile.language_pref if profile.language_pref else profile.state
        crop_name = speech_to_text(audio_bytes, lang)
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

    prices = get_prices_for_commodity(crop, state=profile.state, district=profile.city)

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
        lang = profile.language_pref if profile.language_pref else profile.state
        audio_bytes = text_to_speech(text, lang)
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
    prices = get_prices_for_commodity(crop, state=profile.state, district=profile.city)
    if not prices:
        return jsonify({"error": f"No mandi data found for {crop}"}), 404

    top = prices[0]
    lang_code = profile.language_pref if profile.language_pref else profile.state
    language = get_language(lang_code)

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
        diff = ((offered_price - top.modal_price) / top.modal_price) * 100
        if diff >= -5.0:
            analysis_text = f"This is a FAIR deal ({abs(diff):.1f}% {'above' if diff>=0 else 'below'} the ₹{top.modal_price} market rate). You should accept this offer."
        else:
            analysis_text = f"This deal is POOR ({abs(diff):.1f}% below the ₹{top.modal_price} market rate). You should negotiate or reject this offer."

    # Convert analysis to audio
    try:
        lang_code = profile.language_pref if profile.language_pref else profile.state
        audio_bytes = text_to_speech(analysis_text, lang_code)
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
    from sqlalchemy import case
    dealer_profiles = (
        DealerProfile.query
        .filter(DealerProfile.crop_type.ilike(f"%{crop}%"))
        .order_by(case((DealerProfile.address.ilike(f"%{profile.city}%"), 1), else_=0).desc())
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
            "phone": user.phone if user else "N/A",
            "price_per_quintal": dp.price_per_quintal,
            "city": dp.address,
            "rating": dp.rating,
            "payment_terms": dp.payment_terms,
        })

    # Get mandi modal price
    prices = get_prices_for_commodity(crop, state=profile.state, district=profile.city)
    modal_price = prices[0].modal_price if prices else 0

    lang_code = profile.language_pref if profile.language_pref else profile.state
    language = get_language(lang_code)

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
        ranking_text = "AI Services are currently busy. Top Local Dealers Found:\n"
        for i, d in enumerate(dealers[:3]):
            ranking_text += f"{i+1}. {d['name']}, Phone: {d['phone']}, Address: {d['city']}\n"

    # Convert to audio
    try:
        lang_code = profile.language_pref if profile.language_pref else profile.state
        audio_bytes = text_to_speech(ranking_text, lang_code)
        audio_b64 = __import__("base64").b64encode(audio_bytes).decode("utf-8")
    except Exception as e:
        audio_b64 = None

    return jsonify({
        "ranking": ranking_text,
        "audio_b64": audio_b64,
        "dealers_analysed": len(dealers),
        "modal_price": modal_price,
    })