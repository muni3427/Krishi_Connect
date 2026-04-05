from flask import Blueprint, jsonify, request
from flask_login import login_required
from app.models import MarketPrice
from app.services.market_prices import (
    fetch_and_store_prices,
    get_prices_for_commodity,
    get_today_prices,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/prices/today")
@login_required
def prices_today():
    rows = get_today_prices()
    return jsonify([_mp_to_dict(r) for r in rows])


@api_bp.route("/prices/commodity/<crop>")
@login_required
def prices_by_commodity(crop):
    rows = get_prices_for_commodity(crop)
    return jsonify([_mp_to_dict(r) for r in rows])


@api_bp.route("/prices/refresh", methods=["POST"])
@login_required
def refresh_prices():
    """Manually trigger a price fetch. Useful for testing before scheduler is set up."""
    try:
        fetch_and_store_prices()
        return jsonify({"status": "ok", "message": "Prices refreshed"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route("/prices/districts")
@login_required
def districts():
    """Return distinct districts that have price data — useful for frontend dropdowns."""
    rows = MarketPrice.query.with_entities(MarketPrice.district).distinct().all()
    return jsonify([r.district for r in rows if r.district])


def _mp_to_dict(mp: MarketPrice):
    return {
        "id": mp.id,
        "commodity": mp.commodity,
        "market": mp.market,
        "district": mp.district,
        "state": mp.state,
        "min_price": mp.min_price,
        "max_price": mp.max_price,
        "modal_price": mp.modal_price,
        "arrival_date": mp.arrival_date,
    }