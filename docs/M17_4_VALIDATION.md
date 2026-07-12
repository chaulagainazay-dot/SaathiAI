# M17.4 Validation
Tests: test_m17_4_multiapp.py (12; 2 live ffmpeg verifier). Red-team 75/75.
LIVE-APPLICATION-TESTED: FFmpeg (transcode + png/mp4/wav verifiers on real files).
DEPENDENCY-BLOCKED: LibreOffice/Blender/Kdenlive/Inkscape/ImageMagick.
DETERMINISTIC/SECURITY-TESTED: discovery, installer (path-hijack/URL/smoke),
updater (trust reset + rollback), revocation, resource limits, expanded verifiers
(OpenXML/zip-bomb/dir-tree). Full suite green; release gates green; secret scan
clean. Verdict: HARNESS PLATFORM STAGING READY.
