# 1. 파이썬 3.10 이미지 사용 (MoviePy 호환성 최적화)
FROM python:3.10-slim

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. MoviePy 및 오디오 처리를 위한 시스템 패키지 설치 (방탄 세팅)
RUN apt-get update && apt-get install -y \
    imagemagick \
    ffmpeg \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# 💡 핵심: ImageMagick 보안 정책 수정 (성공 확률 100% 와일드카드 방식)
RUN sed -i 's/none/read,write/g' /etc/ImageMagick-*/policy.xml || true

# 4. 요구사항 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 소스 코드 전체 복사
COPY . .

# 6. 구글 클라우드 런 포트 설정 및 실행 (형님 코인 봇 방식 적용)
ENV PORT=8080
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
