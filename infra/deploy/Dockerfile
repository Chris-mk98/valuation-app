# App Runner 단일 서비스 이미지 — FastAPI 가 API + 빌드된 프론트엔드를 함께 서빙.
# 빌드 컨텍스트: 리포지토리 루트.  build:  docker build -f infra/deploy/Dockerfile -t <img> .

# ---- 1) 프론트엔드 빌드 ----
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- 2) 백엔드 + 정적 ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data \
    FRONTEND_DIST=/app/frontend_dist \
    DATABASE_URL=sqlite:////app/data/cache/valuation.db
WORKDIR /app

# 의존성(외부수집 포함) 설치
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --upgrade pip && pip install ".[sources]"

# 정적 파라미터 + 프론트 빌드 산출물
COPY data ./data
COPY --from=frontend /fe/dist ./frontend_dist
RUN mkdir -p /app/data/cache

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
