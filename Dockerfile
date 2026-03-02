FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

RUN pip install yt-dlp --no-cache-dir

WORKDIR /app
COPY server.py .

ENV PORT=8080
ENV DOWNLOAD_DIR=/tmp/vidsnap

CMD ["python3", "server.py"]
