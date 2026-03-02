FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt server.py ./   # ✅ YEH SAHI HAI (with 's')

RUN pip install --no-cache-dir -r requirements.txt

ENV PORT=8080
ENV DOWNLOAD_DIR=/tmp/vidsnap

CMD ["python3", "server.py"]
