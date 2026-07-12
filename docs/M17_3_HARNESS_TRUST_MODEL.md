# M17.3 Harness Trust Model
discovered → metadata_inspected → license_verified → source_pinned →
dependency_scanned → static_scanned → sandbox_installed → deterministic_tested →
application_tested → security_reviewed → approved → trusted. No skipping, no
backward. APPROVED requires deterministic+security+license+exact-source evidence
AND a human actor. Terminal: rejected/quarantined/deprecated/revoked/incompatible/
compromised/external_untrusted. Only approved|trusted execute.
