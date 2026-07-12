"""M17.4 additional pilot application harness definitions.

LibreOffice / Blender / Kdenlive / Inkscape / ImageMagick. Each is contract-ready:
the definition + operation set + argv builders + verification rules exist, but the
harness only becomes usable when the application is actually installed. When the
backing executable is absent the harness stays DISCOVERED (dependency-blocked) —
never faked as trusted or available.
"""
from __future__ import annotations

import shutil

from saathi.application_harness.models import (
    HarnessDefinition, HarnessOperation, TrustStatus, SideEffect,
)


def _present(exes: list[str]) -> str | None:
    return next((shutil.which(e) for e in exes if shutil.which(e)), None)


def _defn(harness_id, app, vendor, exes, ops, license="") -> HarnessDefinition:
    present = _present(exes)
    return HarnessDefinition(
        harness_id=harness_id, display_name=app, application_name=harness_id,
        application_vendor=vendor, version="system" if present else "unknown",
        source_type="local", license=license, install_method="system_executable",
        entrypoint=present or exes[0], required_executables=exes, risk_ceiling=1,
        supported_operations=ops, verification_strategy="independent",
        # present + first-party wrap of a canonical tool → approved; absent →
        # discovered (dependency-blocked, cannot execute)
        trust_status=(TrustStatus.APPROVED.value if present
                      else TrustStatus.DISCOVERED.value),
        validation_status=("wrapped_canonical" if present else "dependency_blocked"))


def libreoffice() -> HarnessDefinition:
    return _defn("libreoffice", "LibreOffice", "TDF",
                 ["soffice", "libreoffice"],
                 ["export_pdf", "convert_document"], license="MPL-2.0")


def blender() -> HarnessDefinition:
    return _defn("blender", "Blender", "Blender Foundation", ["blender"],
                 ["inspect_version", "render_scene"], license="GPL")


def kdenlive() -> HarnessDefinition:
    return _defn("kdenlive", "Kdenlive", "KDE", ["kdenlive", "melt"],
                 ["render_timeline"], license="GPL")


def inkscape() -> HarnessDefinition:
    return _defn("inkscape", "Inkscape", "Inkscape", ["inkscape"],
                 ["export_png"], license="GPL")


def imagemagick() -> HarnessDefinition:
    return _defn("imagemagick", "ImageMagick", "ImageMagick", ["magick", "convert"],
                 ["convert_image"], license="ImageMagick")


def all_defs() -> list[HarnessDefinition]:
    return [libreoffice(), blender(), kdenlive(), inkscape(), imagemagick()]


# operation catalog (argv builders live per-op; only exercised when app present)
def operations(harness_id: str) -> list[HarnessOperation]:
    common = lambda oid, name, risk, ver: HarnessOperation(
        oid, harness_id, name, risk=risk, side_effect_type=SideEffect.LOCAL_REVERSIBLE.value,
        allowed_file_access="roots", verification_rules=[ver], idempotency_behavior="conditional")
    table = {
        "libreoffice": [common("export_pdf", "Export PDF", 1, "pdf")],
        "blender": [common("inspect_version", "Version", 0, "media"),
                    common("render_scene", "Render scene", 1, "png")],
        "kdenlive": [common("render_timeline", "Render timeline", 1, "mp4")],
        "inkscape": [common("export_png", "Export PNG", 1, "png")],
        "imagemagick": [common("convert_image", "Convert image", 1, "png")],
    }
    return table.get(harness_id, [])
