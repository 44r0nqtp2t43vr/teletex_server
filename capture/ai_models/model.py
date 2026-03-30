# app/ai_models/model.py

import torch
import segmentation_models_pytorch as smp

def load_model(model_path, device="cpu"):
    model = smp.UnetPlusPlus(
        encoder_name="resnet34",
        encoder_weights=None,  # IMPORTANT
        in_channels=3,
        classes=1
    )

    state_dict = torch.load(model_path, map_location=device)
    model.load_state_dict(state_dict)

    model.eval()
    model.to(device)

    return model