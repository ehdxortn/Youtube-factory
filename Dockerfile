# 1. 파이썬 3.10 슬림 버전
FROM python:3.10-slim

# 2. 영상 렌더링 필수 OS 패키지 & 한글 폰트 설치
RUN apt-get update && apt-get install -y \
    imagemagick \
    ffmpeg \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# 3. ImageMagick 텍스트 렌더링 보안 권한 해제 
# (파일 구조가 달라도 빌드가 뻗지 않도록 '|| true' 안전장치 결합)
RUN sed -i 's/rights="none" pattern="@\*"/rights="read|write" pattern="@*"/g' /etc/ImageMagick-6/policy.xml || true
RUN sed -i '/<policy domain="path" rights="none" pattern="@\*"/d' /etc/ImageMagick-6/policy.xml || true

# 4. 환경 변수 세팅 (MoviePy가 엔진을 못 찾는 버그 원천 차단)
ENV IMAGEMAGICK_BINARY=/usr/bin/convert

# 5. 작업 폴더 및 파이썬 패키지 설치
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. 소스코드 복사 및 메인 서버 가동
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
