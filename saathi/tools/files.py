"""File tools — Saathi reads files Ajay drags in (data/files/) AND searches/reads
files anywhere in his home folder by voice (Spotlight-backed, privileged)."""
import subprocess
from pathlib import Path

from .. import config

HOME = Path.home()
SEARCH_ROOTS = [HOME / "Desktop", HOME / "Documents", HOME / "Downloads",
                HOME / "Library/CloudStorage"]  # Google Drive lives here when synced

FILES_DIR = config.ROOT / "data" / "files"
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".html", ".py", ".js", ".ts",
                 ".sql", ".yaml", ".yml", ".log", ".tsv"}
MAX_CHARS = 20000


def my_files(action: str, filename: str = "") -> dict:
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    if action == "list":
        items = [{"name": p.name, "size_kb": round(p.stat().st_size / 1024, 1)}
                 for p in sorted(FILES_DIR.iterdir()) if p.is_file()]
        return {"files": items, "count": len(items)}

    if action == "read":
        path = FILES_DIR / filename.replace("/", "_")
        if not path.exists():
            # fuzzy match: spoken names rarely match exactly ("canteen notes"
            # → canteen_notes.txt)
            import difflib
            names = [p.name for p in FILES_DIR.iterdir() if p.is_file()]
            norm = lambda s: "".join(c for c in s.lower() if c.isalnum())
            target = norm(filename)
            best = [n for n in names if target in norm(n) or norm(n) in target]
            if not best:
                best = difflib.get_close_matches(target, [norm(n) for n in names], 1, 0.5)
                best = [n for n in names if norm(n) in best]
            if best:
                path = FILES_DIR / best[0]
            else:
                return {"error": "not_found", "filename": filename,
                        "available_files": names}
        if path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(errors="replace")
            truncated = len(text) > MAX_CHARS
            return {"filename": path.name, "content": text[:MAX_CHARS],
                    "truncated": truncated}
        if path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
                pages = [p.extract_text() or "" for p in PdfReader(str(path)).pages[:20]]
                text = "\n".join(pages)
                return {"filename": path.name, "content": text[:MAX_CHARS],
                        "truncated": len(text) > MAX_CHARS}
            except ImportError:
                return {"error": "pdf_support_missing",
                        "fix": "pip install pypdf"}
        return {"error": "unsupported_type", "suffix": path.suffix,
                "note": "Text, code, CSV, JSON and PDF files are readable."}

    return {"error": f"unknown action: {action}"}


def _read_any(path: Path) -> dict:
    if path.suffix.lower() in TEXT_SUFFIXES:
        text = path.read_text(errors="replace")
        return {"path": str(path), "content": text[:MAX_CHARS],
                "truncated": len(text) > MAX_CHARS}
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        pages = [p.extract_text() or "" for p in PdfReader(str(path)).pages[:20]]
        text = "\n".join(pages)
        return {"path": str(path), "content": text[:MAX_CHARS],
                "truncated": len(text) > MAX_CHARS}
    return {"error": "unsupported_type", "suffix": path.suffix,
            "note": "Readable: text, code, CSV, JSON, PDF."}


def search_mac_files(query: str) -> dict:
    """Spotlight search across Desktop/Documents/Downloads/Drive by voice."""
    results: list[str] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        p = subprocess.run(["mdfind", "-onlyin", str(root), query],
                           capture_output=True, text=True, timeout=20)
        results += [l for l in p.stdout.splitlines() if l.strip()]
    if not results:
        # fallback: filename substring walk (Spotlight may not index everything)
        ql = query.lower().replace(" ", "")
        for root in SEARCH_ROOTS:
            if root.exists():
                for f in root.rglob("*"):
                    if f.is_file() and ql in f.name.lower().replace(" ", "").replace("_", ""):
                        results.append(str(f))
                        if len(results) >= 15:
                            break
    return {"matches": results[:15], "count": len(results)}


def read_mac_file(path: str) -> dict:
    """Read a file anywhere under Ajay's home folder (voice-driven, privileged)."""
    p = Path(path).expanduser().resolve()
    if not str(p).startswith(str(HOME)):
        return {"error": "outside_home", "note": "Only files in your home folder."}
    if not p.exists():
        return {"error": "not_found", "path": str(p)}
    if p.stat().st_size > 20 * 1024 * 1024:
        return {"error": "too_large"}
    return _read_any(p)
