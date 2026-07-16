from __future__ import annotations

import os, smtplib
from email.message import EmailMessage
from pathlib import Path


def send_report(to_address: str, html_path: Path, text_path: Path) -> None:
    required = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD"]
    missing = [key for key in required if not os.getenv(key)]
    if missing: raise RuntimeError("Missing email configuration: " + ", ".join(missing))
    message = EmailMessage(); message["Subject"] = "Weekly Driver Dispatch Intelligence"; message["From"] = os.environ["SMTP_USERNAME"]; message["To"] = to_address
    message.set_content(text_path.read_text()); message.add_alternative(html_path.read_text(), subtype="html")
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=20) as smtp:
        smtp.starttls(); smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"]); smtp.send_message(message)
