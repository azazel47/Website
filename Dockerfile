# Stage 1: Build the Application
FROM python:3.11 AS build

WORKDIR /usr/src/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# --- PERUBAHAN 1: Path Requirements ---
# Mengambil requirements.txt spesifik dari folder backend
COPY backend/requirements.txt ./requirements.txt

# Install dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# --- PERUBAHAN 2: Path Source Code ---
# Menyalin ISI folder 'backend' ke dalam working directory container
# Ini akan menyalin server.py, folder utils, dll ke /usr/src/app/
COPY backend/ .

# Stage 2: Create the Final Production Image
FROM python:3.11

WORKDIR /usr/src/app

# Copy venv dari stage build
COPY --from=build /opt/venv /opt/venv

# Copy source code dari stage build
COPY --from=build /usr/src/app .

ENV PATH="/opt/venv/bin:$PATH"

# Setup user non-root (Keamanan)
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /usr/src/app
USER appuser

ENV PORT=8080
EXPOSE $PORT

# --- PERUBAHAN 3: Command Start ---
# Berdasarkan gambar, file utama Anda adalah 'server.py', bukan 'app.py'
CMD ["python", "server.py"]
