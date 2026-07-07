# Ufanisi Sacco — Field Operations Web App

Flask web app for Ufanisi Sacco member savings tracking, with M-Pesa (Daraja) STK Push
deposits and a role-based admin/member portal.

## Features (v1)

- **Member self-service portal**: register, log in, view savings balance and transaction
  history, initiate a savings deposit via M-Pesa STK Push (minimum KES 5,000 per
  deposit, configurable), request a savings withdrawal, and withdraw accrued interest.
- **Admin portal**: dashboard with total members/savings/interest liability/pending
  requests, member list, per-member transaction history, manual deposit/withdrawal
  entry for cash or bank transactions, a one-click weekly interest run, and an
  approve/reject queue for withdrawal requests.
- **M-Pesa Daraja integration**: STK Push (Lipa Na M-Pesa Online) request on deposit,
  with a callback endpoint that confirms the transaction and credits the member's
  balance automatically once Safaricom confirms payment.
- **Forgot / reset password**: token-based reset link, valid for 1 hour, single-use.
  Emails via SMTP if configured, otherwise logs the link to the console so the flow
  still works in dev without any mail setup.
- **Admin login by username**: a dedicated `username` field (separate from phone/member
  number) plus configurable bootstrap credentials via `.env`.
- **Weekly interest engine**: see "How interest works" below — this is the part worth
  reading carefully before going live.

## How interest works (and what to watch out for)

Interest is tracked in a field separate from the member's principal savings
(`interest_balance` vs `balance`). This matters because:

- **Only `interest_balance` is self-service withdrawable**, and only once every
  `INTEREST_WITHDRAWAL_COOLDOWN_DAYS` (default 7 days).
- **Principal (`balance`) withdrawals go through admin approval** — a member can
  request one, but it doesn't pay out until an admin approves it in the dashboard.
  This is intentional: letting members drain their own principal with no oversight
  is a bigger risk than letting them pull out a small, regular interest amount.

**Two interest modes**, set via `INTEREST_MODE` in `.env`:

| Mode | How it works | Trade-off |
|---|---|---|
| `flat` (what you asked for) | Every account with balance ≥ `INTEREST_MIN_BALANCE` (default 5,000) gets a fixed `INTEREST_FLAT_AMOUNT` (default 500) credited once a week, no matter the balance size. | Simple to explain to members. **Does not scale**: a member with exactly 5,000 and a member with 500,000 both get the same 500/week. At 500/week on a 5,000 balance that's a 10%/week return — roughly 500%+ annualized if compounded, which is not sustainable for any real savings institution to pay out of its own resources. Fine for a small pilot group or as a fixed promotional bonus, risky at scale. |
| `percentage` | Every qualifying account gets `balance × INTEREST_RATE` (default 1%/week) instead. | Scales fairly — bigger savers earn proportionally more, smaller savers proportionally less. Standard approach used by real saccos, and the payout stays tied to what the sacco can actually afford relative to funds under management. |

**My recommendation**: start in `percentage` mode with a rate that's actually
justified by what Ufanisi Sacco earns on its pooled funds (e.g., from Treasury bills,
inter-lending to members, or fixed deposits), rather than a flat number picked in
advance. A common real-world pattern: set a target *annual* dividend rate (say 8-12%,
typical for Kenyan saccos), divide by 52 for a weekly rate, and let `INTEREST_RATE`
reflect that. If you want to keep the flat KES 500 model for a small trial group,
that's fully supported — just watch the total interest liability figure on the admin
dashboard so it never grows faster than the sacco's actual income.

**Running the weekly job**: there's an admin dashboard button ("Run Weekly Interest
Now") for manual/on-demand runs, and it's idempotent — running it twice in the same
calendar week does nothing on the second run. For real production use, automate it
instead of relying on someone remembering to click the button:

```bash
# crontab entry — runs every Monday at 6am
0 6 * * MON cd /path/to/ufanisi_sacco && /path/to/venv/bin/flask accrue-interest >> /var/log/ufanisi_interest.log 2>&1
```

## Project layout

```
ufanisi_sacco/
├── app.py                  # App factory, blueprint registration, default admin bootstrap
├── config.py                # Config from environment variables
├── extensions.py             # Shared db / login_manager instances
├── models.py                 # User, SavingsAccount, Transaction
├── daraja.py                  # Daraja OAuth + STK Push + callback parsing
├── routes/
│   ├── auth.py               # Login, register, logout
│   ├── admin.py               # Admin dashboard, member list/detail, manual adjustments
│   ├── member.py               # Member dashboard, deposit flow, status polling
│   └── mpesa.py                # Public STK Push callback endpoint
├── templates/                  # Jinja2 templates (Bootstrap 5)
├── static/css/style.css
├── requirements.txt
└── .env.example
```

## Setup

1. **Create a virtual environment and install dependencies**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure environment variables**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and fill in:
   - `SECRET_KEY` — any long random string
   - `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_PHONE` — credentials for the
     default admin account created on first run (change the password after first login)
   - `MIN_DEPOSIT_AMOUNT` — minimum KES per deposit (default 5,000)
   - `INTEREST_MODE`, `INTEREST_FLAT_AMOUNT`, `INTEREST_RATE`, `INTEREST_MIN_BALANCE`,
     `INTEREST_WITHDRAWAL_COOLDOWN_DAYS` — see "How interest works" above
   - `MAIL_SERVER` etc. — optional, for emailing password reset links (leave blank to
     just log reset links to the console during development)
   - `MPESA_CONSUMER_KEY` / `MPESA_CONSUMER_SECRET` — from your Daraja app at
     https://developer.safaricom.co.ke
   - `MPESA_SHORTCODE` — 174379 for sandbox, or your Paybill/Till number in production
   - `MPESA_PASSKEY` — the Lipa Na M-Pesa passkey for your shortcode
   - `MPESA_CALLBACK_URL` — a **publicly reachable HTTPS URL** pointing at
     `/mpesa/callback` on this app (use ngrok for local testing:
     `ngrok http 5000`, then set the callback to
     `https://<your-ngrok-domain>/mpesa/callback`)

3. **Run the app**

   ```bash
   python app.py
   ```

   On first run, the app creates the SQLite database and a default admin account
   using the `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_PHONE` values from `.env`
   (defaults: username `admin`, password `ChangeMe123!`, phone `254700000000`).
   Log in with any of the three as the identifier. **Change the password immediately**
   — use "Forgot your password?" on the login page to reset it via the email flow,
   or edit it directly via the Flask shell if no email is on file yet.

4. **Visit** `http://localhost:5000`

## How the M-Pesa deposit flow works

1. A logged-in member goes to **Deposit**, enters an amount and phone number.
2. The app creates a `pending` `Transaction` and calls `daraja.stk_push(...)`, which
   sends an STK Push prompt to the member's phone.
3. The member enters their M-Pesa PIN on their phone.
4. Safaricom posts the result to `/mpesa/callback` (must be publicly reachable).
   `routes/mpesa.py` matches the callback to the pending transaction by
   `CheckoutRequestID`, marks it `completed` or `failed`, and — if successful —
   credits the member's `SavingsAccount.balance`.
5. The member's dashboard shows the updated balance and the M-Pesa receipt number.

## Known gaps to close before production use

- **Withdrawal payouts are manual, not automatic.** Approving a withdrawal (savings
  or interest) in the admin dashboard marks it paid and adjusts the ledger, but it
  doesn't itself send money anywhere — the admin still has to actually pay the
  member out (M-Pesa B2C, bank transfer, cash) and then approve the request to
  match the books. Wiring up Safaricom's B2C API would automate the M-Pesa side of
  this, but B2C requires a separate Daraja API product application/approval and
  different credentials (initiator name + security credential) from STK Push, so
  it's a deliberate follow-up rather than something bundled in here.
- **No admin "change password" screen** — resetting the default admin password
  currently goes through the same forgot-password email flow as members (works fine
  if the admin account has an email set), or can be done directly via the Flask shell.
- **STK Push status isn't polled automatically on the deposit page** — the endpoint
  `member.transaction_status` exists for this but isn't wired into the front-end
  JS yet (simple `fetch()` polling loop would do it).
- **SQLite is fine for development** — move to PostgreSQL/MySQL for production
  (just change `DATABASE_URL`).
- Add HTTPS, rate limiting, and CSRF protection (Flask-WTF is already in
  requirements — forms should be migrated to `FlaskForm` for CSRF tokens).
- The Daraja callback endpoint should validate the request is genuinely from
  Safaricom's IP ranges before trusting it, or add a shared secret in the callback
  URL query string, since it's a public unauthenticated endpoint by design.
- The interest job currently has to be triggered (via the admin button, or the
  `flask accrue-interest` CLI command on a cron schedule) — there's no built-in
  scheduler running inside the app itself.
