"""M33 — Provider schema compatibility + drift classification.

A provider-specific schema contract declares required/optional fields, types,
bounds, and enums. A response is validated against it and every deviation is
classified. Unknown incompatible drift NEVER becomes a false success: any
incompatible finding makes the whole result incompatible and fails closed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from saathi.connectors.providers.external.models import (
    COMPATIBLE_DRIFT,
    INCOMPATIBLE_DRIFT,
    SchemaDrift,
)

MAX_ARRAY_LEN = 10_000
MAX_STRING_LEN = 8_192


@dataclass
class SchemaField:
    name: str
    type: str                       # bool|string|int|object|array<str>|array<any>
    required: bool = False
    nullable: bool = False
    enum: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SchemaContract:
    provider_id: str
    schema_version: str
    fields: tuple[SchemaField, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "schema_version": self.schema_version,
            "fields": [f.to_dict() for f in self.fields],
        }


@dataclass
class SchemaFinding:
    field: str
    drift: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SchemaCompatResult:
    provider_id: str
    schema_version: str
    compatible: bool
    overall: str
    findings: list[SchemaFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "schema_version": self.schema_version,
            "compatible": self.compatible,
            "overall": self.overall,
            "findings": [f.to_dict() for f in self.findings],
            "privacy_safe": True,
        }


def _type_matches(value: Any, typ: str) -> Optional[str]:
    """Return None if type matches, else a short reason string."""
    t = typ.lower()
    if t == "bool":
        return None if isinstance(value, bool) else "expected_bool"
    if t == "string":
        if not isinstance(value, str):
            return "expected_string"
        return "oversized_string" if len(value) > MAX_STRING_LEN else None
    if t == "int":
        return None if (isinstance(value, int) and not isinstance(value, bool)) else "expected_int"
    if t == "object":
        return None if isinstance(value, dict) else "expected_object"
    if t in ("array<str>", "array<string>"):
        if not isinstance(value, list):
            return "expected_array"
        if len(value) > MAX_ARRAY_LEN:
            return "oversized_array"
        for el in value[:256]:
            if not isinstance(el, str):
                return "array_element_not_string"
            if len(el) > MAX_STRING_LEN:
                return "oversized_string_element"
        return None
    if t in ("array<any>", "array"):
        if not isinstance(value, list):
            return "expected_array"
        return "oversized_array" if len(value) > MAX_ARRAY_LEN else None
    return "unknown_declared_type"


def validate_schema(data: Any, contract: SchemaContract) -> SchemaCompatResult:
    """Validate ``data`` against ``contract``; classify every deviation."""
    findings: list[SchemaFinding] = []

    if not isinstance(data, dict):
        return SchemaCompatResult(
            contract.provider_id, contract.schema_version, False,
            SchemaDrift.INCOMPATIBLE_TYPE_CHANGE.value,
            [SchemaFinding("$", SchemaDrift.INCOMPATIBLE_TYPE_CHANGE.value, "response_not_object")],
        )

    declared = {f.name for f in contract.fields}

    for f in contract.fields:
        if f.name not in data:
            if f.required:
                findings.append(SchemaFinding(f.name, SchemaDrift.INCOMPATIBLE_MISSING_FIELD.value, "required_field_absent"))
            continue
        value = data[f.name]
        if value is None:
            if not f.nullable:
                findings.append(SchemaFinding(f.name, SchemaDrift.INCOMPATIBLE_TYPE_CHANGE.value, "unexpected_null"))
            continue
        reason = _type_matches(value, f.type)
        if reason:
            drift = SchemaDrift.INCOMPATIBLE_TYPE_CHANGE.value
            findings.append(SchemaFinding(f.name, drift, reason))
            continue
        if f.enum and isinstance(value, str) and value not in f.enum:
            findings.append(SchemaFinding(f.name, SchemaDrift.INCOMPATIBLE_ENUM_CHANGE.value, "enum_value_unknown"))

    # additive (unknown) fields — compatible, but recorded
    for k in data:
        if k not in declared:
            findings.append(SchemaFinding(str(k), SchemaDrift.COMPATIBLE_ADDITIVE.value, "unknown_additive_field"))

    incompatible = [x for x in findings if x.drift in {d.value for d in INCOMPATIBLE_DRIFT}]
    if incompatible:
        # worst (first) incompatible finding names the overall class
        overall = incompatible[0].drift
        return SchemaCompatResult(contract.provider_id, contract.schema_version, False, overall, findings)

    overall = SchemaDrift.COMPATIBLE_ADDITIVE.value if any(
        x.drift == SchemaDrift.COMPATIBLE_ADDITIVE.value for x in findings
    ) else "COMPATIBLE_EXACT"
    return SchemaCompatResult(contract.provider_id, contract.schema_version, True, overall, findings)
