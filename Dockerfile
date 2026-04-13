# 1. 파이썬 3.10 슬림 버전
FROM python:3.10-slim

# 2. 필수 조립 공구(build-essential) 및 영상 렌더링 OS 패키지, 한글 폰트 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    imagemagick \
    ffmpeg \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# 3. 에러의 원흉인 ImageMagick 보안 파일 강제 삭제 (자막 에러 원천 차단)
RUN rm -f /etc/ImageMagick-6/policy.xml || true

# 4. 작업 폴더 세팅 및 파이썬 패키지 설치
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 소스코드 복사 및 가동
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
