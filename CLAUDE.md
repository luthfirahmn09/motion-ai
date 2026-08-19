# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram bot that accepts a full-body photo + reference motion video and returns a generated video where the person in the photo mimics the reference motion. Uses Kling v3 Motion Control via Replicate API. Fully async, webhook-based, horizontally scalable.

## Development Commands

```bash
# First-time setup
cp .env.example .env
# Fill in all values in .env

# Start all services (Redis, Postgres, bot, workers, Flower)
docker-compose up -d --build

# Run DB migrations (first time or after model changes)
docker-compose run --rm bot alembic upgrade head

# Create a new migration after model changes
docker-compose run --rm bot alembic revision --autogenerate -m "describe change"

# Tail logs
docker-compose logs -f bot
docker-compose logs -f worker

# Celery task monitoring UI
open http://localhost:5555

# Restart a single service without rebuild
docker-compose restart bot

# Full teardown (keeps volumes)
docker-compose down

# Full teardown including DB and Redis data
docker-compose down -v
```

## Architecture

### Request flow

```
Telegram user
  → HTTPS webhook → FastAPI (bot/main.py :8080/webhook)
  → python-telegram-bot ConversationHandler (bot/handlers.py)
  → validates files, uploads to S3/R2 (api/storage.py)
  → creates Job row in Postgres, marks user active in Redis
  → enqueues Celery task (worker/tasks.py: process_motion_transfer)
  → Celery worker calls Replicate API (api/replicate_client.py)
  → polls prediction status every N seconds
  → on success: downloads output → re-uploads to S3 → sends video via Telegram HTTP API
```

### Conversation state machine

Three states defined in `bot/states.py`:
- `WAIT_PHOTO (1)` → `WAIT_VIDEO (2)` → `CONFIRM_PROCESS (3)` → END

ConversationHandler entry points: `/start`, `/buat`, `/new`. Timeout: 10 minutes idle.

### Job status lifecycle

`queued → uploading → processing → completed | failed`

Stored in `jobs.status` (Postgres). Active job also tracked in Redis key `active_job:{user_id}` with TTL.

### Rate limiting (utils/rate_limiter.py + Redis)

- Per-user: max 1 concurrent job, max N jobs/day (sliding daily key)
- Global: sliding window 60s on Replicate API calls (`GLOBAL_API_CALLS_PER_MINUTE`)

### Storage pattern

All file I/O goes through `api/storage.py` (boto3 → Cloudflare R2 or AWS S3). Input files are deleted after job completes. Output files are kept for re-delivery. Presigned URLs (1h TTL) are passed to Replicate — Replicate fetches inputs directly from S3.

### Worker concurrency

Celery workers run sync tasks (Replicate polling is blocking `time.sleep` loop). `worker_prefetch_multiplier=1` + `task_acks_late=True` for fair distribution. Default: 2 replicas × 20 concurrency = 40 parallel jobs. Scale by adding worker replicas in docker-compose.

## Key env variables

| Variable | Purpose |
|---|---|
| `KLING_MODE` | `std` (720p) or `pro` (1080p) |
| `KLING_ORIENTATION` | `image` or `video` (follow photo or video frame) |
| `KLING_DURATION` | Output seconds, max 10 (image mode) / 30 (video mode) |
| `POLLING_INTERVAL_SEC` | Seconds between Replicate status polls |
| `POLLING_MAX_RETRIES` | Max polls before timeout (72 × 5s = 6min) |
| `CELERY_CONCURRENCY` | Workers per Celery process |

## Replicate model

Model ID: `kwaivgi/kling-v3-motion-control`

Inputs: `reference_image` (public URL), `reference_video` (public URL), `mode`, `character_orientation`, `duration`, `prompt`, `negative_prompt`.

`create_prediction()` returns a prediction ID — polling is manual via `get_prediction_status()`. Do **not** use `replicate.run()` (blocking, no polling control).

## Database

SQLAlchemy 2.x with asyncpg for async queries from the bot, sync psycopg2 from Celery workers. Alembic for migrations. Two tables: `users` (quota tracking) and `jobs` (full job lifecycle).
