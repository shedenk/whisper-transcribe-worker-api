import os
import uuid
from pathlib import Path
from typing import Optional, Literal

from fastapi import FastAPI, UploadFile, File, Body, HTTPException
from fastapi.responses import FileResponse
import httpx

from rq.job import Job
from queue import get_queue, get_redis
from utils import storage_dir, safe_job_id

app = FastAPI(title="Transcribe to SRT API")

# ---- request schemas (simple) ----
# mode: url or upload
@app.post("/v1/transcribe")
async def create_job(
    source_type: Literal["url", "upload"] = Body(...),
    url: Optional[str] = Body(None),
    language: Optional[str] = Body(None),          # e.g. "id" / "en"
    task: Literal["transcribe", "translate"] = Body("transcribe"),
    output: Literal["srt", "vtt", "txt"] = Body("srt"),
    diarize: bool = Body(False),                   # placeholder; belum diaktifkan di worker
    file: UploadFile | None = File(None),
):
    job_uuid = safe_job_id(str(uuid.uuid4()))
    base = storage_dir() / "jobs" / job_uuid
    base.mkdir(parents=True, exist_ok=True)

    input_path = base / "input.bin"

    if source_type == "url":
        if not url:
            raise HTTPException(400, "url wajib diisi untuk source_type=url")
        # download file
        async with httpx.AsyncClient(follow_redirects=True, timeout=600) as client:
            r = await client.get(url)
            r.raise_for_status()
            input_path.write_bytes(r.content)

    elif source_type == "upload":
        if file is None:
            raise HTTPException(400, "file wajib diupload untuk source_type=upload")
        content = await file.read()
        input_path.write_bytes(content)
    else:
        raise HTTPException(400, "source_type tidak valid")

    payload = {
        "job_id": job_uuid,
        "input_path": str(input_path),
        "language": language,
        "task": task,
        "output": output,
        "diarize": diarize,
    }

    q = get_queue()
    rq_job = q.enqueue("worker.process_job", payload, job_id=job_uuid, result_ttl=int(os.getenv("JOB_TTL_SECONDS","86400")))
    return {
        "job_id": rq_job.id,
        "status_url": f"/v1/jobs/{rq_job.id}",
        "result_url": f"/v1/jobs/{rq_job.id}/result"
    }

@app.get("/v1/jobs/{job_id}")
def job_status(job_id: str):
    job_id = safe_job_id(job_id)
    redis = get_redis()
    try:
        job = Job.fetch(job_id, connection=redis)
    except Exception:
        raise HTTPException(404, "job tidak ditemukan")

    meta = job.meta or {}
    return {
        "job_id": job.id,
        "status": job.get_status(),
        "created_at": str(job.created_at),
        "enqueued_at": str(job.enqueued_at),
        "started_at": str(job.started_at),
        "ended_at": str(job.ended_at),
        "progress": meta.get("progress", 0),
        "message": meta.get("message"),
        "error": str(job.exc_info)[:500] if job.is_failed else None,
    }

@app.get("/v1/jobs/{job_id}/result")
def job_result(job_id: str):
    job_id = safe_job_id(job_id)
    base = storage_dir() / "jobs" / job_id

    # worker akan tulis output di sini:
    # output.srt / output.vtt / output.txt
    for fname in ["output.srt", "output.vtt", "output.txt"]:
        p = base / fname
        if p.exists():
            media_type = "text/plain"
            return FileResponse(str(p), media_type=media_type, filename=fname)

    raise HTTPException(404, "hasil belum ada / job belum selesai")
