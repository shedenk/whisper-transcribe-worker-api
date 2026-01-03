import os
import uuid
from pathlib import Path
from typing import Optional, Literal

from fastapi import FastAPI, UploadFile, File, Body, HTTPException, Request
from fastapi.responses import FileResponse
import httpx

from rq.job import Job
from redis_queue import get_queue, get_redis
from utils import storage_dir, safe_job_id
import worker

app = FastAPI(title="Transcribe to SRT API")

from pydantic import BaseModel

class TranscribeRequest(BaseModel):
    source_type: Literal["url", "upload"]
    url: Optional[str] = None
    language: Optional[str] = None
    task: Literal["transcribe", "translate"] = "transcribe"
    output: Literal["srt", "vtt", "txt"] = "srt"
    diarize: bool = False
    callback_url: Optional[str] = None
    db_id: Optional[str] = None

@app.post("/v1/transcribe")
async def create_job(
    request: Request,
    file: Optional[UploadFile] = File(None)
):
    print(f"[*] Received transcription request")
    content_type = request.headers.get("Content-Type", "")
    
    if "application/json" in content_type:
        try:
            data = await request.json()
            params = TranscribeRequest(**data)
        except Exception as e:
            raise HTTPException(422, detail=f"Invalid JSON: {str(e)}")
    else:
        # Assume multipart/form-data or similar
        try:
            form = await request.form()
            params = TranscribeRequest(
                source_type=form.get("source_type"),
                url=form.get("url"),
                language=form.get("language"),
                task=form.get("task", "transcribe"),
                output=form.get("output", "srt"),
                diarize=form.get("diarize", "false").lower() == "true",
                callback_url=form.get("callback_url"),
                db_id=form.get("db_id")
            )
        except Exception as e:
            raise HTTPException(422, detail=f"Invalid Form Data: {str(e)}")

    job_uuid = safe_job_id(str(uuid.uuid4()))
    base = storage_dir() / "jobs" / job_uuid
    base.mkdir(parents=True, exist_ok=True)

    input_path = base / "input.bin"

    if params.source_type == "url":
        if not params.url:
            raise HTTPException(400, "url wajib diisi untuk source_type=url")
        # download file
        async with httpx.AsyncClient(follow_redirects=True, timeout=600) as client:
            r = await client.get(params.url)
            r.raise_for_status()
            input_path.write_bytes(r.content)

    elif params.source_type == "upload":
        if file is None:
            raise HTTPException(400, "file wajib diupload untuk source_type=upload")
        content = await file.read()
        input_path.write_bytes(content)
    else:
        raise HTTPException(400, "source_type tidak valid")

    payload = {
        "job_id": job_uuid,
        "input_path": str(input_path),
        "language": params.language,
        "task": params.task,
        "output": params.output,
        "diarize": params.diarize,
        "callback_url": params.callback_url,
        "db_id": params.db_id,
    }

    q = get_queue()
    rq_job = q.enqueue(
        worker.process_job,
        payload,
        job_id=job_uuid,
        job_timeout=int(os.getenv("JOB_TIMEOUT", "14400")),
        result_ttl=int(os.getenv("JOB_TTL_SECONDS", "86400"))
    )
    rq_job.meta["db_id"] = params.db_id
    rq_job.save_meta()
    print(f"[+] Job enqueued: {job_uuid}")
    return {
        "job_id": rq_job.id,
        "status_url": f"/v1/jobs/{rq_job.id}",
        "result_url": f"/v1/jobs/{rq_job.id}/result"
    }

@app.get("/v1/jobs/{job_id}")
async def job_status(job_id: str):
    job_id = safe_job_id(job_id)
    redis = get_redis()
    
    job = None
    for i in range(3):
        try:
            job = Job.fetch(job_id, connection=redis)
            if job:
                job.refresh() # Ensure we have the latest meta
                break
        except:
            import asyncio
            if i < 2: await asyncio.sleep(0.5)
    
    if not job:
        raise HTTPException(404, "job tidak ditemukan")

    status = job.get_status()
    pos = None
    if status == "queued":
        try:
            q = get_queue()
            pos = q.get_job_position(job_id) # Returns 0-indexed position
        except: pass

    meta = job.meta or {}
    
    def fmt_time(dt):
        return dt.isoformat() if dt else None

    return {
        "job_id": job.id,
        "status": status,
        "queue_position": pos if pos is not None else (0 if status == "started" else None),
        "progress": meta.get("progress", 0),
        "message": meta.get("message"),
        "created_at": fmt_time(job.created_at),
        "enqueued_at": fmt_time(job.enqueued_at),
        "started_at": fmt_time(job.started_at),
        "ended_at": fmt_time(job.ended_at),
        "minio_url": meta.get("minio_url"),
        "db_id": meta.get("db_id"),
        "error": str(job.exc_info)[:500] if job.is_failed else None,
    }

@app.get("/v1/jobs/{job_id}/result")
async def job_result(job_id: str):
    job_id = safe_job_id(job_id)
    redis = get_redis()

    # Retry to find job in case of slight delay
    job = None
    for i in range(3):
        try:
            job = Job.fetch(job_id, connection=redis)
            if job:
                job.refresh()
                break
        except:
            if i < 2:
                import asyncio
                await asyncio.sleep(0.5)
                continue
    
    if not job:
         raise HTTPException(404, "job tidak ditemukan")

    base = storage_dir() / "jobs" / job_id

    # worker akan tulis output di sini:
    # output.srt / output.vtt / output.txt
    for fname in ["output.srt", "output.vtt", "output.txt"]:
        p = base / fname
        if p.exists():
            media_type = "text/plain"
            return FileResponse(str(p), media_type=media_type, filename=fname)

    raise HTTPException(404, "hasil belum ada / job belum selesai")
