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


# Notices after a change to how the user signs in (ASVS 2.2.3, 2.5.5), sent only when SMTP
# is configured (owner answer to requirements open question 4).
_NOTICES = {
    "en": {
        "password_changed": "your password was changed",
        "password_reset": "your password was reset with a one-time link",
        "mfa_enabled": "two-factor sign-in was turned on",
        "mfa_disabled": "two-factor sign-in was turned off",
        "mfa_reset": "two-factor sign-in was switched off by an administrator",
    },
    "bg": {
        "password_changed": "паролата ви беше сменена",
        "password_reset": "паролата ви беше подновена чрез еднократна връзка",
        "mfa_enabled": "двуфакторното влизане беше включено",
        "mfa_disabled": "двуфакторното влизане беше изключено",
        "mfa_reset": "двуфакторното влизане беше изключено от администратор",
    },
}
_NOTICE_TEXTS = {
    "en": (
        "Security notice for your CRM account",
        "Hello {name},\n\nOn {when} {what}.\n\n"
        "If this was you, there is nothing to do. If it was not, contact your CRM "
        "administrator at once.\n",
    ),
    "bg": (
        "Известие за сигурност за профила ви в CRM",
        "Здравейте, {name},\n\nНа {when} {what}.\n\n"
        "Ако това сте били вие, не е нужно да правите нищо. Ако не сте, свържете се "
        "незабавно с администратора на CRM.\n",
    ),
}


def security_notice_email(*, to: str, name: str, locale: str, kind: str, at: datetime) -> Email:
    language = locale if locale in _NOTICE_TEXTS else "en"
    subject, body = _NOTICE_TEXTS[language]
    when = at.astimezone(_SOFIA).strftime("%d.%m.%Y %H:%M")
    what = _NOTICES[language][kind]
    return Email(to=to, subject=subject, body=body.format(name=name, when=when, what=what))
