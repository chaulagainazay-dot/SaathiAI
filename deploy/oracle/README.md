# Host SaathiAI on Oracle Cloud (Always Free) — permanent HTTPS home

Replaces the temporary `trycloudflare` tunnels with a proper always-on server: a stable
public URL, real HTTPS, $0 on Oracle's Always Free ARM tier. One VM, one domain, one cert —
Caddy routes `/api/*` to the FastAPI platform and everything else to the Next.js PWA, so it's
same-origin (no CORS, no mixed content) and the Android app installs cleanly.

## Why ARM Ubuntu (not the 1 GB micro)
The parked 1 GB `VM.Standard.E2.1.Micro` on Oracle Linux thrashed memory under `dnf`. Use the
Always Free **`VM.Standard.A1.Flex` (Ampere ARM)** — up to **4 OCPU / 24 GB RAM** free — running
**Ubuntu 24.04** (`apt`, Python 3.12). Plenty of headroom for FastAPI + Next + Caddy + SQLite.

## 1 · Create the instance (OCI Console)
- Compute → Instances → **Create**.
- Image: **Canonical Ubuntu 24.04**. Shape: **VM.Standard.A1.Flex**, e.g. 2 OCPU / 12 GB
  (or 4/24 — all Always Free). Add your SSH public key.
- Networking: keep the default VCN + public subnet, **assign a public IPv4**.

## 2 · Open the ports (two places — both required)
1. **OCI Security List** (VCN firewall): Networking → your VCN → the public subnet's Security
   List → **Add Ingress Rules**: source `0.0.0.0/0`, protocol TCP, **destination ports 80 and 443**.
2. **Host iptables**: Oracle's Ubuntu image also blocks ports locally — `setup.sh` opens 80/443
   for you.

## 3 · Deploy
```bash
ssh ubuntu@<PUBLIC_IP>

# get the code (either)
git clone <your SaathiAI repo> ~/SaathiAI
#   …or from your Mac:  rsync -az --exclude .venv --exclude node_modules --exclude .next \
#                        ~/SaathiAI/ ubuntu@<PUBLIC_IP>:~/SaathiAI/

# copy your secrets up (NEVER commit .env)
#   from your Mac:  scp ~/SaathiAI/.env ubuntu@<PUBLIC_IP>:~/SaathiAI/.env

bash ~/SaathiAI/deploy/oracle/setup.sh          # instant domain via nip.io
#   or with your own host:  bash ~/SaathiAI/deploy/oracle/setup.sh saathi.example.com
```
When it finishes it prints your URL, e.g. `https://140-238-1-2.nip.io`.

## 4 · Install on Android
Open that URL in **Chrome → ⋮ → Install app**. Real PWA: installs, works offline, live data.

## Domain options
- **nip.io** (default, zero setup): `<dashed-public-ip>.nip.io` resolves to your IP and Caddy
  gets a Let's Encrypt cert automatically. Good enough to start.
- **No-IP** (you already run DUC): point a hostname at the public IP, then
  `setup.sh yourname.ddns.net`.
- **Real domain / Cloudflare**: point an A record at the IP; same `setup.sh <domain>`.

## Operate
```bash
sudo systemctl status saathi-api saathi-ui caddy
journalctl -u saathi-api -f      # platform logs
journalctl -u saathi-ui  -f      # UI logs
# redeploy after code changes:
cd ~/SaathiAI && git pull && ./.venv/bin/pip install -e . \
  && cd saathi-os && npm ci && NEXT_PUBLIC_SAATHI_API="" npm run build \
  && sudo systemctl restart saathi-api saathi-ui
```

## Hardening (do before leaving it public)
The BFF / content / coach GET endpoints are currently **unauthenticated** (whitelisted for the
local companion). On a public server, either:
- put **Logto** in front (Stage 2 — `docs/STAGE2_LOGTO.md`; set `LOGTO_ENDPOINT` and require a
  token from the UI), **or**
- remove those paths from the auth whitelist in `saathi/server.py` and have the UI send the
  session/token.
Also set a strong `SAATHI_TOKEN` in `.env`, and keep the OCI Security List limited to 80/443.

## Cost
Always Free ARM (A1.Flex ≤4 OCPU/24 GB), 200 GB Block Volume, 10 TB egress/mo — **$0** as long as
you stay within Always Free. SQLite lives on the boot/block volume; snapshot it for backups.
