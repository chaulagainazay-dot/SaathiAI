# Deploying Baadar on Koyeb (Free, No Credit Card)

Baadar runs as a FastAPI app on **Koyeb**, a free serverless platform. No credit card needed. Automatic redeploy on every git push to master.

## Why Koyeb?
- **Free tier** — 2 apps included, no credit card
- **Auto-redeploy** — every `git push` builds and deploys automatically
- **Persistent URL** — your Baadar dashboard lives at `https://baadar-xyz.koyeb.app`
- **Easy env vars** — Koyeb dashboard stores secrets securely

## Step 1: Sign up on Koyeb

Go to **https://koyeb.com** → **Sign up** → Google OAuth (no card needed)

## Step 2: Create app on Koyeb

1. Click **New App** → **GitHub**
2. Connect your GitHub account (authorize Koyeb)
3. Select:
   - **Repository**: `chaulagainazay/SaathiAI` (or your fork)
   - **Branch**: `master`
4. Configure:
   - **Build command**: Leave default (Koyeb auto-detects Python)
   - **Run command**: `uvicorn saathi.server:app --host 0.0.0.0 --port 8000`
   - **HTTP Port**: `8000`
   - **Region**: Frankfurt (closest to Nepal)
5. Click **Deploy**

Koyeb clones the repo, installs `requirements.txt`, and starts the server. Deployment takes ~3-5 minutes.

## Step 3: Get your Baadar URL

After deployment, go to your Koyeb app dashboard. You'll see:
```
https://baadar-xyz.koyeb.app
```

This is your public Baadar URL. (The exact name depends on your repo/branch name.)

## Step 4: Set environment variables

Go to **Settings** → **Environment** and add variables. Copy these from your Mac's `~/SaathiAI/.env`:

### REQUIRED (Baadar won't start without these)

| Variable | Copy from | How |
|---|---|---|
| `GROQ_API_KEY` | `~/.env` | `grep GROQ_API_KEY ~/.env` |
| `BAADAR_PASSWORD` | `~/.env` | Your login password |
| `SAATHI_TOKEN` | `~/.env` | `grep SAATHI_TOKEN ~/.env` |
| `TELEGRAM_BOT_TOKEN` | `~/.env` | `grep TELEGRAM_BOT_TOKEN ~/.env` |
| `TELEGRAM_CHAT_ID` | `~/.env` | `grep TELEGRAM_CHAT_ID ~/.env` |
| `FIREBASE_CREDENTIALS_JSON` | `firebase-admin.json` | See below |

### How to export FIREBASE_CREDENTIALS_JSON

Run on your Mac:
```bash
python3 -c "import json; d=json.load(open('~/SaathiAI/firebase-admin.json')); print(json.dumps(d))"
```

Copy the entire output (long string) and paste as the Koyeb env var value.

Alternatively, use the helper script:
```bash
bash ~/SaathiAI/deploy/get-firebase-json.sh
```

### RECOMMENDED (features work better with these)

| Variable | Source | Use case |
|---|---|---|
| `GOOGLE_API_KEY` | aistudio.google.com | Free Gemini API |
| `OPENAI_API_KEY` | platform.openai.com | ChatGPT, GPT-4 |
| `ANTHROPIC_API_KEY` | console.anthropic.com | Claude API |
| `MAILERLITE_API_KEY` | mailerlite.com | Email newsletters |
| `TWITTER_BEARER_TOKEN` | developer.twitter.com | Post to Twitter |
| `LINKEDIN_ACCESS_TOKEN` | linkedin.com/dev | Post to LinkedIn |
| `N8N_WEBHOOK_BASE` | Your n8n URL | e.g., `https://n8n-abc.koyeb.app/webhook/` |
| `SUPABASE_URL` | Your Supabase | e.g., `https://abc123.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Your Supabase | Service role key (keep secret) |

### OPTIONAL (cloud storage for videos/thumbnails)

If you want to store videos/thumbnails in the cloud (not on your Mac):

| Variable | Source | How to get |
|---|---|---|
| `R2_ENDPOINT_URL` | Cloudflare | e.g., `https://abc123.r2.cloudflarestorage.com` |
| `R2_ACCESS_KEY_ID` | Cloudflare | Create API token in R2 dashboard |
| `R2_SECRET_ACCESS_KEY` | Cloudflare | (keep secret) |
| `R2_BUCKET` | Cloudflare | e.g., `baadar-videos` |
| `R2_PUBLIC_URL` | Cloudflare | e.g., `https://videos.example.com` (or public R2 URL) |

R2 is free for the first 10 GB. [Sign up at cloudflare.com](https://dash.cloudflare.com).

## Step 5: Save env vars and redeploy

1. In Koyeb dashboard, click **Save** to apply env vars
2. Click **Redeploy** to restart with new environment
3. Check **Logs** tab — you should see:
   ```
   INFO: Uvicorn running on http://0.0.0.0:8000
   ```

## Step 6: Test Baadar is running

Go to `https://baadar-xyz.koyeb.app/dashboard.html`

You should see the Baadar dashboard. Log in with:
- **Password**: (the one you set in `BAADAR_PASSWORD`)

## Step 7: Auto-deploy on git push (already set up)

Every time you push to `master`:
```bash
git push origin master
```

Koyeb automatically:
1. Detects the push (GitHub webhook)
2. Clones the latest code
3. Runs `pip install -r requirements.txt`
4. Restarts the server with new code

**No manual redeploy needed.** Just push!

## Step 8: Monitor Baadar on Koyeb

### View logs
- Koyeb dashboard → Your app → **Logs** tab
- See real-time output, errors, and startup messages

### Check health
- `https://baadar-xyz.koyeb.app/health` should return `{"status": "ok"}`
- Dashboard at `https://baadar-xyz.koyeb.app/dashboard.html`

### View metrics
- Koyeb dashboard → **Metrics** tab
- CPU, memory, network usage over time

## Troubleshooting

### App fails to deploy
- **Check logs** in Koyeb dashboard → Logs
- Common issues:
  - Missing `requirements.txt` — ensure it's in repo root
  - Python version mismatch — Koyeb uses Python 3.11 by default
  - `FIREBASE_CREDENTIALS_JSON` is malformed — re-generate using the script

### App crashes after deploy
- **Check env vars** — is `GROQ_API_KEY` set correctly?
- **Check Firebase JSON** — paste `FIREBASE_CREDENTIALS_JSON` into a JSON validator
- **Check port** — make sure run command uses `--port 8000` (not 8765)

### Environment variable not being read
- Make sure the variable is set in Koyeb **Settings** → **Environment**
- Redeploy after adding/changing variables
- Variable names are case-sensitive

### Baadar is slow
- Koyeb free tier has limited CPU
- Check **Metrics** tab for CPU/memory usage
- Consider upgrading to Koyeb paid plan ($2/month) for better performance

### Webhook from n8n not reaching Baadar
- Make sure `N8N_WEBHOOK_BASE` in Koyeb env vars is correct
- Test with curl:
  ```bash
  curl https://baadar-xyz.koyeb.app/health
  ```
  Should return `{"status": "ok"}`

## Pushing code from your Mac

From `~/SaathiAI`:

```bash
# Make changes, commit
git add .
git commit -m "feat: my new feature"

# Push to master (triggers auto-deploy on Koyeb)
git push origin master
```

Within 1-2 minutes, Koyeb will build and redeploy. Check **Logs** to see progress.

## Cost

**Free tier**: $0/month
- 2 apps included
- 1 vCPU per app
- 512 MB RAM per app
- Auto-scaling disabled

**If you upgrade**: $2-10/month for more CPU/RAM

See [Koyeb pricing](https://www.koyeb.com/pricing).

## See also
- [Deploying n8n on Koyeb](./n8n-koyeb.md)
- [Export env vars for manual setup](./export-env-for-koyeb.sh)
- [Koyeb Docs](https://koyeb.com/docs)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
