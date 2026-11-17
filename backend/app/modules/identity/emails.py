"""Email texts for password links, in the recipient's language.

The API returns codes, not text; email is the one place the backend writes
user-facing sentences, because nothing else renders them.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.mailer import Email

_SOFIA = ZoneInfo("Europe/Sofia")

_TEXTS = {
    "en": {
        "set": (
            "Your CRM account",
            "Hello {name},\n\nAn account has been created for you in the CRM.\n"
            "Set your password here:\n\n{url}\n\n"
            "The link can be used once and expires on {expires}.\n",
        ),
        "reset": (
            "Reset your CRM password",
            "Hello {name},\n\nA password reset was requested for your CRM account.\n"
            "Choose a new password here:\n\n{url}\n\n"
            "The link can be used once and expires on {expires}.\n"
            "If you did not ask for this, you can ignore this message.\n",
        ),
    },
    "bg": {
        "set": (
            "Вашият профил в CRM",
            "Здравейте, {name},\n\nВ CRM е създаден профил за вас.\n"
            "Задайте паролата си тук:\n\n{url}\n\n"
            "Връзката може да се използва веднъж и изтича на {expires}.\n",
        ),
        "reset": (
            "Нова парола за CRM",
            "Здравейте, {name},\n\nЗаявена е смяна на паролата за вашия профил в CRM.\n"
            "Изберете нова парола тук:\n\n{url}\n\n"
            "Връзката може да се използва веднъж и изтича на {expires}.\n"
            "Ако не сте заявили смяна, не е нужно да правите нищо.\n",
        ),
    },
}


def password_link_email(
    *, to: str, name: str, locale: str, purpose: str, url: str, expires_at: datetime
) -> Email:
    subject, body = _TEXTS.get(locale, _TEXTS["en"])[purpose]
    expires = expires_at.astimezone(_SOFIA).strftime("%d.%m.%Y %H:%M")
    return Email(to=to, subject=subject, body=body.format(name=name, url=url, expires=expires))
