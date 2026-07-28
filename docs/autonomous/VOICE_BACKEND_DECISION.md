# SaathiOS Voice Backend Decision

Date: 2026-07-28  
Milestone: M73  
Target: Apple M2 MacBook, 8 GB unified memory, 256 GB SSD, localhost-first

## Decision

Certify macOS system TTS as the first operational backend. Implement VoxCPM as an
optional, disabled, provider-neutral adapter with explicit local configuration and
process isolation. Do not install VoxCPM or download any weights in this goal.

Default provider order:

1. explicitly configured and healthy VoxCPM, only after a future resource/runtime
   certification;
2. macOS system speech;
3. truthful unavailable provider.

For the current machine, VoxCPM status is:

`IMPLEMENTED_ADAPTER / NOT_INSTALLED / NOT_CONFIGURED / MODEL_UNAVAILABLE /
INFERENCE_NOT_VERIFIED / QUALITY_NOT_REVIEWED / NOT_CERTIFIED`.

## Evidence

Primary upstream evidence reviewed on 2026-07-28:

- [OpenBMB VoxCPM repository](https://github.com/OpenBMB/VoxCPM) documents Python
  `>=3.10,<3.13`, PyTorch `>=2.5`, standard CUDA requirements, an MPS demo device
  option, 30 VoxCPM2 languages, model comparisons, and llama.cpp-omni support.
- [OpenBMB VoxCPM2 model card](https://huggingface.co/openbmb/VoxCPM2) reports a
  2B-parameter BF16 Apache-2.0 model.
- [OpenBMB VoxCPM-0.5B model card](https://huggingface.co/openbmb/VoxCPM-0.5B)
  limits documented language confidence to Chinese and English.
- [VoxCPM2 GGUF model card](https://huggingface.co/DennisHuang648/VoxCPM2-GGUF)
  describes the community conversion required by upstream llama.cpp-omni:
  approximately 1.6 GB Q8 BaseLM plus 1.7 GB acoustic weights.
- [llama.cpp-omni](https://github.com/tc-mb/llama.cpp-omni) is the C++/Metal engine
  linked by the upstream VoxCPM project. It is an external, separately built runtime.

Read-only Hugging Face tree metadata showed approximate repository payloads:

- VoxCPM2: 4,960,731,703 bytes (4.62 GiB), including 4.58 GB model weights and
  377 MB AudioVAE.
- VoxCPM1.5: 1,953,411,139 bytes (1.82 GiB).
- VoxCPM-0.5B: 1,610,127,708 bytes (1.50 GiB).
- VoxCPM2 GGUF recommended pair: approximately 3.3 GB before engine/build overhead.

These are download sizes, not peak runtime memory. Upstream lists approximate CUDA
VRAM at 8 GB for VoxCPM2, 6 GB for VoxCPM1.5, and 5 GB for VoxCPM-0.5B. Unified-memory
pressure also includes macOS, SaathiOS, the browser and caches. No upstream M2/8 GB
benchmark was found.

## Option comparison

| Path | Model/disk posture | 8 GB RAM pressure | Startup/latency evidence | Streaming/cancel | Language posture | Operational decision |
|---|---|---|---|---|---|---|
| A. VoxCPM2 Python/MPS | 2B BF16; about 4.62 GiB weights plus package/cache duplication | Very high; upstream CUDA VRAM is about 8 GB before shared OS load | MPS is supported by the demo, but no M2/8 GB latency or stability evidence | Package generation is bounded only through isolated process termination; true chunk streaming is not certified | 30 documented languages including English/Hindi, not Nepali | ADAPTER_ONLY; do not install/certify on this machine without a separate memory gate |
| B1. VoxCPM1.5 Python | about 1.82 GiB weights; upstream 0.6B/0.8B reporting varies by table/metadata | High; upstream lists about 6 GB CUDA VRAM | No local M2 evidence; smaller than VoxCPM2 | No certified SaathiOS streaming; process cancel only | Chinese/English | EXPERIMENTAL_CANDIDATE after explicit install approval; lacks voice design |
| B2. VoxCPM-0.5B Python | about 1.50 GiB weights | High but lowest Python option; upstream lists about 5 GB CUDA VRAM | No local M2 evidence | No certified SaathiOS streaming; process cancel only | Chinese/English; legacy release | LIGHTEST_VOXCPM_CANDIDATE, but still not safe to auto-install or claim production quality |
| C. VoxCPM2 GGUF/Metal | recommended pair about 3.3 GB plus compiled engine | Potentially lower than BF16 Python, still material and unmeasured on M2/8 GB | Upstream cites RTF about 1.76 on M4 Pro/Metal, which cannot be projected to M2/8 GB | CLI exposes `--stream`; service protocol, cancellation and crash recovery still require certification | VoxCPM2 documented languages; Nepali absent | BEST_FUTURE_VOXCPM_ROUTE, but community weights and custom build add supply-chain/operational work |
| D. macOS system TTS | no model download; OS-managed voices | Low | Measurable locally; native process cold start expected within the 2 s target | Artifact-first synthesis; process-group cancellation supported; playback cancellation is browser-native | Truthfully report only installed voices/locales; certify English first | CERTIFY_NOW |
| E. unavailable provider | no footprint | none | immediate deterministic state | immediate cancellation/no-op | none | REQUIRED fail-closed terminal fallback |

## Practical acceptance envelope

The foundation enforces these initial limits:

- text: 4,000 characters per request and bounded non-empty normalized content;
- queue: 8 non-terminal operations per organization/workspace;
- heavy provider concurrency: 1;
- system provider concurrency: 2;
- retries: none inside a provider invocation; caller may create a new request;
- synthesis timeout: 30 seconds for system TTS, configurable up to 180 seconds for
  an isolated VoxCPM operation;
- output artifact: WAV/AIFF only, maximum 32 MiB;
- retention: 24 hours by default with explicit expiry metadata;
- process output: bounded and never returned verbatim;
- memory: heavy provider refused when not explicitly configured and health-verified;
- no model startup at login and no model download during application startup.

Acceptance targets:

- system-provider artifact available within 2 seconds for the certification phrase;
- cancellation acknowledged within 500 ms where the process is active;
- frontend remains asynchronous and never autoplays;
- one active VoxCPM synthesis at most;
- main SaathiOS API never imports or initializes VoxCPM model weights.

## Provider-specific decisions

### macOS system speech

Use `/usr/bin/say` through a safe argument array and the existing bounded subprocess
convention. The executable is fixed by default, configurable only to an allowlisted
absolute regular executable. Write into a service-owned per-operation artifact
directory. Validate voice names against the runtime inventory; do not pass shell
strings. Synthesis and playback are separate: the provider creates an artifact, and
the authenticated browser plays it. Cancellation terminates the synthesis process;
browser `pause()`/source reset stops playback.

### VoxCPM

The adapter supports explicitly selected modes:

- `python_mps`: a configured absolute worker command/path, never imported in the API;
- `localhost_service`: an allowlisted loopback HTTP endpoint with explicit health
  and synthesis timeouts;
- `gguf_metal`: a configured absolute `voxcpm2-cli` executable plus explicit
  BaseLM/acoustic model paths.

All modes are disabled unless configuration is complete. Paths are validated but
never returned publicly. Service endpoints must resolve to `localhost`, `127.0.0.1`,
or `::1`; listeners are not started by the main application. There is no automatic
restart loop, package install, model download, fallback to cloud, or paid call.

The foundation may prove adapter request mapping with fakes. That is not runtime
integration certification.

## Language decision

English is the only certification target in this goal.

VoxCPM2's documented list includes Hindi but not Nepali. Hindi capability is not
evidence of Nepali capability. No Nepali synthesis is attempted because no VoxCPM
model is installed and no macOS Nepali voice has been quality reviewed. Nepali
remains `UNSUPPORTED_NOT_VERIFIED`.

## Voice cloning decision

Cloning is `CAPABILITY_DISABLED`. The upstream model can clone voices, but SaathiOS
does not yet have a complete verified-subject authorization, consent evidence,
synthetic-label enforcement, revocation/deletion and anti-public-figure workflow.
The adapter rejects reference audio and cloning requests. Provider-neutral written
voice design metadata may be stored, but only a future reviewed provider activation
may map it to provider syntax.

## Re-evaluation gate

A future VoxCPM installation milestone requires explicit user authorization before
downloading weights or adding a large environment. It must record:

- exact upstream commit/package/model revisions and license;
- free disk before/after and cache deduplication plan;
- peak RSS/unified-memory pressure and swap during cold/warm synthesis;
- cold start, time to first audio, total time, real-time factor and artifact size;
- cancellation/orphan-process behavior and crash recovery;
- English human quality review;
- bounded experimental Nepali review only if accepted by the selected backend;
- no public listener, auto-download, hidden external traffic, or cloning activation.

