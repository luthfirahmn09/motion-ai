import os
import subprocess
import threading
import time

import httpx

from api.kling_client import KlingMotionClient
from api.storage import LocalStorage
from db.crud import get_job, get_user, update_job_replicate_id, update_job_status
from utils.rate_limiter import check_global_rate_limit, mark_user_done
from worker.celery_app import celery_app

POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL_SEC", 5))
POLLING_MAX = int(os.getenv("POLLING_MAX_RETRIES", 72))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def _send_message(chat_id: int, text: str, parse_mode: str = "HTML", reply_markup: dict | None = None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    with httpx.Client(timeout=10) as client:
        client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload,
        )


def _send_video(chat_id: int, video_path: str, caption: str):
    with open(video_path, "rb") as f:
        with httpx.Client(timeout=120) as client:
            client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo",
                data={
                    "chat_id": str(chat_id),
                    "caption": caption,
                    "parse_mode": "HTML",
                    "supports_streaming": "true",
                },
                files={"video": f},
            )


def _send_chat_action(chat_id: int, action: str = "upload_video"):
    with httpx.Client(timeout=5) as client:
        client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendChatAction",
            json={"chat_id": chat_id, "action": action},
        )


def _send_video_with_keepalive(chat_id: int, video_path: str, caption: str):
    """Send video file while keeping 'upload_video' chat action alive."""
    stop_event = threading.Event()

    def _keepalive():
        while not stop_event.is_set():
            _send_chat_action(chat_id, "upload_video")
            stop_event.wait(4)

    t = threading.Thread(target=_keepalive, daemon=True)
    t.start()
    try:
        _send_video(chat_id, video_path, caption)
    finally:
        stop_event.set()
        t.join(timeout=5)


def _compress_video(input_path: str, max_mb: int = 45) -> str:
    """Re-encode with CRF 28 if file exceeds max_mb. Returns path to use (original or compressed)."""
    size_mb = os.path.getsize(input_path) / (1024 * 1024)
    if size_mb <= max_mb:
        return input_path

    output_path = input_path.replace(".", "_compressed.", 1)
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vcodec", "libx264", "-crf", "28", "-preset", "fast",
        "-vf", "scale='min(1280,iw)':-2",
        "-acodec", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0 or not os.path.exists(output_path):
        return input_path
    return output_path


def _deliver_video(chat_id: int, output_url: str, video_path: str, caption: str):
    """
    Try to deliver video in order:
    1. Send URL directly (Telegram downloads it — no upload limit on our side)
    2. Upload local file (works up to 50MB)
    3. Send download link as fallback
    """
    # 1. Try by URL
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo",
                json={
                    "chat_id": chat_id,
                    "video": output_url,
                    "caption": caption,
                    "parse_mode": "HTML",
                    "supports_streaming": True,
                },
            )
            if resp.status_code == 200:
                return
    except Exception:
        pass

    # 2. Upload local file
    try:
        _send_video_with_keepalive(chat_id, video_path, caption)
        return
    except Exception:
        pass

    # 3. Send link
    _send_message(
        chat_id,
        f"{caption}\n\n🔗 <a href=\"{output_url}\">Download Video</a>",
    )


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def process_motion_transfer(self, job_id: str):
    from db.database import SessionLocal

    db = SessionLocal()
    storage = LocalStorage()
    job = None

    try:
        job = get_job(db, job_id)
        if not job:
            return

        chat_id = job.chat_id
        user_id = job.user_id

        db_user = get_user(db, user_id)
        user_api_key = db_user.user_api_key if db_user else None
        client = KlingMotionClient(api_key=user_api_key)

        update_job_status(db, job_id, "uploading")

        wait_count = 0
        while not check_global_rate_limit():
            time.sleep(2)
            wait_count += 1
            if wait_count > 30:
                raise Exception("Global rate limit exceeded too long")

        update_job_status(db, job_id, "processing")
        _send_message(chat_id, "⏳ <b>Video sedang diproses...</b>")

        task_id = client.create_prediction(
            image_url=job.photo_path,
            video_url=job.video_path,
            mode=job.mode or "std",
            orientation=job.orientation or "video",
            duration=int(os.getenv("KLING_DURATION", 10)),
            # aspect_ratio=job.aspect_ratio or "9:16",  # TODO: belum aktif
        )
        update_job_replicate_id(db, job_id, task_id)

        last_progress_msg = 0
        for attempt in range(POLLING_MAX):
            time.sleep(POLLING_INTERVAL)

            result = client.get_prediction_status(task_id, mode=job.mode or "std")
            status = result["status"]

            elapsed = (attempt + 1) * POLLING_INTERVAL

            # Keep upload_video indicator active every poll cycle
            _send_chat_action(chat_id, "upload_video")

            # Send text update every 30s
            if elapsed - last_progress_msg >= 30:
                mins, secs = divmod(elapsed, 60)
                _send_message(chat_id, f"⏳ Video masih diproses... ({mins}m {secs}s)")
                last_progress_msg = elapsed

            if status == "succeeded":
                output_url = result["output"]
                _send_message(chat_id, "✅ <b>Selesai! Mengirim video ke kamu...</b>")

                output_key = storage.download_from_url(output_url, prefix="outputs")
                output_path = storage.get_file_path(output_key)
                output_path = _compress_video(output_path)
                update_job_status(db, job_id, "completed", output_path=output_path)

                _deliver_video(
                    chat_id,
                    output_url,
                    output_path,
                    caption="🎬 <b>Video kamu sudah jadi!</b>\n\nKetik /buat untuk buat video baru.",
                )

                for path in {output_path, output_path.replace(".", "_compressed.", 1)}:
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                    except OSError:
                        pass

                return

            elif status == "failed":
                error = result.get("error") or ""
                update_job_status(db, job_id, "failed", error_message=error)
                _send_message(
                    chat_id,
                    "❌ <b>Proses Gagal</b>\n\n"
                    "Kuota API sudah habis. Silakan ganti dengan API key baru di:\n"
                    "⚙️ <b>Account Settings → 🔑 API Settings</b>",
                )
                return

            elif status == "canceled":
                update_job_status(db, job_id, "failed", error_message="Canceled")
                _send_message(chat_id, "⚠️ Proses dibatalkan. Ketik /buat untuk coba lagi.")
                return

        update_job_status(db, job_id, "failed", error_message="Timeout")
        _send_message(
            chat_id,
            "⏰ <b>Proses Gagal</b>\n\n"
            "Waktu habis, server sedang sibuk. Coba lagi nanti dengan /buat.",
        )

    except Exception as exc:
        if job:
            update_job_status(db, job_id, "failed", error_message=str(exc))
            exc_str = str(exc)
            if "429" in exc_str and ("free trial" in exc_str or "billing" in exc_str):
                _send_message(
                    job.chat_id,
                    "❌ <b>API Key Habis</b>\n\n"
                    "Kuota free trial API key kamu sudah habis.\n"
                    "Silakan upgrade atau ganti API key baru.",
                    reply_markup={
                        "inline_keyboard": [[
                            {"text": "🔑 Ganti API Key", "callback_data": "open_settings"}
                        ]]
                    },
                )
                return
            _send_message(
                job.chat_id,
                "❌ Terjadi kesalahan sistem. Ketik /buat untuk coba lagi.",
            )
        raise self.retry(exc=exc)

    finally:
        if job:
            mark_user_done(job.user_id)
        db.close()
