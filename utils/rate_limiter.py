import os
import time

import redis

_redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def check_user_quota(user_id: int) -> tuple[bool, str]:
    max_daily = int(os.getenv("MAX_JOBS_PER_USER_PER_DAY", 10))

    if _redis.exists(f"active_job:{user_id}"):
        return False, "kamu masih punya job yang sedang diproses. Tunggu selesai dulu ya!"

    daily_key = f"daily_quota:{user_id}:{time.strftime('%Y%m%d')}"
    count = _redis.get(daily_key)
    count = int(count) if count else 0

    if count >= max_daily:
        return False, f"quota harian kamu sudah habis ({max_daily} video/hari). Coba lagi besok!"

    return True, ""


def mark_user_active(user_id: int, job_id: str, ttl_seconds: int = 600):
    _redis.setex(f"active_job:{user_id}", ttl_seconds, job_id)


def mark_user_done(user_id: int):
    _redis.delete(f"active_job:{user_id}")


def increment_daily_quota(user_id: int):
    daily_key = f"daily_quota:{user_id}:{time.strftime('%Y%m%d')}"
    pipe = _redis.pipeline()
    pipe.incr(daily_key)
    pipe.expire(daily_key, 86400)
    pipe.execute()


def check_global_rate_limit() -> bool:
    limit = int(os.getenv("GLOBAL_API_CALLS_PER_MINUTE", 15))
    key = "global_api_calls"
    now = time.time()
    window_start = now - 60

    pipe = _redis.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, 120)
    results = pipe.execute()

    return results[2] <= limit
