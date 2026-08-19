import os

import httpx

AKOOL_API_BASE = "https://openapi.akool.com/api/open"


class AkoolMotionClient:
    """
    Akool Character Swap v4 — motion transfer.
    image (foto karakter) + video (referensi gerakan) → output video.
    Auth: x-api-key header.
    Status: video_status 1=queue, 3=completed, 4=failed.
    """

    def __init__(self):
        self.api_key = os.getenv("AKOOL_API_KEY")
        if not self.api_key:
            raise ValueError("AKOOL_API_KEY wajib diisi di .env")

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
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
        Submit character swap job. Return job _id.
        mode: std → 720p, pro → 1080p
        """
        resolution = "1080p" if mode == "pro" else "720p"
        payload = {
            "image": image_url,
            "video": video_url,
            "duration": min(duration, 10),  # Akool max 10 detik
            "resolution": resolution,
            "mode": "animate",
            "prompt": prompt or "Smooth character animation with natural movement",
        }

        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{AKOOL_API_BASE}/v4/characterSwap/create",
                headers=self._headers(),
                json=payload,
            )
            if not resp.is_success:
                raise RuntimeError(f"Akool HTTP {resp.status_code}: {resp.text}")
            data = resp.json()

        if data.get("code") != 1000:
            raise RuntimeError(f"Akool error: {data.get('msg')}")

        return data["data"]["_id"]

    def get_prediction_status(self, job_id: str) -> dict:
        """
        Poll status via video_model_id.
        video_status: 1=queue/processing, 3=completed, 4=failed
        """
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{AKOOL_API_BASE}/v3/content/video/infobymodelid",
                headers=self._headers(),
                params={"video_model_id": job_id},
            )
            if not resp.is_success:
                raise RuntimeError(f"Akool status HTTP {resp.status_code}: {resp.text}")
            data = resp.json()

        if data.get("code") != 1000:
            raise RuntimeError(f"Akool error: {data.get('msg')}")

        task = data["data"]
        video_status = task.get("video_status", 1)

        status_map = {
            1: "processing",
            2: "processing",
            3: "succeeded",
            4: "failed",
        }

        return {
            "id": job_id,
            "status": status_map.get(video_status, "processing"),
            "output": task.get("video") if video_status == 3 else None,
            "error": task.get("faceswap_fail_reason") if video_status == 4 else None,
            "logs": "",
        }

    def cancel_prediction(self, job_id: str):
        pass  # Akool tidak expose cancel endpoint
