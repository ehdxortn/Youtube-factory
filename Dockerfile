# 1. 파이썬 3.10 슬림 버전 기반
FROM python:3.10-slim

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. 필수 시스템 패키지, ImageMagick 및 한글 폰트(나눔) 설치
# MoviePy의 TextClip 사용을 위해 ImageMagick의 보안 정책(policy.xml) 읽기 권한 수정 포함
RUN apt-get update && apt-get install -y --no-install-recommends \
    imagemagick \
    fonts-nanum \
    && ([ -f /etc/ImageMagick-6/policy.xml ] \
    && sed -i 's/rights="none"/rights="read|write"/g' /etc/ImageMagick-6/policy.xml \
    || true) \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 4. ImageMagick 경로 환경변수 강제 설정
ENV IMAGEMAGICK_BINARY=/usr/bin/convert

# 5. 파이썬 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. 소스 코드 전체 복사
COPY . .

# 7. 실행 명령어 (만약 메인 실행 파일 이름이 main.py가 아니라면 해당 부분만 형님 코드에 맞게 변경하십시오)
CMD ["python", "main.py"]
