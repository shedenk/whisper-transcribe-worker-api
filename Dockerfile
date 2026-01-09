FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
  ffmpeg \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["bash", "-c", "\
rm -rf /data/downloads/* /data/jobs/* 2>/dev/null; \
if [ \"$ROLE\" = \"worker\" ]; then \
  echo 'Starting TRANSCRIBE WORKER'; \
  python /app/worker.py; \
else \
  echo 'Starting TRANSCRIBE API'; \
  uvicorn app:app --host 0.0.0.0 --port 8080; \
fi"]
