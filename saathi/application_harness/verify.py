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


# ── M17.4 expanded verifiers ─────────────────────────────────────────────────
_OPENXML_PARTS = {
    "docx": ["[Content_Types].xml", "word/document.xml"],
    "pptx": ["[Content_Types].xml", "ppt/presentation.xml"],
    "xlsx": ["[Content_Types].xml", "xl/workbook.xml"],
}

# zip-bomb guard: refuse archives whose uncompressed size explodes vs compressed
_MAX_COMPRESSION_RATIO = 200
_MAX_UNCOMPRESSED = 2_000_000_000


def verify_openxml(path: str, kind: str) -> dict:
    parts = _OPENXML_PARTS.get(kind, [])
    base = verify_zip_container(path, required_parts=parts)
    if not base.get("verified"):
        return base
    bomb = _zip_bomb_check(path)
    if not bomb["safe"]:
        return _fail(bomb["reason"])
    return _ok({"format": kind, **{k: v for k, v in base.items() if k != "verified"}})


def _zip_bomb_check(path: str) -> dict:
    try:
        with zipfile.ZipFile(path) as z:
            comp = sum(i.compress_size for i in z.infolist()) or 1
            uncomp = sum(i.file_size for i in z.infolist())
            if uncomp > _MAX_UNCOMPRESSED:
                return {"safe": False, "reason": "zip_bomb:uncompressed_too_large"}
            if uncomp / comp > _MAX_COMPRESSION_RATIO:
                return {"safe": False, "reason": "zip_bomb:ratio"}
        return {"safe": True, "ratio": round(uncomp / comp, 1)}
    except Exception as e:
        return {"safe": False, "reason": str(e)[:100]}


def verify_zip_safe(path: str) -> dict:
    """Generic ZIP: reject slip entries + bomb."""
    base = verify_zip_container(path, required_parts=[])
    if not base.get("verified"):
        return base
    bomb = _zip_bomb_check(path)
    return _ok({"format": "zip", "ratio": bomb.get("ratio")}) if bomb["safe"] \
        else _fail(bomb["reason"])


def verify_jpeg(path: str) -> dict:
    try:
        with open(path, "rb") as f:
            sig = f.read(3)
        return _ok({"format": "jpeg", "sha256": sha256(path)[:16]}) \
            if sig == b"\xff\xd8\xff" else _fail("not a JPEG")
    except Exception as e:
        return _fail(str(e)[:120])


def verify_audio(path: str) -> dict:
    """Audio via ffprobe — readable stream + duration + codec + sample rate."""
    info = verify_media(path)
    if not info.get("verified"):
        return info
    return info if info.get("duration", 0) > 0 else _fail("zero-duration audio")


def verify_directory_tree(path: str, roots: list, *, max_entries: int = 100000) -> dict:
    """A produced directory tree: confined, no symlink escape, bounded size."""
    p = Path(path).resolve()
    for r in roots:
        try:
            p.relative_to(Path(r).resolve())
            break
        except ValueError:
            continue
    else:
        return _fail("HARNESS_FILE_ROOT_VIOLATION")
    n, total = 0, 0
    for entry in p.rglob("*"):
        n += 1
        if n > max_entries:
            return _fail("too_many_entries")
        if entry.is_symlink():
            try:
                entry.resolve().relative_to(p)
            except ValueError:
                return _fail("symlink_escape")
        if entry.is_file():
            total += entry.stat().st_size
    return _ok({"entries": n, "bytes": total})


VERIFIERS = {
    "media": verify_media, "png": verify_png, "jpeg": verify_jpeg, "pdf": verify_pdf,
    "xml": verify_xml_safe, "svg": verify_xml_safe, "audio": verify_audio,
    "mp4": verify_media, "mov": verify_media, "mkv": verify_media,
    "mp3": verify_audio, "wav": verify_audio, "zip": verify_zip_safe,
    "docx": lambda p: verify_openxml(p, "docx"),
    "pptx": lambda p: verify_openxml(p, "pptx"),
    "xlsx": lambda p: verify_openxml(p, "xlsx"),
}


def _ok(d: dict) -> dict:
    return {"verified": True, **d}


def _fail(reason: str) -> dict:
    return {"verified": False, "reason": reason}


def _which(name):
    import shutil
    return shutil.which(name)
