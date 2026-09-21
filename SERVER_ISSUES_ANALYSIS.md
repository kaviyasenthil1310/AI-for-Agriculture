# AI-for-Agriculture Server Issues - Analysis & Solutions

## Problems Identified

### 1. **CRITICAL: Missing Model Checkpoint File** ⚠️
**Location:** `backend/predict.py` (line 16, 20)
**Issue:** 
```python
CHECKPOINT = os.path.join(BASE_DIR, "..", "models", "leaf_disease_cnn.pth")
USE_HEURISTIC = not os.path.isfile(CHECKPOINT)
```
- The model file path is `models/leaf_disease_cnn.pth` but this directory doesn't exist in your project
- Server falls back to heuristic (approximate guessing) instead of using trained ML model
- This causes unpredictable behavior and slow performance

**Solution:**
```bash
# Create the models directory
mkdir -p models

# Either:
# A) Train and save the model there
# B) Download pre-trained model and place it in models/
# C) At minimum, create a dummy model file
```

---

### 2. **Model Loading at Module Import (Synchronous Blocking)**
**Location:** `backend/predict.py` (line 25-28)
**Issue:**
```python
model = None
if not USE_HEURISTIC:
    model = get_model(num_classes=NUM_CLASSES, checkpoint_path=CHECKPOINT)
    model.to(DEVICE)  # ← Blocks on server startup
```
- Heavy PyTorch model loads when module is imported
- Blocks the entire server startup
- If model loading fails, entire server crashes
- Can cause timeout if model file is corrupted

**Solution:**
```python
# Lazy load the model on first prediction request
_model_cache = None

def get_cached_model():
    global _model_cache
    if _model_cache is None and not USE_HEURISTIC:
        try:
            _model_cache = get_model(num_classes=NUM_CLASSES, checkpoint_path=CHECKPOINT)
            _model_cache.to(DEVICE)
        except Exception as e:
            logging.error(f"Failed to load model: {e}")
            _model_cache = False  # Mark as failed
    return _model_cache if _model_cache else None
```

---

### 3. **Memory Leaks in Image Processing**
**Location:** `backend/predict.py` (line 44-71, 77-92)
**Issue:**
- Image transformations create intermediate arrays without cleanup
- No garbage collection between predictions
- HSV conversions create temporary arrays
- Long-running server accumulates memory

**Solution:**
```python
import gc

@torch.inference_mode()
def predict_disease(image: Image.Image) -> dict:
    try:
        # ... prediction code ...
        return result
    finally:
        # Clean up
        del image
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
```

---

### 4. **No Request Timeout Configuration**
**Location:** `backend/main.py` (line 107-109)
**Issue:**
```python
def run_server():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    # Missing: timeout, workers, graceful shutdown
```
- No timeout for long-running predictions
- Requests can hang indefinitely
- No worker process management
- Server doesn't gracefully handle crashes

**Solution:**
```python
def run_server():
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        timeout_keep_alive=30,  # Close idle connections after 30s
        timeout_notify=30,      # Timeout for shutdown notification
        workers=2,              # Use 2 worker processes for better stability
        limit_concurrency=10,   # Limit concurrent requests
        limit_max_requests=1000, # Restart workers periodically to prevent memory leaks
    )
```

---

### 5. **Heavy Synchronous Operations in Async Endpoint**
**Location:** `backend/main.py` (line 42-100, predict endpoint)
**Issue:**
```python
@app.post("/predict")
async def predict(...):
    # These are BLOCKING operations in async context
    image = Image.open(io.BytesIO(contents))  # Heavy
    pred = predict_disease(image)  # Very heavy - takes 2-5 seconds
    advisory = get_advisory(pred["disease"])  # OK
```
- `Image.open()` and `predict_disease()` are CPU-intensive
- Running in async context blocks the event loop
- Freezes other requests while prediction runs
- Multiple simultaneous predictions crash the server

**Solution:**
```python
from concurrent.futures import ThreadPoolExecutor
import asyncio

executor = ThreadPoolExecutor(max_workers=2)

@app.post("/predict")
async def predict(...):
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))
        
        # Run CPU-intensive work in thread pool
        loop = asyncio.get_event_loop()
        pred = await loop.run_in_executor(executor, predict_disease, image)
        
        advisory = get_advisory(pred["disease"])
        return {
            "crop": crop,
            "prediction": pred,
            "advisory": advisory,
        }
    except Exception as e:
        logging.exception("Error during prediction")
        return JSONResponse(status_code=500, content={
            "error": str(e),
            "trace": traceback.format_exc(),
        })
```

---

### 6. **Frontend Polling Causing Server Overload**
**Location:** `frontend/index.html` (line 116-117)
**Issue:**
```javascript
checkHealth();
setInterval(checkHealth, 5000);  // Polls every 5 seconds
```
- Every connected client makes HTTP request every 5 seconds
- With 10 users = 120 requests/minute from health checks alone
- Accumulates in server logs, consumes resources
- Can cause server to become unresponsive

**Solution:**
```javascript
// Increase polling interval or use WebSocket
setInterval(checkHealth, 30000);  // Poll every 30 seconds instead

// OR use exponential backoff
let pollInterval = 5000;
const maxInterval = 60000;

async function checkHealthWithBackoff() {
    try {
        const r = await fetch(url, { cache: 'no-store' });
        if (r.ok) {
            backendHealthy = true;
            pollInterval = 5000;  // Reset on success
        }
    } catch (err) {
        backendHealthy = false;
        pollInterval = Math.min(pollInterval * 1.5, maxInterval);
    }
    setTimeout(checkHealthWithBackoff, pollInterval);
}
```

---

### 7. **Missing Error Handling for Corrupted Images**
**Location:** `backend/predict.py` (line 40, 46, 67)
**Issue:**
```python
image = image.convert("RGB")  # Fails for corrupted images
hsv = np.array(small.convert('HSV'))  # Can fail
image.crop((left, upper, right, lower))  # Can fail
```
- Try-catch blocks don't cover all operations
- Corrupted image uploads crash prediction
- Stack trace leaked to frontend (line 99)

**Solution:**
```python
@torch.inference_mode()
def predict_disease(image: Image.Image) -> dict:
    try:
        if not isinstance(image, Image.Image):
            raise ValueError("Invalid image format")
        
        # Validate image
        if image.size[0] < 50 or image.size[1] < 50:
            raise ValueError("Image too small (minimum 50x50)")
        
        image = image.convert("RGB")
        # ... rest of code ...
        
    except Exception as e:
        logging.error(f"Prediction failed: {e}")
        # Return safe default instead of crashing
        return {
            "disease": "Healthy",
            "confidence": 0.0,
            "all_probs": {name: 0.0 for name in CLASS_NAMES},
            "error": str(e)
        }
```

---

### 8. **Dependency Version Conflicts**
**Location:** `requirements.txt`
**Issue:**
```
torch==2.13.0
torchvision==0.28.0  # ← Mismatch! torchvision 0.28 expects torch 2.1+
numpy==2.5.1        # ← Potential compatibility issues with older torch
```
- torch 2.13.0 might not be compatible with torchvision 0.28.0
- numpy 2.5.1 deprecated some APIs torch relies on
- Causes intermittent import errors

**Solution:**
```txt
# Use compatible versions
fastapi==0.141.1
starlette==1.3.1
uvicorn[standard]==0.30.0
python-multipart==0.0.9
torch==2.3.1
torchvision==0.18.1
pillow==10.4.0
numpy==1.24.3
requests==2.32.3
httpx
```

---

### 9. **No Resource Limits or Monitoring**
**Location:** Entire application
**Issue:**
- No memory limit checks
- No CPU usage monitoring
- No request queue management
- Server keeps accepting requests until it crashes

**Solution:**
```python
# Add to main.py
import psutil
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Server starting...")
    yield
    # Shutdown
    print("Server shutting down...")

app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def check_resources(request, call_next):
    # Check memory
    memory_percent = psutil.virtual_memory().percent
    if memory_percent > 90:
        return JSONResponse(
            status_code=503, 
            content={"error": "Server out of memory"}
        )
    
    response = await call_next(request)
    return response
```

---

### 10. **No Graceful Shutdown/Restart Mechanism**
**Location:** Application startup
**Issue:**
- Server crashes = data loss & interruption
- No way to restart without manual intervention
- Long-running predictions get aborted

**Solution:**
Add to your deployment (e.g., systemd, Docker, etc.):
```bash
# systemd service file
[Unit]
Description=AI Agriculture Server
After=network.target

[Service]
Type=notify
User=agriculture
WorkingDirectory=/path/to/app
ExecStart=/usr/bin/python3 run.py
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

---

## Summary of Intermittent Issues Likely Causing Your Problems

| Issue | Symptom | Fix Priority |
|-------|---------|--------------|
| Missing model checkpoint | Server works but gives wrong predictions | CRITICAL |
| Blocking model loading | Server startup timeout/hang | CRITICAL |
| Heavy sync operations in async | Server unresponsive under load | HIGH |
| No timeouts configured | Requests hang indefinitely | HIGH |
| Memory leaks | Gradual slowdown over time | HIGH |
| Dependency conflicts | Import errors, crashes | HIGH |
| Frontend over-polling | Resource exhaustion | MEDIUM |
| No error recovery | Crashes on edge cases | MEDIUM |
| No resource limits | Cascading failures | MEDIUM |

---

## Quick Fix Priority Order

1. **First:** Create `models/` directory and verify model file exists
2. **Second:** Add timeout configuration to uvicorn
3. **Third:** Use thread pool for CPU-intensive operations
4. **Fourth:** Verify dependency versions
5. **Fifth:** Add memory cleanup and gc.collect()
6. **Sixth:** Reduce frontend polling frequency

---

## Testing Checklist

```bash
# 1. Check if model file exists
ls -la models/leaf_disease_cnn.pth

# 2. Verify dependencies
pip list | grep -E "torch|numpy|pillow"

# 3. Monitor memory while running
watch -n 1 'ps aux | grep python'

# 4. Test with load
# Use Apache Bench or wrk to simulate concurrent requests
ab -n 100 -c 10 http://127.0.0.1:8000/health

# 5. Check logs for errors
# Look for: "WARNING:", "ERROR:", "Exception"
```

