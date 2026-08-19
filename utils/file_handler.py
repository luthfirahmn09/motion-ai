import os

import magic
from PIL import Image

MAX_PHOTO_MB = int(os.getenv("MAX_PHOTO_SIZE_MB", 10))
MAX_VIDEO_MB = int(os.getenv("MAX_VIDEO_SIZE_MB", 10))
MIN_VIDEO_SEC = int(os.getenv("MIN_VIDEO_DURATION_SEC", 3))
MAX_VIDEO_SEC = int(os.getenv("MAX_VIDEO_DURATION_SEC", 30))

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"}


def validate_photo(file_path: str) -> tuple[bool, str]:
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > MAX_PHOTO_MB:
        return False, f"Foto terlalu besar ({size_mb:.1f}MB). Maksimal {MAX_PHOTO_MB}MB."

    mime = magic.from_file(file_path, mime=True)
    if mime not in ALLOWED_IMAGE_TYPES:
        return False, "Format foto tidak didukung. Gunakan JPG, PNG, atau WEBP."

    try:
        img = Image.open(file_path)
        w, h = img.size
        if w < 256 or h < 256:
            return False, "Resolusi foto terlalu kecil. Minimal 256x256 pixel."
    except Exception:
        return False, "File foto tidak valid atau rusak."

    return True, ""


def validate_video(file_path: str) -> tuple[bool, str]:
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > MAX_VIDEO_MB:
        return False, f"Video terlalu besar ({size_mb:.1f}MB). Maksimal {MAX_VIDEO_MB}MB."

    mime = magic.from_file(file_path, mime=True)
    if mime not in ALLOWED_VIDEO_TYPES:
        return False, "Format video tidak didukung. Gunakan MP4, MOV, atau AVI."

    return True, ""


async def download_telegram_file(bot, file_id: str, save_dir: str, filename: str) -> str:
    os.makedirs(save_dir, exist_ok=True)
    file = await bot.get_file(file_id)
    save_path = os.path.join(save_dir, filename)
    await file.download_to_drive(save_path)
    return save_path


def cleanup(*paths: str):
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.unlink(path)
        except Exception:
            pass
