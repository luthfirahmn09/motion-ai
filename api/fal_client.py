import os
import time

import httpx

FAL_API_BASE = "https://queue.fal.run"

# Default: Kling v2 motion control di fal.ai
# Ganti via FAL_MODEL env jika model berubah
FAL_MODEL = os.getenv("FAL_MODEL", "fal-ai/kling-video/v2/master/image-to-video")


class FalMotionClient:
    """
    fal.ai queue API — Motion/Video generation.
    Auth: FAL_KEY via Authorization header.
    Async queue: submit → poll status → get result.
    """

    def __init__(self):
        self.api_key = os.getenv("FAL_KEY")
        self.model = FAL_MODEL
        if not self.api_key:
            raise ValueError("FAL_KEY wajib diisi di .env")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }

    def create_prediction(
        self,
        image_url: str,
        video_url: str,
        mode: str = "std",
        orientation: str = "video",
        duration: int = 10,
        prompt: str = "",
    ) -> str:
        """
        Submit job ke fal.ai queue. Return request_id.
        video_url dipakai kalau model mendukung reference video (motion control).
        """
        payload = {
            "image_url": image_url,
            "duration": str(duration),
            "aspect_ratio": "9:16",
        }
        if prompt:
            payload["prompt"] = prompt

        # Beberapa fal.ai model Kling support reference video
        if video_url:
            payload["reference_video_url"] = video_url

        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{FAL_API_BASE}/{self.model}",
                headers=self._headers(),
                json=payload,
            )
            if not resp.is_success:
                raise RuntimeError(f"fal.ai HTTP {resp.status_code}: {resp.text}")
            data = resp.json()

        return data["request_id"]

    def get_prediction_status(self, request_id: str) -> dict:
        """
        Poll status request.
        fal.ai status: IN_QUEUE | IN_PROGRESS | COMPLETED | FAILED
        Mapped ke: starting | processing | succeeded | failed
        """
        status_url = f"{FAL_API_BASE}/{self.model}/requests/{request_id}/status"
        with httpx.Client(timeout=30) as client:
            resp = client.get(status_url, headers=self._headers())
            if not resp.is_success:
                raise RuntimeError(f"fal.ai status HTTP {resp.status_code}: {resp.text}")
            data = resp.json()

        raw_status = data.get("status", "")
        status_map = {
            "IN_QUEUE": "starting",
            "IN_PROGRESS": "processing",
            "COMPLETED": "succeeded",
            "FAILED": "failed",
        }

        output = None
        if raw_status == "COMPLETED":
            # Fetch result
            result_url = f"{FAL_API_BASE}/{self.model}/requests/{request_id}"
            with httpx.Client(timeout=30) as client:
                r = client.get(result_url, headers=self._headers())
                if r.is_success:
                    result = r.json()
                    # fal.ai output: {"video": {"url": "..."}} atau {"output": {"video": ...}}
                    video = result.get("video") or result.get("output", {})
                    if isinstance(video, dict):
                        output = video.get("url")
                    elif isinstance(video, list) and video:
                        output = video[0].get("url")

        return {
            "id": request_id,
            "status": status_map.get(raw_status, raw_status),
            "output": output,
            "error": data.get("error") if raw_status == "FAILED" else None,
            "logs": "",
        }

    def cancel_prediction(self, request_id: str):
        with httpx.Client(timeout=10) as client:
            client.delete(
                f"{FAL_API_BASE}/{self.model}/requests/{request_id}",
                headers=self._headers(),
            )
