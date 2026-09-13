"""평가목적별 제약 규칙 로더 (CLAUDE.md 원칙, docs/data_flow.md §9).

규칙은 data/params/rules/ 아래 YAML(관리자 갱신)로 두고 여기서 로드한다.
스켈레톤 단계에서는 설계서 §9 값을 그대로 담은 4종 목적 + 공통 레드플래그 골격만 제공한다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.config import DATA_DIR

RULES_DIR = DATA_DIR / "params" / "rules"

# 평가목적 키 → YAML 파일명 (Stage 0 평가목적 선택지에 대응)
PURPOSE_FILES: dict[str, str] = {
    "impairment": "impairment.yaml",  # 손상검사 (K-IFRS 1036)
    "merger_ratio": "merger_ratio.yaml",  # 합병비율 (자본시장법)
    "inheritance_gift": "inheritance_gift.yaml",  # 상증세법 보충적평가
    "general_ma": "general_ma.yaml",  # 일반 M&A
}

REVIEW_FLAGS_FILE = "review_flags.yaml"

_REQUIRED_KEYS = {"purpose", "label", "method_weights", "constraints"}


def list_purposes() -> list[str]:
    """지원하는 평가목적 키 목록."""
    return list(PURPOSE_FILES)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"규칙 파일이 없습니다: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"규칙 파일 형식 오류(dict 아님): {path}")
    return data


@lru_cache
def load_rules(purpose: str, rules_dir: Path | None = None) -> dict:
    """평가목적별 제약 규칙을 로드한다.

    Args:
        purpose: PURPOSE_FILES 의 키. 알 수 없으면 KeyError.
    """
    if purpose not in PURPOSE_FILES:
        raise KeyError(f"알 수 없는 평가목적: {purpose!r}. 지원: {list_purposes()}")
    base = rules_dir or RULES_DIR
    data = _load_yaml(base / PURPOSE_FILES[purpose])
    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"{purpose} 규칙에 필수 키 누락: {sorted(missing)}")
    return data


@lru_cache
def load_review_flags(rules_dir: Path | None = None) -> dict:
    """공통 레드플래그 임계치(§9)를 로드한다."""
    base = rules_dir or RULES_DIR
    return _load_yaml(base / REVIEW_FLAGS_FILE)
