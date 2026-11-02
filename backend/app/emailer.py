import logging
from datetime import date, time
from html import escape

import httpx

from app.config import settings

logger = logging.getLogger("uvicorn.error")


def _send(to: str, subject: str, body_html: str) -> None:
    if not settings.resend_api_key:
        # Local development: no email provider configured, so print the email.
        print(f"\n--- EMAIL (not sent, RESEND_API_KEY is empty) ---")
        print(f"To: {to}\nSubject: {subject}\n{body_html}\n--- END EMAIL ---\n")
        return
    try:    
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "html": body_html,
            },
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        
        logger.error("Email to %s failed: %s", to, exc)


def _layout(heading: str, content: str) -> str:
    return (
        '<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto">'
        f"<h2>{escape(heading)}</h2>{content}</div>"
    )


def _when(preferred_date: date, preferred_time: time) -> str:
    return f"{preferred_date.strftime('%d %b %Y')} at {preferred_time.strftime('%H:%M')}"


def send_verification_email(to: str, name: str, token: str) -> None:
    link = f"{settings.frontend_url}/verify-email?token={token}"
    body = _layout(
        "Verify your email",
        f"<p>Hi {escape(name)},</p>"
        "<p>Please confirm your email address to start booking.</p>"
        f'<p><a href="{link}">Verify my email</a></p>'
        "<p>This link expires in 24 hours.</p>",
    )
    _send(to, "Verify your email", body)


def send_password_reset_email(to: str, name: str, token: str) -> None:
    link = f"{settings.frontend_url}/reset-password?token={token}"
    body = _layout(
        "Reset your password",
        f"<p>Hi {escape(name)},</p>"
        f'<p><a href="{link}">Choose a new password</a></p>'
        "<p>This link expires in 30 minutes. If you did not ask for it, "
        "you can ignore this email.</p>",
    )
    _send(to, "Reset your password", body)


def send_booking_received(
    to: str,
    name: str,
    service_title: str,
    preferred_date: date,
    preferred_time: time,
) -> None:
    body = _layout(
        "We received your booking request",
        f"<p>Hi {escape(name)},</p>"
        f"<p>Your request for <b>{escape(service_title)}</b> on "
        f"{_when(preferred_date, preferred_time)} is waiting for confirmation. "
        "We will email you as soon as it is reviewed.</p>",
    )
    _send(to, "Booking request received", body)


def send_admin_new_booking(
    customer_name: str,
    customer_email: str,
    service_title: str,
    preferred_date: date,
    preferred_time: time,
    message: str | None,
) -> None:
    if not settings.admin_notify_email:
        return
    body = _layout(
        "New booking request",
        f"<p><b>{escape(customer_name)}</b> ({escape(customer_email)}) requested "
        f"<b>{escape(service_title)}</b> on "
        f"{_when(preferred_date, preferred_time)}.</p>"
        f"<p>Message: {escape(message or '-')}</p>",
    )
    _send(settings.admin_notify_email, "New booking request", body)


def send_status_update(
    to: str,
    name: str,
    service_title: str,
    status: str,
    admin_note: str | None,
) -> None:
    note = f"<p>Note from us: {escape(admin_note)}</p>" if admin_note else ""
    body = _layout(
        f"Your booking was {status}",
        f"<p>Hi {escape(name)},</p>"
        f"<p>Your request for <b>{escape(service_title)}</b> was "
        f"<b>{escape(status)}</b>.</p>{note}",
    )
    _send(to, f"Your booking was {status}", body)
