"""Provider-neutral email transport with an SMTP implementation."""

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path


LOGO_PATH = Path(__file__).with_name("assets") / "vodacom-logo.png"


@dataclass
class Attachment:
    filename: str
    content: bytes
    maintype: str
    subtype: str


class MailTransport:
    provider = "unknown"

    def send(self, recipients: list[str], cc: list[str], subject: str, html: str, attachment: Attachment) -> str | None:
        raise NotImplementedError


class DisabledTransport(MailTransport):
    provider = "disabled"

    def send(self, recipients, cc, subject, html, attachment):
        raise RuntimeError("MAIL_PROVIDER is disabled; configure an approved mail provider before enabling subscriptions")


class SmtpTransport(MailTransport):
    provider = "smtp"

    def send(self, recipients, cc, subject, html, attachment):
        host = os.getenv("SMTP_HOST", "").strip()
        sender = os.getenv("MAIL_FROM_ADDRESS", "").strip()
        if not host or not sender:
            raise RuntimeError("SMTP_HOST and MAIL_FROM_ADDRESS are required")

        msg = EmailMessage()
        sender_name = os.getenv("MAIL_FROM_NAME", "Vodacom ITIL Reports").strip()
        msg["From"] = formataddr((sender_name, sender)) if sender_name else sender
        msg["To"] = ", ".join(recipients)
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid()
        msg.set_content("This report requires an HTML-capable email client.")
        msg.add_alternative(html, subtype="html")
        if LOGO_PATH.is_file():
            html_part = msg.get_payload()[-1]
            html_part.add_related(
                LOGO_PATH.read_bytes(),
                maintype="image",
                subtype="png",
                cid="<vodacom-logo>",
                filename="vodacom-logo.png",
                disposition="inline",
            )
        msg.add_attachment(
            attachment.content,
            maintype=attachment.maintype,
            subtype=attachment.subtype,
            filename=attachment.filename,
        )

        port = int(os.getenv("SMTP_PORT", "587"))
        timeout = int(os.getenv("SMTP_TIMEOUT_SECONDS", "30"))
        use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}
        username = os.getenv("SMTP_USERNAME", "").strip()
        password = os.getenv("SMTP_PASSWORD", "")
        with smtplib.SMTP(host, port, timeout=timeout) as client:
            if use_tls:
                client.starttls()
            if username:
                client.login(username, password)
            client.send_message(msg, to_addrs=recipients + cc)
        return msg.get("Message-ID")


def configured_transport() -> MailTransport:
    provider = os.getenv("MAIL_PROVIDER", "disabled").strip().lower()
    if provider == "smtp":
        return SmtpTransport()
    if provider in {"microsoft365", "graph"}:
        raise RuntimeError("Microsoft 365 transport is awaiting the approved tenant/application configuration")
    return DisabledTransport()
