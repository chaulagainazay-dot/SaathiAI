# M17.3 CLI-Anything Audit

Clone (temp, not committed): /tmp/saathios-external-audit/CLI-Anything.
License: **Apache-2.0**. Structure: ~90 per-application "agent-harness" dirs each
with HARNESS.md/SKILL.md + a python CLI (stateful REPL or subcommand, JSON out),
a `cli-hub` installer, and public `registry.json`/`public_registry.json`
(npm/brew/bundled install methods).

## Concept classification
| concept | decision |
|---------|----------|
| harness contract (per-app GUI→CLI, JSON output) | **adopt** (original SaathiOS HarnessDefinition/Operation) |
| GUI→CLI SOP (find backend engine, map actions, existing CLI) | **reference only** |
| structured JSON result envelope | **adapt** (defensive parser + independent verify) |
| public registry metadata shape | **adapt** (read-only importer, untrusted) |
| CLI-Hub installer (npm/brew global, mutable versions) | **reject** (unrestricted agent package manager = supply-chain risk) |
| executing from mutable main/latest | **reject** (source pinning required) |
| SKILL.md/HARNESS.md docs | **wrap** (untrusted data; never instructions) |
| FFmpeg/melt/imagemagick building blocks | **wrap** (SaathiOS already uses ffmpeg) |
| stateful REPL sessions | **future consideration** (bounded, user-bound) |

## Security review
Imported registry contained entries with embedded shell chains and traversal —
the SaathiOS importer **rejects** these (17 rejected out of 79 in the live
registry.json; all accepted entries are `external_untrusted`). No CLI-Anything
code executes in SaathiOS; the SaathiOS adapter is argv-only (never shell=True).

## Source map (external concept → SaathiOS component)
harness contract → models.py; JSON output → verify.parse_structured;
registry shape → importer.py + registry.py; GUI→CLI SOP → docs; install schemes →
REJECTED (no installer built).
