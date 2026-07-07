from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User, SavingsAccount

auth_bp = Blueprint("auth", __name__)


def _next_member_number():
    last = User.query.order_by(User.id.desc()).first()
    next_id = (last.id + 1) if last else 1
    return f"UFS{next_id:05d}"


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard" if current_user.is_admin else "member.dashboard"))

    if request.method == "POST":
        phone_or_member = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            (User.phone_number == phone_or_member)
            | (User.member_number == phone_or_member)
            | (User.username == phone_or_member)
        ).first()

        if user and user.check_password(password):
            login_user(user)
            flash(f"Welcome back, {user.full_name.split(' ')[0]}.", "success")
            return redirect(url_for("admin.dashboard" if user.is_admin else "member.dashboard"))

        flash("Invalid member number/phone or password.", "danger")

    return render_template("login.html")


@auth_bp.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard" if current_user.is_admin else "member.dashboard"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            (User.username == identifier)
            | (User.phone_number == identifier)
            | (User.member_number == identifier)
        ).first()

        if user and user.is_admin and user.check_password(password):
            login_user(user)
            flash(f"Welcome back, {user.full_name.split(' ')[0]}.", "success")
            return redirect(url_for("admin.dashboard"))

        flash("Invalid admin credentials.", "danger")

    return render_template("admin_login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("member.dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        national_id = request.form.get("national_id", "").strip()
        email = request.form.get("email", "").strip() or None
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        errors = []
        if not full_name or not phone_number or not password:
            errors.append("Full name, phone number, and password are required.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if User.query.filter_by(phone_number=phone_number).first():
            errors.append("An account with this phone number already exists.")
        if national_id and User.query.filter_by(national_id=national_id).first():
            errors.append("An account with this National ID already exists.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", form=request.form)

        user = User(
            member_number=_next_member_number(),
            full_name=full_name,
            phone_number=phone_number,
            national_id=national_id or None,
            email=email,
            role="member",
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()  # get user.id before creating account

        account = SavingsAccount(user_id=user.id, balance=0)
        db.session.add(account)
        db.session.commit()

        flash(f"Registration successful. Your member number is {user.member_number}. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html", form={})


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        user = User.query.filter(
            (User.phone_number == identifier)
            | (User.member_number == identifier)
            | (User.username == identifier)
            | (User.email == identifier)
        ).first()

        # Always show the same message whether or not the account exists,
        # so this endpoint can't be used to enumerate registered accounts.
        generic_message = (
            "If an account matches those details, we've sent password reset "
            "instructions to the email on file."
        )

        if user and user.email:
            token = user.generate_reset_token()
            db.session.commit()
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            import mailer
            mailer.send_reset_email(user.email, reset_url, user.full_name)
        elif user and not user.email:
            flash(
                "That account has no email on file, so we can't send a reset link. "
                "Please contact an administrator to reset your password directly.",
                "warning",
            )
            return redirect(url_for("auth.login"))

        flash(generic_message, "info")
        return redirect(url_for("auth.login"))

    return render_template("forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()

    if not user or not user.reset_token_is_valid(token):
        flash("This password reset link is invalid or has expired.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not password or password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("reset_password.html", token=token)

        user.set_password(password)
        user.clear_reset_token()
        db.session.commit()
        flash("Your password has been reset. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html", token=token)
