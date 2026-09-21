import io
import os
import sys
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from PIL import Image

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend.advisory import get_advisory
from backend.predict import predict_disease

# Map crops to relevant disease classes. Classes not in the allowed list
# will be masked out for crop-specific prediction.
CROP_CLASS_MAP = {
    "Tomato": ["Healthy", "Early Blight", "Late Blight", "Leaf Spot", "Bacterial Wilt"],
    "Potato": ["Healthy", "Early Blight", "Late Blight", "Leaf Spot"],
    "Paddy": ["Healthy", "Leaf Spot", "Bacterial Wilt"],
    "Rice": ["Healthy", "Leaf Spot", "Bacterial Wilt"],
    "Cotton": ["Healthy", "Leaf Spot", "Bacterial Wilt"],
}


def normalize_crop_name(crop: str) -> str:
    """Accept legacy and updated crop names for compatibility."""
    if crop is None:
        return "Tomato"
    crop = str(crop).strip()
    if crop.lower() == "paddy":
        return "Paddy"
    if crop.lower() == "rice":
        return "Rice"
    return crop

# Thread pool for CPU-intensive operations
# Using 2 workers to prevent overload
executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="predict_")

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown"""
    logger.info("Server starting up...")
    yield
    logger.info("Server shutting down...")
    executor.shutdown(wait=True)

app = FastAPI(
    title="Crop Disease Detection & Advisory",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the frontend HTML"""
    try:
        path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
        return FileResponse(path, media_type="text/html")
    except Exception as e:
        logger.error(f"Failed to serve index.html: {e}")
        return HTMLResponse(
            "<h1>Error</h1><p>Could not load frontend</p>",
            status_code=500
        )


@app.post("/predict")
@app.post("/api/predict")
async def predict(
    file: UploadFile = File(...),  # noqa: B008
    crop: str = Form(default="Tomato"),
    box_left: int = Form(None),
    box_top: int = Form(None),
    box_width: int = Form(None),
    box_height: int = Form(None),
):
    """
    Predict disease from uploaded leaf image
    
    The heavy image processing is offloaded to a thread pool
    to prevent blocking the async event loop.
    """
    try:
        crop = normalize_crop_name(crop)
        # Validate crop type
        if crop not in CROP_CLASS_MAP:
            return JSONResponse(
                status_code=400,
                content={"error": f"Unknown crop type: {crop}"}
            )
        
        # Read file with size limit (10MB)
        MAX_FILE_SIZE = 10 * 1024 * 1024
        contents = await file.read(MAX_FILE_SIZE + 1)
        
        if len(contents) > MAX_FILE_SIZE:
            return JSONResponse(
                status_code=400,
                content={"error": "File too large (max 10MB)"}
            )
        
        if len(contents) == 0:
            return JSONResponse(
                status_code=400,
                content={"error": "Empty file"}
            )
        
        # Process image in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def process_image():
            """Heavy image processing - runs in thread pool"""
            try:
                image = Image.open(io.BytesIO(contents))
                
                # Validate image format
                if image.format not in ['JPEG', 'PNG', 'BMP', 'GIF']:
                    raise ValueError(f"Unsupported image format: {image.format}")
                
                # If frontend provided a selection box, crop the image accordingly.
                if all(v is not None for v in [box_left, box_top, box_width, box_height]):
                    try:
                        left = int(box_left)
                        top = int(box_top)
                        right = left + int(box_width)
                        bottom = top + int(box_height)
                        
                        # Validate crop coordinates
                        if left < 0 or top < 0 or right > image.width or bottom > image.height:
                            logger.warning(f"Invalid crop coordinates: {(left, top, right, bottom)}")
                        else:
                            image = image.crop((left, top, right, bottom))
                    except (ValueError, TypeError, OSError) as e:
                        logger.warning(f"Cropping failed: {e}. Using full image.")
                
                return image
            except Exception as e:
                logger.error(f"Image processing failed: {e}")
                raise
        
        # Load image in thread pool
        try:
            image = await asyncio.wait_for(
                loop.run_in_executor(executor, process_image),
                timeout=10.0  # 10 second timeout for image loading
            )
        except asyncio.TimeoutError:
            logger.error("Image processing timeout")
            return JSONResponse(
                status_code=408,
                content={"error": "Image processing timed out"}
            )
        
        # Run prediction in thread pool
        try:
            pred = await asyncio.wait_for(
                loop.run_in_executor(executor, predict_disease, image),
                timeout=30.0  # 30 second timeout for prediction
            )
        except asyncio.TimeoutError:
            logger.error("Prediction timeout")
            return JSONResponse(
                status_code=408,
                content={"error": "Prediction timed out"}
            )
        
        # Apply crop-specific class masking if applicable
        allowed = CROP_CLASS_MAP.get(crop, None)
        if allowed and "all_probs" in pred:
            probs = pred["all_probs"].copy()
            # zero out disallowed classes
            for cls in list(probs.keys()):
                if cls not in allowed:
                    probs[cls] = 0.0
            total = sum(probs.values())
            if total > 0:
                # normalize and pick top
                probs = {k: v / total for k, v in probs.items()}
                top = max(probs.items(), key=lambda kv: kv[1])
                pred["disease"] = top[0]
                pred["confidence"] = round(float(top[1]), 4)
                pred["all_probs"] = {k: round(float(v), 4) for k, v in probs.items()}

        advisory = get_advisory(pred["disease"])
        return {
            "crop": crop,
            "prediction": pred,
            "advisory": advisory,
        }
        
    except Exception as e:
        logger.exception("Error during prediction")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                # Don't include full traceback in production
                "message": "An error occurred during prediction. Please try again."
            }
        )


@app.get("/health")
@app.get("/api/health")
async def health():
    """Health check endpoint for monitoring"""
    return {
        "status": "ok",
        "model": "ready"
    }


def run_server():
    """Start the server with proper configuration"""
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        # Timeout settings
        timeout_keep_alive=30,            # Close idle connections after 30s
        timeout_graceful_shutdown=30,    # Graceful shutdown timeout
        # Worker settings
        workers=1,                       # Single worker (gunicorn-style) since we use thread pool
        # Concurrency limits
        limit_concurrency=10,             # Limit concurrent requests
        limit_max_requests=1000,         # Restart worker periodically to prevent memory leaks
        # Other settings
        access_log=True,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()
