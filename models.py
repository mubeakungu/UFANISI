from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    member_number = db.Column(db.String(20), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=True)  # primarily used by admins
    full_name = db.Column(db.String(120), nullable=False)
    phone_number = db.Column(db.String(15), unique=True, nullable=False)  # 2547XXXXXXXX
    national_id = db.Column(db.String(20), unique=True, nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member")  # admin | member
    is_active_member = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reset_token = db.Column(db.String(100), unique=True, nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)

    account = db.relationship("SavingsAccount", backref="owner", uselist=False,
                               cascade="all, delete-orphan")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self):
        return self.role == "admin"

    def generate_reset_token(self):
        import secrets
        from datetime import timedelta
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
        return self.reset_token

    def clear_reset_token(self):
        self.reset_token = None
        self.reset_token_expiry = None

    def reset_token_is_valid(self, token):
        return (
            self.reset_token is not None
            and self.reset_token == token
            and self.reset_token_expiry is not None
            and self.reset_token_expiry > datetime.utcnow()
        )

    def __repr__(self):
        return f"<User {self.member_number} {self.full_name}>"


class SavingsAccount(db.Model):
    __tablename__ = "savings_accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    interest_balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    last_interest_accrual_date = db.Column(db.Date, nullable=True)
    last_interest_withdrawal_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = db.relationship("Transaction", backref="account",
                                    cascade="all, delete-orphan",
                                    order_by="Transaction.created_at.desc()")

    def __repr__(self):
        return f"<SavingsAccount user={self.user_id} balance={self.balance}>"


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("savings_accounts.id"), nullable=False)
    tx_type = db.Column(db.String(30), nullable=False)
    # deposit | withdrawal | withdrawal_request | interest_accrual | interest_withdrawal
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    balance_after = db.Column(db.Numeric(12, 2), nullable=True)
    channel = db.Column(db.String(20), default="mpesa")  # mpesa | cash | bank
    status = db.Column(db.String(20), default="pending")  # pending | completed | failed
    mpesa_receipt = db.Column(db.String(40), nullable=True)
    mpesa_checkout_request_id = db.Column(db.String(60), nullable=True, index=True)
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Transaction {self.tx_type} {self.amount} status={self.status}>"
