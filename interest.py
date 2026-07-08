"""
Weekly interest accrual.

Design notes (read this before changing the numbers):
- Interest is tracked SEPARATELY from principal, in SavingsAccount.interest_balance.
  Only interest_balance is withdrawable by members, and only once per
  INTEREST_WITHDRAWAL_COOLDOWN_DAYS (default 7 days). Principal savings withdrawals
  go through the admin-approved withdrawal_request flow instead.
- Two modes are supported, controlled by INTEREST_MODE in .env:
    "flat"       -> every account with balance >= INTEREST_MIN_BALANCE gets a fixed
                    KES INTEREST_FLAT_AMOUNT credited once per week, regardless of
                    how large the balance is.
    "percentage" -> every qualifying account gets balance * INTEREST_RATE credited
                    once per week instead.
  Now running in "percentage" mode at INTEREST_RATE = 0.05 (5% of balance/week),
  set in config.py.
- This function is idempotent per calendar week: each account's
  last_interest_accrual_date is checked against the current ISO week, so running
  it twice in the same week does nothing on the second run.
"""
from datetime import date
from extensions import db
from models import SavingsAccount, Transaction


def _same_iso_week(d1: date, d2: date) -> bool:
    return d1.isocalendar()[:2] == d2.isocalendar()[:2]


def accrue_weekly_interest(app):
    """Run the weekly interest job. Returns a summary dict."""
    with app.app_context():
        mode = app.config["INTEREST_MODE"]
        flat_amount = app.config["INTEREST_FLAT_AMOUNT"]
        rate = app.config["INTEREST_RATE"]
        min_balance = app.config["INTEREST_MIN_BALANCE"]

        today = date.today()
        accounts = SavingsAccount.query.filter(SavingsAccount.balance >= min_balance).all()

        credited = 0
        skipped_already_run = 0
        total_credited_amount = 0.0

        for account in accounts:
            if account.last_interest_accrual_date and _same_iso_week(account.last_interest_accrual_date, today):
                skipped_already_run += 1
                continue

            if mode == "percentage":
                interest_amount = round(float(account.balance) * rate, 2)
            else:
                interest_amount = round(flat_amount, 2)

            if interest_amount <= 0:
                continue

            account.interest_balance = float(account.interest_balance) + interest_amount
            account.last_interest_accrual_date = today

            tx = Transaction(
                account_id=account.id,
                tx_type="interest_accrual",
                amount=interest_amount,
                balance_after=account.balance,  # principal unaffected
                channel="system",
                status="completed",
                notes=f"Weekly interest ({mode})",
            )
            db.session.add(tx)
            credited += 1
            total_credited_amount += interest_amount

        db.session.commit()

        return {
            "accounts_credited": credited,
            "accounts_skipped_already_run": skipped_already_run,
            "total_amount_credited": round(total_credited_amount, 2),
            "mode": mode,
        }
