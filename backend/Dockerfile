# 빌드 컨텍스트는 저장소 루트 (docker-compose.yml 참고)

# 1) 프런트 정적 빌드
FROM node:24-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend .
ARG NEXT_PUBLIC_API_TOKEN=""
RUN npm run build

# 2) API + 정적 파일
FROM python:3.13-slim
WORKDIR /srv
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app app
COPY --from=web /web/out static
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
