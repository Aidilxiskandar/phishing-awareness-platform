"""Send tracked phishing-drill emails.

If no SMTP host is configured (settings.dry_run), the email and its tracking
URLs are printed to the console instead of being sent. That lets the whole
flow be demonstrated with zero infrastructure - and keeps accidental real sends
behind an explicit config step.
"""
from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib

from app.config import settings
from app.models import Campaign, Target


def build_tracking_urls(token: str) -> dict:
    base = settings.base_url.rstrip("/")
    return {
        "open_pixel": f"{base}/t/open/{token}.png",
        "click": f"{base}/t/click/{token}",
        "report": f"{base}/t/report/{token}",
    }


def render_email_html(campaign: Campaign, target: Target, preview: bool = False) -> str:
    """Build the exact HTML a recipient receives.

    When `preview=True` (admin "view email"), the open-tracking pixel is omitted
    and the button is defanged (href="#") so that an admin looking at the message
    never fires an open/click event and pollutes the evidence log.
    """
    urls = build_tracking_urls(target.token)
    greeting = f"Hi {target.name}," if target.name else "Hi,"
    click_href = "#" if preview else urls["click"]
    pixel = "" if preview else (
        f'<img src="{urls["open_pixel"]}" width="1" height="1" alt="" style="display:none;">')
    return f"""\
<html><body style="font-family:Arial,sans-serif;color:#222;margin:0;padding:20px;background:#f4f5f7;">
  <div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:28px;">
  <p>{greeting}</p>
  <p>We detected unusual sign-in activity on your account. Please verify your
     identity within 24 hours to avoid suspension.</p>
  <p><a href="{click_href}"
        style="background:#2563eb;color:#fff;padding:10px 18px;
               text-decoration:none;border-radius:6px;display:inline-block;">Verify my account</a></p>
  <p style="font-size:12px;color:#888;">If you did not request this, you can
     ignore this email.</p>
  </div>
  <!-- open tracking pixel -->
  {pixel}
</body></html>"""


async def send_campaign_email(campaign: Campaign, target: Target) -> None:
    if not target.consented:
        raise PermissionError(
            f"Refusing to send to {target.email}: not marked as consenting/authorised. "
            "This tool only runs against consenting test accounts or with written authorisation."
        )

    html = render_email_html(campaign, target)

    if settings.dry_run:
        urls = build_tracking_urls(target.token)
        print("\n" + "=" * 70)
        print(f"[DRY-RUN] Would send to: {target.name or '(no name)'} <{target.email}>")
        print(f"  From:    {campaign.from_name} <{campaign.from_email}>")
        print(f"  Subject: {campaign.subject}")
        print(f"  Click URL:  {urls['click']}")
        print(f"  Open pixel: {urls['open_pixel']}")
        print("=" * 70)
        return

    msg = EmailMessage()
    msg["From"] = f"{campaign.from_name} <{campaign.from_email}>"
    msg["To"] = f"{target.name} <{target.email}>" if target.name else target.email
    msg["Subject"] = campaign.subject
    msg.set_content("Please view this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user or None,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_use_tls,
    )
