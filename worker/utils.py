import os
from pathlib import Path

def storage_dir() -> Path:
    p = Path(os.environ.get("STORAGE_DIR", "/data"))
    p.mkdir(parents=True, exist_ok=True)
    (p / "jobs").mkdir(parents=True, exist_ok=True)
    return p
