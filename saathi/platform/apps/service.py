"""Universal Application Runtime (M121–M129).

Centralized app lifecycle. Extends ModuleRegistry for navigation composition.
Applications consume Conversation, Knowledge, Skills, Workers, ExecutionGateway,
and Approvals — they never bypass them.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any

from saathi.platform.apps import limits
from saathi.platform.apps.models import (
    APP_ID_RE,
    EXECUTABLE_STATES,
    EXECUTABLE_TRUST,
    VERSION_RE,
    AppBackupRecord,
    AppHealthState,
    AppLifecycleState,
    AppManifest,
    AppRecord,
    AppTrustState,
    content_hash,
    now_ts,
    validate_transition,
)
from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import PlatformPermission, new_id, role_has_permission

APPS_KEY = "m121_apps"
APP_BACKUPS_KEY = "m121_app_backups"
APP_METRICS_KEY = "m121_app_metrics"
APP_EVENTS_KEY = "m121_app_events"
APP_DISCOVERED_KEY = "m121_app_discovered"
SCHEMA = "m121.app_runtime.v1"


def _packages_root() -> Path:
    return Path(__file__).resolve().parent / "packages"


class AppRuntime:
    """Application registry + lifecycle + workspace + backup coordinator."""

    def __init__(self, platform=None, module_registry=None):
        if platform is None:
            from saathi.platform.service import default_platform

            platform = default_platform()
        self.platform = platform
        self.store = platform.store
        self._module_registry = module_registry
        self._lock = threading.RLock()

    def _modules(self):
        if self._module_registry is not None:
            return self._module_registry
        from saathi.platform.module_registry import get_registry

        return get_registry()

    def _read(self, ctx: PlatformExecutionContext) -> None:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)

    def _operate(self, ctx: PlatformExecutionContext) -> None:
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)

    def _audit(self, ctx, event: str, *, outcome: str = "OK", detail: dict | None = None) -> None:
        self.platform._audit(event, ctx, outcome=outcome, detail=detail or {})

    def _apps(self) -> dict[str, dict]:
        return dict(self.store.get_config(APPS_KEY, {}) or {})

    def _save_apps(self, apps: dict) -> None:
        self.store.set_config(APPS_KEY, apps, updated_by="m121")

    def _backups(self) -> dict[str, dict]:
        return dict(self.store.get_config(APP_BACKUPS_KEY, {}) or {})

    def _save_backups(self, backups: dict) -> None:
        self.store.set_config(APP_BACKUPS_KEY, backups, updated_by="m121")

    def _metrics(self) -> dict[str, Any]:
        return dict(self.store.get_config(APP_METRICS_KEY, {}) or {})

    def _bump(self, key: str, n: int = 1) -> None:
        m = self._metrics()
        m[key] = int(m.get(key, 0) or 0) + n
        self.store.set_config(APP_METRICS_KEY, m, updated_by="m121")

    def _key(self, app_id: str, version: str, org_id: str, workspace_id: str) -> str:
        return f"{org_id}:{workspace_id}:{app_id}@{version}"

    def _event(self, ctx, kind: str, **detail) -> None:
        events = list(self.store.get_config(APP_EVENTS_KEY, []) or [])
        events.append(
            {
                "at": now_ts(),
                "kind": kind,
                "org_id": ctx.org_id,
                "workspace_id": ctx.workspace_id,
                **detail,
            }
        )
        self.store.set_config(
            APP_EVENTS_KEY, events[-limits.MAX_RETAINED_EVENTS :], updated_by="m121"
        )

    # ── health ───────────────────────────────────────────────────────────
    def health(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._read(ctx)
        apps = [
            AppRecord.from_dict(a)
            for a in self._apps().values()
            if a.get("org_id") == ctx.org_id and a.get("workspace_id") == ctx.workspace_id
        ]
        by_life: dict[str, int] = {}
        for a in apps:
            by_life[a.lifecycle_state] = by_life.get(a.lifecycle_state, 0) + 1
        modules = self._modules()
        return {
            "schema_version": SCHEMA,
            "runtime_version": limits.RUNTIME_VERSION,
            "extends": ["ModuleRegistry", "SkillRuntime", "ExecutionGateway"],
            "replaces_module_registry": False,
            "replaces_skill_runtime": False,
            "production_authorized": False,
            "marketplace_authorized": False,
            "remote_install_authorized": False,
            "public_listener": False,
            "installed_apps": len(apps),
            "lifecycle_counts": by_life,
            "module_registry_count": len(getattr(modules, "_modules", {}) or modules.list_modules() if hasattr(modules, "list_modules") else []),
            "metrics": self._metrics(),
            "execution_authority": "PlatformAgentRuntime→ExecutionGateway",
            "apps_may_bypass_gateway": False,
            "trading_guardian": "UNCHANGED",
        }

    # ── discovery / validation ───────────────────────────────────────────
    def discover(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._read(ctx)
        root = _packages_root()
        found = []
        if not root.is_dir():
            return {"discovered": [], "count": 0, "marketplace": False}
        packages = sorted(
            [p for p in root.iterdir() if p.is_dir() and (p / "app.json").is_file()]
        )[: limits.MAX_DISCOVERED_APPS]
        for pkg in packages:
            if pkg.is_symlink():
                found.append(
                    {"package_id": pkg.name, "valid": False, "errors": ["symlink_forbidden"]}
                )
                continue
            try:
                pkg.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            v = self.validate_package(ctx, package_id=pkg.name)
            raw = {}
            try:
                raw = json.loads((pkg / "app.json").read_text(encoding="utf-8"))
            except Exception:
                pass
            found.append(
                {
                    "package_id": pkg.name,
                    "app_id": raw.get("app_id"),
                    "version": raw.get("version"),
                    "display_name": raw.get("display_name"),
                    "app_type": raw.get("app_type"),
                    "valid": v.get("ok"),
                    "errors": v.get("errors") or [],
                }
            )
        self.store.set_config(
            APP_DISCOVERED_KEY, {"at": now_ts(), "items": found}, updated_by="m121"
        )
        self._bump("discoveries")
        self._audit(ctx, "app.discover", detail={"count": len(found)})
        return {
            "discovered": found,
            "count": len(found),
            "source": "builtin_packages",
            "marketplace": False,
            "remote_sources": [],
        }

    def validate_package(
        self, ctx: PlatformExecutionContext, *, package_id: str
    ) -> dict[str, Any]:
        self._read(ctx)
        errors: list[str] = []
        if not package_id or ".." in package_id or package_id.startswith("/") or "\\" in package_id:
            return {"ok": False, "errors": ["path_traversal"]}
        root = _packages_root()
        package_dir = root / package_id
        if not (package_dir / "app.json").is_file():
            return {"ok": False, "errors": ["package_not_found"]}
        if package_dir.is_symlink():
            return {"ok": False, "errors": ["symlink_package_root"]}
        try:
            raw_bytes = (package_dir / "app.json").read_bytes()
            if len(raw_bytes) > limits.MAX_MANIFEST_BYTES:
                return {"ok": False, "errors": ["manifest_too_large"]}
            data = json.loads(raw_bytes.decode("utf-8"))
        except Exception as e:
            return {"ok": False, "errors": [f"manifest_read:{e}"]}
        if not isinstance(data, dict):
            return {"ok": False, "errors": ["manifest_not_object"]}

        known = {f.name for f in AppManifest.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        unknown = set(data.keys()) - known - {"extension"}
        if unknown:
            errors.append("unknown_critical_fields:" + ",".join(sorted(unknown)))

        try:
            m = AppManifest.from_dict(data)
        except TypeError as e:
            return {"ok": False, "errors": [f"shape:{e}"]}

        if m.manifest_schema_version != limits.MANIFEST_SCHEMA_VERSION:
            errors.append(f"schema:{m.manifest_schema_version}")
        if not APP_ID_RE.match(m.app_id or ""):
            errors.append("invalid_app_id")
        if not VERSION_RE.match(m.version or ""):
            errors.append("invalid_version")
        if m.app_type not in limits.APP_TYPES:
            errors.append(f"unknown_app_type:{m.app_type}")
        if m.entrypoint_type in limits.FORBIDDEN_ENTRYPOINT_TYPES:
            errors.append(f"forbidden_entrypoint:{m.entrypoint_type}")
        if m.entrypoint_type not in limits.ALLOWED_ENTRYPOINT_TYPES:
            errors.append(f"unknown_entrypoint:{m.entrypoint_type}")
        if m.production_posture not in ("not_authorized", "forbidden", "disabled"):
            errors.append(f"production_posture:{m.production_posture}")
        if m.network_requirements not in ("none", "loopback"):
            errors.append(f"network:{m.network_requirements}")
        caps = set(m.capabilities or [])
        if caps - limits.KNOWN_CAPABILITIES:
            errors.append(
                "unknown_capabilities:" + ",".join(sorted(caps - limits.KNOWN_CAPABILITIES))
            )
        if len(m.navigation or []) > limits.MAX_NAV_ITEMS:
            errors.append("too_many_nav_items")
        if len(m.pages or []) > limits.MAX_PAGES:
            errors.append("too_many_pages")
        if len(m.skills or []) > limits.MAX_SKILLS:
            errors.append("too_many_skills")
        if "direct_tool_execution" in (m.capabilities or []):
            errors.append("capability_forgery")
        if "bypass_gateway" in (m.feature_flags or {}):
            if m.feature_flags.get("bypass_gateway"):
                errors.append("gateway_bypass_forbidden")

        # package files
        total = 0
        file_count = 0
        h = hashlib.sha256()
        # package_hash feeds a stored equality check, so the walk must be
        # ordered by name and not by directory read order. os.walk yields
        # whatever readdir gives it, which differs per filesystem: the same
        # package hashes one way on APFS and another on ext4, and a hash pinned
        # on one host then fails validation on the other.
        for dirpath, dirnames, filenames in os.walk(package_dir):
            dirnames[:] = sorted(
                d for d in dirnames if not (Path(dirpath) / d).is_symlink()
            )
            for fn in sorted(filenames):
                fp = Path(dirpath) / fn
                if fp.is_symlink():
                    errors.append(f"symlink_file:{fn}")
                    continue
                if fp.suffix.lower() not in {".json", ".md", ".txt", ".yaml", ".yml", ""}:
                    errors.append(f"disallowed_file:{fn}")
                try:
                    size = fp.stat().st_size
                except OSError:
                    errors.append(f"stat:{fn}")
                    continue
                total += size
                file_count += 1
                if fp.name != "app.json":
                    h.update(str(fp.relative_to(package_dir)).encode())
                    h.update(fp.read_bytes())
        if file_count > limits.MAX_PACKAGE_FILES:
            errors.append("too_many_files")
        if total > limits.MAX_PACKAGE_BYTES:
            errors.append("package_too_large")
        package_hash = h.hexdigest()
        if m.package_hash and m.package_hash != package_hash:
            errors.append("package_hash_mismatch")

        ok = len(errors) == 0
        self._bump("validations")
        if not ok:
            self._bump("invalid_packages")
        return {
            "ok": ok,
            "errors": errors,
            "app_id": m.app_id,
            "version": m.version,
            "manifest_hash": m.compute_content_hash(),
            "package_hash": package_hash,
        }

    # ── lifecycle ────────────────────────────────────────────────────────
    def register(
        self, ctx: PlatformExecutionContext, *, package_id: str
    ) -> dict[str, Any]:
        self._operate(ctx)
        with self._lock:
            v = self.validate_package(ctx, package_id=package_id)
            if not v["ok"]:
                raise PlatformContextError(
                    "APP_INVALID", "; ".join(v["errors"][:8]) or "invalid"
                )
            package_dir = _packages_root() / package_id
            data = json.loads((package_dir / "app.json").read_text(encoding="utf-8"))
            m = AppManifest.from_dict(data)
            m.package_hash = v["package_hash"]
            m.content_hash = v["manifest_hash"]
            trust = m.local_trust_status
            if trust not in (
                AppTrustState.BUILT_IN.value,
                AppTrustState.TRUSTED_LOCAL.value,
                AppTrustState.DEVELOPMENT_LOCAL.value,
            ):
                raise PlatformContextError("APP_UNTRUSTED", trust)

            key = self._key(m.app_id, m.version, ctx.org_id, ctx.workspace_id)
            apps = self._apps()
            if key in apps:
                raise PlatformContextError(
                    "APP_ALREADY_REGISTERED", f"{m.app_id}@{m.version}"
                )
            now = now_ts()
            rec = AppRecord(
                install_id=new_id("app_"),
                app_id=m.app_id,
                version=m.version,
                lifecycle_state=AppLifecycleState.INSTALLED.value,
                trust_state=trust,
                health_state=AppHealthState.DISABLED.value,
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                package_hash=v["package_hash"],
                manifest_hash=v["manifest_hash"],
                effective=False,
                installed_at=now,
                updated_at=now,
                source_path=package_id,
                manifest=m.to_public(),
                workspace_config={
                    "isolated": True,
                    "storage_prefix": f"app:{m.app_id}:{ctx.workspace_id}",
                    "pages": m.pages,
                    "navigation": m.navigation,
                    "settings": {},
                },
            )
            apps[key] = rec.to_public()
            self._save_apps(apps)
            self._sync_module_registry(rec, enabled=False)
            self._audit(
                ctx,
                "app.registered",
                detail={"app_id": m.app_id, "version": m.version, "install_id": rec.install_id},
            )
            self._event(ctx, "registered", app_id=m.app_id, version=m.version)
            self._bump("registrations")
            return {"app": rec.to_public(), "note": "installed_disabled"}

    def list_apps(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._read(ctx)
        out = [
            AppRecord.from_dict(a).to_public()
            for a in self._apps().values()
            if a.get("org_id") == ctx.org_id
            and a.get("workspace_id") == ctx.workspace_id
            and a.get("lifecycle_state") != AppLifecycleState.UNINSTALLED.value
        ]
        out.sort(key=lambda x: (x["app_id"], x["version"]))
        return {"apps": out, "count": len(out)}

    def get_app(
        self, ctx: PlatformExecutionContext, app_id: str, *, version: str = ""
    ) -> dict[str, Any]:
        self._read(ctx)
        rec = self._find(ctx, app_id, version=version)
        return {
            "app": rec.to_public(),
            "navigation": self.navigation_for(ctx, app_id, version=rec.version),
            "workspace": self.workspace_for(ctx, app_id, version=rec.version),
            "permissions": self.resolve_permissions(ctx, app_id, version=rec.version),
            "integrations": self.integrations(ctx, app_id, version=rec.version),
            "versions": [
                AppRecord.from_dict(a).to_public()
                for a in self._apps().values()
                if a.get("app_id") == app_id
                and a.get("org_id") == ctx.org_id
                and a.get("workspace_id") == ctx.workspace_id
            ],
        }

    def _find(
        self,
        ctx: PlatformExecutionContext,
        app_id: str,
        *,
        version: str = "",
        require_effective: bool = False,
    ) -> AppRecord:
        cands = [
            AppRecord.from_dict(a)
            for a in self._apps().values()
            if a.get("app_id") == app_id
            and a.get("org_id") == ctx.org_id
            and a.get("workspace_id") == ctx.workspace_id
        ]
        if not cands:
            raise PlatformContextError("APP_NOT_FOUND", "unknown app")
        if version:
            for c in cands:
                if c.version == version:
                    return c
            raise PlatformContextError("APP_NOT_FOUND", "version not found")
        if require_effective:
            for c in cands:
                if c.effective and c.lifecycle_state in EXECUTABLE_STATES:
                    return c
        cands.sort(key=lambda c: (c.effective, c.version), reverse=True)
        return cands[0]

    def _persist(self, rec: AppRecord) -> None:
        apps = self._apps()
        apps[self._key(rec.app_id, rec.version, rec.org_id, rec.workspace_id)] = rec.to_public()
        self._save_apps(apps)

    def enable(self, ctx: PlatformExecutionContext, app_id: str, *, version: str = "") -> dict[str, Any]:
        self._operate(ctx)
        with self._lock:
            rec = self._find(ctx, app_id, version=version)
            if rec.trust_state not in EXECUTABLE_TRUST and rec.trust_state != AppTrustState.DEVELOPMENT_LOCAL.value:
                raise PlatformContextError("APP_UNTRUSTED", rec.trust_state)
            if rec.lifecycle_state in (
                AppLifecycleState.QUARANTINED.value,
                AppLifecycleState.REVOKED.value,
            ):
                raise PlatformContextError("APP_BLOCKED", rec.lifecycle_state)
            # only one effective version
            apps = self._apps()
            for k, raw in list(apps.items()):
                if (
                    raw.get("app_id") == app_id
                    and raw.get("org_id") == ctx.org_id
                    and raw.get("workspace_id") == ctx.workspace_id
                    and raw.get("install_id") != rec.install_id
                    and raw.get("effective")
                ):
                    other = AppRecord.from_dict(raw)
                    other.effective = False
                    if other.lifecycle_state in EXECUTABLE_STATES:
                        other.lifecycle_state = AppLifecycleState.DISABLED.value
                        other.health_state = AppHealthState.DISABLED.value
                    apps[k] = other.to_public()
            rec.effective = True
            rec.lifecycle_state = AppLifecycleState.ENABLED.value
            rec.health_state = AppHealthState.HEALTHY.value
            rec.updated_at = now_ts()
            apps[self._key(rec.app_id, rec.version, rec.org_id, rec.workspace_id)] = rec.to_public()
            self._save_apps(apps)
            self._sync_module_registry(rec, enabled=True)
            self._audit(ctx, "app.enabled", detail={"app_id": app_id, "version": rec.version})
            self._bump("enables")
            return {"app": rec.to_public()}

    def disable(self, ctx: PlatformExecutionContext, app_id: str, *, version: str = "") -> dict[str, Any]:
        self._operate(ctx)
        with self._lock:
            rec = self._find(ctx, app_id, version=version)
            rec.lifecycle_state = AppLifecycleState.DISABLED.value
            rec.effective = False
            rec.health_state = AppHealthState.DISABLED.value
            rec.updated_at = now_ts()
            self._persist(rec)
            self._sync_module_registry(rec, enabled=False)
            self._audit(ctx, "app.disabled", detail={"app_id": app_id, "version": rec.version})
            self._bump("disables")
            return {"app": rec.to_public()}

    def launch(self, ctx: PlatformExecutionContext, app_id: str, *, version: str = "") -> dict[str, Any]:
        """Mark app running within workspace; does not execute tools."""
        self._read(ctx)
        with self._lock:
            try:
                rec = self._find(ctx, app_id, version=version, require_effective=True)
            except PlatformContextError:
                rec = self._find(ctx, app_id, version=version)
            if rec.lifecycle_state not in EXECUTABLE_STATES or not rec.effective:
                raise PlatformContextError(
                    "APP_NOT_LAUNCHABLE",
                    f"state={rec.lifecycle_state} effective={rec.effective}",
                )
            if rec.trust_state not in EXECUTABLE_TRUST:
                raise PlatformContextError("APP_UNTRUSTED", rec.trust_state)
            rec.lifecycle_state = AppLifecycleState.RUNNING.value
            rec.last_launched_at = now_ts()
            rec.launch_count += 1
            rec.updated_at = now_ts()
            self._persist(rec)
            self._audit(ctx, "app.launched", detail={"app_id": app_id, "version": rec.version})
            self._bump("launches")
            return {
                "app": rec.to_public(),
                "workspace": self.workspace_for(ctx, app_id, version=rec.version),
                "navigation": self.navigation_for(ctx, app_id, version=rec.version),
                "integrations": self.integrations(ctx, app_id, version=rec.version),
                "bypass_gateway": False,
                "marketplace": False,
            }

    def set_favorite(
        self, ctx: PlatformExecutionContext, app_id: str, *, favorite: bool = True
    ) -> dict[str, Any]:
        self._operate(ctx)
        rec = self._find(ctx, app_id)
        rec.favorite = bool(favorite)
        rec.updated_at = now_ts()
        self._persist(rec)
        return {"app": rec.to_public()}

    # ── workspace / navigation ───────────────────────────────────────────
    def workspace_for(
        self, ctx: PlatformExecutionContext, app_id: str, *, version: str = ""
    ) -> dict[str, Any]:
        self._read(ctx)
        rec = self._find(ctx, app_id, version=version)
        cfg = dict(rec.workspace_config or {})
        return {
            "app_id": rec.app_id,
            "version": rec.version,
            "org_id": rec.org_id,
            "workspace_id": rec.workspace_id,
            "isolated": True,
            "storage_prefix": cfg.get("storage_prefix"),
            "settings": cfg.get("settings") or {},
            "pages": cfg.get("pages") or rec.manifest.get("pages") or [],
            "forms": rec.manifest.get("forms") or [],
            "dashboards": rec.manifest.get("dashboards") or [],
            "tenant_isolated": True,
            "project_scope": "inherited",
        }

    def navigation_for(
        self, ctx: PlatformExecutionContext, app_id: str, *, version: str = ""
    ) -> dict[str, Any]:
        self._read(ctx)
        rec = self._find(ctx, app_id, version=version)
        nav = list(rec.manifest.get("navigation") or [])
        # Compose with ModuleRegistry if linked
        module_nav = []
        mid = rec.manifest.get("module_registry_id") or ""
        if mid:
            try:
                mod = self._modules().get(mid) if hasattr(self._modules(), "get") else None
                if mod is None and hasattr(self._modules(), "get_module"):
                    mod = self._modules().get_module(mid)
                if mod is not None:
                    public = mod.to_public() if hasattr(mod, "to_public") else {}
                    module_nav = public.get("nav_items") or []
            except Exception:
                module_nav = []
        return {
            "app_id": rec.app_id,
            "items": nav,
            "module_nav": module_nav,
            "isolated": True,
        }

    def launcher(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        """Application launcher surface: installed, favorites, recent."""
        self._read(ctx)
        apps = self.list_apps(ctx)["apps"]
        enabled = [a for a in apps if a.get("lifecycle_state") in EXECUTABLE_STATES]
        favorites = [a for a in apps if a.get("favorite")]
        recent = sorted(
            [a for a in apps if a.get("last_launched_at")],
            key=lambda x: x.get("last_launched_at") or 0,
            reverse=True,
        )[:12]
        return {
            "installed": apps,
            "enabled": enabled,
            "favorites": favorites,
            "recent": recent,
            "search_index": [
                {
                    "app_id": a["app_id"],
                    "display_name": (a.get("manifest") or {}).get("display_name")
                    or a["app_id"],
                    "app_type": (a.get("manifest") or {}).get("app_type"),
                    "state": a.get("lifecycle_state"),
                }
                for a in apps
            ],
            "marketplace": False,
            "remote_install": False,
        }

    def resolve_permissions(
        self, ctx: PlatformExecutionContext, app_id: str, *, version: str = ""
    ) -> dict[str, Any]:
        self._read(ctx)
        rec = self._find(ctx, app_id, version=version)
        required = list((rec.manifest or {}).get("required_permissions") or [])
        granted, missing = [], []
        for p in required:
            ok = False
            if p in ("runtime.read", "platform.read", "app.read"):
                ok = role_has_permission(ctx.role, PlatformPermission.RUNTIME_READ)
            elif p in ("runtime.operate", "app.admin", "app.install"):
                ok = role_has_permission(ctx.role, PlatformPermission.RUNTIME_OPERATE)
            elif p in ("runtime.execute", "mission.run"):
                ok = role_has_permission(ctx.role, PlatformPermission.RUNTIME_EXECUTE) or role_has_permission(
                    ctx.role, PlatformPermission.MISSION_RUN
                )
            elif p.startswith("ielts."):
                ok = role_has_permission(ctx.role, PlatformPermission.IELTS_READ) or role_has_permission(
                    ctx.role, PlatformPermission.RUNTIME_OPERATE
                )
            if ok:
                granted.append(p)
            else:
                missing.append(p)
        return {
            "required": required,
            "granted_by_rbac": granted,
            "missing": missing,
            "manifest_cannot_grant": True,
            "ok": len(missing) == 0,
        }

    def integrations(
        self, ctx: PlatformExecutionContext, app_id: str, *, version: str = ""
    ) -> dict[str, Any]:
        self._read(ctx)
        rec = self._find(ctx, app_id, version=version)
        m = rec.manifest or {}
        skills = list(m.get("skills") or [])
        knowledge = list(m.get("knowledge_sources") or [])
        workers = list(m.get("worker_requirements") or [])
        # Optional skill runtime eligibility
        skill_status = []
        try:
            from saathi.platform.skills import default_skill_runtime

            skill_rt = default_skill_runtime(self.platform)
            for sid in skills:
                try:
                    s = skill_rt.get_skill(ctx, sid)
                    skill_status.append(
                        {
                            "skill_id": sid,
                            "state": s["skill"].get("lifecycle_state"),
                            "available": s["skill"].get("lifecycle_state") == "ENABLED",
                        }
                    )
                except PlatformContextError:
                    skill_status.append(
                        {"skill_id": sid, "state": "NOT_REGISTERED", "available": False}
                    )
        except Exception:
            skill_status = [{"skill_id": s, "state": "RUNTIME_UNAVAILABLE"} for s in skills]

        return {
            "conversation": "ConversationService",
            "knowledge": "KnowledgeService",
            "skills": skill_status,
            "knowledge_sources": knowledge,
            "worker_requirements": workers,
            "execution_gateway": "required",
            "approval_center": "required_when_declared",
            "mission_runtime": "optional",
            "bypass_forbidden": True,
            "declared_approvals": m.get("approval_requirements") or [],
        }

    def _sync_module_registry(self, rec: AppRecord, *, enabled: bool) -> None:
        """Best-effort: update linked ModuleRegistry module status if present."""
        mid = (rec.manifest or {}).get("module_registry_id") or ""
        if not mid:
            return
        try:
            from saathi.platform.module_registry import ModuleStatus

            reg = self._modules()
            mod = None
            if hasattr(reg, "get"):
                mod = reg.get(mid)
            if mod is None and hasattr(reg, "_modules"):
                mod = reg._modules.get(mid)
            if mod is not None and hasattr(mod, "status"):
                mod.status = ModuleStatus.ENABLED if enabled else ModuleStatus.DISABLED
        except Exception:
            pass

    # ── business workflow integration (bounded) ──────────────────────────
    def run_workflow(
        self,
        ctx: PlatformExecutionContext,
        app_id: str,
        *,
        workflow_id: str = "",
        approval_reference: str = "",
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a declared app workflow only through platform authority paths."""
        self._operate(ctx)
        rec = self._find(ctx, app_id, require_effective=False)
        if rec.lifecycle_state not in EXECUTABLE_STATES or not rec.effective:
            raise PlatformContextError("APP_NOT_EXECUTABLE", rec.lifecycle_state)
        workflows = list((rec.manifest or {}).get("workflows") or [])
        wf = None
        if workflow_id:
            wf = next((w for w in workflows if w.get("id") == workflow_id), None)
        elif workflows:
            wf = workflows[0]
        if not wf:
            raise PlatformContextError("WORKFLOW_NOT_FOUND", "no workflow")
        if wf.get("approval_required") and not approval_reference:
            raise PlatformContextError(
                "APPROVAL_REQUIRED", "workflow requires approval"
            )
        if (arguments or {}).get("bypass_gateway") or (arguments or {}).get("direct_tool"):
            raise PlatformContextError("GATEWAY_BYPASS_FORBIDDEN", "apps cannot bypass gateway")
        # Prefer skill when declared
        skill_id = (wf.get("skill_id") or (rec.manifest.get("skills") or [None])[0])
        result: dict[str, Any] = {
            "workflow_id": wf.get("id"),
            "app_id": app_id,
            "execution_path": "AppRuntime→SkillRuntime|declarative→ExecutionGateway",
            "direct_tool_execution": False,
            "bypass_gateway": False,
        }
        if skill_id:
            try:
                from saathi.platform.skills import default_skill_runtime

                skill_rt = default_skill_runtime(self.platform)
                # ensure skill available or register domain skill if known package
                out = skill_rt.execute(
                    ctx,
                    skill_id,
                    capability=str(wf.get("capability") or ""),
                    arguments=arguments or {"text": f"{app_id}:{wf.get('id')}"},
                    approval_reference=approval_reference,
                )
                result["skill_execution"] = out.get("execution")
                result["result"] = out.get("result")
                result["execution_path"] = out.get("execution_path")
            except PlatformContextError as e:
                if e.code == "APPROVAL_REQUIRED":
                    raise
                # declarative fallback
                result["result"] = {
                    "status": "ok",
                    "mode": "declarative_fallback",
                    "workflow_id": wf.get("id"),
                    "app_id": app_id,
                    "note": str(e.code),
                }
        else:
            result["result"] = {
                "status": "ok",
                "mode": "declarative",
                "workflow_id": wf.get("id"),
                "app_id": app_id,
            }
        result["content_hash"] = content_hash(result.get("result"))
        self._audit(
            ctx,
            "app.workflow",
            detail={"app_id": app_id, "workflow_id": wf.get("id"), "hash": result["content_hash"]},
        )
        self._bump("workflows")
        return result

    # ── backup / restore / upgrade ───────────────────────────────────────
    def backup(
        self, ctx: PlatformExecutionContext, app_id: str, *, reason: str = "operator"
    ) -> dict[str, Any]:
        self._operate(ctx)
        with self._lock:
            rec = self._find(ctx, app_id)
            prev = rec.lifecycle_state
            rec.lifecycle_state = AppLifecycleState.BACKING_UP.value
            self._persist(rec)
            snap = {
                "app": rec.to_public(),
                "workspace_config": dict(rec.workspace_config or {}),
                "manifest_hash": rec.manifest_hash,
                "package_hash": rec.package_hash,
            }
            ch = content_hash(snap)
            b = AppBackupRecord(
                backup_id=new_id("abk_"),
                app_id=rec.app_id,
                version=rec.version,
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                created_at=now_ts(),
                snapshot=snap,
                reason=reason,
                content_hash=ch,
            )
            backups = self._backups()
            # bound per app
            same = [
                k
                for k, v in backups.items()
                if v.get("app_id") == app_id
                and v.get("org_id") == ctx.org_id
                and v.get("workspace_id") == ctx.workspace_id
            ]
            if len(same) >= limits.MAX_BACKUP_SNAPSHOTS_PER_APP:
                oldest = sorted(same, key=lambda k: backups[k].get("created_at", 0))[0]
                del backups[oldest]
            backups[b.backup_id] = {
                **b.to_public(include_snapshot=True),
            }
            self._save_backups(backups)
            rec.lifecycle_state = (
                prev
                if prev
                in (
                    AppLifecycleState.ENABLED.value,
                    AppLifecycleState.RUNNING.value,
                    AppLifecycleState.DISABLED.value,
                )
                else AppLifecycleState.DISABLED.value
            )
            rec.updated_at = now_ts()
            self._persist(rec)
            self._audit(
                ctx,
                "app.backup",
                detail={"app_id": app_id, "backup_id": b.backup_id, "hash": ch},
            )
            self._bump("backups")
            return {"backup": b.to_public(include_snapshot=False)}

    def list_backups(self, ctx: PlatformExecutionContext, app_id: str = "") -> dict[str, Any]:
        self._read(ctx)
        items = []
        for raw in self._backups().values():
            if raw.get("org_id") != ctx.org_id or raw.get("workspace_id") != ctx.workspace_id:
                continue
            if app_id and raw.get("app_id") != app_id:
                continue
            items.append({k: v for k, v in raw.items() if k != "snapshot"})
        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return {"backups": items, "count": len(items)}

    def restore(
        self,
        ctx: PlatformExecutionContext,
        app_id: str,
        *,
        backup_id: str,
    ) -> dict[str, Any]:
        self._operate(ctx)
        with self._lock:
            backups = self._backups()
            if backup_id not in backups:
                raise PlatformContextError("BACKUP_NOT_FOUND", "unknown backup")
            raw = backups[backup_id]
            if raw.get("org_id") != ctx.org_id or raw.get("workspace_id") != ctx.workspace_id:
                raise PlatformContextError("BACKUP_NOT_FOUND", "out of scope")
            if raw.get("app_id") != app_id:
                raise PlatformContextError("BACKUP_MISMATCH", "app_id mismatch")
            rec = self._find(ctx, app_id, version=str(raw.get("version") or ""))
            rec.lifecycle_state = AppLifecycleState.RESTORING.value
            self._persist(rec)
            snap = raw.get("snapshot") or {}
            cfg = (snap.get("workspace_config") or snap.get("app", {}).get("workspace_config") or {})
            rec.workspace_config = dict(cfg)
            rec.lifecycle_state = AppLifecycleState.ENABLED.value if rec.effective else AppLifecycleState.DISABLED.value
            if rec.effective:
                rec.lifecycle_state = AppLifecycleState.ENABLED.value
                rec.health_state = AppHealthState.HEALTHY.value
            rec.updated_at = now_ts()
            self._persist(rec)
            self._audit(
                ctx,
                "app.restored",
                detail={"app_id": app_id, "backup_id": backup_id},
            )
            self._bump("restores")
            return {"app": rec.to_public(), "backup_id": backup_id, "evidence_preserved": True}

    def upgrade(
        self,
        ctx: PlatformExecutionContext,
        app_id: str,
        *,
        to_version: str,
        package_id: str,
    ) -> dict[str, Any]:
        self._operate(ctx)
        with self._lock:
            current = self._find(ctx, app_id)
            try:
                current = self._find(ctx, app_id, require_effective=True)
            except PlatformContextError:
                pass
            if self._vtuple(to_version) < self._vtuple(current.version):
                raise PlatformContextError("DOWNGRADE_BLOCKED", "use restore/rollback")
            # backup first
            self.backup(ctx, app_id, reason="pre_upgrade")
            current.lifecycle_state = AppLifecycleState.UPGRADING.value
            current.rollback_target = current.version
            self._persist(current)
            reg = self.register(ctx, package_id=package_id)
            new_rec = AppRecord.from_dict(reg["app"])
            if new_rec.version != to_version:
                raise PlatformContextError(
                    "VERSION_MISMATCH", f"{new_rec.version} != {to_version}"
                )
            was = current.effective
            self.disable(ctx, app_id, version=current.version)
            if was:
                self.enable(ctx, app_id, version=to_version)
            new_rec = self._find(ctx, app_id, version=to_version)
            new_rec.rollback_target = current.version
            self._persist(new_rec)
            self._audit(
                ctx,
                "app.upgraded",
                detail={"app_id": app_id, "from": current.version, "to": to_version},
            )
            self._bump("upgrades")
            return {
                "app": new_rec.to_public(),
                "previous_version": current.version,
                "rollback_target": current.version,
            }

    def rollback(self, ctx: PlatformExecutionContext, app_id: str, *, reason: str = "operator") -> dict[str, Any]:
        self._operate(ctx)
        with self._lock:
            current = self._find(ctx, app_id)
            try:
                current = self._find(ctx, app_id, require_effective=True)
            except PlatformContextError:
                pass
            target = current.rollback_target
            if not target:
                versions = sorted(
                    [
                        AppRecord.from_dict(a)
                        for a in self._apps().values()
                        if a.get("app_id") == app_id
                        and a.get("org_id") == ctx.org_id
                        and a.get("workspace_id") == ctx.workspace_id
                    ],
                    key=lambda r: self._vtuple(r.version),
                    reverse=True,
                )
                for v in versions:
                    if self._vtuple(v.version) < self._vtuple(current.version):
                        target = v.version
                        break
            if not target:
                raise PlatformContextError("NO_ROLLBACK_TARGET", "no prior version")
            self.disable(ctx, app_id, version=current.version)
            en = self.enable(ctx, app_id, version=target)
            self._audit(
                ctx,
                "app.rolled_back",
                detail={"app_id": app_id, "from": current.version, "to": target, "reason": reason},
            )
            self._bump("rollbacks")
            return {
                "app": en["app"],
                "from_version": current.version,
                "to_version": target,
                "evidence_preserved": True,
            }

    @staticmethod
    def _vtuple(v: str) -> tuple:
        parts = (v or "0.0.0").split("-")[0].split(".")
        nums = []
        for p in parts[:3]:
            try:
                nums.append(int(p))
            except ValueError:
                nums.append(0)
        while len(nums) < 3:
            nums.append(0)
        return tuple(nums)

    # ── health / quarantine ──────────────────────────────────────────────
    def check_health(
        self, ctx: PlatformExecutionContext, app_id: str, *, version: str = ""
    ) -> dict[str, Any]:
        self._read(ctx)
        rec = self._find(ctx, app_id, version=version)
        issues = []
        if rec.source_path:
            v = self.validate_package(ctx, package_id=rec.source_path)
            if not v.get("ok"):
                issues.extend(v.get("errors") or [])
            elif v.get("package_hash") != rec.package_hash:
                issues.append("package_hash_mismatch")
        if rec.lifecycle_state == AppLifecycleState.QUARANTINED.value:
            health = AppHealthState.QUARANTINED.value
        elif rec.lifecycle_state == AppLifecycleState.DISABLED.value:
            health = AppHealthState.DISABLED.value
        elif issues:
            health = AppHealthState.UNHEALTHY.value
        elif rec.lifecycle_state in EXECUTABLE_STATES:
            health = AppHealthState.HEALTHY.value
        else:
            health = AppHealthState.UNKNOWN.value
        rec.health_state = health
        rec.updated_at = now_ts()
        self._persist(rec)
        self._bump("health_checks")
        return {
            "app_id": app_id,
            "version": rec.version,
            "health": health,
            "issues": issues,
            "side_effects": False,
        }

    def quarantine(
        self, ctx: PlatformExecutionContext, app_id: str, *, reason: str, version: str = ""
    ) -> dict[str, Any]:
        self._operate(ctx)
        rec = self._find(ctx, app_id, version=version)
        rec.lifecycle_state = AppLifecycleState.QUARANTINED.value
        rec.trust_state = AppTrustState.QUARANTINED.value
        rec.health_state = AppHealthState.QUARANTINED.value
        rec.effective = False
        rec.quarantine_reason = reason
        rec.updated_at = now_ts()
        self._persist(rec)
        self._sync_module_registry(rec, enabled=False)
        self._audit(ctx, "app.quarantined", detail={"app_id": app_id, "reason": reason})
        self._bump("quarantines")
        return {"app": rec.to_public()}

    def recover(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._operate(ctx)
        apps = self._apps()
        fixed = []
        mid = {
            AppLifecycleState.UPGRADING.value,
            AppLifecycleState.MIGRATING.value,
            AppLifecycleState.BACKING_UP.value,
            AppLifecycleState.RESTORING.value,
        }
        for k, raw in list(apps.items()):
            if raw.get("org_id") != ctx.org_id:
                continue
            rec = AppRecord.from_dict(raw)
            if rec.lifecycle_state in mid:
                rec.lifecycle_state = AppLifecycleState.DISABLED.value
                rec.effective = False
                rec.health_state = AppHealthState.DISABLED.value
                apps[k] = rec.to_public()
                fixed.append(rec.install_id)
        self._save_apps(apps)
        self._audit(ctx, "app.recovered", detail={"fixed": len(fixed)})
        self._bump("recoveries")
        return {"fixed": fixed, "count": len(fixed)}

    def certify(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        self._operate(ctx)
        return {
            "schema": "m129.app_runtime_certification.v1",
            "verdict": "APPLICATION_RUNTIME_CERTIFIED_WITH_LIMITATIONS",
            "production_authorized": False,
            "marketplace_authorized": False,
            "remote_install_authorized": False,
            "extends_module_registry": True,
            "replaces_module_registry": False,
            "apps_may_bypass_gateway": False,
            "execution_authority": "PlatformAgentRuntime→ExecutionGateway",
            "trading_guardian": "UNCHANGED",
            "health": self.health(ctx),
            "limitations": [
                "local_packages_only",
                "no_public_marketplace",
                "no_remote_install",
                "no_production_activation",
                "single_host_persistence",
                "english_primary_interface",
                "deterministic_test_apps",
            ],
        }


_DEFAULT: AppRuntime | None = None
_LOCK = threading.Lock()


def default_app_runtime(platform_service=None) -> AppRuntime:
    global _DEFAULT
    with _LOCK:
        if platform_service is not None:
            existing = getattr(platform_service, "_app_runtime", None)
            if existing is not None:
                return existing
            svc = AppRuntime(platform_service)
            setattr(platform_service, "_app_runtime", svc)
            return svc
        if _DEFAULT is None:
            _DEFAULT = AppRuntime()
        return _DEFAULT


def reset_app_runtime_for_tests(platform_service=None) -> None:
    global _DEFAULT
    with _LOCK:
        _DEFAULT = None
        if platform_service is not None and hasattr(platform_service, "_app_runtime"):
            delattr(platform_service, "_app_runtime")
