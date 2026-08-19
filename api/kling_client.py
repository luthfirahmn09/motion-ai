import os

import httpx

from api.stealth import apply_request_delay, get_proxy, get_stealth_headers, STEALTH_ENABLED

MAGNIFIC_API_BASE = "https://api.magnific.com/v1/ai/video"


class KlingMotionClient:
    """
    Kling v2.6 Motion Control via Freepik Magnific API.
    Auth: x-magnific-api-key header.
    Endpoint: /kling-v2-6-motion-control-{std|pro}

    Stealth features (when STEALTH_ENABLED=true):
    - Proxy rotation per request
    - Randomized browser fingerprint headers
    - Request delay jitter
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("FREEPIK_API_KEY")
        if not self.api_key:
            raise ValueError("FREEPIK_API_KEY wajib diisi di .env atau set API key di bot settings")

    def _headers(self) -> dict:
        """Build request headers with stealth fingerprint + API auth."""
        headers = get_stealth_headers()  # randomized browser headers
        # API-specific headers (override stealth where needed)
        headers["x-magnific-api-key"] = self.api_key
        headers["Content-Type"] = "application/json"
        return headers

    def _make_client(self, timeout: int = 60) -> httpx.Client:
        """Create httpx client with optional proxy."""
        proxy = get_proxy() if STEALTH_ENABLED else None
        kwargs = {"timeout": timeout}
        if proxy:
            kwargs["proxies"] = {"http://": proxy, "https://": proxy}
        return httpx.Client(**kwargs)

    def create_prediction(
        self,
        image_url: str,
        video_url: str,
        mode: str = "std",
        orientation: str = "video",
        duration: int = 10,
        prompt: str = "",
        cfg_scale: float = 0.5,
        aspect_ratio: str = "9:16",
    ) -> str:
        """
        Submit motion control job. Return task id.
        mode: std → kling-v2-6-motion-control-std
              pro  → kling-v2-6-motion-control-pro
        Max input: 10MB image, 10MB video, 3-30 detik.
        """
        endpoint = f"{MAGNIFIC_API_BASE}/kling-v2-6-motion-control-{mode}"
        payload = {
            "image_url": image_url,
            "video_url": video_url,
            "character_orientation": orientation,
            "cfg_scale": cfg_scale,
            "aspect_ratio": aspect_ratio,
        }
        if prompt:
            payload["prompt"] = prompt

        # Stealth: random delay before request
        apply_request_delay()

        with self._make_client(timeout=60) as client:
            resp = client.post(endpoint, headers=self._headers(), json=payload)
            if not resp.is_success:
                raise RuntimeError(f"Freepik API {resp.status_code}: {resp.text}")
            data = resp.json()

        task_id = data.get("data", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"Task id tidak ditemukan di response: {data}")
        return task_id

    def get_prediction_status(self, task_id: str, mode: str = "std") -> dict:
        """
        Poll status task.
        Return: {id, status, output, error, logs}
        GET /v1/ai/image-to-video/kling-v2-6/{task_id}
        """
        # No delay for polling — only for create requests
        with self._make_client(timeout=30) as client:
            resp = client.get(
                f"https://api.magnific.com/v1/ai/image-to-video/kling-v2-6/{task_id}",
                headers=self._headers(),
            )
            if not resp.is_success:
                raise RuntimeError(f"Freepik status {resp.status_code}: {resp.text}")
            data = resp.json()

        # Normalize dari berbagai kemungkinan format response
        task = data.get("data") or data
        raw_status = task.get("status", "")

        status_map = {
            "CREATED": "starting",
            "IN_PROGRESS": "processing",
            "COMPLETED": "succeeded",
            "FAILED": "failed",
            # lowercase fallback
            "created": "starting",
            "pending": "starting",
            "processing": "processing",
            "completed": "succeeded",
            "failed": "failed",
        }

        output = None
        if status_map.get(raw_status) == "succeeded":
            # generated = ["https://...url_video..."]
            generated = task.get("generated", [])
            if generated and isinstance(generated, list):
                output = generated[0] if isinstance(generated[0], str) else generated[0].get("url")

        return {
            "id": task_id,
            "status": status_map.get(raw_status, "processing"),
            "output": output,
            "error": task.get("error") or task.get("message") if status_map.get(raw_status) == "failed" else None,
            "logs": "",
        }

    def cancel_prediction(self, task_id: str):
        pass
