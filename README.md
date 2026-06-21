# XAuto

Self-contained X (Twitter) post automation platform with a web dashboard, Gemini-powered draft generation, Vercel KV storage, and scheduled publishing via Vercel Cron.

Built for [@devmuradahmed](https://x.com/devmuradahmed) — software architecture, enterprise AI platforms, and agentic QA systems.

## Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, Tailwind CSS, vanilla JavaScript |
| Backend | Python serverless functions (`/api`) |
| Database | Vercel KV (Redis / Upstash REST) |
| AI | Google Gemini `gemini-2.5-flash` |
| Publishing | Tweepy (X API v2) |
| Hosting | Vercel |

## Project structure

```
├── api/
│   ├── generate.py      # Gemini draft generation
│   ├── posts.py         # CRUD for posts
│   ├── publish.py       # Cron + manual publish
│   └── lib/             # KV + HTTP helpers
├── index.html           # Dashboard UI
├── scripts/
│   ├── dev.ps1          # Local dev (Windows)
│   └── dev.sh           # Local dev (macOS/Linux)
├── requirements.txt
├── vercel.json
├── package.json
└── .env.example
```

## Post schema (Vercel KV)

Posts are stored as a JSON array under the key `xauto:posts`.

```json
{
  "id": "uuid",
  "content": "tweet text",
  "scheduled_for": "2026-06-21T18:00:00Z",
  "status": "draft | approved | published",
  "created_at": "2026-06-21T14:00:00Z",
  "published_at": "2026-06-21T18:00:00Z",
  "tweet_id": "1234567890"
}
```

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` / `POST` | `/api/generate` | Generate a Gemini draft (scheduled +4h, status `draft`) |
| `GET` | `/api/posts` | List all posts |
| `POST` | `/api/posts` | `{ "action": "approve", "id": "..." }` or `{ "action": "create", "content": "...", "scheduled_for": "..." }` |
| `DELETE` | `/api/posts` | `{ "id": "..." }` |
| `GET` / `POST` | `/api/publish` | Publish due approved posts (cron or manual) |

## Local development

### Prerequisites

- [Node.js](https://nodejs.org/) 18+
- [Python](https://www.python.org/) 3.12+
- [Vercel CLI](https://vercel.com/docs/cli): `npm i -g vercel`

### Quick start

```bash
# 1. Install Vercel CLI (if needed)
npm i -g vercel

# 2. Copy env template and fill in values
cp .env.example .env.local

# 3. Link to a Vercel project (first time only)
vercel link

# 4. Pull env vars from Vercel (optional, if already deployed)
npm run pull-env

# 5. Start dev server
npm run dev
# or on Windows:
# .\scripts\dev.ps1
```

Open **http://localhost:3000** — the dashboard talks to Python functions at `/api/*` via `vercel dev`.

### Environment variables

Copy `.env.example` to `.env.local` for local dev. Vercel loads `.env.local` automatically.

| Variable | Required | Description |
|---|---|---|
| `KV_REST_API_URL` | Yes | Auto-injected when Vercel KV is linked |
| `KV_REST_API_TOKEN` | Yes | Auto-injected when Vercel KV is linked |
| `GEMINI_API_KEY` | Yes | [Google AI Studio](https://aistudio.google.com/apikey) |
| `TWITTER_API_KEY` | For publish | X Developer Portal — OAuth 1.0a |
| `TWITTER_API_SECRET` | For publish | X Developer Portal |
| `TWITTER_ACCESS_TOKEN` | For publish | User access token (Read + Write) |
| `TWITTER_ACCESS_TOKEN_SECRET` | For publish | User access token secret |
| `CRON_SECRET` | Recommended | Secures `/api/publish` in production |

## Deploy to Vercel

### 1. Push to Git

```bash
git init
git add .
git commit -m "Initial XAuto platform"
git remote add origin <your-repo-url>
git push -u origin main
```

### 2. Import project

1. Go to [vercel.com/new](https://vercel.com/new)
2. Import your repository
3. Framework preset: **Other** (static root + Python `/api`)

### 3. Add Vercel KV

1. Project → **Storage** → **Create Database** → **KV**
2. Link it to the project — `KV_REST_API_URL` and `KV_REST_API_TOKEN` are injected automatically

### 4. Set environment variables

In **Project → Settings → Environment Variables**, add:

- `GEMINI_API_KEY`
- `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET`
- `CRON_SECRET` (generate a random string, e.g. `openssl rand -hex 32`)

Apply to **Production**, **Preview**, and **Development**.

### 5. Deploy

```bash
npm run deploy
# or: vercel --prod
```

### 6. Cron job

`vercel.json` configures a cron that hits `/api/publish` every 5 minutes:

```json
{
  "crons": [{ "path": "/api/publish", "schedule": "*/5 * * * *" }]
}
```

> **Note:** Vercel Hobby plans limit cron to once per day. Pro plans support per-minute schedules. Adjust the schedule in `vercel.json` to match your plan.

When `CRON_SECRET` is set, Vercel Cron sends `Authorization: Bearer <CRON_SECRET>` automatically.

## X (Twitter) API setup

1. Create a project at [developer.x.com](https://developer.x.com)
2. Enable **OAuth 1.0a** with **Read and Write** permissions
3. Generate **Access Token & Secret** for @devmuradahmed
4. Add all four credentials to Vercel environment variables

## Dashboard workflow

1. **Generate Draft** — calls Gemini, saves a draft scheduled 4 hours ahead
2. **Review Drafts** — approve or delete each draft
3. **Approved Queue** — live countdown until publish time
4. **Publish Now** — manually triggers `/api/publish` for due posts
5. **Settings (gear icon)** — store `CRON_SECRET` locally for manual publish in production

## Manual publish (CLI)

```bash
curl -X POST https://your-app.vercel.app/api/publish \
  -H "Authorization: Bearer YOUR_CRON_SECRET"
```

## Troubleshooting

| Issue | Fix |
|---|---|
| `KV_REST_API_URL must be configured` | Link a Vercel KV store to the project |
| `GEMINI_API_KEY is not configured` | Add key to env vars and redeploy |
| `Unauthorized` on Publish Now | Open Settings and paste your `CRON_SECRET` |
| Cron not firing | Check Vercel plan limits; verify cron in Project → Settings → Cron Jobs |
| Tweet fails | Confirm X app has Write permissions and tokens match @devmuradahmed |

## License

Private / personal use.
