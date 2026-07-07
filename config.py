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
    MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE", "174379")
    MPESA_PASSKEY = os.environ.get("MPESA_PASSKEY", "")
    MPESA_CALLBACK_URL = os.environ.get("MPESA_CALLBACK_URL", "")

    SACCO_NAME = os.environ.get("SACCO_NAME", "Ufanisi Sacco")

    # Default admin bootstrap (used only if no admin exists yet)
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "ADMIN")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin123")
    ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "0787187393")

    # Business rules
    MIN_DEPOSIT_AMOUNT = int(os.environ.get("MIN_DEPOSIT_AMOUNT", "5000"))

    # Interest: "flat" credits INTEREST_FLAT_AMOUNT to every account with balance >=
    # MIN_DEPOSIT_AMOUNT once per week. "percentage" credits balance * INTEREST_RATE instead.
    INTEREST_MODE = os.environ.get("INTEREST_MODE", "flat")  # flat | percentage
    INTEREST_FLAT_AMOUNT = float(os.environ.get("INTEREST_FLAT_AMOUNT", "500"))
    INTEREST_RATE = float(os.environ.get("INTEREST_RATE", "0.01"))  # 1%/week if percentage mode
    INTEREST_MIN_BALANCE = int(os.environ.get("INTEREST_MIN_BALANCE", str(MIN_DEPOSIT_AMOUNT)))
    INTEREST_WITHDRAWAL_COOLDOWN_DAYS = int(os.environ.get("INTEREST_WITHDRAWAL_COOLDOWN_DAYS", "7"))

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
