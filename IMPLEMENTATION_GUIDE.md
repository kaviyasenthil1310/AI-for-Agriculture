# Implementation Guide - Fixing Server Issues

## Overview
This guide walks you through implementing the fixes to resolve the intermittent server issues in your AI-for-Agriculture application.

---

## Step 1: Update Dependencies ⚠️ (CRITICAL)

### 1.1 Replace requirements.txt
```bash
cd /path/to/AI-for-Agriculture-main
cp requirements.txt requirements.txt.backup
# Copy the fixed requirements_FIXED.txt as requirements.txt
```

### 1.2 Reinstall dependencies
```bash
# Remove old packages
pip uninstall -y torch torchvision numpy pillow

# Install new versions
pip install -r requirements.txt

# Verify installation
python -c "import torch; print(f'PyTorch {torch.__version__}')"
python -c "import torchvision; print(f'TorchVision {torchvision.__version__}')"
```

---

## Step 2: Create Models Directory

The application expects a trained model at `models/leaf_disease_cnn.pth`. 

### Option A: Create placeholder (for testing without trained model)
```bash
mkdir -p models
# Application will use heuristic fallback
```

### Option B: Use trained model (if you have one)
```bash
mkdir -p models
# Copy your trained model to models/leaf_disease_cnn.pth
cp /path/to/your/leaf_disease_cnn.pth models/
```

### Option C: Train model
```bash
python -m backend.train
# (Requires training data in proper directory structure)
```

---

## Step 3: Update Backend Files

### 3.1 Update predict.py
```bash
cp backend/predict.py backend/predict.py.backup
# Use the contents from predict_FIXED.py
# Or apply the following changes manually:
```

**Key changes:**
- Add lazy model loading (get_cached_model function)
- Add memory cleanup (gc.collect())
- Improve error handling for corrupted images
- Add input validation

### 3.2 Update main.py
```bash
cp backend/main.py backend/main.py.backup
# Use the contents from main_FIXED.py
# Or apply the following changes manually:
```

**Key changes:**
- Add ThreadPoolExecutor for CPU-intensive operations
- Add timeouts to uvicorn configuration
- Add request size limits (10MB)
- Add AsyncIO wait_for() for timeout handling
- Add proper logging configuration
- Add lifespan context manager for graceful shutdown

### 3.3 Update frontend (index.html)
```bash
cp frontend/index.html frontend/index.html.backup
# Use the contents from index_FIXED.html
# Or apply the following changes manually:
```

**Key changes:**
- Increase polling interval from 5s to 30s
- Add exponential backoff for failed health checks
- Add abort timeout for fetch requests
- Add XSS protection with escapeHtml()
- Add loading spinner
- Better status messages

---

## Step 4: Test the Application

### 4.1 Start fresh
```bash
# Terminal 1: Start the backend server
cd /path/to/AI-for-Agriculture-main
python run.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### 4.2 Test health endpoint
```bash
# Terminal 2: Check health
curl http://127.0.0.1:8000/health
# Expected response: {"status":"ok","model":"ready"}
```

### 4.3 Test with single image
```bash
# Upload a test image
curl -X POST http://127.0.0.1:8000/predict \
  -F "file=@tests/_green.jpg" \
  -F "crop=Tomato"
```

### 4.4 Load test
```bash
# Install Apache Bench if not present
sudo apt-get install apache2-utils

# Test with concurrent requests (adjust -c and -n as needed)
ab -n 20 -c 5 http://127.0.0.1:8000/health
```

---

## Step 5: Monitor in Production

### 5.1 Enable logging
```python
# Check logs for errors
python run.py 2>&1 | tee server.log
```

### 5.2 Monitor system resources
```bash
# Terminal: Watch memory/CPU usage
watch -n 1 'ps aux | grep python | grep -v grep'

# Or use a more detailed tool
pip install psutil
python -c "import psutil; print(psutil.virtual_memory())"
```

### 5.3 Check for memory leaks
```bash
# Run for an hour, monitor memory growth
# If memory grows constantly without stabilizing, there's still a leak
ps aux | grep python
# Watch the RSS (memory) column
```

---

## Step 6: Deployment Best Practices

### 6.1 Use systemd for auto-restart (Linux)
Create `/etc/systemd/system/agriculture-server.service`:
```ini
[Unit]
Description=AI Agriculture Server
After=network.target

[Service]
Type=simple
User=agriculture
WorkingDirectory=/path/to/AI-for-Agriculture-main
ExecStart=/usr/bin/python3 run.py
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

Start service:
```bash
sudo systemctl enable agriculture-server
sudo systemctl start agriculture-server
sudo systemctl status agriculture-server
```

### 6.2 Use Docker (Recommended)
Create `Dockerfile`:
```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create models directory
RUN mkdir -p models

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run server
CMD ["python", "run.py"]
```

Build and run:
```bash
docker build -t agriculture-server .
docker run -d \
  --name agriculture-server \
  -p 8000:8000 \
  --restart on-failure \
  agriculture-server
```

### 6.3 Use Nginx as reverse proxy
Create `/etc/nginx/sites-available/agriculture`:
```nginx
upstream agriculture {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name _;
    client_max_body_size 10M;

    # Connection timeouts
    proxy_connect_timeout 10s;
    proxy_send_timeout 30s;
    proxy_read_timeout 60s;

    location / {
        proxy_pass http://agriculture;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Health check endpoint (no rate limiting)
    location /health {
        proxy_pass http://agriculture;
        access_log off;
    }
}
```

Enable:
```bash
sudo ln -s /etc/nginx/sites-available/agriculture /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## Step 7: Verify Fixes

### 7.1 Checklist
- [ ] Model loads without blocking (check startup time < 5s)
- [ ] Multiple concurrent predictions work (test with 5+ simultaneous requests)
- [ ] Memory usage is stable (watch for 30+ minutes)
- [ ] Server responds to requests even under load
- [ ] Corrupted images don't crash server
- [ ] Health endpoint is fast (< 100ms)
- [ ] Server gracefully restarts without data loss

### 7.2 Load testing
```bash
# Install
pip install locust

# Create locustfile.py
```

```python
from locust import HttpUser, task, between

class AgriculturalUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def health_check(self):
        self.client.get("/health")

# Run test
# locust -f locustfile.py -u 10 -r 1 -t 5m
```

---

## Common Issues & Solutions

### Issue: "Model checkpoint not found" warning at startup
**Solution:** This is OK if using heuristic mode. To use trained model, place checkpoint in `models/leaf_disease_cnn.pth`

### Issue: "CUDA out of memory" error
**Solution:** Set `DEVICE = "cpu"` in `backend/predict.py` if GPU is overloaded
```python
DEVICE = "cpu"  # Force CPU
```

### Issue: Server crashes with "Too many open files"
**Solution:** Increase file descriptor limit
```bash
# Check current limit
ulimit -n
# Increase to 65536
ulimit -n 65536
```

### Issue: Frontend shows "Backend unreachable" but server is running
**Solution:** 
- Check CORS settings in `main.py`
- Verify firewall allows traffic on port 8000
- Check that server is listening on 0.0.0.0 (not localhost)
```bash
netstat -tlnp | grep 8000
```

### Issue: Intermittent 502/503 errors
**Solution:**
- Check server logs: `journalctl -u agriculture-server -f`
- Monitor memory: `free -h`
- Check CPU: `top -b -n 1 | head -20`
- Reduce `limit_concurrency` in uvicorn config if too high

---

## Performance Tuning

### For CPU-bound prediction (heuristic mode)
```python
# In main.py, increase worker pool
executor = ThreadPoolExecutor(max_workers=4)  # Adjust based on CPU cores
```

### For GPU-accelerated prediction
```python
# Increase timeouts for model inference
timeout=60.0  # Increase from 30s to 60s for GPU warmup
```

### For high traffic (100+ concurrent users)
```python
# In run_server()
uvicorn.run(
    app,
    host="0.0.0.0",
    port=8000,
    workers=4,              # 1 per CPU core
    limit_concurrency=50,   # Increase from 10
    limit_max_requests=500, # Lower from 1000 to restart workers more often
)
```

---

## Monitoring Setup (Optional)

### Install Prometheus client
```bash
pip install prometheus-client
```

### Add to main.py
```python
from prometheus_client import Counter, Histogram
import time

# Metrics
prediction_counter = Counter('predictions_total', 'Total predictions')
prediction_duration = Histogram('prediction_duration_seconds', 'Prediction duration')

@app.post("/predict")
async def predict(...):
    with prediction_duration.time():
        # ... prediction code ...
        prediction_counter.inc()
```

---

## Summary

By implementing these fixes, you should see:
1. ✓ Faster server startup (no blocking model load)
2. ✓ Stable memory usage (no leaks)
3. ✓ Better handling of concurrent requests
4. ✓ Graceful degradation under high load
5. ✓ Better error messages
6. ✓ Automatic recovery from crashes

**Before applying fixes**: Backup your current files!
**After applying fixes**: Test thoroughly before deploying to production!

