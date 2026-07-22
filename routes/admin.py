from functools import wraps
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_required, current_user

from extensions import db
from models import User, SavingsAccount, Transaction
from interest import accrue_weekly_interest

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view_func(*args, **kwargs)
    return wrapper


@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    total_members = User.query.filter_by(role="member").count()
    total_savings = db.session.query(db.func.coalesce(db.func.sum(SavingsAccount.balance), 0)).scalar()
    total_interest_liability = db.session.query(
        db.func.coalesce(db.func.sum(SavingsAccount.interest_balance), 0)
    ).scalar()
    recent_tx = Transaction.query.order_by(Transaction.created_at.desc()).limit(15).all()
    top_savers = (
        User.query.join(SavingsAccount, User.id == SavingsAccount.user_id)
        .filter(User.role == "member")
        .order_by(SavingsAccount.balance.desc())
        .limit(5)
        .all()
    )
    pending_count = Transaction.query.filter_by(status="pending").count()
    pending_withdrawals = (
        Transaction.query.filter(Transaction.tx_type.in_(["withdrawal_request", "interest_withdrawal"]))
        .filter_by(status="pending")
        .order_by(Transaction.created_at.asc())
        .all()
    )
    pending_deposits = (
        Transaction.query.filter_by(tx_type="deposit", status="pending")
        .order_by(Transaction.created_at.asc())
        .all()
    )

    return render_template(
        "admin/dashboard.html",
        total_members=total_members,
        total_savings=total_savings,
        total_interest_liability=total_interest_liability,
        recent_tx=recent_tx,
        top_savers=top_savers,
        pending_count=pending_count,
        pending_withdrawals=pending_withdrawals,
        pending_deposits=pending_deposits,
        interest_mode=current_app.config["INTEREST_MODE"],
        interest_flat_amount=current_app.config["INTEREST_FLAT_AMOUNT"],
        interest_rate=current_app.config["INTEREST_RATE"],
        min_deposit=current_app.config["MIN_DEPOSIT_AMOUNT"],
    )


@admin_bp.route("/interest/run", methods=["POST"])
@admin_required
def run_interest():
    summary = accrue_weekly_interest(current_app._get_current_object())
    flash(
        f"Interest run complete: {summary['accounts_credited']} account(s) credited, "
        f"{summary['accounts_skipped_already_run']} already credited this week, "
        f"total KES {summary['total_amount_credited']:,.2f}.",
        "success",
    )
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/deposits/<int:tx_id>/approve", methods=["POST"])
@admin_required
def approve_deposit(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    if tx.tx_type != "deposit":
        abort(404)
    if tx.status != "pending":
        flash("This deposit has already been processed.", "warning")
        return redirect(request.referrer or url_for("admin.dashboard"))

    account = tx.account
    amount = float(tx.amount)

    account.balance = float(account.balance) + amount
    account.total_deposited = float(account.total_deposited) + amount
    if not account.first_deposit_at:
        account.first_deposit_at = datetime.utcnow()
    account.next_weekly_deposit_due = (datetime.utcnow() + timedelta(days=7)).date()

    tx.balance_after = account.balance
    tx.status = "completed"
    tx.notes = (tx.notes or "") + f" | Approved by {current_user.full_name}"
    db.session.commit()

    flash(f"Deposit of KES {amount:,.2f} approved and credited to {account.owner.full_name}.", "success")
    return redirect(request.referrer or url_for("admin.dashboard"))


@admin_bp.route("/deposits/<int:tx_id>/reject", methods=["POST"])
@admin_required
def reject_deposit(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    if tx.tx_type != "deposit":
        abort(404)
    if tx.status != "pending":
        flash("This deposit has already been processed.", "warning")
        return redirect(request.referrer or url_for("admin.dashboard"))

    # Nothing to reverse — a pending deposit was never credited to the balance.
    tx.status = "failed"
    tx.notes = (tx.notes or "") + f" | Rejected by {current_user.full_name}"
    db.session.commit()

    flash("Deposit claim rejected.", "info")
    return redirect(request.referrer or url_for("admin.dashboard"))


@admin_bp.route("/withdrawals/<int:tx_id>/approve", methods=["POST"])
@admin_required
def approve_withdrawal(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    if tx.status != "pending":
        flash("This request has already been processed.", "warning")
        return redirect(url_for("admin.dashboard"))

    account = tx.account

    # Principal withdrawals still have their amount sitting in the balance —
    # deduct it now on approval. Interest withdrawals already had their amount
    # zeroed out of interest_balance at request time, so just mark them paid.
    if tx.tx_type == "withdrawal_request":
        if float(tx.amount) > float(account.balance):
            flash("Cannot approve: withdrawal amount exceeds current balance.", "danger")
            return redirect(url_for("admin.dashboard"))
        account.balance = float(account.balance) - float(tx.amount)
        tx.balance_after = account.balance

    tx.status = "completed"
    tx.notes = (tx.notes or "") + f" | Approved by {current_user.full_name}"
    db.session.commit()

    flash(f"Withdrawal of KES {float(tx.amount):,.2f} approved and marked paid out.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/withdrawals/<int:tx_id>/reject", methods=["POST"])
@admin_required
def reject_withdrawal(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    if tx.status != "pending":
        flash("This request has already been processed.", "warning")
        return redirect(url_for("admin.dashboard"))

    # If it was an interest withdrawal, the amount was already deducted from
    # interest_balance at request time — refund it back since we're rejecting.
    if tx.tx_type == "interest_withdrawal":
        tx.account.interest_balance = float(tx.account.interest_balance) + float(tx.amount)

    tx.status = "failed"
    tx.notes = (tx.notes or "") + f" | Rejected by {current_user.full_name}"
    db.session.commit()

    flash("Withdrawal request rejected.", "info")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/transactions")
@admin_required
def transactions():
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "")
    type_filter = request.args.get("type", "")

    query = Transaction.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if type_filter:
        query = query.filter_by(tx_type=type_filter)

    pagination = query.order_by(Transaction.created_at.desc()).paginate(page=page, per_page=25, error_out=False)

    return render_template(
        "admin/transactions.html",
        pagination=pagination,
        status_filter=status_filter,
        type_filter=type_filter,
    )


@admin_bp.route("/settings")
@admin_required
def settings():
    return render_template(
        "admin/settings.html",
        sacco_name=current_app.config["SACCO_NAME"],
        min_deposit=current_app.config["MIN_DEPOSIT_AMOUNT"],
        interest_mode=current_app.config["INTEREST_MODE"],
        interest_flat_amount=current_app.config["INTEREST_FLAT_AMOUNT"],
        interest_rate=current_app.config["INTEREST_RATE"],
        interest_min_balance=current_app.config["INTEREST_MIN_BALANCE"],
        interest_withdrawal_cooldown_days=current_app.config["INTEREST_WITHDRAWAL_COOLDOWN_DAYS"],
        mpesa_env=current_app.config["MPESA_ENV"],
        mpesa_shortcode=current_app.config["MPESA_SHORTCODE"],
        admin_username=current_app.config["ADMIN_USERNAME"],
        admin_phone=current_app.config["ADMIN_PHONE"],
    )


@admin_bp.route("/members")
@admin_required
def members():
    all_members = User.query.filter_by(role="member").order_by(User.created_at.desc()).all()
    return render_template("admin/members.html", members=all_members)


@admin_bp.route("/members/<int:user_id>")
@admin_required
def member_detail(user_id):
    member = User.query.get_or_404(user_id)
    if member.role != "member":
        abort(404)
    transactions = member.account.transactions if member.account else []
    return render_template("admin/member_detail.html", member=member, transactions=transactions)


@admin_bp.route("/members/<int:user_id>/adjust", methods=["POST"])
@admin_required
def adjust_balance(user_id):
    """Record a manual cash/bank deposit or withdrawal (not via M-Pesa)."""
    member = User.query.get_or_404(user_id)
    tx_type = request.form.get("tx_type")
    amount_raw = request.form.get("amount", "").strip()
    notes = request.form.get("notes", "").strip()

    if tx_type not in ("deposit", "withdrawal") or not amount_raw.replace(".", "", 1).isdigit():
        flash("Invalid adjustment request.", "danger")
        return redirect(url_for("admin.member_detail", user_id=user_id))

    amount = float(amount_raw)
    account = member.account
    if tx_type == "withdrawal" and float(account.balance) < amount:
        flash("Withdrawal exceeds current balance.", "danger")
        return redirect(url_for("admin.member_detail", user_id=user_id))

    account.balance = float(account.balance) + amount if tx_type == "deposit" else float(account.balance) - amount

    tx = Transaction(
        account_id=account.id,
        tx_type=tx_type,
        amount=amount,
        balance_after=account.balance,
        channel="manual",
        status="completed",
        notes=notes or f"Manual {tx_type} by {current_user.full_name}",
    )
    db.session.add(tx)
    db.session.commit()

    flash(f"{tx_type.capitalize()} of KES {amount:,.2f} recorded for {member.full_name}.", "success")
    return redirect(url_for("admin.member_detail", user_id=user_id))
