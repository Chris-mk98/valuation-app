# ADR 0001 · 기술 스택 및 스켈레톤 구조

- 상태: 채택
- 날짜: 2026-09-12

## 배경
회계법인 가치평가 업무 자동화 도구. CLAUDE.md 4대 원칙(체크포인트·오버라이드·Excel·Lineage)을
구현 구조에 반영해야 한다. 전체 설계는 docs/data_flow.md.

## 결정
- **Backend**: Python 3.12 + FastAPI + SQLAlchemy 2.0. 개발 DB는 SQLite, 배포는 PostgreSQL(`DATABASE_URL` 오버라이드).
- **패키징**: hatchling 기반 `pyproject.toml`. 외부 데이터 라이브러리(dart-fss, ecos-reader, FDR, pykrx)는
  `[sources]` extra 로 분리해 스켈레톤 빌드를 가볍게 유지, 3단계에서 활성화.
- **계층 구조**: `core/`(횡단 관심사) 를 `sources/`·`stages/`·`api/` 보다 먼저 구현. `stages/`는 순수 함수.
- **Frontend**: React 18 + TypeScript + Vite + Tailwind + recharts.
- **테스트**: pytest + vcrpy(카세트 재생, 네트워크 무의존), 프론트는 `tsc -b && vite build`로 검증.
- **CI**: GitHub Actions — backend(ruff + pytest), frontend(build).
- **컨테이너/compose**: `infra/docker-compose.yml` 하나로 backend+frontend 기동.

## 결과
- 스켈레톤 단계: `/health` 응답 + 빈 대시보드 + 네트워크 없는 pytest 통과.
- 설정 로딩은 키가 없어도 앱이 기동(경고만) — 개발 편의와 원칙(키는 .env 에만) 양립.

## 후속 이슈
- `.env` 의 `ECOS_API_KEY` 이름 뒤 공백 → `.env.example` 에 형식 주의 명시. DART 키는 미발급 상태.
