"""
Email service using SendGrid.
Failures are logged but do not crash the application.
"""
import logging

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.config.settings import config

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """
    Send an HTML email via SendGrid.
    Returns True on success, False on failure.
    Never raises — email failures should not crash user requests.
    """
    try:
        message = Mail(
            from_email=config.FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=html_content,
        )
        sg = SendGridAPIClient(config.SENDGRID_API_KEY)
        response = sg.send(message)
        success = response.status_code in (200, 202)
        if not success:
            logger.error("SendGrid returned %d for %s", response.status_code, to_email)
        return success
    except Exception as exc:
        logger.error("Email send failed for %s: %s", to_email, exc)
        return False


def send_otp_email(to_email: str, otp: str) -> bool:
    return send_email(
        to_email=to_email,
        subject="PixMatch — Email Verification OTP",
        html_content=f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto;">
          <h2>Verify Your Email</h2>
          <p>Your One-Time Password is:</p>
          <div style="font-size:32px;font-weight:bold;letter-spacing:8px;
                      padding:16px;background:#f4f4f4;text-align:center;">
            {otp}
          </div>
          <p>This code expires in <strong>2 minutes</strong>.</p>
          <p>If you didn't request this, please ignore this email.</p>
        </div>
        """,
    )


def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    return send_email(
        to_email=to_email,
        subject="PixMatch — Password Reset",
        html_content=f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto;">
          <h2>Reset Your Password</h2>
          <p>Click the button below to reset your password. This link expires in 15 minutes.</p>
          <a href="{reset_link}"
             style="display:inline-block;padding:12px 24px;background:#7c3aed;
                    color:#fff;text-decoration:none;border-radius:6px;margin:16px 0;">
            Reset Password
          </a>
          <p>If you didn't request a password reset, you can safely ignore this email.</p>
        </div>
        """,
    )
