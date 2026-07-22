# Third-Party Notices

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
