#!/bin/bash

# ==============================================================================
# Script Cleanup Whisper Worker
# Fungsi: Membersihkan folder job sementara yang tertinggal (stuck/crash).
# Cara pakai:
#   1. Beri izin execute: chmod +x cleanup.sh
#   2. Jalankan manual: ./cleanup.sh
#   3. Atau pasang di cron (misal tiap jam): 0 * * * * /path/to/cleanup.sh
# ==============================================================================

# Directory tempat script berada
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ENV_FILE="$SCRIPT_DIR/.env"

# Konfigurasi Default
STORAGE_DIR="/data"
# Hapus folder yang tidak berubah selama 60 menit.
# PENTING: Nilai ini harus lebih besar dari JOB_TIMEOUT di .env (1800s = 30m)
RETENTION_MINUTES=60 

# Coba deteksi STORAGE_DIR dari file .env jika ada
if [ -f "$ENV_FILE" ]; then
    # Grep variable STORAGE_DIR, ambil value-nya, hilangkan quote
    VAL=$(grep "^STORAGE_DIR=" "$ENV_FILE" | cut -d '=' -f2 | tr -d '"' | tr -d "'")
    if [ ! -z "$VAL" ]; then
        STORAGE_DIR="$VAL"
    fi
fi

JOBS_DIR="$STORAGE_DIR/jobs"

echo "[$(date)] Memulai cleanup pada: $JOBS_DIR"

if [ -d "$JOBS_DIR" ]; then
    # Cari folder job yang usianya > RETENTION_MINUTES
    # -mindepth 1: Jangan hapus folder jobs itu sendiri
    # -maxdepth 1: Hanya folder job langsung (UUID)
    # -type d: Hanya direktori
    # -mmin +N: Modified N minutes ago
    
    echo "    Mencari folder yang lebih tua dari $RETENTION_MINUTES menit..."
    find "$JOBS_DIR" -mindepth 1 -maxdepth 1 -type d -mmin +$RETENTION_MINUTES -print -exec rm -rf {} +
else
    echo "[!] Directory $JOBS_DIR tidak ditemukan. Pastikan path benar atau volume ter-mount."
fi