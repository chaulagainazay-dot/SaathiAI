"""Lightweight symbol extraction (no full language server)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

_PY = re.compile(
    r"^(?P<indent>\s*)(?P<kind>class|def|async def)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.M,
)
_JS = re.compile(
    r"^(?P<indent>\s*)(?:export\s+)?(?P<kind>class|function|async function)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.M,
)
_IMPORT_PY = re.compile(
    r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M,
)


@dataclass
class SymbolRecord:
    name: str
    qualified_name: str
    symbol_type: str
    path: str
    start_line: int
    end_line: int
    parent: str = ""
    imports: str = ""  # comma-joined, bounded

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_symbols(path: str, text: str, language: str) -> list[SymbolRecord]:
    if language == "python":
        return _extract_py(path, text)
    if language in ("javascript", "typescript"):
        return _extract_js(path, text)
    if language == "shell":
        return _extract_shell(path, text)
    return []


def _extract_py(path: str, text: str) -> list[SymbolRecord]:
    imports = []
    for m in _IMPORT_PY.finditer(text):
        imports.append(m.group(1) or m.group(2) or "")
    imp_s = ",".join(imports[:30])
    out: list[SymbolRecord] = []
    stack: list[tuple[int, str]] = []  # indent, name
    lines = text.splitlines()
    matches = list(_PY.finditer(text))
    for i, m in enumerate(matches):
        indent = len(m.group("indent").replace("\t", "    "))
        name = m.group("name")
        kind = m.group("kind").replace("async def", "function").replace("def", "function")
        if kind.startswith("class"):
            kind = "class"
        start = text[: m.start()].count("\n") + 1
        end = (
            text[: matches[i + 1].start()].count("\n")
            if i + 1 < len(matches)
            else len(lines)
        )
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1] if stack else ""
        qn = f"{parent}.{name}" if parent else name
        out.append(SymbolRecord(
            name=name, qualified_name=qn, symbol_type=kind, path=path,
            start_line=start, end_line=max(start, end), parent=parent, imports=imp_s,
        ))
        stack.append((indent, name if kind == "class" else (parent or name)))
        if len(out) >= 200:
            break
    return out


def _extract_js(path: str, text: str) -> list[SymbolRecord]:
    out: list[SymbolRecord] = []
    lines = text.splitlines()
    for i, m in enumerate(_JS.finditer(text)):
        name = m.group("name")
        kind = m.group("kind").replace("async function", "function")
        start = text[: m.start()].count("\n") + 1
        out.append(SymbolRecord(
            name=name, qualified_name=name, symbol_type=kind, path=path,
            start_line=start, end_line=min(len(lines), start + 50),
        ))
        if len(out) >= 200:
            break
    return out


def _extract_shell(path: str, text: str) -> list[SymbolRecord]:
    out = []
    for m in re.finditer(r"^(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{", text, re.M):
        start = text[: m.start()].count("\n") + 1
        out.append(SymbolRecord(
            name=m.group(1), qualified_name=m.group(1), symbol_type="function",
            path=path, start_line=start, end_line=start + 20,
        ))
    return out[:100]
