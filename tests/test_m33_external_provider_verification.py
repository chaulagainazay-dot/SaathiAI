"""M33 — External verification state, deterministic fingerprint, drift, and the
non-mutating eligibility-read invariant.

Deterministic; no network. Verifies that material change marks verification stale,
that eligibility reads never mutate state, and that external drift never touches
connector certification or the M32 simulation-verification store.
"""
from __future__ import annotations

import dataclasses

import pytest

from saathi.connectors.providers.external.profiles import (
    GITHUB_META,
    GITHUB_META_SCHEMA,
)
from saathi.connectors.providers.external.schema import SchemaContract, SchemaField
from saathi.connectors.providers.external.tls_policy import TlsPolicy
from saathi.connectors.providers.external.verification import (
    ExternalVerificationStore,
    check_external_drift,
    compute_external_fingerprint,
    resolve_external_verification,
)
from saathi.connectors.providers.external.models import ExternalVerificationState
from saathi.connectors.providers.verification import (
    ProviderVerificationStore,
    verify_provider,
)

P = GITHUB_META
FH = "fixturehash-A"


def _store(tmp_path):
    return ExternalVerificationStore(tmp_path / "ext.json")


def _fp(profile=P, *, tls=None, schema=None, fixture_hash=FH):
    return compute_external_fingerprint(profile=profile, tls_policy=tls, schema=schema or GITHUB_META_SCHEMA, fixture_hash=fixture_hash)


def _record_verified(store, fp):
    store.record_verification(
        "github_meta",
        state=ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS.value,
        fingerprint=fp, limitations=["external_read_only"], live_call_count=1,
    )


# ── Fingerprint determinism (121) ─────────────────────────────────────────────
def test_external_fingerprint_deterministic():
    assert _fp() == _fp()
    assert len(_fp()) == 64


# ── Material change marks stale (122–128) ─────────────────────────────────────
@pytest.mark.parametrize("mutate", [
    ("endpoint", dict(endpoint_reference="https://api.github.com/meta2")),
    ("host_allowlist", dict(hostname_allowlist=("api.github.com", "extra.example.com"))),
    ("redirect_policy", dict(redirect_limit=1)),
    ("adapter_version", dict(adapter_version="2.0.0")),
])
def test_profile_change_marks_stale(tmp_path, mutate):
    _name, kw = mutate
    store = _store(tmp_path)
    _record_verified(store, _fp())
    mutated = dataclasses.replace(P, **kw)
    rep = check_external_drift("github_meta", profile=mutated, schema=GITHUB_META_SCHEMA, fixture_hash=FH, store=store, mark_stale=True)
    assert rep["drifted"]
    assert store.get("github_meta").state == ExternalVerificationState.EXTERNAL_VERIFICATION_STALE.value


def test_tls_policy_change_marks_stale(tmp_path):
    store = _store(tmp_path)
    _record_verified(store, _fp(tls=TlsPolicy(min_version="TLSv1.2")))
    rep = check_external_drift("github_meta", profile=P, tls_policy=TlsPolicy(min_version="TLSv1.3"),
                               schema=GITHUB_META_SCHEMA, fixture_hash=FH, store=store, mark_stale=True)
    assert rep["drifted"]
    assert store.get("github_meta").state == ExternalVerificationState.EXTERNAL_VERIFICATION_STALE.value


def test_schema_change_marks_stale(tmp_path):
    store = _store(tmp_path)
    _record_verified(store, _fp())
    new_schema = SchemaContract("github_meta", "v2", GITHUB_META_SCHEMA.fields + (SchemaField("new_field", "string"),))
    rep = check_external_drift("github_meta", profile=P, schema=new_schema, fixture_hash=FH, store=store, mark_stale=True)
    assert rep["drifted"] and store.get("github_meta").state == ExternalVerificationState.EXTERNAL_VERIFICATION_STALE.value


def test_fixture_corpus_change_marks_stale(tmp_path):
    store = _store(tmp_path)
    _record_verified(store, _fp())
    rep = check_external_drift("github_meta", profile=P, schema=GITHUB_META_SCHEMA, fixture_hash="fixturehash-B", store=store, mark_stale=True)
    assert rep["drifted"] and store.get("github_meta").state == ExternalVerificationState.EXTERNAL_VERIFICATION_STALE.value


# ── Non-mutating read + explicit refresh (129–130) ────────────────────────────
def test_eligibility_read_does_not_refresh_state(tmp_path):
    store = _store(tmp_path)
    _record_verified(store, _fp())
    # a drifted profile → read returns stale but must NOT mutate the stored record
    mutated = dataclasses.replace(P, adapter_version="9.9.9")
    dec = resolve_external_verification("github_meta", profile=mutated, schema=GITHUB_META_SCHEMA, fixture_hash=FH, store=store)
    assert not dec.allowed and dec.state == ExternalVerificationState.EXTERNAL_VERIFICATION_STALE.value
    # stored record is still the original verified state (read did not mutate)
    assert store.get("github_meta").state == ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS.value


def test_explicit_verification_refreshes_state(tmp_path):
    store = _store(tmp_path)
    fp = _fp()
    _record_verified(store, fp)
    dec = resolve_external_verification("github_meta", profile=P, schema=GITHUB_META_SCHEMA, fixture_hash=FH, store=store)
    assert dec.allowed and dec.fresh and dec.state == ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS.value


# ── Drift does not mutate other stores (131–132) ──────────────────────────────
def test_external_drift_does_not_mutate_connector_or_m32(tmp_path):
    ext = _store(tmp_path)
    _record_verified(ext, _fp())
    # set up an M32 sim-verification record and snapshot it
    from saathi.connectors.providers.external.adapters.github_meta import GithubMetaAdapter
    from saathi.connectors.providers.external.verify import _external_config

    a = GithubMetaAdapter(profile=P, transport=None)
    cfg = _external_config(P)
    m32 = ProviderVerificationStore(tmp_path / "m32.json")
    verify_provider("github_meta", identity=a.identity, config=cfg, store=m32, state="SIMULATION_VERIFIED")
    before = m32.get("github_meta").state
    # external drift on a mutated profile
    check_external_drift("github_meta", profile=dataclasses.replace(P, adapter_version="7.0.0"),
                         schema=GITHUB_META_SCHEMA, fixture_hash=FH, store=ext, mark_stale=True)
    after = ProviderVerificationStore(tmp_path / "m32.json").get("github_meta").state
    assert before == after == "SIMULATION_VERIFIED"


# ── Stale blocks future eligibility (133) ─────────────────────────────────────
def test_stale_external_verification_blocks_future_eligibility(tmp_path):
    store = _store(tmp_path)
    _record_verified(store, _fp())
    store.mark_stale("github_meta", reason="manual")
    dec = resolve_external_verification("github_meta", profile=P, schema=GITHUB_META_SCHEMA, fixture_hash=FH, store=store)
    assert not dec.allowed and dec.state == ExternalVerificationState.EXTERNAL_VERIFICATION_STALE.value


def test_revoked_blocks_eligibility(tmp_path):
    store = _store(tmp_path)
    _record_verified(store, _fp())
    store.revoke("github_meta", reason="operator")
    dec = resolve_external_verification("github_meta", profile=P, schema=GITHUB_META_SCHEMA, fixture_hash=FH, store=store)
    assert not dec.allowed and dec.state == ExternalVerificationState.REVOKED.value


def test_simulation_verified_alone_is_not_external_verified(tmp_path):
    store = _store(tmp_path)
    store.record_verification("github_meta", state=ExternalVerificationState.SIMULATION_VERIFIED.value, fingerprint=_fp())
    dec = resolve_external_verification("github_meta", profile=P, schema=GITHUB_META_SCHEMA, fixture_hash=FH, store=store)
    assert not dec.allowed  # simulation alone never satisfies external eligibility


def test_persistence_round_trip(tmp_path):
    path = tmp_path / "ext.json"
    s1 = ExternalVerificationStore(path)
    _record_verified(s1, _fp())
    s2 = ExternalVerificationStore(path)
    assert s2.get("github_meta").state == ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS.value
