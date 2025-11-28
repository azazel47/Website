# Gunakan image Python yang ringan
FROM python:3.9-slim

# 1. Install system dependencies (PROJ & Compiler)
# Ini langkah paling penting untuk memperbaiki error Anda
RUN apt-get update && apt-get install -y \
    build-essential \
    libproj-dev \
    proj-bin \
    libgdal-dev \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set environment variable agar pyproj bisa menemukan PROJ
ENV PROJ_DIR=/usr/

# Setup working directory
WORKDIR /app

# 2. Copy requirements dan install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy sisa source code
COPY . .

# Perintah untuk menjalankan aplikasi Anda
# GANTI "main:app" sesuai nama file dan app Anda (misal: app:server, atau manage.py runserver)
CMD ["python", "main.py"]
