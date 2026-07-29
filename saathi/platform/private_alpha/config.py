"""M160 — Versioned local configuration contract for private alpha."""
from __future__ import annotations

import json
import re
import shutil
import time
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT / "data" / "alpha" / "config"
CONFIG_PATH = CONFIG_DIR / "alpha_config.json"
CONFIG_HISTORY = CONFIG_DIR / "history"
CONFIG_SCHEMA_VERSION = "m160.alpha_config.v1"

_SECRET_KEY_RE = re.compile(
    r"(password|secret|token|api[_-]?key|credential|authorization|cookie|private[_-]?key)",
    re.I,
)
_SECRET_VALUE_RE = re.compile(
    r"(sk-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})",
)


@dataclass
class AlphaConfig:
    schema_version: str = CONFIG_SCHEMA_VERSION
    host: str = "127.0.0.1"
    backend_port: int = 8765
    frontend_port: int = 3000
    database_path: str = "data/platform/platform.db"
    backup_path: str = "data/backups/system"
    log_path: str = "data/alpha/logs"
    release_channel: str = "private-alpha"
    local_provider_choices: dict[str, str] = field(
        default_factory=lambda: {"llm": "local_fixture", "voice": "disabled"}
    )
    notification_preferences: dict[str, Any] = field(
        default_factory=lambda: {"email": False, "in_app": True, "desktop": False}
    )
    automation_execution_enabled: bool = False  # global kill switch; default OFF
    demo_data_enabled: bool = True
    retention_days: int = 30
    transcript_retention_days: int = 7
    support_bundle_privacy: str = "strict"  # strict | standard
    production_authorized: bool = False
    public_exposure_authorized: bool = False
    first_run_completed: bool = False
    updated_at: float = 0.0

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        d["production_authorized"] = False
        d["public_exposure_authorized"] = False
        return d


def default_config() -> AlphaConfig:
    return AlphaConfig(updated_at=time.time())


def _reject_secrets(obj: Any, path: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_path = f"{path}.{k}" if path else str(k)
            if _SECRET_KEY_RE.search(str(k)):
                raise ValueError(f"secret-shaped key rejected: {key_path}")
            _reject_secrets(v, key_path)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _reject_secrets(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        if _SECRET_VALUE_RE.search(obj):
            raise ValueError(f"secret-shaped value rejected at {path or 'root'}")


def validate_config(raw: dict[str, Any] | AlphaConfig) -> dict[str, Any]:
    data = asdict(raw) if isinstance(raw, AlphaConfig) else dict(raw or {})
    _reject_secrets(data)

    host = str(data.get("host") or "127.0.0.1")
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError(f"unsafe host rejected (localhost-only): {host}")

    for port_key in ("backend_port", "frontend_port"):
        port = int(data.get(port_key) or 0)
        if not (1 <= port <= 65535):
            raise ValueError(f"invalid {port_key}: {port}")

    if data.get("production_authorized") is True:
        raise ValueError("production_authorized must be false for private alpha")
    if data.get("public_exposure_authorized") is True:
        raise ValueError("public_exposure_authorized must be false for private alpha")

    channel = str(data.get("release_channel") or "private-alpha")
    if channel not in ("private-alpha", "local-dev"):
        raise ValueError(f"unsupported release_channel: {channel}")

    privacy = str(data.get("support_bundle_privacy") or "strict")
    if privacy not in ("strict", "standard"):
        raise ValueError("support_bundle_privacy must be strict|standard")

    # Normalize safe defaults
    data["host"] = host
    data["schema_version"] = str(data.get("schema_version") or CONFIG_SCHEMA_VERSION)
    data["production_authorized"] = False
    data["public_exposure_authorized"] = False
    data["automation_execution_enabled"] = bool(
        data.get("automation_execution_enabled", False)
    )
    return data


def migrate_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Migrate older config schemas to current; never invent secrets."""
    data = dict(raw or {})
    ver = str(data.get("schema_version") or "")
    if not ver or ver in ("m160.alpha_config.v0", "0"):
        data.setdefault("host", "127.0.0.1")
        data.setdefault("backend_port", 8765)
        data.setdefault("frontend_port", 3000)
        data.setdefault("automation_execution_enabled", False)
        data.setdefault("demo_data_enabled", True)
        data.setdefault("support_bundle_privacy", "strict")
        data.setdefault("release_channel", "private-alpha")
        data["schema_version"] = CONFIG_SCHEMA_VERSION
    # Force safety flags on every migration
    data["production_authorized"] = False
    data["public_exposure_authorized"] = False
    if data.get("host") not in ("127.0.0.1", "localhost"):
        data["host"] = "127.0.0.1"
    return validate_config(data)


def load_config(path: Path | None = None) -> AlphaConfig:
    p = path or CONFIG_PATH
    if not p.exists():
        return default_config()
    raw = json.loads(p.read_text(encoding="utf-8"))
    data = migrate_config(raw)
    known = {f.name for f in AlphaConfig.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    filtered = {k: v for k, v in data.items() if k in known}
    return AlphaConfig(**filtered)


def _backup_existing(path: Path) -> Path | None:
    if not path.exists():
        return None
    CONFIG_HISTORY.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = CONFIG_HISTORY / f"alpha_config.{stamp}.json"
    shutil.copy2(path, dest)
    # retain last 20
    history = sorted(CONFIG_HISTORY.glob("alpha_config.*.json"))
    for old in history[:-20]:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


def save_config(cfg: AlphaConfig | dict[str, Any], path: Path | None = None) -> AlphaConfig:
    p = path or CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    data = validate_config(cfg)
    data["updated_at"] = time.time()
    _backup_existing(p)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return load_config(p)


def config_diff(a: dict | AlphaConfig, b: dict | AlphaConfig) -> dict[str, Any]:
    da = asdict(a) if isinstance(a, AlphaConfig) else dict(a)
    db = asdict(b) if isinstance(b, AlphaConfig) else dict(b)
    changed = {}
    keys = set(da) | set(db)
    for k in sorted(keys):
        if da.get(k) != db.get(k):
            changed[k] = {"from": da.get(k), "to": db.get(k)}
    return {"changed": changed, "count": len(changed)}


def rollback_config(path: Path | None = None) -> AlphaConfig:
    """Restore most recent history snapshot."""
    p = path or CONFIG_PATH
    history = sorted(CONFIG_HISTORY.glob("alpha_config.*.json"))
    if not history:
        raise FileNotFoundError("no configuration history to roll back")
    prev = history[-1]
    data = migrate_config(json.loads(prev.read_text(encoding="utf-8")))
    # Do not re-backup the same file into history as latest again
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return load_config(p)


def precedence_rules() -> dict[str, Any]:
    return {
        "order": [
            "safe_defaults",
            "alpha_config.json",
            "explicit_cli_flags",
            "never_raw_environment_for_secrets",
        ],
        "notes": [
            "Environment variables never override production_authorized or host binding.",
            "Secret-shaped keys and values are rejected at validation time.",
            "No raw environment dump is ever emitted by config surfaces.",
        ],
    }
