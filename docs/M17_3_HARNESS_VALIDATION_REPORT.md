# M17.3 Harness Validation Report
LIVE-APPLICATION-TESTED: FFmpeg probe_media + transcode through the gateway, with
INDEPENDENT ffprobe verification (real streams + checksum) + shell-injection
rejected + cross-user blocked. DEPENDENCY-BLOCKED: LibreOffice, Blender (not
installed). DETERMINISTIC/SECURITY/RED-TEAM-TESTED: trust lifecycle, adapter
argv-only, importer untrusted+defensive, XXE/ZIP-slip/oversize verifiers, resolver
order (19 tests + 11 red-team probes, 68/68 hold).
Verdict: AGENT-NATIVE APPLICATION PILOT READY — one real application harness
(FFmpeg) executes through ExecutionGateway, produces a verified artifact, trust +
source pinning enforced, cross-user blocked, red-team green. Not PRODUCTION READY
(single app; installation/update security + multi-user + monitoring unproven).
