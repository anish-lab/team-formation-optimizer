import os


class Config:
    MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 5 * 1024 * 1024))
    MAX_ROWS = int(os.environ.get("MAX_ROWS", 5000))
    MAX_CANDIDATES = int(os.environ.get("MAX_CANDIDATES", 300))
    MAX_TIME_LIMIT = float(os.environ.get("MAX_TIME_LIMIT", 600))
    MAX_TASKS = int(os.environ.get("MAX_TASKS", 50))
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
