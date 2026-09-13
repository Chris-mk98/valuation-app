"""pytest 공용 픽스처 + VCR 설정 골격.

외부 API 통합 테스트는 vcrpy 카세트를 재생하며, 네트워크 없이 통과해야 한다.
실제 API 키·인증정보는 카세트에 기록되지 않도록 여기서 필터링한다(3단계에서 실사용).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base

CASSETTE_DIR = Path(__file__).parent / "integration" / "cassettes"


@pytest.fixture
def db() -> Iterator[Session]:
    """테스트용 in-memory SQLite 세션. 각 테스트마다 새 스키마."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(scope="session")
def vcr_config() -> dict:
    """민감정보(API 키)를 카세트에서 제거하는 공통 설정.

    dart/ecos 는 인증키를 쿼리스트링(crtfc_key / api key)으로 전달하므로 마스킹한다.
    """
    return {
        "cassette_library_dir": str(CASSETTE_DIR),
        "record_mode": "none",  # 카세트 없으면 실패 → 네트워크 의존 방지
        "filter_query_parameters": [
            ("crtfc_key", "DUMMY"),
            ("api_key", "DUMMY"),
            ("authKey", "DUMMY"),
        ],
        "filter_headers": ["authorization"],
    }
