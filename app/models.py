from app import db
from flask_login import UserMixin
from datetime import date

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'farmer' or 'dealer'
    is_verified = db.Column(db.Boolean, default=False)
    password = db.Column(db.String(200), nullable=False)

class FarmerProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    farmer_id = db.Column(db.Integer)
    postal_address = db.Column(db.String(200))
    village = db.Column(db.String(100))
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    crop_type = db.Column(db.String(100))
    quantity = db.Column(db.Float)
    price_per_quintal = db.Column(db.Float)
    quality = db.Column(db.String(100))
    has_transport = db.Column(db.Boolean, default=False)

class DealerProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    dealer_id = db.Column(db.Integer)
    dealer_type = db.Column(db.String(100))
    address = db.Column(db.String(200))
    crop_type = db.Column(db.String(100))
    quantity = db.Column(db.Float)
    price_per_quintal = db.Column(db.Float)
    rating = db.Column(db.Float)
    years_in_business = db.Column(db.Integer)
    payment_terms = db.Column(db.String(100))
    quality_requirements = db.Column(db.String(100))

class MarketPrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    commodity = db.Column(db.String(100))
    market = db.Column(db.String(100))
    district = db.Column(db.String(100))
    state = db.Column(db.String(100))
    min_price = db.Column(db.Float)
    max_price = db.Column(db.Float)
    modal_price = db.Column(db.Float)
    arrival_date = db.Column(db.Date, default=date.today)
    fetched_at = db.Column(db.DateTime)