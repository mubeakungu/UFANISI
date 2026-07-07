from flask import Blueprint, request, jsonify
from extensions import db
from models import Transaction, SavingsAccount
import daraja

mpesa_bp = Blueprint("mpesa", __name__, url_prefix="/mpesa")


@mpesa_bp.route("/callback", methods=["POST"])
def callback():
    """
    Safaricom posts here after the member enters (or cancels) their M-Pesa PIN.
    This endpoint must be publicly reachable over HTTPS and registered as
    MPESA_CALLBACK_URL. It should NOT require login.
    """
    payload = request.get_json(force=True, silent=True) or {}
    parsed = daraja.parse_callback(payload)

    tx = Transaction.query.filter_by(
        mpesa_checkout_request_id=parsed["checkout_request_id"]
    ).first()

    if not tx:
        # Unknown transaction — acknowledge so Safaricom doesn't retry, but log it.
        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200

    if parsed["success"]:
        tx.status = "completed"
        tx.mpesa_receipt = parsed["receipt"]
        account = tx.account
        account.balance = float(account.balance) + float(parsed["amount"] or tx.amount)
        tx.balance_after = account.balance
    else:
        tx.status = "failed"
        tx.notes = parsed["result_desc"]

    db.session.commit()

    # Safaricom expects this exact acknowledgement shape.
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200
