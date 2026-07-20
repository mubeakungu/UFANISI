from flask import Flask, redirect, url_for, render_template
from flask_login import current_user
from config import Config
from extensions import db, login_manager
from models import User
from flask import current_app


def _to_whatsapp_format(phone: str) -> str:
    """Convert a local Kenyan number (07... / 01...) to wa.me format (2547.../2541...)."""
    if not phone:
        return ""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("0"):
        return "254" + digits[1:]
    if digits.startswith("254"):
        return digits
    return digits


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.member import member_bp
    from routes.mpesa import mpesa_bp
    from routes.assistant import assistant_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(member_bp)
    app.register_blueprint(mpesa_bp)
    app.register_blueprint(assistant_bp)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("admin.dashboard" if current_user.is_admin else "member.dashboard"))
        return render_template("index.html")

    @app.context_processor
    def inject_globals():
        return {
            "sacco_name": app.config["SACCO_NAME"],
            "whatsapp_number": _to_whatsapp_format(app.config["ADMIN_PHONE"]),
        }

    with app.app_context():
        db.create_all()
        _ensure_default_admin(app)

    _register_cli_commands(app)
    return app


def _ensure_default_admin(app):
    """Create a default admin account on first run if none exists."""
    if User.query.filter_by(role="admin").first():
        return
    admin = User(
        member_number="UFS-ADMIN",
        username=app.config["ADMIN_USERNAME"],
        full_name="Sacco Administrator",
        phone_number=app.config["ADMIN_PHONE"],
        role="admin",
    )
    admin.set_password(app.config["ADMIN_PASSWORD"])
    db.session.add(admin)
    db.session.commit()
    print(
        f"Created default admin -> username: {app.config['ADMIN_USERNAME']} / "
        f"password: {app.config['ADMIN_PASSWORD']} (CHANGE THIS via .env or after first login)"
    )


def _register_cli_commands(app):
    @app.cli.command("accrue-interest")
    def accrue_interest_command():
        """Run the weekly interest accrual job. Schedule this with cron, e.g.:
        0 6 * * MON cd /path/to/app && /path/to/venv/bin/flask accrue-interest
        """
        from interest import accrue_weekly_interest
        summary = accrue_weekly_interest(app)
        print(
            f"Interest accrual complete: {summary['accounts_credited']} accounts credited, "
            f"{summary['accounts_skipped_already_run']} already run this week, "
            f"total KES {summary['total_amount_credited']:,.2f} ({summary['mode']} mode)."
        )


if __name__ == "__main__":
    application = create_app()
    application.run(debug=True, port=5000)
