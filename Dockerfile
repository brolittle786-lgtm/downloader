FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg \
    && pip install yt-dlp --no-cache-dir

WORKDIR /app
COPY vidsnap_server.py .

ENV PORT=8080
CMD ["python3", "vidsnap_server.py"]
