# Valuation App — 기업가치평가 자동화·감사추적 도구

[![CI](https://github.com/Chris-mk98/valuation-app/actions/workflows/ci.yml/badge.svg)](https://github.com/Chris-mk98/valuation-app/actions/workflows/ci.yml)

회계법인 가치평가 업무를 자동화하되, **"자동 계산기"가 아니라 전문가의 판단을 구조화·기록하는 도구**.
DART·ECOS·KRX 데이터를 수집해 **수익가치(DCF)·시장가치·자산가치**를 산출하고, 몬테카를로로 분포를 추정한 뒤,
**평가목적별 규제 제약**(손상검사·합병비율·상증세법·일반 M&A)으로 종합한다. 모든 숫자에 출처를 남기고, Stage마다
검토·승인을 거치며, 시스템이 채운 값은 **사유와 함께 덮어쓸 수 있다.**

> 전체 설계: [`docs/data_flow.md`](docs/data_flow.md) · 프로젝트 규칙: [`CLAUDE.md`](CLAUDE.md) · 개발 로그: [`docs/ai_dev_log.md`](docs/ai_dev_log.md)

---

## 핵심 설계 원칙 (예외 없음)

| 원칙 | 구현 |
|---|---|
| **① 검토 체크포인트 (HITL)** | 모든 Stage는 `자동산출 → 검토 → 승인` 후에만 다음으로. 상위 변경 시 하위 자동 무효화 (`core/stage_gate.py`) |
| **② 전문가 오버라이드** | 파생값은 **사유 필수**로 덮어쓰기, 원본은 보존. 되돌리면 시스템 제안값 복원 (`core/lineage.py`) |
| **③ Excel 전면 지원** | 입력 표는 템플릿 다운/업로드+검증, 모든 Stage 결과 다운로드 |
| **④ Lineage** | 어떤 숫자도 출처(`USER·API·PARAM_TABLE·DERIVED·EXPERT_OVERRIDE·EXCEL_UPLOAD`) 없이 저장 금지 |

---

## 10-Stage 파이프라인

| Stage | 내용 | 순수 계산함수 |
|---|---|---|
| 0 설정 | 대상회사·기준일·평가목적 → corp_code 매핑 | — |
| 1 수집 | DART 재무제표(5개년)·기업개황, ECOS 국고채, KRX 주가 (캐시·원본보존·호출로그) | — |
| 2 정규화 | DART 표준계정 → 내부계정 매핑 (account_id 우선+계정명 폴백) | `s2_normalize` |
| 3 유사기업 | KRX 업종 프리필터 → **DART KSIC 중분류** 확정 → 규모·흑자·상장연수 필터 | `s3_peers` |
| 4 WACC | 유사기업 **주간 β OLS**(2년·KOSPI) → 언레버/리레버 → CAPM Ke → Kd → WACC | `s4_wacc` |
| 5 DCF | 과거비율 예측가정 → FCFF → 현가+고든 TV → EV → 주주가치 | `s5_dcf` |
| 6 시장접근 | EV/EBITDA·PER·PBR → **IQR 이상치 제거·중앙값** → 대상 적용 | `s6_market` |
| 7 자산접근 | 지배주주 순자산 ± 조정항목 → 조정순자산 (상증세법 할증) | `s7_asset` |
| 8 몬테카를로 | 6변수 정규분포·**촐레스키 상관** → 10,000회 DCF → P10/50/90·토네이도 | `s8_montecarlo` |
| 9 목적별 종합 | 방법론 가중(목적별 잠금)·**ECOS 명목GDP**·레드플래그 승인 게이트 | `s9_review` |
| 10 산출물 | 풋볼필드·HTML 리포트·전체 워크북(10시트)·감사추적 CSV·케이스 JSON | — |

> `stages/*` 는 **순수 함수**(DB·HTTP 접근 금지). 각 함수는 손계산 기대값 fixture로 검증된다 — 포트폴리오의 핵심.

---

## 실계 동작 예시 — 삼성전자 (기준일 2023-12-28, 일반 M&A)

전체 파이프라인을 **실제 DART/ECOS/KRX API로 종단 검증**한 결과:

```
수집        DART 연결재무 5개년 (2019~2023, 176~210계정)
정규화      매출 258.9조 · 영업이익 6.57조 · CAPEX 60.5조 · 순차입금 −56.4조(순현금)
            (D&A는 삼성 fnlttSinglAcntAll에 없어 unmapped → 주석 기준 오버라이드)
유사기업    KSIC 중분류 26 → LG전자 확정 (β 1.0, R² 0.31)
WACC        Rf 3.18% + β·(ERP 4.6%+국가위험 0.9%) → Ke 8.68%, Kd 7.34% → WACC 8.68%
DCF         EV 170.5조 · 주주가치 226.9조 · 주당 38,814원 · TV비중 66%
시장접근    PER 28.2·PBR 1.65 → 가치범위 437~584조
자산접근    조정순자산 353조 · 주당 61,276원
몬테카를로  10,000회(0.1초) → P10 104조 / P50 226조 / P90 363조 · 토네이도 1위 CAPEX/매출
종합        명목GDP 3.71%(ECOS) 기준 레드플래그 평가 → 최종 363.6조 (유사기업<5 플래그 승인)
```

**풋볼필드 (방법론별 범위, 조원)**

```
수익가치(DCF)  |========104~363========|          (몬테카를로 P10~P90)
시장가치        |          437~584 =====|
자산가치        |     353 ▮             |
최종            |            ▮ 363.6    |
```

---

## 도메인 차별화

- **평가목적별 규제 제약을 규칙(YAML)으로 강제** — 손상검사(예측≤5년·사용가치/공정가치 병렬), 합병비율(수익:자산 **1.5:1 가중치 잠금**), 상증세법(순손익:순자산 **3:2 + 순자산 80% 하한 + 최대주주 할증**), 일반 M&A(사용자 가중).
- **레드플래그 승인 게이트** — TV비중>70%·영구성장률>명목GDP·예측마진>과거최고·CAPEX<D&A·유사기업<5·베타 R²<0.1. 발동된 플래그를 **승인해야만** 진행되며 승인 내역이 기록된다.
- **결손 데이터를 숨기지 않고 경고로 노출** — 삼성처럼 D&A가 미상이면 unmapped로 표시하고 오버라이드를 유도, 유사기업 부족(<5)은 레드플래그로 표시.

---

## 아키텍처 · 기술 스택

```
backend/   FastAPI + SQLAlchemy 2.0 + SQLite/PostgreSQL
  core/      lineage · stage_gate · rules   (횡단 관심사, Stage 코드보다 우선)
  sources/   dart · ecos · price            (외부 API, 캐시·원본보존·호출로그)
  stages/    s2~s9                          (순수 계산함수)
  params/    account_map · param_tables     (📄 다모다란·수동표)
  excel/ · reports/ · api/
frontend/  React 18 + TypeScript + Vite + Tailwind + recharts
infra/     docker-compose · 배포 설정
data/      정적 파라미터(CSV·YAML) + SQLite 캐시(gitignore)
```

- **데이터**: OpenDART(재무·기업개황) · ECOS(국고채 10Y·명목GDP) · FinanceDataReader/pykrx(상장사·주가) · 다모다란(ERP·베타)
- **테스트**: pytest + vcrpy(외부 API 카세트 녹화, 네트워크 없이 재생) · 손계산 fixture · seed 재현성
- **CI**: GitHub Actions — ruff lint + pytest(backend) · vite build(frontend)

---

## 로컬 실행

### Backend
```bash
cd backend
pip install -e ".[dev]"                 # 계산·API. 외부수집까지: pip install -e ".[dev,sources]"
uvicorn app.main:app --reload           # http://localhost:8000/health · /docs
pytest                                   # 125건, 네트워크 없이 통과
ruff check .
```

### Frontend
```bash
cd frontend
npm install
npm run dev                              # http://localhost:5173
```

### Docker (both)
```bash
cp .env.example .env                     # DART_API_KEY / ECOS_API_KEY 입력
docker compose -f infra/docker-compose.yml up --build
```

> API 키가 없어도 앱은 기동한다(수집 기능만 제한). 실제 키는 `.env`에만 두며 코드·로그·커밋에 노출하지 않는다.

---

## 테스트

```bash
cd backend && pytest -q
```

- **125건 통과 · 네트워크 불필요** — 계산 로직은 손계산 기대값 대조, 외부 API는 VCR 카세트(키 스크럽) 재생, 몬테카를로는 seed 고정 재현성.
- 예: `test_s4_wacc`(β OLS·언레버/리레버·WACC), `test_s5_dcf`(FCFF·TV·EV), `test_s8_montecarlo`(분포·토네이도), `test_s9_review`(목적별 가중·레드플래그).

---

## 로드맵

- 거래사례 DART 주요사항보고서 파싱 자동구축 (현재 엑셀 업로드)
- 예측가정 연도별 세분화 · 실시간 상관행렬 입력
- 수식 살아있는 최종 워크북 · PDF 리포트(CJK 폰트 임베딩)
- Docker 이미지 배포 (AWS App Runner / Render)

---

## 환경변수

`.env` (커밋 금지) — 항목은 [`.env.example`](.env.example) 참고. 키 이름 뒤 공백 금지(`KEY=value`).
