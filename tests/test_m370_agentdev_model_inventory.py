"""M370 — inventory parsing, resource baseline and the eligibility rules.

Every test drives pure parsers with fixed payloads. No daemon is contacted and
no model is loaded, so the suite establishes the rules rather than the state of
whatever machine happens to run it.
"""
from __future__ import annotations

import pytest

from saathi.agentdev.host_probe import (
    PROBES,
    parse_memory_pressure,
    parse_swapusage,
    parse_vm_stat,
)
from saathi.agentdev.model_inventory import (
    KV_CACHE_ALLOWANCE_BYTES,
    THRESHOLDS,
    Eligibility,
    InstalledModel,
    ResourceBaseline,
    ResourceThresholds,
    assess_safety,
    classify_eligibility,
    enrich_from_show,
    find_duplicate_digests,
    parse_ps,
    parse_tags,
)

GIB = 1024 ** 3

TAGS = {
    "models": [
        {
            "name": "qwen3:4b", "digest": "359d7dd4bcda" + "0" * 52,
            "size": int(2.33 * GIB),
            "details": {"family": "qwen3", "parameter_size": "4.0B",
                        "quantization_level": "Q4_K_M"},
        },
        {
            "name": "qwen2.5:1.5b", "digest": "65ec06548149" + "0" * 52,
            "size": int(0.92 * GIB),
            "details": {"family": "qwen2", "parameter_size": "1.5B",
                        "quantization_level": "Q4_K_M"},
        },
    ]
}


def test_tags_are_parsed_into_models() -> None:
    models = parse_tags(TAGS)
    assert [m.name for m in models] == ["qwen2.5:1.5b", "qwen3:4b"]
    four_b = models[1]
    assert four_b.tag == "4b"
    assert four_b.family == "qwen3"
    assert four_b.parameter_size == "4.0B"
    assert four_b.quantization == "Q4_K_M"
    assert four_b.size_gib == pytest.approx(2.33, abs=0.01)


def test_a_nameless_entry_is_dropped_rather_than_half_recorded() -> None:
    assert parse_tags({"models": [{"size": 1}, "not-a-dict", {"name": "  "}]}) == []


def test_missing_digest_is_reported_not_invented() -> None:
    models = parse_tags({"models": [{"name": "x:1b", "size": 1}]})
    assert models[0].digest == ""
    assert models[0].to_dict()["digest_short"] == ""


def test_duplicate_digests_are_surfaced_not_merged() -> None:
    shared = "a" * 64
    models = parse_tags({
        "models": [
            {"name": "one:latest", "digest": shared, "size": 1},
            {"name": "two:latest", "digest": shared, "size": 1},
            {"name": "three:latest", "digest": "b" * 64, "size": 1},
        ]
    })
    duplicates = find_duplicate_digests(models)
    assert duplicates == {shared: ["one:latest", "two:latest"]}
    assert len(models) == 3, "a duplicate digest must not collapse two entries"


def test_ps_reports_resident_models() -> None:
    assert parse_ps({"models": [{"name": "qwen3:4b", "size": 3 * GIB}]}) == {
        "qwen3:4b": 3 * GIB
    }
    assert parse_ps({"models": []}) == {}


def test_show_enriches_context_and_capabilities() -> None:
    model = InstalledModel(name="qwen3:4b")
    enrich_from_show(model, {
        "capabilities": ["tools", "completion", "thinking"],
        "details": {"quantization_level": "Q4_K_M", "family": "qwen3"},
        "model_info": {"qwen3.context_length": 262144, "general.parameter_count": 4},
    })
    assert model.context_length == 262144
    assert model.capabilities == ["completion", "thinking", "tools"]


# ---- eligibility ------------------------------------------------------------


def test_a_model_within_the_ceiling_is_eligible() -> None:
    model = classify_eligibility(
        InstalledModel(name="small:1b", size_bytes=1 * GIB, capabilities=["completion"]),
        total_memory_bytes=8 * GIB,
    )
    assert model.eligibility == Eligibility.ELIGIBLE
    assert model.exclusion_reason == ""
    assert model.expected_memory_bytes == 1 * GIB + KV_CACHE_ALLOWANCE_BYTES


def test_an_oversized_model_is_host_unsuitable_not_disqualified() -> None:
    model = classify_eligibility(
        InstalledModel(name="big:70b", size_bytes=6 * GIB, capabilities=["completion"]),
        total_memory_bytes=8 * GIB,
    )
    assert model.eligibility == Eligibility.RESOURCE_UNSUITABLE
    # The wording must be about the host, never about the model's quality.
    assert "host ceiling" in model.exclusion_reason
    assert "physical memory" in model.exclusion_reason


def test_a_model_the_adapter_cannot_drive_is_adapter_incompatible() -> None:
    model = classify_eligibility(
        InstalledModel(name="embed:1b", size_bytes=1 * GIB, capabilities=["embedding"]),
        total_memory_bytes=8 * GIB,
    )
    assert model.eligibility == Eligibility.ADAPTER_INCOMPATIBLE
    assert "completion" in model.exclusion_reason


def test_the_three_exclusions_are_distinct_findings() -> None:
    assert len({
        Eligibility.RESOURCE_UNSUITABLE,
        Eligibility.ADAPTER_INCOMPATIBLE,
        Eligibility.NOT_INSTALLED,
    }) == 3


# ---- host probes ------------------------------------------------------------


def test_swapusage_is_parsed_into_bytes() -> None:
    parsed = parse_swapusage(
        "vm.swapusage: total = 7168.00M  used = 6121.44M  free = 1046.56M  (encrypted)"
    )
    assert parsed["available"] is True
    assert parsed["total_mib"] == pytest.approx(7168.0)
    assert parsed["free_mib"] == pytest.approx(1046.56, abs=0.1)
    assert parsed["used_fraction"] == pytest.approx(0.854, abs=0.01)


def test_unparseable_swap_output_is_a_reason_not_an_exception() -> None:
    assert parse_swapusage("nothing here")["available"] is False
    assert parse_swapusage("")["available"] is False


def test_vm_stat_available_memory_excludes_wired_and_active() -> None:
    parsed = parse_vm_stat(
        "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
        "Pages free:                       1000.\n"
        "Pages active:                     5000.\n"
        "Pages inactive:                   2000.\n"
        "Pages speculative:                 100.\n"
        "Pages wired down:                 4000.\n"
    )
    assert parsed["available"] is True
    assert parsed["page_size_bytes"] == 16384
    assert parsed["available_bytes"] == (1000 + 2000 + 100) * 16384


def test_memory_pressure_free_percentage_is_parsed() -> None:
    parsed = parse_memory_pressure("System-wide memory free percentage: 43%")
    assert parsed == {
        "available": True, "free_percent": 43, "used_percent": 57,
        "note": parsed["note"],
    }


def test_every_probe_argv_is_frozen_and_takes_no_argument() -> None:
    """No caller-supplied string may reach a command line."""
    for name, argv in PROBES.items():
        assert isinstance(argv, tuple), name
        assert argv[0].startswith("/"), f"{name} uses an unqualified binary"
        for token in argv:
            assert "{" not in token and "%" not in token, f"{name} looks formatted"


# ---- safety -----------------------------------------------------------------


def _baseline(**overrides) -> ResourceBaseline:
    base = {
        "host": {"disk_free_gib": 60.0, "total_memory_bytes": 8 * GIB},
        "swap": {"available": True, "free_mib": 2000.0},
        "pages": {"available": True, "available_mib": 3000.0},
        "pressure": {"available": True, "free_percent": 50},
        "resident_models": {},
    }
    base.update(overrides)
    return ResourceBaseline(**base)


def test_a_healthy_host_is_safe() -> None:
    decision = assess_safety(_baseline())
    assert decision.safe, decision.breaches
    assert decision.to_dict()["verdict"] == "proceed"


@pytest.mark.parametrize(
    "override, fragment",
    [
        ({"swap": {"available": True, "free_mib": 100.0}}, "free swap"),
        ({"pages": {"available": True, "available_mib": 200.0}}, "reclaimable memory"),
        ({"pressure": {"available": True, "free_percent": 5}}, "free memory 5%"),
        ({"host": {"disk_free_gib": 2.0, "total_memory_bytes": 8 * GIB}}, "free disk"),
    ],
)
def test_each_threshold_breach_aborts_and_names_itself(override, fragment) -> None:
    decision = assess_safety(_baseline(**override))
    assert not decision.safe
    assert any(fragment in b for b in decision.breaches), decision.breaches
    assert decision.to_dict()["verdict"] == "RESOURCE_LIMIT_EXCEEDED"


def test_an_unmeasurable_probe_is_a_breach_not_a_pass() -> None:
    """Proceeding on an unmeasured host is what the thresholds exist to stop."""
    decision = assess_safety(
        _baseline(swap={"available": False, "reason": "sysctl exited 1"})
    )
    assert not decision.safe
    assert any("could not be measured" in b for b in decision.breaches)


def test_a_platform_without_the_probe_is_skipped_not_counted() -> None:
    decision = assess_safety(
        _baseline(swap={"available": False, "reason": "no swap probe for Linux"})
    )
    assert decision.safe, decision.breaches


def test_a_second_resident_model_breaches_the_one_model_ceiling() -> None:
    candidate = classify_eligibility(
        InstalledModel(name="b:1b", size_bytes=1 * GIB, capabilities=["completion"]),
        total_memory_bytes=8 * GIB,
    )
    decision = assess_safety(
        _baseline(resident_models={"a:1b": 1 * GIB}), model=candidate
    )
    assert not decision.safe
    assert any("already resident" in b for b in decision.breaches)


def test_an_ineligible_candidate_is_refused_before_loading() -> None:
    candidate = classify_eligibility(
        InstalledModel(name="big:70b", size_bytes=6 * GIB, capabilities=["completion"]),
        total_memory_bytes=8 * GIB,
    )
    decision = assess_safety(_baseline(), model=candidate)
    assert not decision.safe
    assert any(Eligibility.RESOURCE_UNSUITABLE in b for b in decision.breaches)


def test_thresholds_are_published_before_they_are_applied() -> None:
    report = THRESHOLDS.to_dict()
    for key in (
        "max_model_size_fraction_of_ram", "min_free_swap_mib",
        "min_available_memory_mib", "min_free_disk_gib",
        "max_resident_models", "max_concurrent_evaluations", "rationale",
    ):
        assert key in report
    assert THRESHOLDS.max_resident_models == 1
    assert THRESHOLDS.max_concurrent_evaluations == 1


def test_thresholds_can_be_overridden_explicitly_for_another_host() -> None:
    """A different machine gets different numbers, stated rather than implied."""
    generous = ResourceThresholds(max_model_size_fraction_of_ram=0.9)
    model = classify_eligibility(
        InstalledModel(name="big:70b", size_bytes=6 * GIB, capabilities=["completion"]),
        total_memory_bytes=8 * GIB, thresholds=generous,
    )
    assert model.eligibility == Eligibility.ELIGIBLE
