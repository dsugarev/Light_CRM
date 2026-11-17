"""Operator commands: `python -m app.cli <command>`.

Commands: `export-openapi`, `create-admin`. Phase 6 adds
`create-integration-client`.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.core.clock import SystemClock
from app.core.config import Environment, Settings, get_settings
from app.core.db import create_engine, create_session_factory
from app.core.errors import AppError
from app.core.mailer import create_mailer
from app.main import create_app, create_event_bus
from app.modules.identity import service as identity_service


def export_openapi(output: Path | None) -> None:
    """Write the OpenAPI document; the frontend generates its API types from it."""
    # Development settings so the document is always produced, whatever ENV says.
    app = create_app(Settings(env=Environment.DEVELOPMENT))
    document = json.dumps(app.openapi(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(document)
    else:
        output.write_text(document, encoding="utf-8")


async def create_admin(email: str, full_name: str, locale: str, password: str | None) -> int:
    """Create an Admin. Prints a one-time set-password link, or sets the password
    read from stdin (for automation); a password is never a command-line argument."""
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            ctx = identity_service.Context(
                session=session,
                events=create_event_bus(),
                settings=settings,
                mailer=create_mailer(settings),
                now=SystemClock().now(),
            )
            created = await identity_service.create_admin(
                ctx, email=email, full_name=full_name, locale=locale, password=password
            )
    except AppError as error:
        codes = ", ".join(e.code for e in error.errors) or error.code.value
        print(f"Could not create the admin: {codes}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    print(f"Created admin {created.user.email} ({created.user.id}).")
    if password is None:
        expires = f"{created.set_password.expires_at:%Y-%m-%d %H:%M}"
        print(f"Set the password here (valid until {expires} UTC):")
        print(created.set_password.url)
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    openapi = commands.add_parser("export-openapi", help="Write the OpenAPI document as JSON")
    openapi.add_argument("--output", type=Path, help="File to write; stdout when omitted")

    admin = commands.add_parser("create-admin", help="Create an Admin user (first run)")
    admin.add_argument("--email", required=True)
    admin.add_argument("--full-name", required=True)
    admin.add_argument("--locale", choices=["en", "bg"], default="en")
    admin.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from stdin instead of printing a set-password link",
    )

    args = parser.parse_args(argv)
    if args.command == "export-openapi":
        export_openapi(args.output)
    elif args.command == "create-admin":
        password = sys.stdin.readline().rstrip("\n") if args.password_stdin else None
        raise SystemExit(
            asyncio.run(create_admin(args.email, args.full_name, args.locale, password))
        )


if __name__ == "__main__":
    main()
