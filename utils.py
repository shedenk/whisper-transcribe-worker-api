import os
import re
from pathlib import Path


def valid_int_env(key: str, default: int) -> int:
    val = os.environ.get(key, str(default))
    if not val or not val.strip():
        return default
    try:
        return int(val)
    except ValueError:
        return default

def storage_dir() -> Path:
    p = Path(os.environ.get("STORAGE_DIR", "/data"))
    p.mkdir(parents=True, exist_ok=True)
    (p / "jobs").mkdir(parents=True, exist_ok=True)
    return p

def safe_job_id(job_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", job_id)[:80]
