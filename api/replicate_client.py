import os

import replicate


class ReplicateMotionClient:
    """
    Wrapper untuk Kling v3 Motion Control via Replicate API.
    Local mode: pass file objects langsung — SDK upload otomatis ke Replicate CDN.
    """

    def __init__(self):
        self.client = replicate.Client(api_token=os.getenv("REPLICATE_API_TOKEN"))
        self.model = os.getenv("KLING_MODEL", "kwaivgi/kling-v3-motion-control")

    def create_prediction(
        self,
        image_path: str,
        video_path: str,
        mode: str = "std",
        orientation: str = "video",
        duration: int = 10,
        prompt: str = "",
    ) -> str:
        """
        Submit job ke Replicate. Return prediction_id.
        File di-upload langsung dari local path — tidak perlu S3/URL publik.
        """
        with open(image_path, "rb") as img_f, open(video_path, "rb") as vid_f:
            prediction = self.client.predictions.create(
                model=self.model,
                input={
                    "reference_image": img_f,
                    "reference_video": vid_f,
                    "mode": mode,
                    "character_orientation": orientation,
                    "duration": duration,
                    "prompt": prompt,
                },
            )
        return prediction.id

    def get_prediction_status(self, prediction_id: str) -> dict:
        """
        Cek status prediction.
        Return: {id, status, output, error, logs}
        Status: starting | processing | succeeded | failed | canceled
        """
        prediction = self.client.predictions.get(prediction_id)
        output = prediction.output
        if isinstance(output, list) and output:
            output = output[0]
        return {
            "id": prediction.id,
            "status": prediction.status,
            "output": output,
            "error": prediction.error,
            "logs": prediction.logs,
        }

    def cancel_prediction(self, prediction_id: str):
        self.client.predictions.cancel(prediction_id)
