# Whisper Transcribe Worker API

API berbasis FastAPI dan Redis Queue (RQ) untuk melakukan transkripsi audio/video menggunakan model [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper). Sistem ini dirancang untuk menangani antrian pekerjaan (jobs) secara asinkron, stabil, dan dapat diskalakan.

## Fitur Utama

- **Faster-Whisper**: Implementasi Whisper yang jauh lebih cepat dan hemat memori dibanding versi original OpenAI.
- **Asynchronous Processing**: Menggunakan Redis Queue untuk manajemen antrian job.
- **Robust Error Handling**: Dilengkapi mekanisme timeout untuk FFmpeg dan proses transkripsi agar worker tidak _stuck_.
- **Auto-Cleanup**: Container _sidecar_ khusus yang otomatis membersihkan file temporary dari job yang crash/tertinggal.
- **Webhook Notifications**: Mengirim notifikasi ke URL callback saat job selesai atau gagal.
- **MinIO Integration**: Upload otomatis hasil transkripsi ke S3-compatible storage.
- **Monitoring**: Endpoint statistik real-time untuk memantau antrian.

## Persyaratan

- Docker & Docker Compose
- NVIDIA Driver & NVIDIA Container Toolkit (Wajib jika ingin menggunakan akselerasi GPU)

## Instalasi & Konfigurasi

1.  **Clone Repository**

    ```bash
    git clone <repository_url>
    cd whisper-transcribe-worker-api
    ```

2.  **Konfigurasi Environment**
    Buat file `.env` (bisa dicopy dari contoh jika ada) dan sesuaikan variabel berikut:

    ```dotenv
    # Konfigurasi Worker
    MODEL_SIZE=small              # tiny, base, small, medium, large-v2
    MAX_CONCURRENCY=2             # Jumlah job paralel per container
    WHISPER_DEVICE=auto           # 'cuda' untuk GPU, 'cpu' untuk CPU
    WHISPER_COMPUTE_TYPE=default  # 'float16' (GPU) atau 'int8' (CPU)

    # Safety & Timeout (Mencegah Stuck)
    JOB_TIMEOUT=1800              # Batas waktu total job (detik), default 30 menit
    FFMPEG_TIMEOUT=300            # Batas waktu konversi audio (detik), default 5 menit
    WEBHOOK_ON_ERROR=true         # Kirim webhook jika job gagal

    # Storage (MinIO / S3)
    MINIO_ENDPOINT=minio:9000
    MINIO_ACCESS_KEY=your_access_key
    MINIO_SECRET_KEY=your_secret_key
    MINIO_BUCKET=transcribe
    ```

3.  **Jalankan Aplikasi**
    ```bash
    docker-compose up -d --build
    ```
    Perintah ini akan menjalankan 4 service: `redis`, `transcribe-api`, `transcribe-worker`, dan `cleanup`.

## Penggunaan API

### 1. Submit Job Transkripsi

**POST** `/v1/transcribe`

Mendukung input berupa URL file audio atau Upload file langsung.

**Contoh Body (JSON):**

```json
{
  "source_type": "url",
  "url": "https://example.com/audio_podcast.mp3",
  "language": "id",
  "task": "transcribe",
  "output": "srt",
  "callback_url": "https://api.domainkamu.com/webhook/result"
}
```

### 2. Cek Status Job

**POST** `/v1/jobs/{job_id}`

Mengembalikan status job (`queued`, `started`, `finished`, `failed`) dan persentase progress.

### 3. Download Hasil

**GET** `/v1/jobs/{job_id}/result`

Mengunduh file output (`.srt`, `.vtt`, atau `.txt`) jika job sudah selesai.

### 4. Monitoring Statistik (Baru)

**GET** `/v1/stats`

Melihat kesehatan sistem antrian.

```json
{
  "queued": 5,
  "started": 2,
  "failed": 0,
  "finished": 120,
  "workers": 2
}
```

## Mekanisme Maintenance (Auto-Cleanup)

Sistem ini menyertakan service `cleanup` yang berjalan di background.

- **Fungsi**: Memindai folder temporary jobs setiap jam.
- **Aturan**: Menghapus folder job yang usianya lebih dari **60 menit**.
- **Tujuan**: Mencegah disk penuh akibat file sampah dari job yang mungkin crash atau dihentikan paksa.
- **Script**: Logika pembersihan ada di file `cleanup.sh`.

## Webhook Callback

If a `callback_url` is provided in the request, the worker will send a POST request to that URL upon job completion or failure.

### Success Payload
```json
{
  "job_id": "90ba2c64-9bab-45f8-b622-7276a68275ab",
  "status": "finished",
  "language": "en",
  "duration": 120.5,
  "output": "srt",
  "minio_url": "https://storage.example.com/transcribe/90ba2c64-9bab-45f8-b622-7276a68275ab/output.srt",
  "db_id": "optional_db_id"
}
```

### Failure Payload
```json
{
  "job_id": "90ba2c64-9bab-45f8-b622-7276a68275ab",
  "status": "failed",
  "error": "Error description here",
  "db_id": "optional_db_id"
}
```
