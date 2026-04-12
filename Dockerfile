# 1. 파이썬 3.10 슬림 버전
FROM python:3.10-slim

# 2. 영상 렌더링 필수 OS 패키지 & 한글 폰트 설치
RUN apt-get update && apt-get install -y \
    imagemagick \
    ffmpeg \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# 3. ImageMagick 텍스트 렌더링 보안 권한 해제 
RUN sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/g' /etc/ImageMagick-6/policy.xml || true
RUN sed -i '/<policy domain="path" rights="none" pattern="@\*"/d' /etc/ImageMagick-6/policy.xml || true
ENV IMAGEMAGICK_BINARY=/usr/bin/convert

WORKDIR /app

# 4. 💡 무한 루프(타임아웃) 방지를 위한 패키지 분할 고속 설치
RUN pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir fastapi uvicorn pydantic httpx
RUN pip install --no-cache-dir litellm langgraph langfuse openai
RUN pip install --no-cache-dir google-api-python-client google-auth-oauthlib
RUN pip install --no-cache-dir python-telegram-bot==20.3 moviepy==1.0.3

# 5. 소스코드 복사 및 메인 서버 가동
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
