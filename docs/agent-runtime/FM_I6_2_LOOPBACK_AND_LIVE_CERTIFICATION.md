# FM-I6.2 — Operator-Owned Ollama Loopback Remediation and Minimal Live Certification

**Status:** Operator action required — live certification not started
**Date:** 2026-08-07
**Terminal verdict:** `FM_I6_2_OPERATOR_ACTION_REQUIRED`
**Baseline:** `8540e686f4a56d54b9dca8ec3d36004468fd0392` (PR #21 tip)
**Branch:** `hardening/fm-i6.2-ollama-live-certification`
**Production certified:** **False**
**FM-I7 ready:** **No**
**Autonomous host mutation:** **None**

---

## Scope

Phase A–B completed (read-only inventory + duplicate-runtime diagnosis).
Phases D–J (post-remediation verification and live cert) **blocked** until the operator completes remediation and re-invokes verification.

No LocalModelHarness feature expansion. No model qualification. No FM-I7.

---

## Phase A — Host inventory (2026-08-07 ~08:14 +0545)

| Field | Value |
| --- | --- |
| Host | Macs-MacBook-Pro.local · arm64 · macOS 26.5.1 (25F80) |
| Ollama CLI | `/usr/local/bin/ollama` · **0.32.5** |
| Ollama.app | CFBundleShortVersionString **0.32.5** |
| API version | `{"version":"0.32.5"}` via `127.0.0.1:11434` |
| Loaded models | **None** (`ollama ps` empty) |
| Pin model | `qwen2.5:1.5b` digest **exact match** |
| Firewall | **Disabled** (State = 0) |
| Login items | Lemon, Claude, Raycast (no Ollama in login-item list) |
| OLLAMA_* env (agent shell) | none |
| Memory | free% ≈ **19.74** · avail ≈ **1617 MiB** · swap used ≈ **3784 / 4096 MiB** |
| Memory live gate | **Fail** (free% &lt; 20) |
| LAN | `192.168.1.89` · port 11434 **open** |
| Global IPv6 :11434 | **open** |

---

## Phase B — Duplicate-runtime diagnosis

### Process table

| PID | PPID | Classification | Command | Binding | Launch source |
| --- | --- | --- | --- | --- | --- |
| **979** | 1 (launchd) | **CLI-managed LaunchAgent** | `/usr/local/bin/ollama serve` | **`127.0.0.1:11434`** | `~/Library/LaunchAgents/com.ajay.ollama.plist` (`KeepAlive`+`RunAtLoad`) |
| **975** | (SM) | **Ollama.app SMAppService bootstrap** | Squirrel `background` | n/a | `com.ollama.ollama` (submitted by smd; parent bundle `com.electron.ollama`) |
| **987** | 975 | **Ollama.app GUI** | `.../Ollama.app/.../Ollama hidden` | n/a | child of app service |
| **1010** | 987 | **Ollama.app-managed server** | `.../Resources/ollama serve` | **`*:11434` (wildcard)** | child of Ollama.app |

### Ownership decision (recommended)

| Choice | Runtime | Rationale |
| --- | --- | --- |
| **RETAIN** | `com.ajay.ollama` (PID 979) | Already loopback IPv4; user LaunchAgent; matches USER_MANAGED_RUNTIME; SaathiOS target `127.0.0.1:11434` |
| **CLOSE** | Ollama.app tree (975/987/1010) | Wildcard listener; LAN/global exposure source |

**Preferred final state:** exactly one server = LaunchAgent `com.ajay.ollama` with explicit `OLLAMA_HOST=127.0.0.1:11434`, Ollama.app **quit and not auto-restarting**, firewall **enabled**.

Ownership is **not ambiguous** → no `FM_I6_2_RUNTIME_OWNERSHIP_AMBIGUOUS`.

### Operator decision table

| Process | Binding | Recommendation | Manual action | Rollback | Verify |
| --- | --- | --- | --- | --- | --- |
| 979 CLI LaunchAgent | 127.0.0.1 | **Retain** | Keep agent; optionally add `EnvironmentVariables` `OLLAMA_HOST` | unload agent if abandoned | `lsof` shows only 979 |
| 1010 app serve | `*:11434` | **Close** | **Quit Ollama** from menu bar (preferred UI) | reopen app | PID 1010 gone; no `*:11434` |
| 987/975 app | n/a | **Close** | same Quit | reopen app | no Ollama.app processes |

SaathiOS / Grok **will not** `kill`, `pkill`, `launchctl bootout`, or edit plists for you.

---

## Phase C — Operator remediation sequence (stop after each step)

Full guide: `docs/agent-runtime/FM_I6_1_OLLAMA_LOOPBACK_OPERATOR_GUIDE.md` (updated for dual-runtime).

### Step 1 (do this first) — Quit Ollama.app only

**Issue:** PID 1010 exposes `*:11434` to LAN/global IPv6.

**Action (UI — preferred):** menu bar Ollama icon → **Quit Ollama**.

**Do not** run `kill` unless UI is unavailable; if you must use a terminal command later, request it explicitly and accept responsibility.

**Expected:** processes 975/987/1010 exit; PID 979 may remain (LaunchAgent).

**Verify after you act:**

```bash
ps -axo pid,ppid,user,command | grep -i '[o]llama'
lsof -nP -iTCP:11434 -sTCP:LISTEN
```

**Rollback:** `open -a Ollama` (restores app-managed server; may restore wildcard).

**STOP here until operator confirms Step 1.**

### Step 2 — Confirm single loopback listener

```bash
lsof -nP -iTCP:11434 -sTCP:LISTEN
# Want: only 127.0.0.1:11434 (and optionally [::1]:11434)
# Must NOT: *:11434, 0.0.0.0:11434
```

```bash
python3 - <<'PY'
import socket
for host in ["127.0.0.1", "192.168.1.89"]:
    s = socket.socket(); s.settimeout(0.5)
    print(host, s.connect_ex((host, 11434)))  # lo → 0; lan → non-zero
    s.close()
PY
```

### Step 3 — Optional: pin LaunchAgent host (operator edits only)

If you choose to harden `com.ajay.ollama.plist`, add:

```xml
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key>
    <string>127.0.0.1:11434</string>
  </dict>
```

Then **you** reload (Grok will not run this):

```bash
launchctl bootout gui/$(id -u)/com.ajay.ollama
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ajay.ollama.plist
```

### Step 4 — Enable Application Firewall (operator System Settings)

System Settings → Network → Firewall → **On**.

Verify:

```bash
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
# expect enabled
```

### Step 5 — Memory for live gate

- Close heavy apps manually.
- Ensure `ollama ps` is empty.
- **FM-I6.2-MG / MG-FIX:** pure free is **diagnostic only**. Combined gate
  `fm_i6_2_mg_fix.combined_macos.v1` is implemented in
  `local_model_memory_gate.py` (see `docs/agent-runtime/FM_I6_2_MEMORY_GATE_FIX.md`).
- Live admission requires Darwin free% ≥ 20, reclaimable ≥ 2048 MiB, reclaimable ≥
  model headroom (~4022 MiB for pin — **estimate**), swap ≤ 512 MiB and not rising,
  compressor &lt; 50% soft / &lt; 70% hard, single session, single/pinned model, valid probes.

---

## Phase D–J status

| Phase | Status |
| --- | --- |
| D Loopback verify | **Pending operator** (host later showed loopback-only bind; re-verify) |
| E Memory | **Design revised** (FM-I6.2-MG) — pure free primary rejected; combined gate accepted; implementation deferred; live still blocked |
| F Model pin | **Pass** (0.32.5 / digest match) — recheck after remediation |
| G Regression | **Pass** — 184 passed, 1 skipped |
| H Live cert | **Not started** |
| I–J Post-live / security | **Not started** |

---

## Phase K — Weekly radar note (2026-08-01…07 review)

Documented dispositions only — **no implementation** in FM-I6.2:

| Item | Status |
| --- | --- |
| Liquid model claim (`LFM2.5-2.6B`) | `REQUIRES_PRIMARY_SOURCE_REVERIFICATION` — do not download/benchmark |
| LocalAI | `ISOLATED_EVALUATION_LATER` — do not install |
| MerchantBench long-horizon pattern | `APPROVED_AS_FUTURE_EVALUATION_PATTERN` — not now |
| RepoProbe pre-write gate pattern | `APPROVED_AS_FUTURE_PRE_WRITE_GATE_PATTERN` — not now |
| InteracVid | `BAADAR_SCHEMA_ADAPTATION_LATER` — not now |

Radar does **not** override FM-I6 → I6.1 → I6.2 → I7 sequence.

---

## Evidence

- `docs/evidence/fm_i6_2/RUNTIME_BOUNDARY_EVIDENCE.json`
- `docs/evidence/fm_i6_2/LIVE_GATE_EVIDENCE.json`
- `docs/evidence/fm_i6_2/CERTIFICATION.json`

Live inference evidence file **omitted** (not run).

---

## Explicit non-actions (this session)

No kill/pkill · no launchctl bootout · no Ollama restart · no plist edit · no firewall change · no model pull · no live inference · no FM-I7 · no feature expansion · no push required for operator wait.

---

## Exact stop statement

**STOP after FM-I6.2 Phase B/C (operator action required).**
Do not begin FM-I7.
Do not qualify the model.
Do not install or benchmark another model.
Do not integrate LocalAI.
Do not implement RepoProbe or MerchantBench yet.
Do not connect Claude Code, Codex, OpenCode, Pi or cloud providers.
Do not add credentials, browser, shell, filesystem mutation, production missions or trading authority.

**Operator:** complete Step 1 (Quit Ollama.app), run the verify commands, then ask to resume FM-I6.2 verification.
