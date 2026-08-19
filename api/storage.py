import os
import shutil
import uuid
from pathlib import Path

import httpx


class LocalStorage:
    """
    Local filesystem storage — pengganti S3/R2 untuk development.
    Semua file disimpan di TEMP_DIR (default: ./storage).
    """

    def __init__(self):
        self.base_dir = Path(os.getenv("TEMP_DIR", "./storage")).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_file(self, local_path: str, prefix: str = "uploads") -> str:
        """Copy file ke storage dir. Return relative key."""
        ext = Path(local_path).suffix
        key = f"{prefix}/{uuid.uuid4()}{ext}"
        dest = self.base_dir / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)
        return key

    def get_file_path(self, key: str) -> str:
        """Return absolute path untuk stored file."""
        return str(self.base_dir / key)

    def download_from_url(self, url: str, prefix: str = "outputs") -> str:
        """Download dari URL (hasil Replicate) ke storage. Return key."""
        key = f"{prefix}/{uuid.uuid4()}.mp4"
        dest = self.base_dir / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            dest.write_bytes(response.content)
        return key

    def delete_file(self, key: str):
        path = self.base_dir / key
        if path.exists():
            path.unlink()
