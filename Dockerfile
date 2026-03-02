FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg
RUN pip install yt-dlp --no-cache-dir

COPY . /app

ENV PORT=8080
EXPOSE 8080

CMD ["python3", "/app/vidsnap_server.py"]
