import os
import re
from pathlib import Path

def storage_dir() -> Path:
    p = Path(os.environ.get("STORAGE_DIR", "/data"))
    p.mkdir(parents=True, exist_ok=True)
    (p / "jobs").mkdir(parents=True, exist_ok=True)
    return p

def safe_job_id(job_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", job_id)[:80]
