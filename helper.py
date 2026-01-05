import os
import smtplib
from email.mime.text import MIMEText
import re


def send_admin_alert(subject, body):
    """Alert admin when LLM fails or cannot extract information."""
    admin_mail = os.getenv("ADMIN_ALERT_EMAIL")
    if not admin_mail:
        print("⚠ ADMIN_ALERT_EMAIL not set — skipping alert")
        return

    EMAIL = os.getenv("EMAIL")
    PASSWORD = os.getenv("PASSWORD")
    SMTP_SERVER = os.getenv("SMTP_SERVER")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

    try:
        msg = MIMEText(body)
        msg["From"] = EMAIL
        msg["To"] = admin_mail
        msg["Subject"] = subject

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL, PASSWORD)
            server.send_message(msg)

        print(f"📩 Admin alert sent to {admin_mail}")
    except Exception as e:
        print(f"❌ Failed to send admin alert: {e}")




def sanitize_sensitive_numbers(text: str) -> str:
    if not text:
        return text

    # --------------------------
    # MASK CREDIT / DEBIT CARD (13–19 digits starting 3–6)
    # --------------------------
    def mask_card(match):
        s = re.sub(r"[ -]", "", match.group())  # remove spaces/hyphens first
        return "*" * len(s)

    text = re.sub(
        r'\b(?:3|4|5|6)(?:\d[ -]?){12,18}\b',
        lambda m: mask_card(m),
        text
    )

    # --------------------------
    # MASK PASSPORT (6–12 alphanumeric, must include both letters + digits)
    # avoid PNR / booking codes using exclusion rules
    # --------------------------
    def mask_passport(match):
        return "*" * len(match.group())

    text = re.sub(
        r'\b(?=[A-Z0-9]{6,12}\b)(?=.*[A-Z])(?=.*\d)(?![A-Z]{3,6}\d{2,6})(?!\d{6})[A-Z0-9]+\b',
        lambda m: mask_passport(m),
        text,
        flags=re.I
    )

    # --------------------------
    # MASK IBAN (must start with 2 letters + 2 digits + 10–30 alphanumerics)
    # --------------------------
    def mask_iban(match):
        return "*" * len(match.group())

    text = re.sub(
        r'\b[A-Z]{2}\d{2}[0-9A-Z]{10,30}\b',
        lambda m: mask_iban(m),
        text,
        flags=re.I
    )

    # normalize spaces
    text = re.sub(r'\s{2,}', ' ', text).strip()

    return text


def build_full_quoted_thread(threads_data, ticket_id, zoho_api):
    """Build complete email thread history with both bot and customer messages"""
    quoted = ""

    # Get all threads (both in and out)
    all_messages = []
    for t in threads_data.get("data", []):
        direction = t.get("direction")
        msg_date = t.get("createdTime", "")
        sender = t.get("fromEmailAddress") or t.get("email", "")
        thread_id = t.get("id")

        # Fetch full body
        body_data = zoho_api.get_thread_body(ticket_id, thread_id)
        text = (body_data.get("plainText") if isinstance(body_data, dict) else "") or t.get("content", "")

        if text.strip():
            all_messages.append({
                "date": msg_date,
                "sender": sender,
                "content": text.strip().replace('\n', '<br>'),
                "direction": direction
            })

    # Sort by date (oldest first)
    all_messages.sort(key=lambda x: x["date"])

    # Build quoted thread (reverse order for email display)
    for msg in reversed(all_messages):
        quoted += f"""<br><br>
<div class="gmail_quote">
On {msg['date']}, {msg['sender']} wrote:<br>
<blockquote class="gmail_quote" style="margin:0 0 0 .8ex;border-left:1px #ccc solid;padding-left:1ex">
{msg['content']}
</blockquote>
</div>
"""

    return quoted

def remove_quote(text):
    # Check if <email> exists
    if "<support@cozmotest.zohodesk.com>" in text:
        # 1) Split at <emailid>
        left_part = text.split("<support@cozmotest.zohodesk.com>")[0].strip()

        # 2) Remove last 8 words from left_part
        words = left_part.split()
        if len(words) > 8:
            return " ".join(words[:-8]).strip()
        else:
            return ""  # or return left_part if you want to keep it
    else:
        # If no <emailid>, return original text
        return text.strip()


