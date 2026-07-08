from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user

from extensions import db
from models import Transaction
import daraja

member_bp = Blueprint("member", __name__, url_prefix="/member")


@member_bp.before_request
@login_required
def restrict_to_members():
    # Admins can still view their own dashboard if they also have an account,
    # but this area is primarily for members.
    pass


@member_bp.route("/dashboard")
def dashboard():
    account = current_user.account
    recent_tx = account.transactions[:10] if account else []
    return render_template(
        "member/dashboard.html",
        account=account,
        transactions=recent_tx,
        min_deposit=current_app.config["MIN_DEPOSIT_AMOUNT"],
        interest_rate=current_app.config["INTEREST_RATE"],
        weekly_deposit_amount=current_app.config["WEEKLY_DEPOSIT_AMOUNT"],
        referral_min_count=current_app.config["REFERRAL_MIN_COUNT"],
        referral_min_deposit=current_app.config["REFERRAL_MIN_DEPOSIT"],
        referral_bonus_rate=current_app.config["REFERRAL_BONUS_RATE"],
    )


@member_bp.route("/transactions")
def transactions():
    account = current_user.account
    page = request.args.get("page", 1, type=int)

    if account:
        pagination = (
            Transaction.query.filter_by(account_id=account.id)
            .order_by(Transaction.created_at.desc())
            .paginate(page=page, per_page=20, error_out=False)
        )
    else:
        pagination = None

    return render_template("member/transactions.html", account=account, pagination=pagination)


@member_bp.route("/referrals")
def referrals():
    account = current_user.account

    # Older accounts created before the referral program existed may not have a code yet.
    if not current_user.referral_code:
        current_user.ensure_referral_code()
        db.session.commit()

    referred_users = current_user.referrals  # backref from User.referred_by
    referral_link = url_for("auth.register", ref=current_user.referral_code, _external=True)

    min_deposit = current_app.config["REFERRAL_MIN_DEPOSIT"]
    min_count = current_app.config["REFERRAL_MIN_COUNT"]
    bonus_rate = current_app.config["REFERRAL_BONUS_RATE"]

    qualifying_count = current_user.qualifying_referral_count
    paid_count = sum(1 for r in referred_users if r.referral_bonus_paid)
    slots_remaining = max(0, min_count - qualifying_count)

    return render_template(
        "member/referrals.html",
        account=account,
        referred_users=referred_users,
        referral_code=current_user.referral_code,
        referral_link=referral_link,
        min_deposit=min_deposit,
        min_count=min_count,
        bonus_rate=bonus_rate,
        qualifying_count=qualifying_count,
        paid_count=paid_count,
        slots_remaining=slots_remaining,
    )


@member_bp.route("/deposit", methods=["GET", "POST"])
def deposit():
    if request.method == "POST":
        amount = request.form.get("amount", "").strip()
        phone_number = request.form.get("phone_number", current_user.phone_number).strip()

        min_deposit = current_app.config["MIN_DEPOSIT_AMOUNT"]

        if not amount or not amount.isdigit() or int(amount) < min_deposit:
            flash(f"Minimum deposit is KES {min_deposit:,}.", "danger")
            return render_template("member/deposit.html", min_deposit=min_deposit)

        account = current_user.account
        tx = Transaction(
            account_id=account.id,
            tx_type="deposit",
            amount=int(amount),
            channel="mpesa",
            status="pending",
        )
        db.session.add(tx)
        db.session.commit()

        try:
            response = daraja.stk_push(
                phone_number=phone_number,
                amount=int(amount),
                account_reference=current_user.member_number,
                description="Sacco Savings Deposit",
            )
            tx.mpesa_checkout_request_id = response.get("CheckoutRequestID")
            db.session.commit()
            flash("STK push sent. Check your phone and enter your M-Pesa PIN to complete the deposit.", "success")
        except Exception as exc:
            tx.status = "failed"
            tx.notes = str(exc)
            db.session.commit()
            flash("Could not reach M-Pesa right now. Please try again shortly.", "danger")

        return redirect(url_for("member.dashboard"))

    return render_template("member/deposit.html", min_deposit=current_app.config["MIN_DEPOSIT_AMOUNT"])


@member_bp.route("/transaction-status/<int:tx_id>")
def transaction_status(tx_id):
    """Lightweight polling endpoint the deposit page can call to check if a payment cleared."""
    tx = Transaction.query.get_or_404(tx_id)
    if tx.account.user_id != current_user.id:
        return jsonify({"error": "not found"}), 404
    return jsonify({"status": tx.status, "receipt": tx.mpesa_receipt})


@member_bp.route("/withdraw-savings", methods=["GET", "POST"])
def withdraw_savings():
    """
    Request a withdrawal of principal savings. This does NOT pay out immediately —
    it creates a pending request an admin must approve, since paying out real
    money automatically carries more risk than accepting a deposit does.
    """
    account = current_user.account

    if request.method == "POST":
        amount_raw = request.form.get("amount", "").strip()
        notes = request.form.get("notes", "").strip()

        if not amount_raw.replace(".", "", 1).isdigit() or float(amount_raw) <= 0:
            flash("Enter a valid withdrawal amount.", "danger")
            return render_template("member/withdraw_savings.html", account=account)

        amount = float(amount_raw)
        if amount > float(account.balance):
            flash("You can't withdraw more than your current savings balance.", "danger")
            return render_template("member/withdraw_savings.html", account=account)

        tx = Transaction(
            account_id=account.id,
            tx_type="withdrawal_request",
            amount=amount,
            channel="manual",
            status="pending",
            notes=notes or "Awaiting admin approval",
        )
        db.session.add(tx)
        db.session.commit()

        flash(
            "Your withdrawal request has been submitted and is awaiting admin approval. "
            "You'll see it marked completed here once processed.",
            "success",
        )
        return redirect(url_for("member.dashboard"))

    return render_template("member/withdraw_savings.html", account=account)


@member_bp.route("/withdraw-interest", methods=["POST"])
def withdraw_interest():
    """
    Self-service withdrawal of the INTEREST portion only (never principal),
    limited to once per INTEREST_WITHDRAWAL_COOLDOWN_DAYS.
    """
    account = current_user.account
    cooldown_days = current_app.config["INTEREST_WITHDRAWAL_COOLDOWN_DAYS"]

    if float(account.interest_balance) <= 0:
        flash("You have no withdrawable interest yet.", "warning")
        return redirect(url_for("member.dashboard"))

    if account.last_interest_withdrawal_at:
        next_allowed = account.last_interest_withdrawal_at + timedelta(days=cooldown_days)
        if datetime.utcnow() < next_allowed:
            flash(
                f"Interest can only be withdrawn once every {cooldown_days} days. "
                f"Next withdrawal available {next_allowed.strftime('%d %b %Y')}.",
                "warning",
            )
            return redirect(url_for("member.dashboard"))

    amount = float(account.interest_balance)

    tx = Transaction(
        account_id=account.id,
        tx_type="interest_withdrawal",
        amount=amount,
        channel="manual",
        status="pending",
        notes="Interest withdrawal — awaiting admin payout",
    )
    account.interest_balance = 0
    account.last_interest_withdrawal_at = datetime.utcnow()
    db.session.add(tx)
    db.session.commit()

    flash(
        f"Interest withdrawal of KES {amount:,.2f} requested. "
        f"An admin will process your payout shortly.",
        "success",
    )
    return redirect(url_for("member.dashboard"))
