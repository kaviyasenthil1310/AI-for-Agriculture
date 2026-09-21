import os
import gc
import logging

import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image

from backend.model import get_model
from backend.labels import CLASS_NAMES

IMG_SIZE = 224
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

NUM_CLASSES = 5
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CHECKPOINT = os.path.join(BASE_DIR, "..", "models", "leaf_disease_cnn.pth")

# If there is no trained checkpoint, use a lightweight heuristic so
# different images produce different (but approximate) outputs.
USE_HEURISTIC = not os.path.isfile(CHECKPOINT)

if USE_HEURISTIC:
    logging.warning(f"Model checkpoint not found at '{CHECKPOINT}'. Using heuristic fallback for predictions.")

# Lazy load model - don't load at import time
_model_cache = None

def get_cached_model():
    """Lazy load model on first use to avoid blocking server startup"""
    global _model_cache
    
    if _model_cache is not None:
        return _model_cache if _model_cache != False else None
    
    if USE_HEURISTIC:
        _model_cache = False  # Mark as not needed
        return None
    
    try:
        model = get_model(num_classes=NUM_CLASSES, checkpoint_path=CHECKPOINT)
        model.to(DEVICE)
        _model_cache = model
        logging.info("Model loaded successfully")
        return model
    except Exception as e:
        logging.error(f"Failed to load model: {e}", exc_info=True)
        _model_cache = False  # Mark as failed
        return None


transform = T.Compose([
    T.Resize((IMG_SIZE, IMG_SIZE)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]),
])


@torch.inference_mode()
def predict_disease(image: Image.Image) -> dict:
    """
    Predict disease from leaf image
    
    Args:
        image: PIL Image object
        
    Returns:
        dict with disease, confidence, and all_probs
    """
    try:
        # Validate input
        if not isinstance(image, Image.Image):
            raise ValueError("Input must be PIL Image object")
        
        # Validate image dimensions
        if image.size[0] < 50 or image.size[1] < 50:
            raise ValueError(f"Image too small: {image.size}. Minimum 50x50 required")
        
        image = image.convert("RGB")

        # Attempt to crop the image to the largest green leaf region to focus
        # the prediction on the target leaf when multiple leaves are present.
        def crop_to_leaf(img: Image.Image) -> Image.Image:
            try:
                small = img.resize((IMG_SIZE, IMG_SIZE))
                hsv = np.array(small.convert('HSV')).astype(np.int32)
                h = hsv[:, :, 0]
                s = hsv[:, :, 1]
                green_mask = (h > int(35 / 360 * 255)) & (h < int(85 / 360 * 255)) & (s > 40)
                coords = np.column_stack(np.where(green_mask))
                if coords.size == 0:
                    return img
                y0, x0 = coords.min(axis=0)
                y1, x1 = coords.max(axis=0)
                # map bbox from small back to original image size
                w, h_img = img.size
                scale_x = w / IMG_SIZE
                scale_y = h_img / IMG_SIZE
                left = max(0, int(x0 * scale_x) - 10)
                upper = max(0, int(y0 * scale_y) - 10)
                right = min(w, int(x1 * scale_x) + 10)
                lower = min(h_img, int(y1 * scale_y) + 10)
                # require a minimum area to avoid tiny crops
                if (right - left) * (lower - upper) < 500:
                    return img
                return img.crop((left, upper, right, lower))
            except (ValueError, OSError, TypeError, IndexError) as e:
                logging.debug(f"Leaf cropping failed: {e}")
                return img

        image = crop_to_leaf(image)

        if USE_HEURISTIC:
            # Improved heuristic using HSV color ratios and dark-spot fraction.
            # This produces smoother, image-dependent probabilities without
            # requiring a trained model. It's still an approximation.
            try:
                small = image.resize((IMG_SIZE, IMG_SIZE))
                arr = np.array(small).astype(np.float32) / 255.0
                r_mean = float(arr[:, :, 0].mean())
                g_mean = float(arr[:, :, 1].mean())
                b_mean = float(arr[:, :, 2].mean())

                hsv = np.array(small.convert('HSV')).astype(np.uint8)
                h = hsv[:, :, 0].astype(np.int32)  # 0-255
                s = hsv[:, :, 1].astype(np.int32)
                v = hsv[:, :, 2].astype(np.int32)

                # Heuristic masks (tuned for demo purposes)
                green_mask = (h > int(35 / 360 * 255)) & (h < int(85 / 360 * 255)) & (s > 40)
                brown_mask = (h > int(5 / 360 * 255)) & (h < int(40 / 360 * 255)) & (v < 220) & (s > 30)
                dark_mask = (np.array(small.convert('L')) < 100)

                green_ratio = float(green_mask.mean())
                brown_ratio = float(brown_mask.mean())
                dark_fraction = float(dark_mask.mean())
                avg_brightness = float(v.mean() / 255.0)

                # Compose scores for each class (higher = more likely)
                healthy_score = max(0.0, green_ratio - dark_fraction * 0.8 + (avg_brightness - 0.45) * 0.4)
                leaf_spot_score = max(0.0, dark_fraction * 2.5 + brown_ratio * 0.6)
                early_blight_score = max(0.0, brown_ratio * 1.5 + dark_fraction * 1.2)
                late_blight_score = max(0.0, dark_fraction * 1.8 + (1.0 - green_ratio) * 0.3)
                wilt_score = max(0.0, (r_mean - g_mean) * 2.0 * (1.0 - green_ratio))

                scores = np.array([wilt_score, early_blight_score, healthy_score, late_blight_score, leaf_spot_score], dtype=np.float32)
                
                # Avoid all-zero
                if scores.sum() <= 1e-6:
                    # fallback to simple color heuristic
                    if g_mean > r_mean and g_mean > b_mean:
                        scores = np.array([0.0, 0.0, 1.0, 0.0, 0.0], dtype=np.float32)
                    else:
                        scores = np.array([0.1, 0.4, 0.1, 0.2, 0.2], dtype=np.float32)

                # Softmax-like probabilities
                exp = np.exp(scores)
                probs = exp / exp.sum()

                top_idx = int(np.argmax(probs))
                confidence = float(probs[top_idx])

                all_probs = {name: round(float(p), 4) for name, p in zip(CLASS_NAMES, probs.tolist())}

                return {
                    "disease": CLASS_NAMES[top_idx],
                    "confidence": round(confidence, 4),
                    "all_probs": all_probs,
                }
            except Exception as e:
                logging.error(f"Heuristic prediction failed: {e}")
                # Return safe default
                return {
                    "disease": "Healthy",
                    "confidence": 0.5,
                    "all_probs": {name: 1.0/len(CLASS_NAMES) for name in CLASS_NAMES},
                }

        # Fall back to the trained model if available
        model = get_cached_model()
        if model is None:
            raise RuntimeError("Model not available and USE_HEURISTIC is False")
        
        x = transform(image).unsqueeze(0).to(DEVICE)
        logits = model(x)
        probs = torch.softmax(logits, dim=1).squeeze(0)
        top_idx = int(torch.argmax(probs).item())
        confidence = float(probs[top_idx].item())
        
        return {
            "disease": CLASS_NAMES[top_idx],
            "confidence": round(confidence, 4),
            "all_probs": {CLASS_NAMES[i]: round(p, 4) for i, p in enumerate(probs.tolist())},
        }
        
    except Exception as e:
        logging.error(f"Prediction failed: {e}", exc_info=True)
        # Return safe default instead of crashing
        return {
            "disease": "Healthy",
            "confidence": 0.0,
            "all_probs": {name: 0.0 for name in CLASS_NAMES},
            "error": str(e)
        }
    finally:
        # Clean up memory
        gc.collect()
        if torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except:
                pass
