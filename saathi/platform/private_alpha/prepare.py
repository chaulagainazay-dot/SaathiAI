"""M158 — Installation, preparation, doctor, and first-run surfaces."""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import AlphaConfig, default_config, load_config, save_config
from .manifest import (
    REQUIRED_DIRS,
    REQUIRED_DISK_HEADROOM_GB,
    REQUIRED_PORTS,
    SUPPORTED_ARCH,
    SUPPORTED_OS,
    SUPPORTED_PYTHON,
    build_release_manifest,
    write_manifest,
)

ROOT = Path(__file__).resolve().parents[3]

# M336–M343 — installable build artifacts vs host prerequisites.
#
# `.venv` and `saathi-os/node_modules` are OUTPUTS of installation, not
# preconditions of it. Classifying their absence as a required host-prerequisite
# FAIL made prepare() — the private-alpha installer preflight — permanently
# unable to succeed on any checkout where installation had not already been
# performed in place (fresh clone, git worktree, clean-clone certification, or a
# newly invited tester's machine), which in turn blocked init_first_run(),
# upgrade_preflight() and the M165 certification gate.
#
# These checks are NOT removed, downgraded or silenced: they still run, still
# report FAIL status, and still emit their full remediation text. They are
# aggregated into a separate deterministic field, `install_complete`, so callers
# can distinguish "this host cannot run SaathiOS" (ok=False) from "dependencies
# have not been installed yet" (install_complete=False).
INSTALLABLE_CHECKS = ("python_venv", "frontend_deps")


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            return s.connect_ex((host, port)) == 0
        except OSError:
            return False


def _disk_free_gb(path: Path) -> float:
    usage = shutil.disk_usage(str(path if path.exists() else ROOT))
    return usage.free / (1024**3)


def _py_ok(version: str) -> bool:
    return any(version.startswith(v) for v in SUPPORTED_PYTHON)


def _check_public_bind_risk() -> list[dict[str, Any]]:
    """Detect unsafe public-bind configuration without mutating listeners."""
    issues = []
    # Static scan of launcher for 0.0.0.0 binds
    launcher = ROOT / "bin" / "saathi-local"
    if launcher.is_file():
        text = launcher.read_text(encoding="utf-8", errors="replace")
        if "0.0.0.0" in text and "--host 0.0.0.0" in text:
            issues.append(
                {
                    "code": "PUBLIC_BIND_IN_LAUNCHER",
                    "severity": "critical",
                    "remediation": "Restore bin/saathi-local to bind 127.0.0.1 only",
                }
            )
    cfg = load_config()
    if cfg.host not in ("127.0.0.1", "localhost"):
        issues.append(
            {
                "code": "UNSAFE_HOST_CONFIG",
                "severity": "critical",
                "remediation": f"Set host to 127.0.0.1 (current: {cfg.host})",
            }
        )
    return issues


def prepare(*, install_deps: bool = False) -> dict[str, Any]:
    """Inspect prerequisites and create required local directories safely."""
    checks: list[dict[str, Any]] = []
    remediations: list[str] = []
    ok = True
    install_complete = True

    def add(name: str, status: str, detail: str = "", required: bool = True) -> None:
        nonlocal ok, install_complete
        installable = name in INSTALLABLE_CHECKS
        checks.append(
            {
                "check": name,
                "status": status,
                "detail": detail,
                "required": required,
                "installable": installable,
            }
        )
        if status != "FAIL":
            return
        if installable:
            # Reported, remediated, and surfaced via install_complete — but it is
            # an un-run install step, not an unusable host.
            install_complete = False
        elif required:
            ok = False

    # OS / arch
    sys_name = platform.system()
    arch = platform.machine()
    if sys_name == "Darwin" and arch in ("arm64", "aarch64"):
        add("os_arch", "PASS", f"{sys_name} {arch} (certified class)")
    elif sys_name == "Darwin":
        add("os_arch", "WARN", f"{sys_name} {arch} — not the primary certified class", required=False)
    else:
        add("os_arch", "FAIL", f"{sys_name} {arch} — private alpha certifies {SUPPORTED_OS}/{SUPPORTED_ARCH}")
        remediations.append("Use an Apple Silicon Mac for private-alpha certification.")

    # Python
    py_ver = platform.python_version()
    # Prefer venv python if present
    venv_py = ROOT / ".venv" / "bin" / "python"
    if venv_py.is_file():
        try:
            out = subprocess.run(
                [str(venv_py), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            py_ver = (out.stdout or out.stderr or "").replace("Python", "").strip() or py_ver
        except Exception:
            pass
        add("python_venv", "PASS", str(venv_py))
    else:
        add("python_venv", "FAIL", ".venv missing")
        remediations.append("python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'")

    if _py_ok(py_ver):
        add("python_version", "PASS", py_ver)
    else:
        add("python_version", "WARN", f"{py_ver} (supported: {SUPPORTED_PYTHON})", required=False)

    # Node / npm
    node = "missing"
    try:
        node = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=3
        ).stdout.strip()
        add("node", "PASS", node)
    except Exception:
        add("node", "FAIL", "node not found")
        remediations.append("Install Node.js >= 18")

    try:
        npm = subprocess.run(
            ["npm", "--version"], capture_output=True, text=True, timeout=3
        ).stdout.strip()
        add("npm", "PASS", npm)
    except Exception:
        add("npm", "FAIL", "npm not found")
        remediations.append("Install npm")

    # Frontend deps (optional install)
    nm = ROOT / "saathi-os" / "node_modules"
    if nm.is_dir():
        add("frontend_deps", "PASS", "saathi-os/node_modules present")
    else:
        add("frontend_deps", "FAIL", "saathi-os/node_modules missing")
        remediations.append("cd saathi-os && npm install")
        if install_deps and shutil.which("npm"):
            try:
                subprocess.run(
                    ["npm", "install"],
                    cwd=str(ROOT / "saathi-os"),
                    timeout=600,
                    check=False,
                )
                if nm.is_dir():
                    checks[-1]["status"] = "PASS"
                    checks[-1]["detail"] = "installed during prepare"
                    install_complete = not any(
                        c["status"] == "FAIL" and c.get("installable") for c in checks
                    )
            except Exception as exc:
                remediations.append(f"npm install failed: {exc}")

    # Disk
    free = _disk_free_gb(ROOT)
    if free >= REQUIRED_DISK_HEADROOM_GB:
        add("disk_headroom", "PASS", f"{free:.1f} GB free")
    else:
        add("disk_headroom", "FAIL", f"{free:.1f} GB free (< {REQUIRED_DISK_HEADROOM_GB} GB)")
        remediations.append(f"Free at least {REQUIRED_DISK_HEADROOM_GB} GB of disk space")

    # Memory advisory
    try:
        import sys

        if sys.platform == "darwin":
            mem = int(
                subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                ).stdout.strip()
                or 0
            )
            mem_gb = mem / (1024**3)
            if mem_gb >= 7.5:
                add("memory", "PASS", f"~{mem_gb:.0f} GB", required=False)
            else:
                add("memory", "WARN", f"~{mem_gb:.0f} GB (8 GB recommended)", required=False)
        else:
            add("memory", "WARN", "not measured", required=False)
    except Exception:
        add("memory", "WARN", "not measured", required=False)

    # Ports
    for name, port in REQUIRED_PORTS.items():
        if _port_in_use(port):
            add("port_" + name, "WARN", f"port {port} already in use", required=False)
        else:
            add("port_" + name, "PASS", f"port {port} free", required=False)

    # Public bind
    bind_issues = _check_public_bind_risk()
    if bind_issues:
        for issue in bind_issues:
            add("public_bind", "FAIL", issue["code"])
            remediations.append(issue["remediation"])
    else:
        add("public_bind", "PASS", "localhost-only posture")

    # Directories (idempotent)
    created = []
    for rel in REQUIRED_DIRS:
        p = ROOT / rel
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(rel)
        elif p.is_symlink():
            add("dir_" + rel.replace("/", "_"), "FAIL", f"symlink rejected: {rel}")
            remediations.append(f"Replace symlink {rel} with a real directory")
            continue
        add("dir_" + rel.replace("/", "_"), "PASS", rel, required=False)

    # Database path
    db_parent = ROOT / "data" / "platform"
    db_parent.mkdir(parents=True, exist_ok=True)
    add("database_dir", "PASS", str(db_parent.relative_to(ROOT)))

    # Config
    try:
        cfg = load_config()
        if not (ROOT / "data" / "alpha" / "config" / "alpha_config.json").exists():
            save_config(cfg)
        add("config", "PASS", "alpha config valid")
    except Exception as exc:
        add("config", "FAIL", str(exc)[:160])
        remediations.append("Fix or delete corrupted data/alpha/config/alpha_config.json")

    # Manifest
    try:
        write_manifest()
        add("release_manifest", "PASS", "written")
    except Exception as exc:
        add("release_manifest", "WARN", str(exc)[:120], required=False)

    # Never collect secrets / paid providers
    add("secret_collection", "PASS", "no API credentials requested")
    add("paid_providers", "PASS", "not activated during prepare")
    add("production", "PASS", "production_authorized=false")

    pending_install = [
        c["check"] for c in checks if c["status"] == "FAIL" and c.get("installable")
    ]
    return {
        "ok": ok,
        "install_complete": install_complete,
        "pending_install_steps": pending_install,
        "checks": checks,
        "remediations": remediations,
        "created_directories": created,
        "release_manifest": build_release_manifest(),
        "install_deps": install_deps,
        "production_authorized": False,
        "public_exposure_authorized": False,
    }


def doctor() -> dict[str, Any]:
    """Combine prepare + local readiness + process posture (read-only)."""
    prep = prepare(install_deps=False)
    local = {}
    try:
        from saathi.platform.local_readiness import report as local_report

        local = local_report()
    except Exception as exc:
        local = {"overall": "UNKNOWN", "error": str(exc)[:160]}

    # Live listeners snapshot (read-only)
    listeners = []
    try:
        out = subprocess.run(
            ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in (out.stdout or "").splitlines()[1:]:
            if "127.0.0.1" in line or "localhost" in line or "*:" in line or "0.0.0.0" in line:
                # redact user path noise; keep command + address
                parts = line.split()
                if len(parts) >= 9:
                    listeners.append(
                        {
                            "command": parts[0][:40],
                            "pid": parts[1],
                            "address": parts[8][:60],
                        }
                    )
    except Exception:
        pass

    saathi_public = [
        L
        for L in listeners
        if L.get("command") in ("python", "uvicorn", "node", "next-server", "Python")
        and (
            str(L.get("address", "")).startswith("*:")
            or "0.0.0.0" in str(L.get("address", ""))
        )
    ]

    return {
        "prepare": prep,
        "local_readiness": local,
        "listeners_sample": listeners[:40],
        "saathi_public_listeners": saathi_public,
        "public_listener_regression": bool(saathi_public),
        "ok": prep.get("ok") and not saathi_public,
        "install_complete": prep.get("install_complete"),
        "pending_install_steps": prep.get("pending_install_steps") or [],
        "production_authorized": False,
    }


def init_first_run(
    *,
    acknowledge_local_only: bool = False,
    email: str = "",
    name: str = "Private Alpha Owner",
    password: str = "",
    org_name: str = "Private Alpha Org",
    workspace_name: str = "Main Workspace",
    enable_hcg_demo: bool = True,
    enable_ielts_demo: bool = True,
    backup_destination: str = "data/backups/system",
    platform=None,
) -> dict[str, Any]:
    """Idempotent first-run onboarding. Never requests API credentials."""
    if not acknowledge_local_only:
        return {
            "ok": False,
            "error": "LOCAL_ONLY_ACK_REQUIRED",
            "message": "Acknowledge local-only private-alpha posture to continue.",
            "production_authorized": False,
            "public_exposure_authorized": False,
            "notice": "PRODUCTION DISABLED · PUBLIC EXPOSURE DISABLED · NO PAID PROVIDERS",
        }

    prep = prepare(install_deps=False)
    if not prep.get("ok"):
        # Host prerequisites are unmet — first run must not proceed.
        return {"ok": False, "error": "PREPARE_FAILED", "prepare": prep}

    cfg = load_config()
    if cfg.first_run_completed and not email:
        return {
            "ok": True,
            "already_initialized": True,
            "first_run_completed": True,
            "config": cfg.to_public(),
            "install_complete": prep.get("install_complete"),
            "pending_install_steps": prep.get("pending_install_steps") or [],
            "notice": "PRODUCTION DISABLED",
        }

    if platform is None:
        from saathi.platform.service import default_platform

        platform = default_platform()

    result: dict[str, Any] = {
        "ok": True,
        "already_initialized": False,
        "owner": None,
        "demo": {},
        # Onboarding may legitimately run before dependencies are installed; the
        # caller is told exactly which install steps remain rather than being
        # blocked with an opaque PREPARE_FAILED.
        "install_complete": prep.get("install_complete"),
        "pending_install_steps": prep.get("pending_install_steps") or [],
        "notice": "PRODUCTION DISABLED · NO API CREDENTIALS COLLECTED · LOCAL ONLY",
    }

    # Bootstrap owner only when email+password provided (tests / explicit init)
    if email and password:
        try:
            owner = platform.bootstrap_owner_secure(
                email=email,
                name=name,
                password=password,
                org_name=org_name,
                workspace_name=workspace_name,
            )
            result["owner"] = {
                "user_id": owner.get("user_id") or (owner.get("user") or {}).get("user_id"),
                "org_id": owner.get("org_id") or (owner.get("org") or {}).get("org_id"),
                "workspace_id": owner.get("workspace_id")
                or (owner.get("workspace") or {}).get("workspace_id"),
                "email": email,
                # never return token in init report when possible; tests may need it
                "token_issued": bool(owner.get("token")),
            }
            # Keep token only for in-process callers that already have the dict
            result["_token"] = owner.get("token")
        except Exception as exc:
            # Idempotent: existing identity is acceptable
            msg = str(exc)
            if "exists" in msg.lower() or "UNIQUE" in msg or "already" in msg.lower():
                result["owner"] = {"email": email, "existing": True}
            else:
                return {"ok": False, "error": "BOOTSTRAP_FAILED", "detail": msg[:200]}

    token = result.get("_token")
    if token and (enable_hcg_demo or enable_ielts_demo):
        try:
            ctx = platform.require_context(token)
            from saathi.platform.apps import default_app_runtime

            apps = default_app_runtime(platform)
            for pkg, aid, flag in (
                ("hcg_pos", "saathi.hcg_pos", enable_hcg_demo),
                ("ielts_alert", "saathi.ielts_alert", enable_ielts_demo),
            ):
                if not flag:
                    continue
                try:
                    apps.register(ctx, package_id=pkg)
                    apps.enable(ctx, aid)
                    result["demo"][aid] = "enabled"
                except Exception as exc:
                    result["demo"][aid] = f"skipped:{str(exc)[:80]}"
        except Exception as exc:
            result["demo"]["error"] = str(exc)[:120]

    cfg.backup_path = backup_destination
    cfg.demo_data_enabled = bool(enable_hcg_demo or enable_ielts_demo)
    cfg.first_run_completed = True
    cfg.automation_execution_enabled = False
    cfg.production_authorized = False
    cfg.public_exposure_authorized = False
    save_config(cfg)
    write_manifest()

    result["config"] = load_config().to_public()
    result["applications_available"] = ["saathi.hcg_pos", "saathi.ielts_alert"]
    result["voice_provider"] = "disabled_by_default"
    result["notification_preferences"] = cfg.notification_preferences
    result.pop("_token", None)
    # For test callers that pass platform, re-attach token only if they used password
    if email and password and "token_issued" in (result.get("owner") or {}):
        # re-bootstrap is not re-run; tests should use platform bootstrap themselves
        pass
    return result


def open_entry() -> dict[str, Any]:
    """Return the reliable localhost entry point (does not force browser)."""
    cfg = load_config()
    return {
        "url": f"http://localhost:{cfg.frontend_port}",
        "api": f"http://{cfg.host}:{cfg.backend_port}",
        "binding": "localhost-only",
        "production_authorized": False,
        "launcher": "bin/saathi-local open",
        "alpha_cli": "bin/saathi-alpha open",
    }
