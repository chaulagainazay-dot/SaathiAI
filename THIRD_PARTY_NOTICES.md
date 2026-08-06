# Third-Party Notices

## yc-software/qm (MIT License)
- Source: https://github.com/yc-software/qm
- License: MIT (Copyright (c) 2026 QM contributors)
- Audited commit: `0f0e0adccce2` (2026-08-05, M377–M384 analysis)
- Use in SaathiOS: **architectural / design reference only — NO source code copied,
  NO submodule, NO npm dependency, NO bundled QM files.**

SaathiOS does not vendor the QM repository and does not replace ExecutionGateway,
Approval, Governance, RBAC, agent_runtime, or Trading Guardian. Selected *ideas*
(multi-harness session interface shape, policy floor composition, skill promotion
lifecycle) may inform future **original** SaathiOS designs under
ADR-QM-MULTI-AGENT-RUNTIME (`ADAPT_SELECTED_PATTERNS`) and
ADR-AGENT-HARNESS-INTERFACE.

This notice records design-reference auditability. It does **not** imply that MIT
copyright notice obligations were triggered for idea-only reference, and it does
**not** imply that QM software is distributed with SaathiOS. If any QM file is
copied in future, its MIT copyright notice, license text, source path, and commit
will be preserved here and modifications documented before merge.

Evidence: `docs/adr/ADR-QM-MULTI-AGENT-RUNTIME.md`,
`docs/agent-runtime/M377_M384_QM_MULTI_AGENT_RUNTIME_GAP_ANALYSIS.md`,
`docs/adr/ADR-AGENT-HARNESS-INTERFACE.md`.

## open-jarvis/OpenJarvis (Apache License 2.0)
- Source: https://github.com/open-jarvis/OpenJarvis.git
- License: Apache-2.0
- Audited commit: `2e68e227b78876d2c82e375b07a456d3aa97835d` (2026-07-16, M20.1 Slice A)
- Use in SaathiOS: **design/concepts only — NO source code copied.**

SaathiOS `saathi/inference/` is an ORIGINAL implementation informed by OpenJarvis
patterns (InferenceEngine method surface, engine discovery/health, model catalogue
fields, benchmark metrics shape, mount-block path ideas). SaathiOS does not vendor
the OpenJarvis repository, does not add it as a submodule, does not run the
OpenJarvis daemon as the platform runtime, and does not replace ModelRouter,
ExecutionGateway, mission engine, memory governance, or Trading Guardian.

If any OpenJarvis file is copied in future, its Apache-2.0 header, NOTICE, source
path, and commit will be preserved here and modifications documented.

## HKUDS/CLI-Anything (Apache License 2.0)
- Source: https://github.com/HKUDS/CLI-Anything
- License: Apache-2.0 (see the project's LICENSE)
- Use in SaathiOS: **design/concepts only — NO source code copied.**

SaathiOS M17.3's Application Harness Platform is an ORIGINAL implementation
informed by CLI-Anything's harness conventions (the GUI→CLI harness SOP, the
structured-JSON output idea, the HARNESS.md/SKILL.md documentation pattern, and
the public-registry metadata shape). SaathiOS does not vendor the repository, does
not add it as a submodule, does not use its CLI-Hub installer, and does not
execute any external harness automatically. The CLI-Anything public registry may
be imported READ-ONLY as untrusted discovery records
(`saathi/application_harness/importer.py`); every imported entry is marked
`external_untrusted` and cannot execute until human review + source pinning.

No Apache-2.0 licensed source files were copied into this repository. If any file
is copied in future, its Apache-2.0 header, NOTICE, source path, and commit will
be preserved here and modifications documented.
