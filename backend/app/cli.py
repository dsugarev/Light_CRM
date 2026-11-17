"""Operator commands: `python -m app.cli <command>`.

Phase 0: `export-openapi`. Later phases add `create-admin` (Phase 1) and
`create-integration-client` (Phase 6).
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.core.config import Environment, Settings
from app.main import create_app


def export_openapi(output: Path | None) -> None:
    """Write the OpenAPI document; the frontend generates its API types from it."""
    # Development settings so the document is always produced, whatever ENV says.
    app = create_app(Settings(env=Environment.DEVELOPMENT))
    document = json.dumps(app.openapi(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(document)
    else:
        output.write_text(document, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    openapi = commands.add_parser("export-openapi", help="Write the OpenAPI document as JSON")
    openapi.add_argument("--output", type=Path, help="File to write; stdout when omitted")

    args = parser.parse_args(argv)
    if args.command == "export-openapi":
        export_openapi(args.output)


if __name__ == "__main__":
    main()
