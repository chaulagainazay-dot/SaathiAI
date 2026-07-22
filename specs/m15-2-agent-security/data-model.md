# M15.2 Data Model
Finding{attack_id, requirement_id, category, target, severity, boundary_held,
deterministic_evidence, judge_assessment(advisory), component, state,
evidence_class, regression_test, finding_id(fingerprint), first/last_seen}.
Baseline{corpus_version, hackagent_pinned/status, totals, fingerprints}.
No secrets stored — every artifact passes redact_obj.
