"""
UfanisiAssist — AI chat widget backend.

Answers member/prospect questions about how the sacco works (interest, deposits,
withdrawals, referrals). It is informational only:
  - It NEVER moves money, changes account settings, or approves/rejects anything.
  - If logged in, it may reference the current user's OWN account figures only —
    never another member's data.
  - For anything it can't safely answer (disputes, forgotten passwords, fraud
    concerns), it tells the person to use the WhatsApp button or contact an admin.

Requires ANTHROPIC_API_KEY set in the environment (.env locally / Render env vars).
"""
import os
import requests
from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user

assistant_bp = Blueprint("assistant", __name__, url_prefix="/assistant")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT_TEMPLATE = """You are UfanisiAssist, the AI help assistant for {sacco_name}, \
a Kenyan SACCO (savings and credit cooperative). You answer questions from members and \
prospective members about how the sacco works. Be warm, concise, and use KES amounts.

Current rules of the sacco (always answer using these, never invent different numbers):
- Minimum deposit to open/maintain an account: KES {min_deposit:,}.
- Interest: {interest_rate_pct}% of the member's balance, credited weekly to a separate \
interest balance. Interest can be withdrawn on its own every {cooldown_days} days; it \
does not touch the principal savings.
- Recurring savings: after a member's first deposit, they're expected to deposit at least \
KES {weekly_deposit:,} every week to stay in good standing.
- Referral program: every member gets a referral code/link. Once a member has referred \
{referral_min_count} people who have each deposited at least KES {referral_min_deposit:,}, \
the referrer earns a {referral_bonus_pct}% bonus on each qualifying referred member's \
total deposits, credited to the referrer's interest balance.
- Principal savings withdrawals require admin approval and are not instant. Interest \
withdrawals are self-service but capped to once every {cooldown_days} days.

Hard rules for you:
- You cannot execute deposits, withdrawals, or any account changes — you only explain.
- Never disclose or guess any other member's personal or financial information.
- If asked about something outside the sacco's product (e.g. unrelated financial advice, \
legal advice, or anything requiring a human), say so and point them to WhatsApp or an admin.
- Keep answers short — a few sentences, not an essay — unless the person asks for detail.
"""


def _build_system_prompt():
    cfg = current_app.config
    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        sacco_name=cfg["SACCO_NAME"],
        min_deposit=cfg["MIN_DEPOSIT_AMOUNT"],
        interest_rate_pct=round(cfg["INTEREST_RATE"] * 100, 2),
        cooldown_days=cfg["INTEREST_WITHDRAWAL_COOLDOWN_DAYS"],
        weekly_deposit=cfg["WEEKLY_DEPOSIT_AMOUNT"],
        referral_min_count=cfg["REFERRAL_MIN_COUNT"],
        referral_min_deposit=cfg["REFERRAL_MIN_DEPOSIT"],
        referral_bonus_pct=round(cfg["REFERRAL_BONUS_RATE"] * 100, 2),
    )

    if current_user.is_authenticated and not current_user.is_admin:
        account = current_user.account
        if account:
            prompt += (
                f"\nThe person you're talking to is logged in as {current_user.full_name} "
                f"(member number {current_user.member_number}). Their OWN account: "
                f"savings balance KES {float(account.balance):,.2f}, "
                f"withdrawable interest KES {float(account.interest_balance):,.2f}, "
                f"qualifying referrals so far {current_user.qualifying_referral_count}. "
                f"You may share these figures with them since it's their own account, but "
                f"never invent figures you weren't given, and never discuss anyone else's account."
            )
    return prompt


@assistant_bp.route("/chat", methods=["POST"])
def chat():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "Assistant is not configured yet. Please use WhatsApp for help."}), 503

    data = request.get_json(force=True, silent=True) or {}
    user_message = (data.get("message") or "").strip()
    history = data.get("history") or []  # [{role: "user"|"assistant", content: "..."}]

    if not user_message:
        return jsonify({"error": "Message is required."}), 400
    if len(user_message) > 2000:
        return jsonify({"error": "Message is too long."}), 400

    # Keep the request small and bounded — only the last few turns.
    trimmed_history = history[-8:]
    messages = [
        {"role": m.get("role"), "content": m.get("content", "")}
        for m in trimmed_history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    messages.append({"role": "user", "content": user_message})

    try:
        resp = requests.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 500,
                "system": _build_system_prompt(),
                "messages": messages,
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        reply_text = "".join(
            block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"
        ).strip()
        if not reply_text:
            reply_text = "Sorry, I couldn't work that out — please try WhatsApp for help."
        return jsonify({"reply": reply_text})
    except requests.exceptions.RequestException:
        return jsonify({"error": "UfanisiAssist is temporarily unavailable. Please use WhatsApp for help."}), 502
