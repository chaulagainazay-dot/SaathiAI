"""Content-aware deterministic chunking for code, markdown, and config."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

from saathi.codebase_memory.classify import FileClass

MAX_CHUNK_CHARS = 2400
OVERLAP_CHARS = 120
MIN_CHUNK_CHARS = 40

_PY_SYM = re.compile(
    r"^(?P<indent>\s*)(?P<kind>class|def|async def)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.M,
)
_JS_SYM = re.compile(
    r"^(?P<indent>\s*)(?P<kind>export\s+)?(?P<kw>class|function|async function|const|let)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.M,
)
_MD_HEAD = re.compile(r"^(#{1,6})\s+(.+)$", re.M)


@dataclass
class Chunk:
    chunk_id: str
    path: str
    start_line: int
    end_line: int
    text: str
    symbol: str = ""
    symbol_type: str = ""
    section: str = ""
    chunk_version: str = "c1"

    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8", errors="replace")).hexdigest()[:16]


def _cid(path: str, start: int, end: int, body: str) -> str:
    h = hashlib.sha256(f"{path}:{start}:{end}:{body[:64]}".encode()).hexdigest()[:16]
    return f"chk_{h}"


def _split_lines(text: str) -> list[str]:
    return text.splitlines()


def chunk_source(path: str, text: str, language: str) -> list[Chunk]:
    lines = _split_lines(text)
    if not lines:
        return []
    # Prefer symbol-bounded chunks for py/js/ts
    sym_re = _PY_SYM if language == "python" else _JS_SYM if language in (
        "javascript", "typescript",
    ) else None
    if not sym_re:
        return chunk_plain(path, text)

    matches = list(sym_re.finditer(text))
    if not matches:
        return chunk_plain(path, text)

    chunks: list[Chunk] = []
    # preamble (imports)
    first_start = text[: matches[0].start()].count("\n") + 1
    preamble = text[: matches[0].start()].rstrip()
    if len(preamble) >= MIN_CHUNK_CHARS:
        end_line = first_start - 1 if first_start > 1 else 1
        chunks.append(Chunk(
            chunk_id=_cid(path, 1, max(1, end_line), preamble),
            path=path, start_line=1, end_line=max(1, end_line),
            text=preamble[:MAX_CHUNK_CHARS], symbol="", symbol_type="preamble",
        ))

    for i, m in enumerate(matches):
        start_char = m.start()
        end_char = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start_char:end_char].rstrip()
        if len(body) < MIN_CHUNK_CHARS:
            continue
        start_line = text[:start_char].count("\n") + 1
        end_line = start_line + body.count("\n")
        name = m.group("name")
        kind = m.groupdict().get("kind") or m.groupdict().get("kw") or "symbol"
        # split oversized bodies
        if len(body) <= MAX_CHUNK_CHARS:
            chunks.append(Chunk(
                chunk_id=_cid(path, start_line, end_line, body),
                path=path, start_line=start_line, end_line=end_line,
                text=body, symbol=name, symbol_type=str(kind).strip(),
            ))
        else:
            for ch in _window(body, MAX_CHUNK_CHARS, OVERLAP_CHARS):
                chunks.append(Chunk(
                    chunk_id=_cid(path, start_line, end_line, ch),
                    path=path, start_line=start_line, end_line=end_line,
                    text=ch, symbol=name, symbol_type=str(kind).strip(),
                ))
        if len(chunks) >= 40:
            break
    return chunks[:40]


def chunk_markdown(path: str, text: str) -> list[Chunk]:
    lines = _split_lines(text)
    if not lines:
        return []
    sections: list[tuple[str, int, list[str]]] = []
    current_title = Path_title(path)
    current_start = 1
    buf: list[str] = []
    for i, line in enumerate(lines, start=1):
        hm = _MD_HEAD.match(line)
        if hm and buf:
            sections.append((current_title, current_start, buf))
            current_title = hm.group(2).strip()
            current_start = i
            buf = [line]
        else:
            buf.append(line)
    if buf:
        sections.append((current_title, current_start, buf))

    chunks: list[Chunk] = []
    for title, start, body_lines in sections:
        body = "\n".join(body_lines).strip()
        if len(body) < MIN_CHUNK_CHARS:
            continue
        end = start + len(body_lines) - 1
        if len(body) <= MAX_CHUNK_CHARS:
            chunks.append(Chunk(
                chunk_id=_cid(path, start, end, body),
                path=path, start_line=start, end_line=end,
                text=body, section=title, symbol=title[:80], symbol_type="heading",
            ))
        else:
            for ch in _window(body, MAX_CHUNK_CHARS, OVERLAP_CHARS):
                chunks.append(Chunk(
                    chunk_id=_cid(path, start, end, ch),
                    path=path, start_line=start, end_line=end,
                    text=ch, section=title, symbol=title[:80], symbol_type="heading",
                ))
        if len(chunks) >= 40:
            break
    return chunks[:40]


def Path_title(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def chunk_plain(path: str, text: str) -> list[Chunk]:
    lines = _split_lines(text)
    if not lines:
        return []
    chunks: list[Chunk] = []
    buf: list[str] = []
    start = 1
    for i, line in enumerate(lines, start=1):
        buf.append(line)
        if sum(len(x) + 1 for x in buf) >= MAX_CHUNK_CHARS:
            body = "\n".join(buf)
            chunks.append(Chunk(
                chunk_id=_cid(path, start, i, body),
                path=path, start_line=start, end_line=i, text=body,
            ))
            # overlap
            overlap_n = max(1, OVERLAP_CHARS // 40)
            buf = buf[-overlap_n:]
            start = i - len(buf) + 1
            if len(chunks) >= 40:
                break
    if buf and len(chunks) < 40:
        body = "\n".join(buf)
        if len(body) >= MIN_CHUNK_CHARS:
            end = start + len(buf) - 1
            chunks.append(Chunk(
                chunk_id=_cid(path, start, end, body),
                path=path, start_line=start, end_line=end, text=body,
            ))
    return chunks


def _window(text: str, size: int, overlap: int) -> Iterable[str]:
    if len(text) <= size:
        yield text
        return
    i = 0
    while i < len(text):
        yield text[i:i + size]
        if i + size >= len(text):
            break
        i += max(1, size - overlap)


def chunk_file(path: str, text: str, *, file_class: FileClass, language: str) -> list[Chunk]:
    if file_class in (
        FileClass.DOCUMENTATION, FileClass.ARCHITECTURE, FileClass.ROADMAP,
        FileClass.STYLE_GUIDE, FileClass.BUSINESS_CONTEXT,
    ) or path.endswith(".md"):
        return chunk_markdown(path, text)
    if language in ("python", "javascript", "typescript") or file_class in (
        FileClass.SOURCE_CODE, FileClass.TEST_CODE,
    ):
        return chunk_source(path, text, language or "python")
    return chunk_plain(path, text)
