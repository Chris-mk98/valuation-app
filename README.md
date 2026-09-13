# Valuation App

회계법인 가치평가팀의 반복 업무를 자동화하되, **전문가의 판단을 구조화·기록**하는 내부 도구.
자동 계산기가 아니라 모든 값에 출처(lineage)를 남기고, Stage별 검토·승인(HITL)을 거치며,
시스템이 채운 파생값을 사유와 함께 오버라이드할 수 있게 한다.

전체 설계: [`docs/data_flow.md`](docs/data_flow.md) · 프로젝트 규칙: [`CLAUDE.md`](CLAUDE.md)

## 아키텍처

```
backend/   FastAPI + SQLAlchemy. core/(lineage·stage_gate·rules) 위에 sources/·stages/·api/
frontend/  React + TS + Vite + Tailwind + recharts
infra/     docker-compose, 배포 설정
data/      정적 파라미터 테이블 + SQLite 캐시(gitignore)
```

- `stages/*` 는 순수 함수(DB·HTTP 금지) — 손계산 대조 테스트로 검증.
- 외부 API 호출은 `sources/` 에서만, 캐시 우선 + 원본 보존 + 호출 로그.
- 어떤 숫자도 출처(`USER|API|PARAM_TABLE|DERIVED|EXPERT_OVERRIDE|EXCEL_UPLOAD`) 없이 저장하지 않는다.

## 로컬 실행

### Backend
```bash
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload      # http://localhost:8000/health
pytest                             # 네트워크 없이 통과
```

### Frontend
```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

### Docker (both)
```bash
cp .env.example .env               # DART_API_KEY / ECOS_API_KEY 채우기
docker compose -f infra/docker-compose.yml up --build
```

## 상태

- [x] 스켈레톤 (backend /health, frontend 대시보드, CI, compose)
- [x] core/: lineage · stage_gate · rules (오버라이드 사유필수·하위 무효화·목적별 YAML)
- [x] Stage 0~2 수직 슬라이스: DART/ECOS 수집(캐시·원본보존) → 정규화(계정매핑) → 검토·오버라이드·승인 UI
- [x] Stage 3 유사기업: KRX 유니버스 → KSIC 중분류 스크리닝 → 포함/제외(사유필수)·수동추가
- [x] Stage 4 WACC: 유사기업 주간베타(2년·KOSPI) → 언레버/리레버 → CAPM Ke → Kd → WACC (구성요소 오버라이드·재계산)
- [x] Stage 5 DCF: 과거비율 예측가정 → FCFF → 현가+TV → EV → 주주가치·주당가치 (가정 오버라이드·재계산)
- [x] Stage 6 시장접근: 유사기업 EV/EBITDA·PER·PBR → IQR 이상치 제거·중앙값 → 대상 적용 (거래사례 엑셀 업로드)
- [x] Stage 7 자산접근: 장부 순자산(지배주주) ± 조정항목 → 조정순자산 (상증세법 최대주주 할증)
- [x] Stage 8 몬테카를로: 6변수 정규분포·촐레스키 상관 → 10,000회 DCF → P10/50/90·히스토그램·토네이도
- [x] Stage 9 목적별 조정·리뷰: 방법론 가중종합(목적별 잠금)·ECOS 명목GDP·레드플래그 승인 게이트
- [x] Stage 10 산출물: 풋볼필드·HTML 리포트·전체 워크북(10시트)·감사추적 CSV·케이스 JSON 스냅샷

**Stage 0~10 전 파이프라인 완성** — 삼성전자로 케이스 생성부터 목적별 종합·산출물까지 실계 동작 검증.
테스트 125건(손계산·VCR·재현성) 네트워크 없이 통과.

계정 매핑 기준(EBIT·D&A·NWC·순차입금 정의)은 회계 판단으로 확정 — `data/params/account_map.yaml` 참조.
테스트 43건(손계산·VCR 카세트) 네트워크 없이 통과. 실계 삼성전자로 Stage 2 승인까지 검증 완료.

## 환경변수

`.env` (커밋 금지) — 자세한 항목은 [`.env.example`](.env.example) 참고.
