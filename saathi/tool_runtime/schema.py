"""Minimal JSON-schema-ish validation (no external dependency)."""
from __future__ import annotations

from typing import Any


def validate_against_schema(data: Any, schema: dict) -> list[str]:
    """Validate data against a small subset of JSON Schema.

    Supports: type (object/string/number/integer/boolean/array), required,
    properties, enum, additionalProperties=false (when set).
    """
    errs: list[str] = []
    _check(data, schema, "", errs)
    return errs


def _check(data: Any, schema: dict, path: str, errs: list[str]) -> None:
    if not schema:
        return
    t = schema.get("type")
    if t == "object":
        if not isinstance(data, dict):
            errs.append(f"{path or '$'}: expected object")
            return
        required = schema.get("required") or []
        for r in required:
            if r not in data:
                errs.append(f"{path + '.' if path else ''}{r}: required")
        props = schema.get("properties") or {}
        addl = schema.get("additionalProperties", True)
        for k, v in data.items():
            if k in props:
                _check(v, props[k], f"{path}.{k}" if path else k, errs)
            elif addl is False:
                errs.append(f"{path + '.' if path else ''}{k}: unexpected property")
    elif t == "string":
        if not isinstance(data, str):
            errs.append(f"{path or '$'}: expected string")
            return
        if "enum" in schema and data not in schema["enum"]:
            errs.append(f"{path or '$'}: not in enum")
        mx = schema.get("maxLength")
        if mx is not None and len(data) > int(mx):
            errs.append(f"{path or '$'}: maxLength {mx}")
    elif t == "number":
        if not isinstance(data, (int, float)) or isinstance(data, bool):
            errs.append(f"{path or '$'}: expected number")
    elif t == "integer":
        if not isinstance(data, int) or isinstance(data, bool):
            errs.append(f"{path or '$'}: expected integer")
    elif t == "boolean":
        if not isinstance(data, bool):
            errs.append(f"{path or '$'}: expected boolean")
    elif t == "array":
        if not isinstance(data, list):
            errs.append(f"{path or '$'}: expected array")
            return
        item_s = schema.get("items")
        if item_s:
            for i, item in enumerate(data):
                _check(item, item_s, f"{path}[{i}]", errs)
