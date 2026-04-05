from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.models import FarmerProfile, DealerProfile, User
from app.services.market_prices import get_prices_for_commodity

dealer_bp = Blueprint("dealer", __name__, url_prefix="/dealer")


@dealer_bp.route("/dashboard")
@login_required
def dashboard():
    profile = DealerProfile.query.filter_by(dealer_id=current_user.id).first()
    # Show farmers selling the same crop type as dealer's interest
    farmers = []
    if profile and profile.crop_type:
        farmers = (
            FarmerProfile.query
            .filter(FarmerProfile.crop_type.ilike(f"%{profile.crop_type}%"))
            .all()
        )
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

    return jsonify([
        {
            "farmer_id": f.farmer_id,
            "village": f.village,
            "city": f.city,
            "state": f.state,
            "crop_type": f.crop_type,
            "quantity": f.quantity,
            "price_per_quintal": f.price_per_quintal,
            "quality": f.quality,
            "has_transport": f.has_transport,
        }
        for f in results
    ])


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