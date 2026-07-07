"""
Daraja API helper for Lipa Na M-Pesa Online (STK Push).
Docs: https://developer.safaricom.co.ke/APIs/MpesaExpressSimulate
"""
import base64
import requests
from datetime import datetime
from flask import current_app


def get_access_token():
    """Fetch an OAuth access token from Safaricom Daraja."""
    consumer_key = current_app.config["MPESA_CONSUMER_KEY"]
    consumer_secret = current_app.config["MPESA_CONSUMER_SECRET"]
    url = f"{_base_url()}/oauth/v1/generate?grant_type=client_credentials"
    resp = requests.get(url, auth=(consumer_key, consumer_secret), timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _base_url():
    env = current_app.config["MPESA_ENV"]
    return "https://api.safaricom.co.ke" if env == "production" else "https://sandbox.safaricom.co.ke"


def _password_and_timestamp():
    shortcode = current_app.config["MPESA_SHORTCODE"]
    passkey = current_app.config["MPESA_PASSKEY"]
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    raw = f"{shortcode}{passkey}{timestamp}"
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


def normalize_phone(phone: str) -> str:
    """Convert 07XXXXXXXX or +254XXXXXXXXX to 2547XXXXXXXX format required by Daraja."""
    phone = phone.strip().replace(" ", "").replace("+", "")
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    elif phone.startswith("7") or phone.startswith("1"):
        phone = "254" + phone
    return phone


def stk_push(phone_number: str, amount: int, account_reference: str, description: str = "Sacco Deposit"):
    """
    Initiate an STK Push (Lipa Na M-Pesa Online) request to the member's phone.
    Returns the parsed JSON response from Daraja, which includes CheckoutRequestID.
    """
    access_token = get_access_token()
    password, timestamp = _password_and_timestamp()
    shortcode = current_app.config["MPESA_SHORTCODE"]
    callback_url = current_app.config["MPESA_CALLBACK_URL"]
    phone = normalize_phone(phone_number)

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": shortcode,
        "PhoneNumber": phone,
        "CallBackURL": callback_url,
        "AccountReference": account_reference[:20],
        "TransactionDesc": description[:20],
    }

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    url = f"{_base_url()}/mpesa/stkpush/v1/processrequest"
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_callback(payload: dict):
    """
    Parse the JSON body Safaricom POSTs to your callback URL after STK push resolves.
    Returns a dict: {checkout_request_id, success, amount, receipt, phone, result_desc}
    """
    body = payload.get("Body", {}).get("stkCallback", {})
    checkout_request_id = body.get("CheckoutRequestID")
    result_code = body.get("ResultCode")
    result_desc = body.get("ResultDesc")

    parsed = {
        "checkout_request_id": checkout_request_id,
        "success": result_code == 0,
        "result_desc": result_desc,
        "amount": None,
        "receipt": None,
        "phone": None,
    }

    if result_code == 0:
        items = body.get("CallbackMetadata", {}).get("Item", [])
        for item in items:
            name = item.get("Name")
            value = item.get("Value")
            if name == "Amount":
                parsed["amount"] = value
            elif name == "MpesaReceiptNumber":
                parsed["receipt"] = value
            elif name == "PhoneNumber":
                parsed["phone"] = value

    return parsed
