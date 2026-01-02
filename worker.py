import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from rq import Worker, Queue, get_current_job
from faster_whisper import WhisperModel
import srt
from redis_queue import get_redis
from utils import storage_dir

MODEL_SIZE = os.getenv("MODEL_SIZE", "small")
DEVICE = os.getenv("DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "1"))

# cache model in memory (per worker process)
_model: Optional[WhisperModel] = None

def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
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
    subprocess.check_call(cmd, timeout=600)

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

def process_job(payload: Dict[str, Any]) -> Dict[str, Any]:
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
    print(f"    - Converting to WAV...")
    _to_wav(input_path, wav_path)

    job.meta["progress"] = 10
    job.meta["message"] = "loading model"
    job.save_meta()

    print(f"    - Loading model ({MODEL_SIZE})...")
    model = _get_model()

    job.meta["progress"] = 15
    job.meta["message"] = "transcribing"
    job.save_meta()

    print(f"    - Transcribing...")
    segments, info = model.transcribe(
        wav_path,
        language=language,
        task=task,
        vad_filter=True,
        beam_size=1,
    )
    print(f"      [Detected language: {info.language}]")
    segments = list(segments)

    job.meta["progress"] = 90
    job.meta["message"] = "writing output"
    job.save_meta()

    print(f"    - Writing {output} output...")
    if output == "srt":
        _write_srt(segments, base / "output.srt")
    elif output == "vtt":
        _write_vtt(segments, base / "output.vtt")
    else:
        _write_txt(segments, base / "output.txt")

    job.meta["progress"] = 100
    job.meta["message"] = "done"
    job.save_meta()
    print(f"[+] Job {job_id} completed successfully.")

    return {
        "job_id": job_id,
        "language": info.language,
        "duration": info.duration,
        "output": output
    }

if __name__ == "__main__":
    redis_conn = get_redis()
    q = Queue("transcribe", connection=redis_conn)
    w = Worker([q], connection=redis_conn)
    w.work()
