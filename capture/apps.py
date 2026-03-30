from django.apps import AppConfig
from django.conf import settings
from pathlib import Path
import torch


class CaptureConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'capture'

    ai_model = None
    ai_device = None

    def ready(self):
        try:
            from capture.ai_models.model import load_model

            model_path = Path(settings.BASE_DIR) / "capture" / "ai_models" / "best_texture_model.pth"
            device = "cuda" if torch.cuda.is_available() else "cpu"

            self.ai_device = device
            self.ai_model = load_model(str(model_path), device=device)

            print(f"[AI] Model loaded on {device}: {model_path}")
        except Exception as e:
            print(f"[AI] Model not loaded: {e}")
            self.ai_model = None
            self.ai_device = None