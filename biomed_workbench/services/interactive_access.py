"""Private status records for browser-authenticated scientific services.

These records deliberately contain no password, OAuth token, browser cookie, or
recovery secret.  They let an agent explain the next safe interactive action
without pretending that a browser session is an injectable API credential.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


ALPHAFOLD_SERVER = "ALPHAFOLD_SERVER"
ALLOWED_INTERACTIVE_SERVICES = frozenset({ALPHAFOLD_SERVER})
ALLOWED_ACCESS_STATES = frozenset(
    {
        "not-configured",
        "ready",
        "authentication-error",
        "session-expired",
        "access-denied",
        "quota-exhausted",
        "terms-not-accepted",
    }
)
_STORE_FILENAME = "interactive-access.json"
_CONFIG_HOME_OVERRIDE = "BIOMED_WORKBENCH_CONFIG_HOME"
_ALPHAFOLD_SERVER_URL = "https://alphafoldserver.com/"
_ALPHAFOLD_SERVER_TERMS_URL = "https://alphafoldserver.com/output-terms"


def interactive_access_store_path() -> Path:
    override = os.environ.get(_CONFIG_HOME_OVERRIDE, "").strip()
    if override:
        return Path(override).expanduser().resolve() / _STORE_FILENAME
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "biomed-workbench"
    elif os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        root = root / "biomed-workbench"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        root = root / "biomed-workbench"
    return root / _STORE_FILENAME


def _validate_service(service: str) -> None:
    if service not in ALLOWED_INTERACTIVE_SERVICES:
        raise ValueError(f"interactive service is not allowlisted: {service}")


def _read_store() -> dict[str, dict[str, object]]:
    path = interactive_access_store_path()
    if not path.exists():
        return {}
    if path.is_symlink():
        raise PermissionError(f"interactive access store must not be a symbolic link: {path}")
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError(f"interactive access store permissions must be 0600 or stricter: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("interactive access store must contain a JSON object")
    result: dict[str, dict[str, object]] = {}
    forbidden = ("password", "token", "cookie", "secret", "credential", "recovery")
    for service, record in payload.items():
        _validate_service(str(service))
        if not isinstance(record, dict) or any(
            marker in str(key).lower() for key in record for marker in forbidden
        ):
            raise ValueError("interactive access records must never contain authentication secrets")
        state = record.get("state")
        if state not in ALLOWED_ACCESS_STATES - {"not-configured"}:
            raise ValueError(f"invalid interactive access state for {service}")
        result[str(service)] = dict(record)
    return result


def _write_store(values: Mapping[str, Mapping[str, object]]) -> None:
    path = interactive_access_store_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".interactive-access-", suffix=".json", dir=path.parent, text=True
    )
    temporary_path = Path(temporary_name)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(dict(sorted(values.items())), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _mask_account(value: str | None) -> str | None:
    if not value or "@" not in value:
        return None
    local, domain = value.split("@", 1)
    visible = local[:1]
    return f"{visible}{'*' * max(3, len(local) - 1)}@{domain}"


def configure_interactive_access(
    service: str,
    *,
    account: str,
    terms_reviewed: bool,
    state: str = "ready",
) -> None:
    """Record an observed browser-access state without storing login secrets."""

    _validate_service(service)
    normalized = account.strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+", normalized):
        raise ValueError("account must be a valid email address")
    if state not in ALLOWED_ACCESS_STATES - {"not-configured"}:
        raise ValueError(f"invalid interactive access state: {state}")
    if state == "ready" and not terms_reviewed:
        raise ValueError("ready status requires confirmation that current output terms were reviewed")
    now = datetime.now(timezone.utc).isoformat()
    values = _read_store()
    values[service] = {
        "account": normalized,
        "state": state,
        "checked_at": now,
        "terms_reviewed_at": now if terms_reviewed else None,
        "terms_url": _ALPHAFOLD_SERVER_TERMS_URL,
    }
    _write_store(values)


def mark_interactive_access(service: str, state: str) -> None:
    _validate_service(service)
    if state not in ALLOWED_ACCESS_STATES - {"not-configured", "ready"}:
        raise ValueError("mark state must describe an observed access problem")
    values = _read_store()
    if service not in values:
        raise ValueError("interactive service has no configured account record")
    values[service]["state"] = state
    values[service]["checked_at"] = datetime.now(timezone.utc).isoformat()
    _write_store(values)


def remove_interactive_access(service: str) -> bool:
    _validate_service(service)
    values = _read_store()
    removed = values.pop(service, None) is not None
    if not removed:
        return False
    if values:
        _write_store(values)
    else:
        interactive_access_store_path().unlink(missing_ok=True)
    return True


def interactive_access_status(service: str = ALPHAFOLD_SERVER) -> dict[str, object]:
    _validate_service(service)
    record = _read_store().get(service)
    state = str(record.get("state")) if record else "not-configured"
    next_action = {
        "not-configured": "Sign in interactively on the official AlphaFold Server, review current terms, then confirm the observed access state.",
        "ready": "Prepare a submission package; the user must review and submit it in the official browser session.",
        "authentication-error": "Sign in again on the official site; never paste or store the Google password in the workbench.",
        "session-expired": "Renew the official browser session before submission or result download.",
        "access-denied": "Resolve official account eligibility or access restrictions before submission.",
        "quota-exhausted": "Wait for the official quota window to reset or use an approved local deployment.",
        "terms-not-accepted": "Review and accept the current official terms before submission.",
    }[state]
    return {
        "service": service,
        "state": state,
        "configured": record is not None,
        "account_hint": _mask_account(str(record.get("account"))) if record else None,
        "authentication_mode": "interactive-google-sign-in",
        "password_stored": False,
        "token_stored": False,
        "checked_at": record.get("checked_at") if record else None,
        "terms_reviewed_at": record.get("terms_reviewed_at") if record else None,
        "service_url": _ALPHAFOLD_SERVER_URL,
        "terms_url": _ALPHAFOLD_SERVER_TERMS_URL,
        "next_action": next_action,
    }
