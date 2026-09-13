"""FastAPI 엔트리포인트.

스켈레톤 단계: /health 만 제공. 비즈니스 라우터는 2·3단계에서 app/api 아래에 추가하고
여기서 include_router 로 연결한다.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import cases, excel_routes, outputs, stages
from app.config import get_settings
from app.db.models import Base
from app.db.session import engine

logging.basicConfig(level=logging.INFO)
# httpx/httpcore 는 요청 URL(인증키 포함)을 INFO 로 남기므로 억제 (CLAUDE.md: 키 로그 노출 금지)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

settings = get_settings()

# 개발 편의: 기동 시 테이블 생성(배포는 마이그레이션으로 대체 예정)
Base.metadata.create_all(engine)

app = FastAPI(
    title="Valuation App API",
    version="0.1.0",
    description="기업가치평가 웹앱 — 전문가 판단을 구조화·기록하는 내부 도구",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """헬스체크. 배포 환경 기동 확인용."""
    return {"status": "ok"}


app.include_router(cases.router)
app.include_router(stages.router)
app.include_router(excel_routes.router)
app.include_router(outputs.router)

# 배포(App Runner 단일 서비스): 빌드된 프론트엔드 정적파일을 같은 오리진에서 서빙.
# FRONTEND_DIST 가 설정된 경우에만 마운트 → 개발/테스트에는 영향 없음. API 라우트가 우선.
_frontend_dist = os.environ.get("FRONTEND_DIST")
if _frontend_dist and os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
