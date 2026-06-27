FROM python:3.11-slim

# HF Spaces runs as non-root user 1000
RUN useradd -m -u 1000 baadar

# System deps for moviepy/PIL/ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create data dir (persists across restarts on HF Spaces persistent storage)
RUN mkdir -p /app/data && chown -R baadar:baadar /app

USER baadar

# Write Firebase credentials from env var at startup
ENV FIREBASE_SA_KEY=/app/firebase-admin.json
ENV SAATHI_HOST=0.0.0.0
ENV PORT=7860

# HF Spaces uses port 7860
EXPOSE 7860

CMD ["sh", "-c", "\
  if [ -n \"$FIREBASE_ADMIN_JSON\" ]; then echo \"$FIREBASE_ADMIN_JSON\" > /app/firebase-admin.json; fi && \
  if [ -n \"$CONNECTIONS_JSON\" ]; then echo \"$CONNECTIONS_JSON\" > /app/data/connections.json; fi && \
  exec python -m saathi.server \
"]
