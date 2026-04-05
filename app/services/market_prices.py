import requests
from datetime import date, datetime
from app import db
from app.models import MarketPrice
from flask import current_app

def fetch_and_store_prices(app=None):
    """Fetch today's mandi prices from Agmarknet and store in DB."""
    from flask import current_app as _app
    ctx = None
    if app:
        ctx = app.app_context()
        ctx.push()
    api_key = _app.config.get("DATA_GOV_API_KEY")
    target_states = _app.config.get("TARGET_STATES", [
        "Karnataka", "Tamil Nadu", "Andhra Pradesh", "Telangana", "Kerala"
    ])
    if ctx:
        ctx.pop()

    url = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"

    for state in target_states:
        params = {
            "api-key": api_key,
            "format": "json",
            "filters[state]": state,
            "limit": 500,
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            records = resp.json().get("records", [])
        except Exception as e:
            current_app.logger.error(f"Agmarknet fetch failed for {state}: {e}")
            continue

        for r in records:
            # Skip if already stored today
            arrival = r.get("arrival_date", "")
            existing = MarketPrice.query.filter_by(
                commodity=r.get("commodity"),
                market=r.get("market"),
                district=r.get("district"),
                arrival_date=arrival,
            ).first()
            if existing:
                continue

            mp = MarketPrice(
                commodity=r.get("commodity"),
                market=r.get("market"),
                district=r.get("district"),
                state=r.get("state"),
                min_price=float(r.get("min_price", 0) or 0),
                max_price=float(r.get("max_price", 0) or 0),
                modal_price=float(r.get("modal_price", 0) or 0),
                arrival_date=arrival,
                fetched_at=datetime.utcnow(),
            )
            db.session.add(mp)

    db.session.commit()


def get_prices_for_commodity(commodity_name: str):
    """Return latest MarketPrice rows for a commodity (case-insensitive)."""
    return (
        MarketPrice.query
        .filter(MarketPrice.commodity.ilike(f"%{commodity_name}%"))
        .order_by(MarketPrice.fetched_at.desc())
        .limit(50)
        .all()
    )


def get_today_prices():
    """Return all prices fetched today."""
    today = date.today().isoformat()
    return (
        MarketPrice.query
        .filter(MarketPrice.arrival_date == today)
        .order_by(MarketPrice.commodity)
        .all()
    )