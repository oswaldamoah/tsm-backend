"""
Transactional email via Resend (https://resend.com).

Set RESEND_API_KEY and RESEND_FROM_EMAIL. Without an API key, emails are
printed to the server log instead, so local development works with no setup.
"""
import html
import logging
import os

import httpx

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _from_address() -> str:
    # onboarding@resend.dev works without a verified domain, but Resend only
    # delivers it to the email address that owns the Resend account.
    return os.environ.get("RESEND_FROM_EMAIL", "Telecom Site Manager <onboarding@resend.dev>")


def frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def send_email(to: str, subject: str, html_body: str, text_body: str) -> bool:
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key:
        print(f"[EMAIL - RESEND_API_KEY not set, not sent]\nTo: {to}\nSubject: {subject}\n\n{text_body}\n")
        return False
    try:
        res = httpx.post(
            RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": _from_address(),
                "to": [to],
                "subject": subject,
                "html": html_body,
                "text": text_body,
            },
            timeout=15,
        )
        if res.status_code >= 300:
            logger.error("Resend rejected email to %s: %s %s", to, res.status_code, res.text[:500])
            return False
        return True
    except Exception as e:  # network problems must never break the request
        logger.error("Resend request failed for %s: %s", to, e)
        return False


def send_password_reset_email(to: str, username: str, token: str, company_name: "str | None", ttl_minutes: int):
    app_name = company_name or "Telecom Site Manager"
    link = f"{frontend_url()}/?reset_token={token}"
    safe_name = html.escape(username)
    safe_app = html.escape(app_name)

    subject = f"Reset your {app_name} password"
    text_body = (
        f"Hi {username},\n\n"
        f"Someone asked to reset the password for your {app_name} account.\n"
        f"Open this link to choose a new one (it expires in {ttl_minutes} minutes and works once):\n\n"
        f"{link}\n\n"
        "If you didn't ask for this, ignore this email - your password won't change."
    )
    html_body = f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#eef1f4;font-family:Helvetica,Arial,sans-serif;color:#172033;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 12px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="max-width:480px;background:#ffffff;border-radius:14px;overflow:hidden;">
          <tr><td style="height:6px;background:#0e7c86;font-size:0;line-height:0;">&nbsp;</td></tr>
          <tr><td style="padding:32px 32px 8px;">
            <p style="margin:0 0 4px;font-size:14px;color:#5b6576;">{safe_app}</p>
            <h1 style="margin:0 0 16px;font-size:22px;line-height:1.3;">Reset your password</h1>
            <p style="margin:0 0 24px;font-size:15px;line-height:1.6;">
              Hi {safe_name}, someone asked to reset the password for your account.
              Choose a new one with the button below.
            </p>
            <a href="{html.escape(link)}"
               style="display:inline-block;background:#0e7c86;color:#ffffff;text-decoration:none;
                      font-weight:600;font-size:15px;padding:12px 22px;border-radius:10px;">
              Choose a new password
            </a>
            <p style="margin:24px 0 0;font-size:13px;line-height:1.6;color:#5b6576;">
              The link expires in {ttl_minutes} minutes and can be used once. If you didn't ask
              for this, ignore this email and your password stays the same.
            </p>
          </td></tr>
          <tr><td style="padding:16px 32px 28px;font-size:12px;color:#8a93a3;word-break:break-all;">
            Button not working? Paste this into your browser:<br>{html.escape(link)}
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""
    return send_email(to, subject, html_body, text_body)
