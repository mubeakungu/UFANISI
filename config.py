import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'ufanisi_sacco.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Daraja / M-Pesa
    MPESA_ENV = os.environ.get("MPESA_ENV", "sandbox")
    MPESA_CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY", "")
    MPESA_CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET", "")
    MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE", "6892410")
    MPESA_PASSKEY = os.environ.get("MPESA_PASSKEY", "")
    MPESA_CALLBACK_URL = os.environ.get("MPESA_CALLBACK_URL", "")
    # "CustomerBuyGoodsOnline" for a Till number, "CustomerPayBillOnline" for a Paybill.
    # Ufanisi deposits via till 6892410, so Buy Goods is the default here.
    MPESA_TRANSACTION_TYPE = os.environ.get("MPESA_TRANSACTION_TYPE", "CustomerBuyGoodsOnline")

    SACCO_NAME = os.environ.get("SACCO_NAME", "Ufanisi Sacco")

    # Default admin bootstrap (used only if no admin exists yet)
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "ADMIN_UFANISI")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "0757979633")

    # Business rules
    MIN_DEPOSIT_AMOUNT = int(os.environ.get("MIN_DEPOSIT_AMOUNT", "3000"))

    # Interest: "flat" credits INTEREST_FLAT_AMOUNT to every account with balance >=
    # MIN_DEPOSIT_AMOUNT once per week. "percentage" credits balance * INTEREST_RATE instead.
    INTEREST_MODE = os.environ.get("INTEREST_MODE", "percentage")  # flat | percentage
    INTEREST_FLAT_AMOUNT = float(os.environ.get("INTEREST_FLAT_AMOUNT", "500"))
    INTEREST_RATE = float(os.environ.get("INTEREST_RATE", "0.05"))  # 5% (of balance) in percentage mode
    INTEREST_MIN_BALANCE = int(os.environ.get("INTEREST_MIN_BALANCE", str(MIN_DEPOSIT_AMOUNT)))
    INTEREST_WITHDRAWAL_COOLDOWN_DAYS = int(os.environ.get("INTEREST_WITHDRAWAL_COOLDOWN_DAYS", "7"))

    # Referral program: once a member has REFERRAL_MIN_COUNT referred members who have each
    # deposited >= REFERRAL_MIN_DEPOSIT, the referrer earns REFERRAL_BONUS_RATE of each
    # qualifying referred member's total deposit, credited to the referrer's interest_balance.
    REFERRAL_MIN_COUNT = int(os.environ.get("REFERRAL_MIN_COUNT", "1"))
    REFERRAL_MIN_DEPOSIT = int(os.environ.get("REFERRAL_MIN_DEPOSIT", "3000"))
    REFERRAL_BONUS_RATE = float(os.environ.get("REFERRAL_BONUS_RATE", "0.025"))

    # Recurring savings: after a member's first deposit, they're expected to deposit at
    # least WEEKLY_DEPOSIT_AMOUNT every 7 days. Used for arrears flagging on dashboards.
    WEEKLY_DEPOSIT_AMOUNT = int(os.environ.get("WEEKLY_DEPOSIT_AMOUNT", "1000"))

    # Loan / benefit qualification: a member becomes "qualified" once they have
    # saved at least QUALIFICATION_MIN_SAVINGS, referred at least
    # QUALIFICATION_MIN_REFERRALS people, and have been a member for at least
    # QUALIFICATION_MIN_MEMBERSHIP_MONTHS months.
    QUALIFICATION_MIN_SAVINGS = int(os.environ.get("QUALIFICATION_MIN_SAVINGS", "10000"))
    QUALIFICATION_MIN_REFERRALS = int(os.environ.get("QUALIFICATION_MIN_REFERRALS", "10"))
    QUALIFICATION_MIN_MEMBERSHIP_MONTHS = int(os.environ.get("QUALIFICATION_MIN_MEMBERSHIP_MONTHS", "6"))

    # Password reset emails (optional — if left blank, reset links are logged to console
    # instead of emailed, so the app still works without SMTP configured)
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "no-reply@ufanisisacco.example")

    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5000")

    @property
    def MPESA_BASE_URL(self):
        if self.MPESA_ENV == "production":
            return "https://api.safaricom.co.ke"
        return "https://sandbox.safaricom.co.ke"
