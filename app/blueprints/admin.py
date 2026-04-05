from flask import Blueprint, render_template
from flask_login import login_required, current_user

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/admin/dashboard")
@login_required
def dashboard():
    return render_template("admin/dashboard.html", user=current_user)