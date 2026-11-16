"""Entry point: uv run main.py  →  http://127.0.0.1:8000"""
import uvicorn

if __name__ == "__main__":
    # 127.0.0.1 keeps the app local to your machine (there is no login).
    uvicorn.run("app.api:app", host="127.0.0.1", port=8000, reload=True)
