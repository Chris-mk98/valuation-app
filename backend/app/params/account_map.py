"""계정 매핑표 로더 (data/params/account_map.yaml).

Stage 2 정규화가 사용하는 DART→내부계정 매핑 정의를 읽는다. 관리자/엑셀 업로드로 갱신 가능.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.config import DATA_DIR

ACCOUNT_MAP_PATH = DATA_DIR / "params" / "account_map.yaml"


@lru_cache
def load_account_map(path: Path | None = None) -> dict:
    """계정 매핑 정의를 dict 로 반환."""
    p = path or ACCOUNT_MAP_PATH
    if not p.exists():
        raise FileNotFoundError(f"계정 매핑 파일이 없습니다: {p}")
    with p.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "targets" not in data:
        raise ValueError(f"계정 매핑 형식 오류: {p}")
    return data
