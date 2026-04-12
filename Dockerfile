# 1. 가볍고 빠른 파이썬 3.10 슬림 버전 사용
FROM python:3.10-slim

# 2. 영상 렌더링에 필수적인 OS 레벨 그래픽 패키지 및 한글 폰트 설치
RUN apt-get update && apt-get install -y \
    imagemagick \
    ffmpeg \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# 3. ImageMagick의 자막(Text) 렌더링 보안 정책 해제 (이거 없으면 권한 에러 남)
RUN sed -i 's/<policy domain="path" rights="none" pattern="@\*"//' /etc/ImageMagick-6/policy.xml

# 4. 작업 폴더 설정
WORKDIR /app

# 5. 파이썬 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. 소스코드 복사
COPY . .

# 7. 서버 구동
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
