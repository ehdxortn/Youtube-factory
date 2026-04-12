# Python 3.10 슬림 버전 사용
FROM python:3.10-slim

# MoviePy (ImageMagick, FFmpeg) 및 오디오 처리를 위한 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    imagemagick \
    ffmpeg \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# 💡 핵심 수정: ImageMagick 6, 7 버전에 상관없이 모두 적용되도록 와일드카드(*) 사용
RUN sed -i 's/none/read,write/g' /etc/ImageMagick-*/policy.xml || true

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run에서 주입하는 PORT 환경변수 사용
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
