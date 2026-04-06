from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.models import FarmerProfile, DealerProfile, User
from app.services.sarvam_voice import rank_farmers
from app.services.market_prices import get_prices_for_commodity
from flask import jsonify, request, render_template



dealer_bp = Blueprint("dealer", __name__, url_prefix="/dealer")


@dealer_bp.route("/dashboard")
@login_required
def dashboard():
    profile = DealerProfile.query.filter_by(dealer_id=current_user.id).first()
    # Show farmers selling the same crop type as dealer's interest
    farmers = []
    if profile and profile.crop_type:
        f_list = (
            FarmerProfile.query
            .filter(FarmerProfile.crop_type.ilike(f"%{profile.crop_type}%"))
            .all()
        )
        for f in f_list:
            u = User.query.get(f.farmer_id)
            farmers.append({
                "farmer_id": f.farmer_id,
                "name": u.name if u else "Unknown",
                "phone": u.phone if u else "Unknown",
                "village": f.village,
                "city": f.city,
                "state": f.state,
                "crop_type": f.crop_type,
                "quantity": f.quantity,
                "price_per_quintal": f.price_per_quintal,
                "quality": f.quality,
                "has_transport": f.has_transport,
            })
    return render_template("dealer/dashboard.html", profile=profile, farmers=farmers)


@dealer_bp.route("/search")
@login_required
def search_farmers():
    """
    Query params: crop, district, max_price
    Returns JSON list of matching farmer profiles.
    """
    crop = request.args.get("crop", "")
    district = request.args.get("district", "")
    max_price = request.args.get("max_price", type=float)

    query = FarmerProfile.query
    if crop:
        query = query.filter(FarmerProfile.crop_type.ilike(f"%{crop}%"))
    if district:
        query = query.filter(FarmerProfile.city.ilike(f"%{district}%"))
    if max_price:
        query = query.filter(FarmerProfile.price_per_quintal <= max_price)

    results = query.limit(50).all()
    farmers = []

    for f in results:
        u = User.query.get(f.farmer_id)
        farmers.append({
            "farmer_id": f.farmer_id,
            "name": u.name if u else "Unknown",
            "phone": u.phone if u else "Unknown",
            "village": f.village,
            "city": f.city,
            "state": f.state,
            "crop_type": f.crop_type,
            "quantity": f.quantity,
            "price_per_quintal": f.price_per_quintal,
            "quality": f.quality,
            "has_transport": f.has_transport,
        })

    return jsonify(farmers)


@dealer_bp.route("/prices/<crop>")
@login_required
def mandi_prices(crop):
    """Dealer can also check mandi prices before bidding."""
    rows = get_prices_for_commodity(crop)
    return jsonify([
        {
            "market": r.market,
            "district": r.district,
            "modal_price": r.modal_price,
            "arrival_date": r.arrival_date,
        }
        for r in rows
    ])

@dealer_bp.route("/analyse/farmers", methods=["POST"])
@login_required
def analyse_farmers():
    """
    Dealer taps Analyse button.
    Sarvam LLM ranks top 3 farmers for the dealer's crop.
    Returns text ranking only (no audio on dealer side).
    """
    profile = DealerProfile.query.filter_by(dealer_id=current_user.id).first_or_404()
    crop = profile.crop_type

    if not crop:
        return jsonify({"error": "Update your crop type in profile first"}), 400

    # Fetch matching farmers from DB
    farmer_profiles = (
        FarmerProfile.query
        .filter(FarmerProfile.crop_type.ilike(f"%{crop}%"))
        .limit(10)
        .all()
    )

    if not farmer_profiles:
        return jsonify({"error": f"No farmers found selling {crop}"}), 404

    # Build farmer list for LLM
    farmers = []
    for fp in farmer_profiles:
        user = User.query.get(fp.farmer_id)
        farmers.append({
            "name": user.name if user else "Unknown",
            "phone": user.phone if user else "Unknown",
            "price_per_quintal": fp.price_per_quintal,
            "city": fp.city,
            "quantity": fp.quantity,
            "quality": fp.quality,
            "has_transport": fp.has_transport,
        })

    # Get mandi modal price for context
    prices = get_prices_for_commodity(crop)
    modal_price = prices[0].modal_price if prices else 0

    # Get LLM ranking
    try:
        ranking_text = rank_farmers(
            crop=crop,
            dealer_city=profile.address,
            farmers=farmers,
            modal_price=modal_price,
        )
    except Exception as e:
        ranking_text = "AI Services are currently busy. Top Local Farmers Found:\n"
        for i, f in enumerate(farmers[:3]):
            ranking_text += f"{i+1}. {f['name']} — Phone: {f['phone']}, Price: ₹{f['price_per_quintal']}/q\n"

    return jsonify({
        "ranking": ranking_text,
        "farmers_analysed": len(farmers),
        "modal_price": modal_price,
        "crop": crop,
    })