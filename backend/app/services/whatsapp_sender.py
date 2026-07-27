"""
whatsapp_sender.py — Send a report to a client over WhatsApp via Twilio.

Demo-scoped: built against Twilio's WhatsApp Sandbox, not a verified
production WhatsApp Business number. Twilio delivers media by fetching
it from a public URL at send time, so `media_url` must be reachable
from the internet (see BACKEND_PUBLIC_URL in config.py / an ngrok
tunnel during a demo) — Twilio cannot fetch "localhost".
"""

import logging

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def send_report_whatsapp(to_number: str, project_name: str, media_url: str) -> str:
    """
    Send a WhatsApp message with the project's report PDF attached.

    Returns the Twilio message SID on success. Raises RuntimeError if Twilio
    isn't configured, or the underlying Twilio exception on API failure —
    callers should catch and log rather than let one failure abort a batch.
    """
    if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_whatsapp_from):
        raise RuntimeError(
            "Twilio is not configured — set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
            "and TWILIO_WHATSAPP_FROM (see .env.example)."
        )

    from twilio.rest import Client

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    message = client.messages.create(
        from_=f"whatsapp:{settings.twilio_whatsapp_from}",
        to=f"whatsapp:{to_number}",
        body=f"📋 Your BuildWatch progress report for {project_name} is ready.",
        media_url=[media_url],
    )
    logger.info(f"WhatsApp report sent — project={project_name!r} to={to_number} sid={message.sid}")
    return message.sid
