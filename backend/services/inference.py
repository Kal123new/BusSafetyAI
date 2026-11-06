import io
import logging
import os
import tempfile
import threading
import time
import warnings
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageStat, UnidentifiedImageError


class Inference:
    def __init__(self, settings):
        self.settings = settings
        self.model = None
        self.message = "AI model not loaded"
        self.lock = threading.Lock()

    def load(self):
        if not self.settings.model_path:
            return
        if not Path(self.settings.model_path).is_file():
            self.message = "Configured model file was not found"
            return
        try:
            logging.getLogger(__name__).info('Loading person-detection model')
            os.environ.setdefault('YOLO_CONFIG_DIR', str(Path(tempfile.gettempdir()) / 'safesense-local' / 'yolo-settings'))
            os.environ['YOLO_AUTOINSTALL'] = 'False'
            os.environ['YOLO_OFFLINE'] = 'True'
            from ultralytics import YOLO
            from ultralytics import settings as yolo_settings
            import torch
            torch.set_num_threads(4)
            yolo_settings.update({'sync': False})
            self.model = YOLO(self.settings.model_path)
            self.model.predict(Image.new('RGB', (640, 480), (110, 110, 110)), verbose=False)
            self.message = "AI model loaded"
        except Exception:
            logging.getLogger(__name__).exception('Person-detection model failed to load')
            self.model = None
            self.message = "AI model could not be loaded; check dependencies and model compatibility"

    def response(self, status, frame_id, captured_at, detections=None):
        detections = detections or []
        return {"model_loaded": self.model is not None, "message": self.message,
                "frame_status": status, "frame_id": frame_id, "captured_at": captured_at,
                "processed_at": time.time(), "model_version": Path(self.settings.model_path).name or None,
                "detections": detections,
                "visible_person_count": sum(d["class_name"].lower() == "person" for d in detections) if status == "valid" else None}

    def predict(self, data, frame_id, captured_at):
        if len(data) > self.settings.max_upload_bytes:
            raise HTTPException(413, "Frame exceeds 5 MB")
        if captured_at is not None and not 0 <= time.time() - captured_at <= 10:
            return self.response("stale", frame_id, captured_at)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(io.BytesIO(data))
                if image.width * image.height > 16_000_000:
                    raise HTTPException(413, "Frame resolution exceeds 16 megapixels")
                image = image.convert("RGB")
                stats = ImageStat.Stat(image.resize((96, 54)).convert("L"))
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            return self.response("decode_error", frame_id, captured_at)
        if stats.mean[0] < 6 and stats.stddev[0] < 4:
            return self.response("too_dark", frame_id, captured_at)
        if self.model is None:
            return self.response("model_unavailable", frame_id, captured_at)
        if not self.lock.acquire(blocking=False):
            raise HTTPException(429, "Inference busy; send the latest frame later")
        try:
            result = self.model.predict(image, conf=self.settings.confidence, verbose=False)[0]
            detections = []
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                x1, x2 = sorted((max(0, min(image.width, x1)), max(0, min(image.width, x2))))
                y1, y2 = sorted((max(0, min(image.height, y1)), max(0, min(image.height, y2))))
                class_id = int(box.cls[0])
                detections.append({"class_id": class_id, "class_name": str(result.names[class_id]),
                                   "confidence": float(box.conf[0]), "x": x1 / image.width * 100,
                                   "y": y1 / image.height * 100, "width": (x2 - x1) / image.width * 100,
                                   "height": (y2 - y1) / image.height * 100})
            return self.response("valid", frame_id, captured_at, detections)
        except Exception:
            return self.response("inference_error", frame_id, captured_at)
        finally:
            self.lock.release()
