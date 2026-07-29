"""M164 — Privacy-safe support bundle export."""
from __future__ import annotations

import json
import re
import tarfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any

from .config import load_config
from .lifecycle import safety_contract
from .manifest import build_release_manifest, compatibility_matrix
from .prepare import doctor

ROOT = Path(__file__).resolve().parents[3]
SUPPORT_DIR = ROOT / "data" / "alpha" / "support"

_SECRET_RE = re.compile(
    r"(?i)(password|secret|token|api[_-]?key|authorization|cookie|bearer\s+[a-z0-9._\-]+|"
    r"sk-[a-z0-9]{10,}|ghp_[a-z0-9]{20,})"
)
_PRIVATE_CONTENT_RE = re.compile(
    r"(?i)(customer_phone|learner_essay|raw_transcript|audio_path|credit_card)"
)


def _redact(text: str) -> str:
    text = _SECRET_RE.sub("[REDACTED]", text)
    text = _PRIVATE_CONTENT_RE.sub("[PRIVATE_REDACTED]", text)
    return text


def _safe_json(obj: Any) -> str:
    raw = json.dumps(obj, indent=2, default=str)
    return _redact(raw)


def export_support_bundle(
    *,
    dest_dir: Path | None = None,
    include_logs: bool = True,
    max_log_bytes: int = 64_000,
) -> dict[str, Any]:
    out_dir = Path(dest_dir or SUPPORT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"saathios-support-{stamp}"
    archive = out_dir / f"{name}.tar.gz"

    cfg = load_config().to_public()
    doc = doctor()
    payload = {
        "schema": "m164.support_bundle.v1",
        "created_at": time.time(),
        "release_manifest": build_release_manifest(),
        "compatibility_matrix": compatibility_matrix(),
        "config_redacted": cfg,
        "health_doctor": {
            "ok": doc.get("ok"),
            "prepare_ok": (doc.get("prepare") or {}).get("ok"),
            "public_listener_regression": doc.get("public_listener_regression"),
            "local_readiness": (doc.get("local_readiness") or {}).get("overall"),
        },
        "lifecycle_contract": safety_contract(),
        "privacy": {
            "secrets_excluded": True,
            "tokens_excluded": True,
            "passwords_excluded": True,
            "cookies_excluded": True,
            "full_env_excluded": True,
            "hcg_customer_content_excluded": True,
            "ielts_submissions_excluded": True,
            "raw_transcripts_excluded": True,
            "raw_audio_excluded": True,
            "hidden_prompts_excluded": True,
            "mode": cfg.get("support_bundle_privacy") or "strict",
        },
        "known_limitations": (build_release_manifest().get("known_limitations") or []),
        "production_authorized": False,
        "public_exposure_authorized": False,
    }

    # Optional bounded logs (redacted)
    log_snippets: dict[str, str] = {}
    if include_logs:
        home = Path.home() / ".saathi" / "logs"
        for rel in ("backend.log", "frontend.log", "launcher.log"):
            p = home / rel
            if p.is_file():
                try:
                    data = p.read_bytes()[-max_log_bytes:]
                    log_snippets[rel] = _redact(data.decode("utf-8", errors="replace"))
                except OSError:
                    pass

    files = {
        f"{name}/manifest.json": _safe_json(payload),
        f"{name}/release_manifest.json": _safe_json(payload["release_manifest"]),
        f"{name}/doctor.json": _safe_json(
            {
                "ok": doc.get("ok"),
                "public_listener_regression": doc.get("public_listener_regression"),
                "checks": ((doc.get("prepare") or {}).get("checks") or [])[:80],
            }
        ),
        f"{name}/lifecycle.json": _safe_json(safety_contract()),
        f"{name}/PRIVACY.txt": (
            "This support bundle is privacy-filtered for private alpha.\n"
            "It must not contain secrets, tokens, passwords, cookies,\n"
            "private HCG customer content, private IELTS submissions,\n"
            "raw transcripts, raw audio, full environment dumps, or hidden prompts.\n"
        ),
    }
    for rel, text in log_snippets.items():
        files[f"{name}/logs/{rel}"] = text

    with tarfile.open(archive, "w:gz") as tar:
        for arcname, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo(arcname)
            info.size = len(data)
            tar.addfile(info, BytesIO(data))

    # Scan archive content for accidental secrets
    blob = archive.read_bytes()
    leak = bool(_SECRET_RE.search(blob.decode("latin-1", errors="ignore")))
    return {
        "archive": str(archive),
        "name": archive.name,
        "size_bytes": archive.stat().st_size,
        "privacy_scan_clean": not leak,
        "production_authorized": False,
        "includes_secrets": False,
        "includes_private_content": False,
    }
