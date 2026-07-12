"""M17.3 capability resolver — pick the safest, strongest available method.

Order: canonical API/connector → trusted application harness → DOM/CDP →
Accessibility → OCR/vision → coordinate. Never drops to a lower-level fallback
when a trusted structured capability is available and healthy for the operation.
Returns the selection, its reason, and the rejected alternatives.
"""
from __future__ import annotations

from dataclasses import dataclass

LAYERS = ["connector_api", "trusted_harness", "dom_cdp", "accessibility",
          "ocr_vision", "coordinate"]


@dataclass
class Resolution:
    selected: str
    reason: str
    trust_status: str
    risk: int
    verification_available: bool
    rejected: list
    fallback_policy: str

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def resolve(*, application: str, operation: str,
            connector_supports: bool = False,
            harness=None,          # HarnessDefinition or None
            harness_healthy: bool = True,
            dom_available: bool = False,
            accessibility_available: bool = False,
            vision_available: bool = False) -> Resolution:
    rejected = []

    if connector_supports:
        return Resolution("connector_api", "canonical connector supports the operation",
                          "trusted", 0, True, rejected, "harness_then_gui")
    rejected.append({"layer": "connector_api", "reason": "no canonical connector"})

    if harness is not None:
        from saathi.application_harness import trust as T
        ok, why = T.can_execute(harness)
        if ok and harness_healthy and operation in getattr(harness, "supported_operations", []):
            return Resolution("trusted_harness",
                              f"trusted harness {harness.harness_id} supports {operation}",
                              harness.trust_status, harness.risk_ceiling, True,
                              rejected, "gui_only_if_policy_permits")
        rejected.append({"layer": "trusted_harness",
                         "reason": why if not ok else
                         ("unhealthy" if not harness_healthy else "operation_unsupported")})
    else:
        rejected.append({"layer": "trusted_harness", "reason": "no harness for application"})

    # a lower-level fallback is only chosen when no trusted structured layer works
    if dom_available:
        return Resolution("dom_cdp", "browser DOM/CDP fallback", "n/a", 2, True,
                          rejected, "verify_final_outcome")
    rejected.append({"layer": "dom_cdp", "reason": "not a browser context"})
    if accessibility_available:
        return Resolution("accessibility", "OS accessibility fallback", "n/a", 2, True,
                          rejected, "verify_final_outcome")
    rejected.append({"layer": "accessibility", "reason": "permission-blocked/unavailable"})
    if vision_available:
        return Resolution("ocr_vision", "visual fallback", "n/a", 2, False, rejected,
                          "verify_final_outcome")
    rejected.append({"layer": "ocr_vision", "reason": "dependency-blocked"})
    return Resolution("coordinate", "coordinate fallback (least reliable)", "n/a", 2,
                      False, rejected, "requires_structured_element_check")
