"""애플리케이션 설정 로더.

실제 API 키는 .env 에만 두고, 코드·로그에 값을 노출하지 않는다(CLAUDE.md 환경 규칙).
키가 없어도 앱은 기동해야 한다(스켈레톤/개발 편의) — 없을 때는 경고만 남긴다.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# 리포지토리 루트 (backend/ 의 부모)
REPO_ROOT = Path(__file__).resolve().parents[2]
# 배포 이미지에서는 소스 레이아웃과 달라질 수 있어 DATA_DIR 을 env 로 오버라이드 가능하게 둔다.
DATA_DIR = Path(os.environ["DATA_DIR"]) if os.environ.get("DATA_DIR") else REPO_ROOT / "data"


class Settings(BaseSettings):
    """.env 및 환경변수에서 로드하는 설정.

    pydantic-settings 는 환경변수 이름의 앞뒤 공백을 무시하지 못할 수 있으므로,
    .env 는 `KEY=value` 형식(이름 뒤 공백 없음)으로 유지한다.
    """

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 외부 API 키 (값은 절대 로그로 남기지 않음)
    dart_api_key: str | None = Field(default=None)
    ecos_api_key: str | None = Field(default=None)

    # 데이터베이스 (개발: SQLite, 배포: PostgreSQL)
    database_url: str = Field(default=f"sqlite:///{DATA_DIR / 'cache' / 'valuation.db'}")

    # CORS 허용 오리진 (프론트 개발 서버)
    cors_origins: list[str] = Field(default=["http://localhost:5173", "http://127.0.0.1:5173"])

    def warn_missing_keys(self) -> None:
        """키 존재 여부만 로깅한다(값은 노출 금지)."""
        for name, present in (
            ("DART_API_KEY", bool(self.dart_api_key)),
            ("ECOS_API_KEY", bool(self.ecos_api_key)),
        ):
            if not present:
                logger.warning("%s 미설정 — 외부 데이터 수집(Stage 1) 기능은 제한됩니다.", name)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.warn_missing_keys()
    return settings
