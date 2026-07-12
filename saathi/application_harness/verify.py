"""M17.3 independent output verification + structured-output parsing.

Verification does NOT trust exit codes or a harness `status:success` field. It
independently inspects the produced artifact (magic bytes, container structure,
ffprobe, checksum). Ambiguous/failed verification is NEVER reported as success.
XML/SVG parsing rejects external entities (XXE); archives reject ZIP-slip.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import zipfile
from pathlib import Path

MAX_OUTPUT_BYTES = 2_000_000
_SECRET_HINT = ("password", "api_key", "secret", "token=", "bearer ", "-----begin")


class ParsedOutput:
    def __init__(self, ok: bool, data: dict, error: str = ""):
        self.ok = ok
        self.data = data
        self.error = error


def parse_structured(stdout: str) -> ParsedOutput:
    """Parse a harness JSON envelope defensively. status:success is advisory."""
    if len(stdout) > MAX_OUTPUT_BYTES:
        return ParsedOutput(False, {}, "HARNESS_OUTPUT_TOO_LARGE")
    s = stdout.strip()
    if not s:
        return ParsedOutput(True, {"raw": ""}, "")
    if not (s.startswith("{") or s.startswith("[")):
        return ParsedOutput(True, {"raw": s[:2000]}, "")   # non-JSON is allowed but untrusted
    try:
        obj = json.loads(s)
    except Exception:
        return ParsedOutput(False, {}, "HARNESS_OUTPUT_INVALID")
    low = s.lower()
    if any(h in low for h in _SECRET_HINT):
        # never surface an output that looks like it leaks a secret
        return ParsedOutput(False, {}, "HARNESS_OUTPUT_INVALID:secret_pattern")
    return ParsedOutput(True, obj if isinstance(obj, dict) else {"list": obj}, "")


# ── independent artifact verifiers ──────────────────────────────────────────
def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_png(path: str) -> dict:
    try:
        with open(path, "rb") as f:
            sig = f.read(24)
        if sig[:8] != b"\x89PNG\r\n\x1a\n":
            return _fail("not a PNG")
        w, h = struct.unpack(">II", sig[16:24])
        return _ok({"format": "png", "width": w, "height": h, "sha256": sha256(path)[:16]}) \
            if w > 0 and h > 0 else _fail("zero dimensions")
    except Exception as e:
        return _fail(str(e)[:120])


def verify_pdf(path: str) -> dict:
    try:
        with open(path, "rb") as f:
            head = f.read(5)
            f.seek(-1024, os.SEEK_END)
            tail = f.read()
        if head != b"%PDF-":
            return _fail("not a PDF")
        pages = tail.count(b"/Type/Page") + tail.count(b"/Type /Page")
        return _ok({"format": "pdf", "startxref": b"startxref" in tail,
                    "bytes": os.path.getsize(path), "sha256": sha256(path)[:16]})
    except Exception as e:
        return _fail(str(e)[:120])


def verify_zip_container(path: str, *, required_parts: list) -> dict:
    """DOCX/PPTX/XLSX are ZIP; reject ZIP-slip entries, require OpenXML parts."""
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            for n in names:
                if n.startswith("/") or ".." in Path(n).parts:
                    return _fail(f"zip-slip entry: {n}")
            missing = [p for p in required_parts if p not in names]
            if missing:
                return _fail(f"missing parts: {missing}")
        return _ok({"format": "openxml", "entries": len(names), "sha256": sha256(path)[:16]})
    except Exception as e:
        return _fail(str(e)[:120])


def verify_media(path: str) -> dict:
    """FFprobe-based independent verification (real decode of container)."""
    exe = _which("ffprobe")
    if not exe:
        return {"verified": False, "reason": "HARNESS_DEPENDENCY_MISSING:ffprobe"}
    try:
        r = subprocess.run([exe, "-v", "error", "-show_format", "-show_streams",
                           "-of", "json", path], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return _fail("ffprobe rejected file")
        info = json.loads(r.stdout or "{}")
        fmt = info.get("format", {})
        streams = info.get("streams", [])
        dur = float(fmt.get("duration", 0) or 0)
        return _ok({"format": fmt.get("format_name"), "duration": dur,
                    "streams": len(streams),
                    "codecs": [s.get("codec_name") for s in streams],
                    "sha256": sha256(path)[:16]}) if streams else _fail("no streams")
    except Exception as e:
        return _fail(str(e)[:120])


def verify_xml_safe(path: str) -> dict:
    """Parse XML/SVG rejecting external entities (XXE)."""
    try:
        text = Path(path).read_text(errors="replace")[:200000]
        if "<!ENTITY" in text or "SYSTEM" in text or "<!DOCTYPE" in text.upper():
            return _fail("external entity / DOCTYPE rejected (XXE)")
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text)   # ET does not resolve external entities
        return _ok({"root": root.tag})
    except Exception as e:
        return _fail(str(e)[:120])


def verify_file_in_roots(path: str, roots: list) -> dict:
    p = Path(path).resolve()
    for r in roots:
        try:
            p.relative_to(Path(r).resolve())
            return _ok({"confined": True, "sha256": sha256(path)[:16]}) if p.exists() \
                else _fail("file missing")
        except ValueError:
            continue
    return _fail("HARNESS_FILE_ROOT_VIOLATION")


def _ok(d: dict) -> dict:
    return {"verified": True, **d}


def _fail(reason: str) -> dict:
    return {"verified": False, "reason": reason}


def _which(name):
    import shutil
    return shutil.which(name)
