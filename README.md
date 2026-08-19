# 🕺 Motion AI Bot

A Telegram bot that turns a full-body photo + a reference motion video into a new video of the person in the photo performing that motion — built on Kling's motion-control model (via the Freepik Magnific API), with subscriptions, quotas, and a Midtrans payment flow on top.

## How it works

```
Telegram user
  → webhook (FastAPI, bot/main.py)
  → python-telegram-bot ConversationHandler (bot/handlers.py)
  → validates files, stores them (api/storage.py)
  → creates a Job row (Postgres) + enqueues a Celery task
  → worker/tasks.py calls the motion-generation provider (api/kling_client.py)
  → polls prediction status until done
  → downloads the output, sends it back via the Telegram Bot API
```

Bot and workers are separate processes/containers, coordinated through Redis, so the bot keeps responding to other users while a job renders in the background.

**Conversation states** (`bot/states.py`): `WAIT_PHOTO → WAIT_VIDEO → CONFIRM_PROCESS → END`. Entry points: `/start`, `/buat`, `/new`. Idle timeout: 10 minutes.

**Job lifecycle**: `queued → uploading → processing → completed | failed`, tracked in the `jobs` table and mirrored in Redis (`active_job:{user_id}`) for fast lookups.

## Subscriptions & payments

- Each Telegram user has an `account_status` (whitelist by default) and an optional `subscription_status` + `subscription_expires_at`.
- New users pick a plan (`subscription_plans` table) and pay through **Midtrans Snap**; a webhook (`/midtrans/notification`) verifies the payment signature and activates the account automatically.
- Users can optionally supply their own provider API key (`user_api_key`) instead of using the bot's shared quota.

## Rate limiting

Implemented in `utils/rate_limiter.py` on top of Redis:
- Per-user: 1 concurrent job, capped jobs/day.
- Global: a sliding 60-second window on provider API calls (`GLOBAL_API_CALLS_PER_MINUTE`), so one bot instance doesn't blow through the provider's own rate limit.

## Providers

`api/kling_client.py` (Freepik Magnific — Kling v2.6 motion control) is the active provider. `api/replicate_client.py`, `api/akool_client.py`, and `api/fal_client.py` exist as alternate motion-generation backends behind the same interface, for swapping providers without touching the bot/worker code.

Outbound provider requests optionally go through `api/stealth.py`: proxy rotation and randomized browser-like headers/timing, configured via `PROXY_URL`/`PROXY_LIST` and `STEALTH_ENABLED`. Off by default unless a proxy is configured.

## Storage

`api/storage.py` currently uses local filesystem storage (`TEMP_DIR`, default `./storage`) as a Docker bind-mount shared between the `bot` and `worker` containers. Input files are deleted after a job completes; outputs are kept for re-delivery.

## Database

SQLAlchemy 2.x — `asyncpg` for the async bot, `psycopg2` for sync Celery tasks — with Alembic migrations (`alembic/versions/`). Core tables: `users`, `subscription_plans`, `subscription_transactions`, `jobs`.

## Getting started

```bash
cp .env.example .env
# fill in the required values — see SETUP.md for how to get each one

docker-compose up -d --build
docker-compose run --rm bot alembic upgrade head   # first run: create tables
docker-compose logs -f bot
docker-compose logs -f worker

open http://localhost:5555   # Flower — Celery task monitoring
```

Local dev without Docker:

```bash
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python -m bot.main
celery -A worker.celery_app worker --loglevel=info --concurrency=2
```

Full account/service setup (Telegram bot, Freepik/Kling API key, storage, VPS + domain for the webhook) is in [`SETUP.md`](SETUP.md).

## Key environment variables

| Variable | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` / `WEBHOOK_URL` | Bot auth + public HTTPS URL for the Telegram webhook |
| `FREEPIK_API_KEY` | Motion-control provider key |
| `KLING_ORIENTATION` / `KLING_DURATION` | Follow photo or video framing; output length |
| `DATABASE_URL` / `REDIS_URL` | Postgres + Redis connection strings |
| `MAX_JOBS_PER_USER_PER_DAY` / `GLOBAL_API_CALLS_PER_MINUTE` | Quota + rate-limit knobs |
| `MIDTRANS_SERVER_KEY` / `MIDTRANS_CLIENT_KEY` / `MIDTRANS_IS_PRODUCTION` | Payment gateway credentials |
| `PROXY_URL` / `PROXY_LIST` / `STEALTH_ENABLED` | Optional outbound proxy + request fingerprinting |

See `.env.example` for the full list.

## Project structure

```
bot/        # FastAPI webhook entry point, conversation handlers, keyboards, states
worker/     # Celery app + the motion-transfer task
api/        # provider clients (kling/replicate/akool/fal), storage, midtrans, stealth
db/         # SQLAlchemy models + CRUD helpers
alembic/    # migrations
utils/      # rate limiter, file handling, logging
```

## License

MIT
