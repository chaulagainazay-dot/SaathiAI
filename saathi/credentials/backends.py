"""M31 — Secure storage backend contract and test implementations.

No real secrets. No operator-approved live backends in M31.
"""
from __future__ import annotations

import json
import os
import stat
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional


class SecretBackendError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


class SecretBackend(ABC):
    """Backend contract — secret material never appears in exceptions."""

    kind: str = "base"

    @abstractmethod
    def put(self, locator: str, fields: dict[str, str]) -> None:
        ...

    @abstractmethod
    def get(self, locator: str, fields: Optional[list[str]] = None) -> dict[str, str]:
        ...

    @abstractmethod
    def exists(self, locator: str) -> bool:
        ...

    @abstractmethod
    def delete(self, locator: str) -> None:
        ...

    def readiness(self) -> dict[str, Any]:
        return {"kind": self.kind, "ready": True, "live_credentials": False}


class InMemoryTestSecretBackend(SecretBackend):
    """Deterministic process-local store for tests only."""

    kind = "in_memory_test"

    def __init__(self) -> None:
        self._data: dict[str, dict[str, str]] = {}
        self._lock = threading.RLock()
        self.fail_mode: str = ""  # write | read | delete | ""

    def put(self, locator: str, fields: dict[str, str]) -> None:
        if self.fail_mode == "write":
            raise SecretBackendError("secret_write_failure")
        with self._lock:
            self._data[locator] = dict(fields)

    def get(self, locator: str, fields: Optional[list[str]] = None) -> dict[str, str]:
        if self.fail_mode == "read":
            raise SecretBackendError("secret_read_failure")
        with self._lock:
            raw = self._data.get(locator)
            if raw is None:
                raise SecretBackendError("secret_not_found")
            if fields is None:
                return dict(raw)
            return {k: raw[k] for k in fields if k in raw}

    def exists(self, locator: str) -> bool:
        with self._lock:
            return locator in self._data

    def delete(self, locator: str) -> None:
        if self.fail_mode == "delete":
            raise SecretBackendError("secret_delete_failure")
        with self._lock:
            self._data.pop(locator, None)


class EnvironmentReferenceBackend(SecretBackend):
    """Resolves env var NAMES only as declared locators — never invents keys."""

    kind = "environment_reference"

    def __init__(self, environ: Optional[dict[str, str]] = None) -> None:
        self._env = environ if environ is not None else dict(os.environ)
        self._declared: dict[str, list[str]] = {}  # locator -> field env names

    def declare(self, locator: str, field_env_map: dict[str, str]) -> None:
        """field_name -> env var name (not value)."""
        self._declared[locator] = list(field_env_map.values())
        self._field_map = getattr(self, "_field_map", {})
        self._field_map[locator] = dict(field_env_map)

    def put(self, locator: str, fields: dict[str, str]) -> None:
        # Environment backend does not accept arbitrary puts of live secrets in M31
        raise SecretBackendError("env_backend_put_not_supported")

    def get(self, locator: str, fields: Optional[list[str]] = None) -> dict[str, str]:
        fmap = getattr(self, "_field_map", {}).get(locator) or {}
        if not fmap:
            raise SecretBackendError("undeclared_env_locator")
        out: dict[str, str] = {}
        want = fields or list(fmap.keys())
        for fname in want:
            ename = fmap.get(fname)
            if not ename:
                continue
            val = (self._env.get(ename) or "").strip()
            if val:
                out[fname] = val
        if not out:
            raise SecretBackendError("env_secret_missing")
        return out

    def exists(self, locator: str) -> bool:
        try:
            return bool(self.get(locator))
        except SecretBackendError:
            return False

    def delete(self, locator: str) -> None:
        raise SecretBackendError("env_backend_delete_not_supported")


class UnavailableSecureBackend(SecretBackend):
    kind = "unavailable"

    def put(self, locator: str, fields: dict[str, str]) -> None:
        raise SecretBackendError("backend_unavailable")

    def get(self, locator: str, fields: Optional[list[str]] = None) -> dict[str, str]:
        raise SecretBackendError("backend_unavailable")

    def exists(self, locator: str) -> bool:
        return False

    def delete(self, locator: str) -> None:
        raise SecretBackendError("backend_unavailable")

    def readiness(self) -> dict[str, Any]:
        return {"kind": self.kind, "ready": False, "live_credentials": False}


class EncryptedLocalTestBackend(SecretBackend):
    """Test-only local file backend using Fernet if available.

    NOT operator-approved for live credentials. Test keys must not be
    written into evidence packages.
    """

    kind = "encrypted_local_test"

    def __init__(self, root: Path, *, key: Optional[bytes] = None) -> None:
        self.root = Path(root)
        if self.root.is_symlink():
            raise SecretBackendError("symlink_path_rejected")
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, stat.S_IRWXU)  # 0o700
        except Exception:
            pass
        self._key = key
        self._fernet = None
        if key is not None:
            try:
                from cryptography.fernet import Fernet
                self._fernet = Fernet(key)
            except Exception:
                self._fernet = None
        self._lock = threading.RLock()

    def _path(self, locator: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in locator)[:120]
        p = (self.root / f"{safe}.bin").resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise SecretBackendError("path_escape_rejected")
        if p.is_symlink():
            raise SecretBackendError("symlink_path_rejected")
        return p

    def put(self, locator: str, fields: dict[str, str]) -> None:
        payload = json.dumps(fields, sort_keys=True).encode()
        if self._fernet:
            blob = self._fernet.encrypt(payload)
        else:
            # Fallback: obfuscation only — still test-only; document no crypto claim
            blob = b"M31TEST:" + payload
        path = self._path(locator)
        tmp = path.with_suffix(".tmp")
        with self._lock:
            tmp.write_bytes(blob)
            try:
                os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
            except Exception:
                pass
            tmp.replace(path)

    def get(self, locator: str, fields: Optional[list[str]] = None) -> dict[str, str]:
        path = self._path(locator)
        if not path.is_file():
            raise SecretBackendError("secret_not_found")
        blob = path.read_bytes()
        try:
            if self._fernet:
                raw = self._fernet.decrypt(blob)
            else:
                if not blob.startswith(b"M31TEST:"):
                    raise SecretBackendError("secret_read_failure")
                raw = blob[len(b"M31TEST:"):]
            data = json.loads(raw.decode())
        except SecretBackendError:
            raise
        except Exception:
            raise SecretBackendError("secret_read_failure")
        if fields is None:
            return dict(data)
        return {k: data[k] for k in fields if k in data}

    def exists(self, locator: str) -> bool:
        return self._path(locator).is_file()

    def delete(self, locator: str) -> None:
        path = self._path(locator)
        if path.is_file():
            path.unlink()

    def readiness(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "ready": True,
            "live_credentials": False,
            "operator_approved_for_live": False,
            "encryption": "fernet" if self._fernet else "test_obfuscation_only",
        }


# Approved backend kinds for broker construction (no arbitrary import)
APPROVED_BACKENDS: dict[str, type] = {
    "in_memory_test": InMemoryTestSecretBackend,
    "environment_reference": EnvironmentReferenceBackend,
    "unavailable": UnavailableSecureBackend,
    "encrypted_local_test": EncryptedLocalTestBackend,
}


def create_backend(kind: str, **kwargs: Any) -> SecretBackend:
    if kind not in APPROVED_BACKENDS:
        raise SecretBackendError(f"backend_not_allowed:{kind}")
    cls = APPROVED_BACKENDS[kind]
    if kind == "encrypted_local_test":
        return cls(kwargs.get("root") or Path("/tmp/m31_secrets_test"), key=kwargs.get("key"))
    if kind == "environment_reference":
        return cls(environ=kwargs.get("environ"))
    return cls()
