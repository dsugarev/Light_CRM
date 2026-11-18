"""Operator commands: `python -m app.cli <command>`.

Commands: `export-openapi`, `create-admin`, `create-integration-client`, `seed-demo`
(test and demo environments).
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app import seed
from app.core.clock import SystemClock
from app.core.config import Environment, Settings, get_settings
from app.core.db import create_engine, create_session_factory
from app.core.errors import AppError
from app.core.mailer import create_mailer
from app.main import create_app, create_event_bus
from app.modules.identity import service as identity_service
from app.modules.integration import service as integration_service
from app.modules.integration.schemas import IntegrationClientCreate


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


async def create_integration_clients(systems: Sequence[str]) -> int:
    """API spec 19.9: the initial clients with their read-only profiles, inactive and
    without keys until an Admin issues them (FR-INT-01)."""
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            ctx = integration_service.Context(
                session=session, events=create_event_bus(), settings=settings,
                now=SystemClock().now(),
            )  # fmt: skip
            existing = {c.system.code for c in await integration_service.list_clients(ctx)}
            for system in systems:
                if system in existing:
                    print(f"{system}: a client already exists, skipped.")
                    continue
                name, scopes = integration_service.PROFILES[system]
                created = await integration_service.create_client(
                    ctx,
                    None,
                    IntegrationClientCreate.model_validate(
                        {"name": name, "system": system, "scopes": scopes, "is_active": False}
                    ),
                )
                print(f"{system}: created {created.name} ({created.id}), inactive, no keys.")
    except AppError as error:
        print(f"Could not create the client: {error.code.value}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    return 0


async def reset_mfa(email: str) -> int:
    """Switch two-factor sign-in off for a user who lost the device and the recovery
    codes (operations guide). Their sessions end; the change is audited."""
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            done = await identity_service.reset_mfa(
                session, create_event_bus(), SystemClock().now(), email, create_mailer(settings)
            )
    finally:
        await engine.dispose()
    if not done:
        print(f"No user with the email {email}.", file=sys.stderr)
        return 1
    print(f"Two-factor sign-in switched off for {email}; they can set it up again.")
    return 0


async def seed_demo(counts: seed.Counts, seed_value: int) -> int:
    """NFR-01 volumes of fictional data; refused in production."""
    settings = get_settings()
    if settings.is_production:
        print("seed-demo is not available in production.", file=sys.stderr)
        return 1
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            created = await seed.seed(session, counts, seed=seed_value)
    except RuntimeError as error:
        print(f"Could not seed: {error}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    print("Created " + ", ".join(f"{n} {kind}" for kind, n in created.items()) + ".")
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

    clients = commands.add_parser(
        "create-integration-client",
        help="Create the Conclusion, ERP and Billing clients (API spec 19.9), inactive",
    )
    clients.add_argument(
        "--system",
        choices=[*integration_service.PROFILES, "all"],
        default="all",
        help="One system, or all three",
    )

    reset = commands.add_parser(
        "reset-mfa", help="Switch off two-factor sign-in for a user who lost their device"
    )
    reset.add_argument("--email", required=True)

    demo = commands.add_parser("seed-demo", help="Insert fictional data (not in production)")
    defaults = seed.Counts()
    for kind in ("organizations", "contacts", "leads", "opportunities"):
        demo.add_argument(f"--{kind}", type=int, default=getattr(defaults, kind))
    demo.add_argument("--seed", type=int, default=1, help="Random seed (same data each time)")

    args = parser.parse_args(argv)
    if args.command == "export-openapi":
        export_openapi(args.output)
    elif args.command == "create-admin":
        password = sys.stdin.readline().rstrip("\n") if args.password_stdin else None
        raise SystemExit(
            asyncio.run(create_admin(args.email, args.full_name, args.locale, password))
        )
    elif args.command == "create-integration-client":
        systems = list(integration_service.PROFILES) if args.system == "all" else [args.system]
        raise SystemExit(asyncio.run(create_integration_clients(systems)))
    elif args.command == "reset-mfa":
        raise SystemExit(asyncio.run(reset_mfa(args.email)))
    elif args.command == "seed-demo":
        counts = seed.Counts(
            organizations=args.organizations,
            contacts=args.contacts,
            leads=args.leads,
            opportunities=args.opportunities,
        )
        raise SystemExit(asyncio.run(seed_demo(counts, args.seed)))


if __name__ == "__main__":
    main()
