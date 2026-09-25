# Operator Guide — Bind Ollama to Loopback Only (FM-I6.1 / FM-I6.2)

**Audience:** Human operator (not automated by SaathiOS)
**Updated:** FM-I6.2 host re-inventory (2026-08-07)
**Why:** This host runs **two** Ollama servers. The CLI LaunchAgent already binds
`127.0.0.1:11434`, but **Ollama.app** starts a second server on wildcard `*:11434`
that is reachable on LAN IPv4 and global IPv6. The application firewall is disabled.

**SaathiOS / Grok will not** restart, kill, or reconfigure Ollama for you.

---

## 1. Current dual-runtime explanation (verified)

| PID | Source | Binding | Role |
| --- | --- | --- | --- |
| 979 | LaunchAgent `com.ajay.ollama` → `/usr/local/bin/ollama serve` | **`127.0.0.1:11434`** | Prefer **retain** |
| 1010 | Ollama.app → `.../Resources/ollama serve` (child of app PID 987) | **`*:11434`** | Prefer **close** |
| 975/987 | App Service Management / GUI | n/a | Close with app |

Plist (read-only evidence):

`~/Library/LaunchAgents/com.ajay.ollama.plist`
`RunAtLoad=true`, `KeepAlive=true`, program `/usr/local/bin/ollama` `serve`
(no `OLLAMA_HOST` override today; CLI default is loopback, which matches the listener)

App service label: `com.ollama.ollama` (submitted by smd / Electron parent).

Risk: any machine that can route to this Mac can call the model API on port 11434 via the app server.

---

## 2. Preferred final state

1. Exactly **one** Ollama server: LaunchAgent `com.ajay.ollama`.
2. Listener only `127.0.0.1:11434` (optional `[::1]:11434` if loopback-only).
3. Ollama.app **quit** and not reopening automatically during certification.
4. macOS Application Firewall **On**.
5. No model loaded until intentional live test (`ollama ps` empty).
6. Free memory percentage ≥ 20% and available ≥ 1024 MiB before live.

---

## 3. Operator steps (one phase at a time)

### Step 1 — Quit Ollama.app (closes wildcard server)

**UI (preferred):** menu bar whale icon → **Quit Ollama**.

**Verify:**

```bash
ps -axo pid,ppid,user,command | grep -i '[o]llama'
lsof -nP -iTCP:11434 -sTCP:LISTEN
```

**Expect:** PID 1010 / Ollama.app gone. PID 979 may remain. No `*:11434`.

**Rollback:**

```bash
open -a Ollama
```

(May restore wildcard — only for rollback.)

### Step 2 — Confirm loopback-only reachability

```bash
lsof -nP -iTCP:11434 -sTCP:LISTEN
```

```bash
python3 - <<'PY'
import socket
for host in ["127.0.0.1", "192.168.1.89"]:
    s = socket.socket(); s.settimeout(0.5)
    print(host, s.connect_ex((host, 11434)))  # lo 0; lan non-zero
    s.close()
PY
```

### Step 3 — Optional harden LaunchAgent (you edit the file)

Add environment to `~/Library/LaunchAgents/com.ajay.ollama.plist`:

```xml
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key>
    <string>127.0.0.1:11434</string>
  </dict>
```

Reload **yourself** (Grok will not run these):

```bash
launchctl bootout gui/$(id -u)/com.ajay.ollama
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ajay.ollama.plist
```

**Rollback:** remove `EnvironmentVariables` block; bootout/bootstrap again.

### Step 4 — Enable Application Firewall

System Settings → Network → Firewall → **On**.

```bash
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
```

### Step 5 — Memory for live gate

Close heavy apps manually. Confirm:

```bash
ollama ps
# empty
```

Free% ≥ 20 and available ≥ 1024 MiB (harness live gate).

### Step 6 — If you prefer Ollama.app as the only runtime instead

1. Unload LaunchAgent yourself:
   `launchctl bootout gui/$(id -u)/com.ajay.ollama`
   (and disable `RunAtLoad` / remove KeepAlive if you no longer want it).
2. Start app with host pin:
   `launchctl setenv OLLAMA_HOST 127.0.0.1:11434`
   then `open -a Ollama`.
3. Verify only loopback listeners.

Default recommendation remains: **keep LaunchAgent, quit app**.

---

## 4. Verification commands for FM-I6.2 resume

```bash
ollama --version
ollama list
ollama ps
lsof -nP -iTCP:11434 -sTCP:LISTEN
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
curl -sS --max-time 2 http://127.0.0.1:11434/api/version
# Then ask agent to resume FM-I6.2 Phase D verification
```

---

## 5. What SaathiOS continues to do regardless

- Client endpoint remains `http://127.0.0.1:11434` only
- Live path refuses non-loopback OS bindings when binding gate is on
- No automatic model download, start, stop, or kill
