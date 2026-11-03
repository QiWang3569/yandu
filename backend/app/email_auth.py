"""Email ownership proof for registered accounts."""
import hashlib
import hmac
import re
import secrets
import smtplib
import ssl
from email.message import EmailMessage

import certifi


EMAIL_PATTERN = re.compile(
    r'^[a-z0-9][a-z0-9._%+-]*@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+'
    r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$',
    re.IGNORECASE,
)


def normalize_email(value: str) -> str | None:
    email = value.strip().lower()
    local_part = email.partition('@')[0]
    return email if len(email) <= 254 and len(local_part) <= 64 and EMAIL_PATTERN.fullmatch(email) else None


def code_digest(secret: str, challenge_id: str, email: str, code: str) -> str:
    return hmac.new(secret.encode(), f'{challenge_id}:{email}:{code}'.encode(), hashlib.sha256).hexdigest()


def new_code() -> str:
    return f'{secrets.randbelow(100_000_000):08d}'


def send_verification_email(settings, recipient: str, code: str) -> None:
    message = EmailMessage()
    message['Subject'] = '燕渡邮箱验证码'
    message['From'] = settings.smtp_from
    message['To'] = recipient
    message.set_content(f'你的燕渡验证码是 {code}，可用于注册、登录或设置密码，10 分钟内有效。若非本人操作，请忽略此邮件。')
    context = ssl.create_default_context(cafile=certifi.where())
    if settings.smtp_port in {465, 994}:
        client = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=8, context=context)
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8)
    with client:
        if settings.smtp_port not in {465, 994}:
            client.starttls(context=context)
        if settings.smtp_user:
            client.login(settings.smtp_user, settings.smtp_password)
        client.send_message(message)
