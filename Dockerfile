# Python 3.10 슬림 버전 사용
FROM python:3.10-slim

# MoviePy (ImageMagick, FFmpeg) 및 오디오 처리(pydub)를 위한 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    imagemagick \
    ffmpeg \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# ImageMagick 보안 정책 수정 (MoviePy TextClip 오류 방지)
RUN sed -i 's/none/read,write/g' /etc/ImageMagick-6/policy.xml

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run에서 주입하는 PORT 환경변수 사용
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
