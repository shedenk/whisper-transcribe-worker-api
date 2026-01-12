import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from rq import Worker, Queue, get_current_job
from faster_whisper import WhisperModel
import srt
from redis_queue import get_redis
from utils import storage_dir, valid_int_env, valid_str_env, sanitize_minio_endpoint
from minio import Minio
from minio.error import S3Error
import requests


MODEL_SIZE = valid_str_env("MODEL_SIZE", "small")
DEVICE = valid_str_env("WHISPER_DEVICE", "auto")
COMPUTE_TYPE = valid_str_env("WHISPER_COMPUTE_TYPE", "default")
# Optimize for CPU
if DEVICE == "cpu" and COMPUTE_TYPE == "default":
    COMPUTE_TYPE = "int8"

MAX_CONCURRENCY = valid_int_env("MAX_CONCURRENCY", 1)
CPU_THREADS = valid_int_env("CPU_THREADS", 0)
FFMPEG_TIMEOUT = valid_int_env("FFMPEG_TIMEOUT", 300)
WEBHOOK_ON_ERROR = os.getenv("WEBHOOK_ON_ERROR", "true").lower() == "true"

# MinIO Config
MINIO_ENDPOINT = sanitize_minio_endpoint(os.getenv("MINIO_ENDPOINT", ""))
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
MINIO_BUCKET = valid_str_env("MINIO_BUCKET", "transcribe")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_PUBLIC_BASE_URL = os.getenv("MINIO_PUBLIC_BASE_URL")

# cache model in memory (per worker process)
_model: Optional[WhisperModel] = None

def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        # If CPU threads not specified, we calculate it based on concurrency
        # to avoid oversubscribing a 6-core machine (typical for user)
        threads = CPU_THREADS
        if threads == 0:
            # Assume 6 cores as baseline if not specified
            threads = max(1, 6 // MAX_CONCURRENCY)
            
        print(f"[*] Initializing WhisperModel ({MODEL_SIZE}) with {threads} threads")
        _model = WhisperModel(
            MODEL_SIZE, 
            device=DEVICE, 
            compute_type=COMPUTE_TYPE,
            cpu_threads=threads
        )
    return _model

def _to_wav(input_path: str, wav_path: str):
    # convert anything to 16k mono wav for consistent speed
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", "16000",
        "-vn",
        wav_path
    ]
    subprocess.check_call(cmd, timeout=FFMPEG_TIMEOUT)

def _write_srt(segments, out_path: Path):
    subs = []
    for i, seg in enumerate(segments, start=1):
        subs.append(
            srt.Subtitle(
                index=i,
                start=srt.timedelta(seconds=float(seg.start)),
                end=srt.timedelta(seconds=float(seg.end)),
                content=(seg.text or "").strip()
            )
        )
    out_path.write_text(srt.compose(subs), encoding="utf-8")

def _write_txt(segments, out_path: Path):
    text = "\n".join([(seg.text or "").strip() for seg in segments]).strip() + "\n"
    out_path.write_text(text, encoding="utf-8")

def _write_vtt(segments, out_path: Path):
    # simple VTT from srt lib: reuse srt compose then replace commas to dots + header
    import re
    tmp = srt.compose([
        srt.Subtitle(
            index=i+1,
            start=srt.timedelta(seconds=float(seg.start)),
            end=srt.timedelta(seconds=float(seg.end)),
            content=(seg.text or "").strip()
        ) for i, seg in enumerate(segments)
    ])
    vtt = "WEBVTT\n\n" + re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", tmp)
    out_path.write_text(vtt, encoding="utf-8")

def _upload_to_minio(file_path: Path, object_name: str) -> Optional[str]:
    if not all([MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY]):
        print("[!] MinIO configuration incomplete, skipping upload.")
        return None
    
    try:
        client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE
        )
        
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)
            
        client.fput_object(MINIO_BUCKET, object_name, str(file_path))
        
        # Construct URL
        if MINIO_PUBLIC_BASE_URL:
            # Ensure no trailing slash in base url and join with object name
            base = MINIO_PUBLIC_BASE_URL.rstrip("/")
            return f"{base}/{object_name}"
            
        protocol = "https" if MINIO_SECURE else "http"
        return f"{protocol}://{MINIO_ENDPOINT}/{MINIO_BUCKET}/{object_name}"
    except Exception as e:
        print(f"[!] MinIO upload failed: {e}")
        return None

def _send_webhook(url: str, data: Dict[str, Any]):
    """Helper untuk mengirim webhook dengan aman"""
    print(f"    -> Sending webhook to: {url}")
    print(f"    -> Webhook payload: {data}")
    try:
        resp = requests.post(url, json=data, timeout=10)
        print(f"    -> Webhook status: {resp.status_code}")
    except Exception as e:
        print(f"    [!] Webhook failed: {e}")

def process_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Wrapper untuk menangani error dan mengirim webhook kegagalan"""
    try:
        return _execute_job_logic(payload)
    except Exception as e:
        job_id = payload.get("job_id", "unknown")
        callback_url = payload.get("callback_url")
        print(f"[{job_id}] CRITICAL ERROR: {str(e)}")
        
        if WEBHOOK_ON_ERROR and callback_url:
            error_payload = {
                "job_id": job_id,
                "status": "failed",
                "error": str(e),
                "db_id": payload.get("db_id")
            }
            _send_webhook(callback_url, error_payload)
        raise e  # Re-raise agar RQ mencatat job sebagai failed

def _execute_job_logic(payload: Dict[str, Any]) -> Dict[str, Any]:
    job = get_current_job()
    job.meta["progress"] = 1
    job.meta["message"] = "preparing"
    job.save_meta()

    job_id = payload["job_id"]
    print(f"[#] Starting job: {job_id}")
    input_path = payload["input_path"]
    language = payload.get("language")  # "id" etc.
    task = payload.get("task", "transcribe")
    output = payload.get("output", "srt")

    base = storage_dir() / "jobs" / job_id
    base.mkdir(parents=True, exist_ok=True)

    wav_path = str(base / "audio.wav")
    print(f"[{job_id}] Converting to WAV...")
    _to_wav(input_path, wav_path)

    job.meta["progress"] = 10
    job.meta["message"] = "loading model"
    job.save_meta()

    print(f"[{job_id}] Loading model ({MODEL_SIZE})...")
    model = _get_model()

    job.meta["progress"] = 15
    job.meta["message"] = "transcribing"
    job.save_meta()

    print(f"[{job_id}] Transcribing...")
    segments_gen, info = model.transcribe(
        wav_path,
        language=language,
        task=task,
        vad_filter=True,
        beam_size=1,
    )
    print(f"      [Detected language: {info.language}]")
    print(f"      [Audio duration: {info.duration:.2f}s]")

    segments = []
    last_log_time = 0
    for segment in segments_gen:
        segments.append(segment)
        # Log progress every 5 seconds or every 50 segments
        current_pos = segment.end
        if current_pos - last_log_time > 10: # Log every 10 seconds of audio processed
            percent = (current_pos / info.duration) * 100 if info.duration > 0 else 0
            print(f"[{job_id}] Progress: {current_pos:.1f}s / {info.duration:.1f}s ({percent:.1f}%)")
            last_log_time = current_pos
            
            # Update job meta for API progress tracking
            job.meta["progress"] = max(1, min(99, 15 + int(percent * 0.75)))
            job.save_meta()

    print(f"[{job_id}] Transcription finished. Total segments: {len(segments)}")

    job.meta["progress"] = 90
    job.meta["message"] = "writing output"
    job.save_meta()

    print(f"[{job_id}] Writing {output} output...")
    out_file = None
    if output == "srt":
        out_file = base / "output.srt"
        _write_srt(segments, out_file)
    elif output == "vtt":
        out_file = base / "output.vtt"
        _write_vtt(segments, out_file)
    else:
        out_file = base / "output.txt"
        _write_txt(segments, out_file)

    # Auto Upload to MinIO
    minio_url = None
    if out_file and out_file.exists():
        job.meta["message"] = "uploading to minio"
        job.save_meta()
        print(f"[{job_id}] Uploading to MinIO...")
        object_name = f"{job_id}/{out_file.name}"
        minio_url = _upload_to_minio(out_file, object_name)
        if minio_url:
            job.meta["minio_url"] = minio_url
            print(f"[{job_id}] Uploaded: {minio_url}")

    job.meta["progress"] = 100
    job.meta["message"] = "done"
    job.save_meta()
    print(f"[+] Job {job_id} completed successfully.")

    result = {
        "job_id": job_id,
        "status": "finished",
        "language": info.language,
        "duration": info.duration,
        "output": output,
        "minio_url": minio_url,
        "db_id": payload.get("db_id")
    }

    # Webhook Callback
    callback_url = payload.get("callback_url")
    if callback_url:
        _send_webhook(callback_url, result)

    return result

if __name__ == "__main__":
    import multiprocessing
    import time

    print(f"[*] Worker manager starting (MAX_CONCURRENCY: {MAX_CONCURRENCY})...")
    
    def run_worker(worker_id):
        # Increased heartbeat_ttl to 10 minutes (600s) to handle long transcription gaps
        # Increased job_monitoring_interval to 60s
        try:
            redis_conn = get_redis()
            q = Queue("transcribe", connection=redis_conn)
            
            # Using a custom name to identify which slot the worker occupies
            worker_name = f"worker-{os.uname().nodename}-{worker_id}"
            
            w = Worker(
                [q], 
                connection=redis_conn, 
                name=worker_name,
                job_monitoring_interval=60,
                worker_ttl=3600
            )
            # Ensure we give the worker enough time to heartbeat even under load
            print(f"    [+] Worker {worker_id} started, listening on: {q.name}")
            w.work(logging_level="INFO")
        except Exception as e:
            print(f"    [!] Worker {worker_id} failed: {e}")

    processes = {}

    def start_process(i):
        p = multiprocessing.Process(target=run_worker, args=(i,), name=f"WorkerProcess-{i}")
        p.start()
        processes[i] = p
        return p

    for i in range(MAX_CONCURRENCY):
        start_process(i)
    
    # Manager loop: check for dead processes and restart them
    try:
        while True:
            for i, p in list(processes.items()):
                if not p.is_alive():
                    print(f"[!] Worker process {i} died. Restarting...")
                    p.close()
                    start_process(i)
            time.sleep(10)
    except KeyboardInterrupt:
        print("[*] Manager shutting down...")
        for p in processes.values():
            p.terminate()
