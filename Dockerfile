# Krypton — cloud version (Hugging Face Spaces, Docker). Groq + offline engines; no local GPU.
FROM python:3.12-slim

# Chromium makes the PDFs; Noto fonts cover all Indian scripts in them
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY . .

ENV KRYPTON_HOST=0.0.0.0 KRYPTON_MAX_USERS=50 PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1
RUN useradd -m -u 1000 user && mkdir -p /app/data && chown -R user /app
USER user
WORKDIR /app/backend
CMD ["python", "krypton_server.py"]
