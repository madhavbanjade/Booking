import logging
import smtplib
import ssl
from datetime import date, time
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from html.parser import HTMLParser

from app.config import settings

logger = logging.getLogger("uvicorn.error")


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "tr", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)


def _plain_text(body_html: str) -> str:
    parser = _PlainText()
    parser.feed(body_html)
    return "\n".join(line for line in (part.strip() for part in parser.parts) if line)


def _send(to: str, subject: str, body_html: str) -> None:
    username = settings.smtp_username
    password = settings.smtp_password
    if not username or not password:
        # Keep local development usable without sending real mail.
        print(f"\n--- EMAIL (not sent; configure SMTP_USERNAME and SMTP_PASSWORD) ---")
        print(f"To: {to}\nSubject: {subject}\n{body_html}\n--- END EMAIL ---\n")
        return

    sender = settings.smtp_from_email or username
    message = EmailMessage()
    message["From"] = formataddr((settings.smtp_from_name, sender))
    message["To"] = to
    message["Subject"] = subject
    message.set_content(_plain_text(body_html))
    message.add_alternative(body_html, subtype="html")

    try:
        context = ssl.create_default_context()
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15, context=context) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        logger.error("SMTP email to %s failed: %s", to, exc)


def _layout(preheader: str, heading: str, content: str, button_label: str | None = None, button_url: str | None = None) -> str:
    button = ""
    if button_label and button_url:
        button = (
            '<p style="margin:28px 0">'
            f'<a href="{escape(button_url, quote=True)}" style="display:inline-block;background:#17365d;color:#ffffff;'
            'padding:12px 20px;border-radius:6px;text-decoration:none;font-weight:600">'
            f"{escape(button_label)}</a></p>"
            '<p style="font-size:12px;color:#667085">If the button does not work, copy this link:<br>'
            f"{escape(button_url)}</p>"
        )
    return (
        '<!doctype html><html><body style="margin:0;padding:0;background:#f3f6fa;color:#182230;'
        'font-family:Arial,Helvetica,sans-serif">'
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{escape(preheader)}</div>'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f6fa;padding:32px 12px">'
        '<tr><td align="center"><table role="presentation" width="600" cellspacing="0" cellpadding="0" '
        'style="width:100%;max-width:600px;background:#ffffff;border:1px solid #e4e9f0;border-radius:10px;overflow:hidden">'
        '<tr><td style="background:#17365d;padding:22px 32px;color:#ffffff;font-size:18px;font-weight:700;letter-spacing:.3px">BuildCo</td></tr>'
        '<tr><td style="padding:32px">'
        f'<h1 style="margin:0 0 20px;color:#172b4d;font-size:24px;line-height:1.3">{escape(heading)}</h1>'
        f'<div style="font-size:15px;line-height:1.7;color:#475467">{content}</div>{button}'
        '<p style="margin:28px 0 0;padding-top:18px;border-top:1px solid #e9edf2;color:#667085;font-size:12px;line-height:1.6">'
        'This is an automated message from BuildCo. If you need help, please contact our team.</p>'
        '</td></tr></table><p style="margin:16px 0 0;color:#98a2b3;font-size:11px">&copy; BuildCo</p>'
        '</td></tr></table></body></html>'
    )


def _when(preferred_date: date, preferred_time: time) -> str:
    return f"{preferred_date.strftime('%d %b %Y')} at {preferred_time.strftime('%H:%M')}"


def _summary_row(label: str, value: str) -> str:
    return (
        '<tr><td style="padding:8px 12px 8px 0;color:#667085;font-size:13px">'
        f"{escape(label)}</td><td style=\"padding:8px 0;color:#182230;font-size:14px;font-weight:600\">{escape(value)}</td></tr>"
    )


def send_verification_email(to: str, name: str, token: str) -> None:
    link = f"{settings.frontend_url}/verify-email?token={token}"
    content = (
        f"<p>Hello {escape(name)},</p><p>Thanks for creating a BuildCo account. Confirm your email address to start booking our services.</p>"
        '<p style="font-size:13px;color:#667085">This verification link expires in 24 hours. If you did not create an account, you can ignore this email.</p>'
    )
    _send(to, "Confirm your BuildCo email address", _layout("Confirm your email to finish setting up your account.", "Verify your email", content, "Verify email", link))


def send_password_reset_email(to: str, name: str, token: str) -> None:
    link = f"{settings.frontend_url}/reset-password?token={token}"
    content = (
        f"<p>Hello {escape(name)},</p><p>We received a request to reset the password for your BuildCo account.</p>"
        '<p style="font-size:13px;color:#667085">This link expires in 30 minutes. If you did not request a reset, you can ignore this email; your password will remain unchanged.</p>'
    )
    _send(to, "Reset your BuildCo password", _layout("Use the secure link to reset your password.", "Password reset", content, "Reset password", link))


def send_booking_received(to: str, name: str, service_title: str, preferred_date: date, preferred_time: time) -> None:
    when = _when(preferred_date, preferred_time)
    content = (
        f"<p>Hello {escape(name)},</p><p>We’ve received your booking request. Our team will review the details and email you when a decision has been made.</p>"
        '<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;margin:20px 0;background:#f7f9fc;border-radius:8px;padding:12px">'
        f"{_summary_row('Service', service_title)}{_summary_row('Preferred appointment', when)}"
        '<tr><td style="padding:8px 12px 8px 0;color:#667085;font-size:13px">Status</td>'
        '<td style="padding:8px 0"><span style="display:inline-block;background:#fff1c2;color:#8a4b08;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600">Pending review</span></td></tr>'
        "</table><p>Thank you for choosing BuildCo.</p>"
    )
    _send(to, "We received your BuildCo booking request", _layout("Your booking request is now pending review.", "Booking request received", content))


def send_admin_new_booking(customer_name: str, customer_email: str, service_title: str, preferred_date: date, preferred_time: time, message: str | None) -> None:
    if not settings.admin_notify_email:
        return
    content = (
        '<p>A new service booking is waiting for review.</p>'
        '<table role="presentation" cellspacing="0" cellpadding="0" style="width:100%;margin:20px 0;background:#f7f9fc;border-radius:8px;padding:12px">'
        f"{_summary_row('Customer', customer_name)}{_summary_row('Email', customer_email)}"
        f"{_summary_row('Service', service_title)}{_summary_row('Preferred appointment', _when(preferred_date, preferred_time))}"
        "</table>"
        f'<p style="margin-bottom:4px;font-weight:600;color:#344054">Customer message</p><blockquote style="margin:0;padding:12px 16px;border-left:3px solid #f79009;background:#fffaf2;color:#475467">{escape(message or "No message provided.")}</blockquote>'
    )
    _send(settings.admin_notify_email, "New BuildCo booking request", _layout("A customer submitted a new service request.", "New booking request", content))


def send_status_update(to: str, name: str, service_title: str, status: str, admin_note: str | None) -> None:
    decision = status.capitalize()
    tone = "#067647" if status == "approved" else "#b42318"
    note = (
        '<div style="margin-top:20px;padding:14px 16px;border-left:3px solid #f79009;background:#fffaf2">'
        '<p style="margin:0 0 6px;font-weight:600;color:#344054">Note from our team</p>'
        f'<p style="margin:0">{escape(admin_note)}</p></div>'
        if admin_note else ""
    )
    content = (
        f"<p>Hello {escape(name)},</p><p>There’s an update about your BuildCo booking for <strong>{escape(service_title)}</strong>.</p>"
        f'<p style="margin:20px 0"><span style="display:inline-block;background:#f2f4f7;color:{tone};padding:6px 12px;border-radius:20px;font-weight:700">{escape(decision)}</span></p>'
        f"{note}<p>Thank you for choosing BuildCo.</p>"
    )
    _send(to, f"Your BuildCo booking was {status}", _layout(f"Your booking has been {status}.", f"Booking {decision.lower()}", content))
