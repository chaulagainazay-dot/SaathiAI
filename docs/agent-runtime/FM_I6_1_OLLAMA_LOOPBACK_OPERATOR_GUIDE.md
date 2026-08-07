# Operator Guide — Bind Ollama to Loopback Only (FM-I6.1)

**Audience:** Human operator (not automated by SaathiOS)  
**Why:** FM-I6.1 verified that Ollama on this host listens on `*:11434` (true wildcard),
reachable on LAN IPv4 (`192.168.1.89`) and global IPv6 addresses, with the application
firewall disabled. SaathiOS clients only connect to `http://127.0.0.1:11434`, but the
runtime process remains network-exposed until reconfigured.

**SaathiOS will not** restart, kill, or reconfigure Ollama for you.

---

## 1. Explanation

| Observation | Meaning |
| --- | --- |
| `127.0.0.1:11434` (pid 979) | Loopback IPv4 — acceptable |
| `*:11434` / `tcp46 *.11434` (pid 1010) | Dual-stack wildcard — **accepts non-loopback clients** |
| `connect_ex(LAN_IP, 11434) == 0` | Confirmed open on LAN, not a display artifact |
| Firewall disabled | No OS-level compensation |

Risk: other machines or local malware on the network path can reach the model API
if they can route to this host.

---

## 2. Minimal operator steps (macOS + Ollama.app)

### Preferred: environment variable for Ollama host bind

1. Quit Ollama completely (menu bar → Quit Ollama). Confirm no listeners:

```bash
lsof -nP -iTCP:11434 -sTCP:LISTEN || echo "no listeners"
```

2. Start Ollama bound to loopback only. Options (pick one that matches your install):

**Option A — CLI serve (session):**

```bash
OLLAMA_HOST=127.0.0.1:11434 /usr/local/bin/ollama serve
```

**Option B — LaunchAgent / shell profile for app:**

Set for the user session before launching Ollama.app:

```bash
launchctl setenv OLLAMA_HOST 127.0.0.1:11434
open -a Ollama
```

Or add to `~/.zshrc` / login item documentation for this machine:

```bash
export OLLAMA_HOST=127.0.0.1:11434
```

3. Verify listeners are loopback-only:

```bash
lsof -nP -iTCP:11434 -sTCP:LISTEN
# Expect only 127.0.0.1:11434 and optionally [::1]:11434
# Must NOT show *:11434 or 0.0.0.0:11434
```

4. Verify LAN is closed:

```bash
python3 - <<'PY'
import socket
s=socket.socket(); s.settimeout(0.5)
# replace with this Mac's LAN IP
print("lan", s.connect_ex(("192.168.1.89", 11434)))  # expect non-zero
s.close()
s=socket.socket(); s.settimeout(0.5)
print("lo", s.connect_ex(("127.0.0.1", 11434)))  # expect 0
PY
```

5. Confirm API still works on loopback:

```bash
curl -sS --max-time 2 http://127.0.0.1:11434/api/tags | head -c 200; echo
ollama list
```

6. Optional: enable macOS Application Firewall if policy requires.

---

## 3. Rollback

1. Quit Ollama.
2. Unset bind restriction:

```bash
launchctl unsetenv OLLAMA_HOST
unset OLLAMA_HOST
```

3. Start Ollama normally (`open -a Ollama`).
4. Re-check `lsof` (may return to prior wildcard behavior).

---

## 4. Verification commands (for FM-I7 live re-entry)

```bash
ollama --version
lsof -nP -iTCP:11434 -sTCP:LISTEN
ollama list
ollama ps
curl -sS http://127.0.0.1:11434/api/version
# Memory (harness gate): free% >= 20 and available >= 1024 MiB
# Then optional:
# LOCAL_MODEL_LIVE=1 pytest tests/test_fm_i6_local_model_harness.py -m live_ollama -q
```

Live still requires memory gate pass and synthetic-only prompts.

---

## 5. What SaathiOS continues to do regardless

- Client endpoint remains `http://127.0.0.1:11434` only
- Live path refuses non-loopback OS bindings when binding gate is on
- No automatic model download, start, stop, or kill
