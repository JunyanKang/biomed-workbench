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
        elif command == "location":
            _emit(
                {
                    "passed": True,
                    "store": str(credential_store_path()),
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
