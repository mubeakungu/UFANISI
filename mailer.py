"""
Minimal mailer for password-reset links. If MAIL_SERVER isn't configured in .env,
falls back to logging the link to the console so the app is fully usable in dev
without any SMTP setup.
"""
import smtplib
from email.mime.text import MIMEText
from flask import current_app


def send_reset_email(to_email: str, reset_url: str, recipient_name: str = ""):
    subject = f"{current_app.config['SACCO_NAME']} — Password Reset"
    body = (
        f"Hi {recipient_name or 'there'},\n\n"
        f"We received a request to reset your {current_app.config['SACCO_NAME']} password.\n"
        f"Click the link below to set a new password (valid for 1 hour):\n\n"
        f"{reset_url}\n\n"
        f"If you didn't request this, you can safely ignore this email.\n"
    )

    if not current_app.config.get("MAIL_SERVER"):
        # No SMTP configured — log it so the flow is still testable in dev.
        current_app.logger.info(f"[DEV] Password reset link for {to_email}: {reset_url}")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = current_app.config["MAIL_DEFAULT_SENDER"]
    msg["To"] = to_email

    with smtplib.SMTP(current_app.config["MAIL_SERVER"], current_app.config["MAIL_PORT"]) as server:
        if current_app.config["MAIL_USE_TLS"]:
            server.starttls()
        if current_app.config["MAIL_USERNAME"]:
            server.login(current_app.config["MAIL_USERNAME"], current_app.config["MAIL_PASSWORD"])
        server.sendmail(current_app.config["MAIL_DEFAULT_SENDER"], [to_email], msg.as_string())

    return True
