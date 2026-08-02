#!/usr/bin/env python3
"""Configure optional scientific-service credentials without exposing values."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.services.credentials import (  # noqa: E402
    ALLOWED_CREDENTIALS,
    configure_credential,
    credential_sources,
    credential_store_path,
    remove_credential,
)
from biomed_workbench.services.interactive_access import (  # noqa: E402
    ALLOWED_ACCESS_STATES,
    ALLOWED_INTERACTIVE_SERVICES,
    configure_interactive_access,
    interactive_access_status,
    interactive_access_store_path,
    mark_interactive_access,
    remove_interactive_access,
)


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manage optional scientific-service credentials in a private, "
            "repository-external user store."
        )
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="Show configuration state without values.")

    set_parser = subparsers.add_parser("set", help="Configure a credential using hidden input.")
    set_parser.add_argument("name", choices=sorted(ALLOWED_CREDENTIALS))
    set_parser.add_argument("--stdin", action="store_true", help=argparse.SUPPRESS)

    remove_parser = subparsers.add_parser("remove", help="Remove a stored credential.")
    remove_parser.add_argument("name", choices=sorted(ALLOWED_CREDENTIALS))
    connect_parser = subparsers.add_parser(
        "connect-service",
        help="Record a browser-authenticated service after the user signs in and reviews terms.",
    )
    connect_parser.add_argument("service", choices=sorted(ALLOWED_INTERACTIVE_SERVICES))
    connect_parser.add_argument("--account-stdin", action="store_true", help=argparse.SUPPRESS)
    connect_parser.add_argument("--terms-reviewed", action="store_true", required=True)
    mark_parser = subparsers.add_parser(
        "mark-service", help="Record an observed browser-access problem."
    )
    mark_parser.add_argument("service", choices=sorted(ALLOWED_INTERACTIVE_SERVICES))
    mark_parser.add_argument(
        "state",
        choices=sorted(ALLOWED_ACCESS_STATES - {"not-configured", "ready"}),
    )
    disconnect_parser = subparsers.add_parser(
        "disconnect-service", help="Remove a local browser-access status record."
    )
    disconnect_parser.add_argument("service", choices=sorted(ALLOWED_INTERACTIVE_SERVICES))
    subparsers.add_parser("location", help="Show the private store location.")
    return parser


def _read_secret(name: str, *, from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass(f"{name}: ")
    second = getpass.getpass(f"Confirm {name}: ")
    if first != second:
        raise ValueError("entries did not match; no credential was saved")
    return first


def _read_account(service: str, *, from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    return getpass.getpass(f"{service} account email (hidden): ")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = args.command or "status"
    try:
        if command == "status":
            _emit(
                {
                    "passed": True,
                    "credentials": credential_sources(),
                    "interactive_services": {
                        service: interactive_access_status(service)
                        for service in sorted(ALLOWED_INTERACTIVE_SERVICES)
                    },
                    "core_use_requires_credentials": False,
                }
            )
        elif command == "set":
            configure_credential(args.name, _read_secret(args.name, from_stdin=args.stdin))
            _emit(
                {
                    "passed": True,
                    "credential": args.name,
                    "configured": True,
                    "source": credential_sources()[args.name],
                    "value_exposed": False,
                }
            )
        elif command == "remove":
            removed = remove_credential(args.name)
            _emit(
                {
                    "passed": True,
                    "credential": args.name,
                    "removed_from_local_store": removed,
                    "source": credential_sources()[args.name],
                }
            )
        elif command == "connect-service":
            configure_interactive_access(
                args.service,
                account=_read_account(args.service, from_stdin=args.account_stdin),
                terms_reviewed=args.terms_reviewed,
            )
            _emit({"passed": True, "interactive_service": interactive_access_status(args.service)})
        elif command == "mark-service":
            mark_interactive_access(args.service, args.state)
            _emit({"passed": True, "interactive_service": interactive_access_status(args.service)})
        elif command == "disconnect-service":
            removed = remove_interactive_access(args.service)
            _emit(
                {
                    "passed": True,
                    "removed_from_local_store": removed,
                    "interactive_service": interactive_access_status(args.service),
                }
            )
        elif command == "location":
            _emit(
                {
                    "passed": True,
                    "credential_store": str(credential_store_path()),
                    "interactive_access_store": str(interactive_access_store_path()),
                    "repository_external": True,
                }
            )
        else:
            parser.error(f"unsupported command: {command}")
    except (OSError, PermissionError, ValueError, json.JSONDecodeError) as exc:
        _emit({"passed": False, "error": str(exc), "value_exposed": False})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
