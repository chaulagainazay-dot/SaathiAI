# Deploy Baadar to Hugging Face Spaces (free, no credit card)

## One-time setup (5 minutes)

### Step 1 — Create HF Space
1. Go to https://huggingface.co/new-space
2. Name: `baadar-ai`
3. SDK: **Docker**
4. Visibility: **Private**
5. Click **Create Space**

### Step 2 — Get your HF token
1. Go to https://huggingface.co/settings/tokens
2. Click **New token** → type: **Write**
3. Copy the token (starts with `hf_...`)

### Step 3 — Push code from your Mac
```bash
cd ~/SaathiAI

# Set your HF username (e.g. "ajay-hf")
HF_USERNAME="YOUR_HF_USERNAME"
HF_TOKEN="hf_YOUR_TOKEN_HERE"

# Add HF remote
git remote add hf https://$HF_USERNAME:$HF_TOKEN@huggingface.co/spaces/$HF_USERNAME/baadar-ai

# Push (first time takes ~2 min to build Docker image)
git push hf master
```

### Step 4 — Set environment variables
In your HF Space → Settings → **Variables and secrets**, add each secret:

Run this to get the values to copy:
```bash
cd ~/SaathiAI
bash deploy/export-env-for-hf.sh
```

Key secrets to set:
- `FIREBASE_ADMIN_JSON` — paste output of: `cat firebase-admin.json | tr -d '\n'`
- `CONNECTIONS_JSON` — paste output of: `cat data/connections.json | tr -d '\n'`
- All vars from your .env file

### Step 5 — Your live URLs
- Dashboard: `https://HF_USERNAME-baadar-ai.hf.space/dashboard.html`
- API: `https://HF_USERNAME-baadar-ai.hf.space/api/v1/health`
- Telegram bot: set webhook to `https://HF_USERNAME-baadar-ai.hf.space/api/v1/telegram/webhook`

## Updating Baadar
```bash
cd ~/SaathiAI
git push hf master   # HF auto-rebuilds in ~1 min
```

## Notes
- Free tier: CPU Basic (2 vCPU, 16GB RAM) — always on, never sleeps
- Storage: ephemeral (SQLite resets on redeploy — keep Firebase as source of truth)
- For persistent SQLite: upgrade to HF Pro ($9/mo) to get persistent `/data` volume
