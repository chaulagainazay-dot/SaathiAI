# Third-Party Notices

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
