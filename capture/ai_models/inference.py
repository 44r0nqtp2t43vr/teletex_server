from django.apps import apps
from PIL import Image
import numpy as np
import torch
import torchvision.transforms.functional as TF

IMAGE_SIZE = 256


def get_loaded_model():
    app_config = apps.get_app_config("capture")
    model = getattr(app_config, "ai_model", None)
    device = getattr(app_config, "ai_device", "cpu")

    if model is None:
        raise RuntimeError("AI model is not loaded.")

    return model, device


def predict_binary_from_pil(pil_img: Image.Image) -> np.ndarray:
    model, device = get_loaded_model()

    img = pil_img.convert("RGB")
    img = TF.resize(img, (IMAGE_SIZE, IMAGE_SIZE))
    img_t = TF.to_tensor(img).unsqueeze(0).to(device)

    with torch.no_grad():
        pred = model(img_t)
        pred = torch.sigmoid(pred)
        pred = (pred > 0.5).float()

    pred = pred.squeeze().cpu().numpy().astype(np.uint8) * 255
    return pred