# Deploying n8n on Koyeb (Free, No Credit Card)

n8n runs as a **SEPARATE Koyeb app** from Baadar. Koyeb free tier allows 2 services, so you can run both side-by-side at no cost.

## Why n8n on Koyeb?
- **24/7 uptime** — n8n runs in the cloud, never stopped by your Mac sleeping
- **No Mac disk use** — workflows and databases live on Koyeb + Supabase (free PostgreSQL)
- **Webhook-ready** — receives real-time triggers from Baadar, PIELTS, and external services
- **Free tier** — Koyeb gives you 2 apps free, no credit card needed

## Step 1: Create n8n app on Koyeb

1. Go to **https://koyeb.com** → Sign up with Google (no card needed)
2. Click **New App** → **Docker**
3. Fill in:
   - **Docker image**: `n8nio/n8n:latest`
   - **Port**: `5678`
   - **Region**: Frankfurt (closest to Nepal, best latency)
   - **Name**: `n8n` (or `n8n-baadar`)
4. Click **Deploy**. Koyeb builds the image (takes ~2 min).
5. You'll get a URL like `https://n8n-abc123.koyeb.app`

## Step 2: Set environment variables on Koyeb

After deployment starts, go to **Environment Variables** and add these:

| Variable | Value | Notes |
|---|---|---|
| `N8N_HOST` | `your-n8n-app.koyeb.app` | e.g., `n8n-abc123.koyeb.app` |
| `N8N_PORT` | `5678` | Fixed |
| `N8N_PROTOCOL` | `https` | Koyeb provides free HTTPS |
| `WEBHOOK_URL` | `https://your-n8n-app.koyeb.app/` | n8n webhook base (with trailing slash) |
| `N8N_BASIC_AUTH_ACTIVE` | `true` | Enable login |
| `N8N_BASIC_AUTH_USER` | `ajay` | Your username |
| `N8N_BASIC_AUTH_PASSWORD` | (your strong password) | Generate at passwordgenerator.net |
| `DB_TYPE` | `postgresdb` | Use PostgreSQL |
| `DB_POSTGRESDB_HOST` | (Supabase host) | From SUPABASE_URL in your `.env` |
| `DB_POSTGRESDB_PORT` | `5432` | Standard Postgres port |
| `DB_POSTGRESDB_DATABASE` | `postgres` | Default Supabase database |
| `DB_POSTGRESDB_USER` | `postgres` | Default Supabase user |
| `DB_POSTGRESDB_PASSWORD` | (Supabase service key) | From SUPABASE_SERVICE_KEY in your `.env` |
| `N8N_ENCRYPTION_KEY` | (32-char random string) | Generate: `openssl rand -base64 32` |
| `EXECUTIONS_DATA_PRUNE` | `true` | Auto-clean old executions |
| `EXECUTIONS_DATA_MAX_AGE` | `7` | Keep 7 days of execution history |

### How to extract Supabase details from your .env

Run this on your Mac:
```bash
grep "SUPABASE_URL=" ~/.env
grep "SUPABASE_SERVICE_KEY=" ~/.env
```

From `SUPABASE_URL`, extract the **host**:
- If it's `https://abc123.supabase.co` → host is `abc123.supabase.co`

### Generate N8N_ENCRYPTION_KEY

```bash
openssl rand -base64 32
```

Copy the output into the Koyeb environment variable.

## Step 3: Restart n8n on Koyeb

After setting environment variables, redeploy:
1. In Koyeb dashboard, click your app
2. Click **Settings** → **Redeploy**
3. Wait for the new deployment to complete (check logs)

When n8n starts successfully, you'll see in the logs:
```
INFO: n8n ready on 0.0.0.0:5678
```

## Step 4: Access n8n

Go to `https://your-n8n-app.koyeb.app` and log in with:
- **Username**: `ajay`
- **Password**: (the one you set)

You're now in the n8n UI. Create your first workflow!

## Step 5: Connect Baadar to n8n

Update your Mac's `~/SaathiAI/.env`:

```bash
N8N_WEBHOOK_BASE=https://your-n8n-app.koyeb.app/webhook/
```

Restart Baadar:
```bash
pkill -f "uvicorn saathi"  # Stop the local server
uvicorn saathi.server:app --port 8765 --reload
```

Now Baadar can trigger n8n workflows via webhooks.

## Step 6: Persist n8n workflows (optional but recommended)

n8n on Koyeb stores workflows in PostgreSQL (Supabase). **No extra setup needed** — workflows are automatically persisted as you create them in the UI.

**Backup workflows to Git**:
If you want to version-control your n8n workflows, export them as JSON:

1. In n8n UI, select a workflow
2. Click **Export** → save as `.json`
3. Commit to Git: `git add n8n-workflows/ && git commit -m "backup: n8n workflows"`

## Troubleshooting

### n8n won't start
- **Check logs** in Koyeb dashboard → Logs tab
- **Verify PostgreSQL credentials** — run this on your Mac:
  ```bash
  psql -h abc123.supabase.co -U postgres -d postgres -c "SELECT 1;"
  ```
  If it prompts for password, enter your `SUPABASE_SERVICE_KEY` value.

### n8n is slow
- Koyeb free tier has limited CPU. Consider upgrading if workflows are complex.
- Monitor execution logs in n8n UI → Execution tab.

### Webhook not firing
- Verify `WEBHOOK_URL` in Koyeb env vars matches your app URL exactly
- In n8n workflow, test the webhook trigger — it will show the webhook URL to POST to
- From Baadar, test with curl:
  ```bash
  curl -X POST https://your-n8n-app.koyeb.app/webhook/my-trigger \
    -H "Content-Type: application/json" \
    -d '{"test": "data"}'
  ```

### Out of storage on Koyeb
- Koyeb free tier includes enough storage for n8n. If you hit limits:
  - Reduce `EXECUTIONS_DATA_MAX_AGE` to prune older executions
  - Or upgrade to Koyeb paid plan ($2/month)

## See also
- [Deploying Baadar on Koyeb](./koyeb-baadar.md)
- [n8n Official Docs](https://docs.n8n.io/)
- [Supabase PostgreSQL Docs](https://supabase.com/docs/guides/database)
