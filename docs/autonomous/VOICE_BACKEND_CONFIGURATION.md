# Voice backend configuration

## Certified default

SaathiOS uses `MacOSSystemSpeechProvider` as the certified lightweight local
backend on macOS. It invokes the fixed `/usr/bin/say` executable through the
existing bounded subprocess controller with an argument array, a 30-second
timeout, process-group cancellation, bounded output capture, and no shell. Audio
is written to the private SaathiOS artifact root and is never addressed by an
absolute path in the API.

No voice backend starts playback automatically. The authenticated browser client
requests synthesis and the user explicitly starts the returned audio.

## Optional VoxCPM state

VoxCPM is disabled by default. Normal SaathiOS startup does not import VoxCPM,
start a model service, contact Hugging Face, or download weights. The current
machine has no SaathiOS-configured VoxCPM executable or model, so the truthful
runtime state is `CONFIGURED_NOT_INSTALLED`.

The adapter accepts only these explicit modes:

- `gguf_metal`: a separately installed `voxcpm2-cli` executable plus explicit
  absolute BaseLM and acoustic `.gguf` paths.
- `localhost_service`: an already-running HTTP service whose URL resolves
  syntactically to `localhost`, `127.0.0.1`, or `::1`. HTTPS, credentials in the
  URL, remote hosts, and implicit public listeners are rejected.

Configuration is process-local:

```text
SAATHI_VOXCPM_ENABLED=true
SAATHI_VOXCPM_MODE=gguf_metal
SAATHI_VOXCPM_EXECUTABLE=/absolute/path/to/voxcpm2-cli
SAATHI_VOXCPM_BASE_MODEL=/absolute/path/to/base-model.gguf
SAATHI_VOXCPM_ACOUSTIC_MODEL=/absolute/path/to/acoustic-model.gguf
SAATHI_VOXCPM_STARTUP_TIMEOUT=30
SAATHI_VOXCPM_SYNTH_TIMEOUT=180
```

For an isolated service:

```text
SAATHI_VOXCPM_ENABLED=true
SAATHI_VOXCPM_MODE=localhost_service
SAATHI_VOXCPM_ENDPOINT=http://127.0.0.1:PORT
```

These variables only configure the adapter. They do not install a package,
download a model, start a listener, or certify the backend. A future operator
must independently establish all six states: installed, configured, model
available, runtime verified, quality reviewed, and certified.

## Hardware gate

On the target M2 with 8 GB unified memory, the standard VoxCPM2 Python route is
not approved: upstream reports a 2B model and about 8 GB CUDA VRAM, before API,
browser, and operating-system memory. VoxCPM1.5 and VoxCPM-0.5B remain external
experiments rather than certified SaathiOS backends. The GGUF/Metal path is the
best future evaluation candidate, but must use an isolated worker, concurrency
one, explicit local files, and live pressure/swap observation.

Do not add Torch or VoxCPM packages to the core SaathiOS environment and do not
duplicate existing Torch/model caches. Re-run the disk, Python, dependency,
memory, and supply-chain checks in `VOICE_BACKEND_DECISION.md` before any
installation.

## Language and cloning

English is the only certified language. Provider-reported language metadata is
not a SaathiOS quality certification. Nepali is `UNSUPPORTED_NOT_VERIFIED`:
Hindi or generic Devanagari support must never be relabeled as Nepali.

Voice cloning and reference-audio enrollment are `CAPABILITY_DISABLED`.
Configuration cannot enable them. The provider-neutral Yeti profile contains
only a written voice-design description and does not represent a real person.

## Artifact policy

The default root is the `voice-artifacts` directory next to the platform
database, under ignored runtime data. `SAATHI_VOICE_ARTIFACT_DIR` may select a
dedicated local root, but `/` and the user home directory are rejected. Artifacts
are bounded to 32 MiB, retained for 24 hours by default, and deleted after
confirmed cancellation or expiry. Speech text is held in process only while the
bounded operation runs; persistence contains a hash, length, and non-text
metadata.
