"""
Deposit-driven business rules: recurring weekly deposit tracking + referral bonus payout.

Call record_deposit(app, account, amount) once, right after you mark a deposit
Transaction as status="completed" (in your mpesa callback and/or cash-deposit route),
BEFORE you commit. It is safe to call db.session.commit() once after this returns.

What it does:
1. Adds `amount` to account.total_deposited (lifetime deposits — never reduced by withdrawals,
   used for referral qualification so a member can't withdraw to duck the threshold).
2. Schedules/advances next_weekly_deposit_due:
     - First-ever deposit: due date = deposit_date + 7 days.
     - Later deposits: if the deposit is >= WEEKLY_DEPOSIT_AMOUNT and is made on/after the
       current due date's window, due date rolls forward by 7 days from the deposit date.
       (Deposits below WEEKLY_DEPOSIT_AMOUNT don't satisfy the weekly requirement and the
       due date is left as-is, so the member shows as overdue until they top up.)
3. Runs referral qualification + payout for the account owner (see process_referral_bonus).
"""
from datetime import date, datetime, timedelta
from extensions import db
from models import User, SavingsAccount, Transaction


def record_deposit(app, account: SavingsAccount, amount: float, deposit_date: date = None):
    d = deposit_date or date.today()
    weekly_min = app.config["WEEKLY_DEPOSIT_AMOUNT"]

    account.total_deposited = float(account.total_deposited or 0) + float(amount)

    if not account.first_deposit_at:
        account.first_deposit_at = datetime.utcnow()
        account.next_weekly_deposit_due = d + timedelta(days=7)
    elif float(amount) >= weekly_min:
        base = account.next_weekly_deposit_due or d
        if d >= base - timedelta(days=7):
            account.next_weekly_deposit_due = d + timedelta(days=7)

    referred_user = account.owner
    if referred_user:
        process_referral_bonus(app, referred_user)


def get_deposit_status(account: SavingsAccount) -> str:
    """For dashboards: 'no_deposits_yet' | 'current' | 'overdue'."""
    if not account or not account.next_weekly_deposit_due:
        return "no_deposits_yet"
    if date.today() > account.next_weekly_deposit_due:
        return "overdue"
    return "current"


def process_referral_bonus(app, referred_user: User):
    """
    Mark `referred_user` as referral-qualified once their lifetime deposits hit
    REFERRAL_MIN_DEPOSIT, then check whether their referrer has now reached
    REFERRAL_MIN_COUNT qualifying referrals. Once the threshold is reached, pay out
    REFERRAL_BONUS_RATE of each unpaid qualifying referral's total_deposited to the
    referrer's interest_balance (credited once per referred member, never twice).
    """
    account = referred_user.account
    if not referred_user.referred_by_id or not account:
        return 0.0

    min_deposit = app.config["REFERRAL_MIN_DEPOSIT"]
    if not referred_user.referral_qualified and float(account.total_deposited or 0) >= min_deposit:
        referred_user.referral_qualified = True

    if referred_user.referral_bonus_paid or not referred_user.referral_qualified:
        return 0.0

    referrer = User.query.get(referred_user.referred_by_id)
    if not referrer or not referrer.account:
        return 0.0

    min_count = app.config["REFERRAL_MIN_COUNT"]
    bonus_rate = app.config["REFERRAL_BONUS_RATE"]

    paid_count = User.query.filter_by(referred_by_id=referrer.id, referral_bonus_paid=True).count()
    qualified_unpaid = User.query.filter_by(
        referred_by_id=referrer.id, referral_qualified=True, referral_bonus_paid=False
    ).all()

    if paid_count + len(qualified_unpaid) < min_count:
        # Threshold not reached yet — leave these qualified-but-unpaid, they'll be
        # picked up automatically once the Nth qualifying referral comes in.
        return 0.0

    total_bonus = 0.0
    for ref in qualified_unpaid:
        bonus = round(float(ref.account.total_deposited) * bonus_rate, 2)
        ref.referral_bonus_paid = True
        total_bonus += bonus

    if total_bonus > 0:
        referrer.account.interest_balance = float(referrer.account.interest_balance) + total_bonus
        db.session.add(Transaction(
            account_id=referrer.account.id,
            tx_type="referral_bonus",
            amount=total_bonus,
            balance_after=referrer.account.balance,
            channel="system",
            status="completed",
            notes=f"Referral bonus for {len(qualified_unpaid)} qualifying referral(s)",
        ))

    return total_bonus
