# M17.3 Harness Operations Guide
CLI: python -m saathi.application_harness.cli list|inspect|operations|resolve|
import-cli-anything|health|live-report. FFmpeg pilot: probe_media (risk 0),
transcode (risk 1). Every op declares input/output schema, risk, verification
rules; execution is gateway-governed + independently verified; unavailable apps
(LibreOffice/Blender) are dependency-blocked.
