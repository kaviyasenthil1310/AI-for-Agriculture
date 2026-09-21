# Crop Disease Detection & Advisory

Run the backend server and open the app in your browser.

Requirements
- Python 3.10+
- See `requirements.txt`

Install

```bash
python -m pip install -r requirements.txt
```

Run

```bash
# start with uvicorn (preferred for development)
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
# or
python run.py
```

Open the app

- Visit http://127.0.0.1:8000/ in your browser after starting the backend.
- Do not open `frontend/index.html` directly via `file://`; the page must be served through the backend so API calls and routing work correctly.

Health check

```bash
curl http://127.0.0.1:8000/health
# -> {"status":"ok"}
```

Debugging

- Use DevTools Network/Console to inspect requests and errors.
- If you see "Backend unreachable" the server isn't running or is on a different port.
 - (The app no longer includes a manual selection UI — uploads use the full image.)
