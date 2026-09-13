# 프로젝트 셋업: 폴더 구조 & Claude Code 첫 프롬프트

---

## 1. 폴더 구조

```
valuation-app/
├── CLAUDE.md                      # Claude Code가 항상 읽는 프로젝트 규칙 (아래 2장)
├── docs/
│   ├── data_flow.md               # 데이터 흐름 설계서 (앞서 만든 문서 그대로)
│   ├── adr/                       # 설계 결정 기록 (Architecture Decision Records)
│   │   └── 0001-stack.md
│   └── ai_dev_log.md              # Claude Code 사용 기록: 프롬프트·검증·수정 내역 (포트폴리오 증빙)
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI 엔트리
│   │   ├── config.py              # 환경변수(API 키), 설정
│   │   ├── db/
│   │   │   ├── models.py          # SQLAlchemy 모델 (cases, lineage, stage_status ...)
│   │   │   └── session.py
│   │   ├── sources/               # 🌐 외부 데이터 어댑터 (원본 보존, 캐시)
│   │   │   ├── dart.py
│   │   │   ├── ecos.py
│   │   │   ├── price.py           # FDR/pykrx + CSV 폴백
│   │   │   └── damodaran.py       # CSV 적재
│   │   ├── params/                # 📄 파라미터 테이블 로더 + 버전관리
│   │   ├── stages/                # 단계별 계산 (순수 함수, 프레임워크 무관)
│   │   │   ├── s2_normalize.py
│   │   │   ├── s3_peers.py
│   │   │   ├── s4_wacc.py
│   │   │   ├── s5_dcf.py
│   │   │   ├── s6_market.py
│   │   │   ├── s7_asset.py
│   │   │   ├── s8_montecarlo.py
│   │   │   └── s9_adjust_review.py
│   │   ├── core/                  # 횡단 관심사
│   │   │   ├── lineage.py         # 모든 값 기록, 오버라이드 처리
│   │   │   ├── stage_gate.py      # DRAFT/REVIEWED/APPROVED 상태기계, 하위 무효화
│   │   │   └── rules.py           # 평가목적별 제약·레드플래그 규칙 엔진
│   │   ├── excel/                 # Excel I/O
│   │   │   ├── templates/         # 업로드 템플릿 생성기 (Stage별)
│   │   │   ├── importers.py       # 업로드 검증·반영
│   │   │   └── exporters.py       # Stage별 다운로드, 최종 워크북(수식 포함)
│   │   ├── reports/               # PDF 리포트 생성
│   │   └── api/                   # 라우터 (cases, stages, overrides, excel, reports)
│   ├── tests/
│   │   ├── unit/                  # 계산 로직 (CPA 검증 케이스 포함)
│   │   ├── integration/           # API 어댑터 (VCR 카세트로 녹화)
│   │   └── fixtures/              # 샘플 재무제표·주가
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/                 # 케이스 목록, Stage별 검토 화면, 대시보드
│   │   ├── components/
│   │   │   ├── StageStepper.tsx   # 진행·승인 현황
│   │   │   ├── ReviewPanel.tsx    # 산출값·근거·경고·변경분 표시 + 승인 버튼
│   │   │   ├── OverrideCell.tsx   # 덮어쓰기 + 사유 입력 + reset
│   │   │   ├── ExcelDropzone.tsx  # 템플릿 다운로드·업로드·셀 단위 오류
│   │   │   └── charts/            # 풋볼필드, 히스토그램, 토네이도
│   │   └── api/                   # 백엔드 클라이언트
│   ├── package.json
│   └── Dockerfile
├── data/
│   ├── params/                    # damodaran_erp.csv, size_premium.csv, tax_rates.csv ...
│   └── cache/                     # SQLite (gitignore)
├── infra/
│   ├── docker-compose.yml
│   └── deploy/                    # AWS App Runner 또는 Render 설정
├── .github/workflows/
│   └── ci.yml                     # lint + pytest + frontend build
├── .env.example                   # DART_API_KEY, ECOS_API_KEY
├── README.md                      # 아키텍처, 데모 URL, 캡처, 업무효율 효과, AI 활용 방식
└── .gitignore
```

**설계 포인트**
- `stages/`는 순수 함수로 두어 pytest로 숫자 검증이 쉽게. CPA로서 손계산·엑셀로 대조한 테스트 케이스를 여기에 넣는 것이 포트폴리오 핵심.
- `core/`가 세 원칙(체크포인트·오버라이드·엑셀)을 구현. Stage 코드는 이 모듈을 통해서만 값을 읽고 쓴다.
- `docs/ai_dev_log.md`는 매 작업마다 "무엇을 시켰고, 무엇이 틀렸고, 어떻게 고쳤는지"를 남겨 채용 담당자가 AI 활용 역량을 볼 수 있게.

---

## 2. CLAUDE.md (프로젝트 루트에 저장)

```markdown
# Valuation App — 프로젝트 규칙

## 프로젝트 목적
회계법인 가치평가팀의 반복 업무를 자동화하되, 전문가의 판단을 구조화·기록하는 내부 도구.
전체 설계는 docs/data_flow.md 를 따른다. 설계와 충돌하는 구현은 하지 않는다.

## 절대 원칙 (예외 없음)
1. 체크포인트: 모든 Stage는 자동산출 → 검토화면 → 승인 후에만 다음 Stage 진행. core/stage_gate.py 경유.
2. 오버라이드: 시스템이 채운 모든 파생값은 사용자가 덮어쓸 수 있고, 사유 입력 필수. 🌐 원본 데이터는 수정 금지.
   덮어쓰기는 반드시 core/lineage.py 의 record_override() 로만 처리.
3. Excel: 사용자 입력이 필요한 모든 표는 템플릿 다운로드 + 업로드 경로를 함께 제공. 모든 Stage 결과는 다운로드 가능.
4. Lineage: 어떤 숫자도 출처(USER|API|PARAM_TABLE|DERIVED|EXPERT_OVERRIDE|EXCEL_UPLOAD) 없이 저장하지 않는다.

## 기술 스택
- Backend: Python 3.12, FastAPI, SQLAlchemy, SQLite(개발)/PostgreSQL(배포), pandas, numpy, openpyxl, scipy
- Frontend: React + TypeScript + Vite, Tailwind, recharts
- 데이터: OpenDART(dart-fss), ECOS(ecos-reader), FinanceDataReader/pykrx
- 테스트: pytest, vcrpy(외부 API 녹화), vitest
- 배포: Docker, GitHub Actions, AWS App Runner (또는 Render)

## 코드 규칙
- stages/*.py 는 순수 함수. DB·HTTP 접근 금지. 입력 DataFrame/dict → 출력 dict.
- 외부 API 호출은 sources/ 에서만. 호출 전 캐시 확인, 호출 후 원본 저장 + api_call_log 기록.
- 금액은 Decimal 대신 float(백만원 단위)로 통일하되, 테스트에서는 abs tol 1e-6.
- 모든 계산 함수에 산식을 docstring으로 명시(예: β_u = β_L / (1 + (1−t)·D/E)).
- 새 기능은 반드시 테스트와 함께. 계산 로직은 손계산 기대값을 fixture로.

## 작업 방식
- 큰 작업은 먼저 계획을 제시하고 승인 후 구현.
- 구현 후 pytest 통과 확인, 실패 시 스스로 수정.
- 각 작업 종료 시 docs/ai_dev_log.md 에 3줄 요약 추가: 작업 / 발견된 문제 / 해결.
- 도메인 판단(회계기준, 세법, 평가 실무)이 필요하면 추측하지 말고 질문.

## 환경
- 실제 API 키는 .env 에만. 코드·로그·테스트에 절대 노출 금지.
- 테스트는 vcr 카세트 사용, 네트워크 없이 통과해야 함.
```

---

## 3. Claude Code 첫 프롬프트 (그대로 붙여넣기)

> 사전 준비: 빈 폴더에서 `git init`, `docs/data_flow.md`와 `CLAUDE.md`를 먼저 넣고, `.env`에 DART/ECOS 키 저장 후 Claude Code 실행.

```
이 프로젝트의 규칙은 CLAUDE.md, 전체 설계는 docs/data_flow.md 에 있다. 두 파일을 먼저 읽고 요약해줘.

그 다음 아래 순서로 "스켈레톤 + Stage 0~2 수직 슬라이스"를 만든다. 각 단계마다 계획을 먼저 보여주고 내 승인을 받은 뒤 구현해라.

## 1단계: 프로젝트 스켈레톤
- 위 폴더 구조대로 backend/frontend/infra/.github 생성
- pyproject.toml, package.json, docker-compose.yml, ci.yml(lint+pytest+build), .env.example, .gitignore
- backend는 `uvicorn app.main:app` 로 뜨고 /health 응답, frontend는 빈 대시보드 페이지가 뜨면 됨

## 2단계: 횡단 관심사 core/ 먼저 구현 (Stage 코드보다 우선)
- core/lineage.py: record_value(), record_override(rationale 필수), get_lineage(case_id) — docs/data_flow.md 6장 스키마 그대로
- core/stage_gate.py: 상태기계 DRAFT→REVIEWED→APPROVED, approve(), invalidate_downstream(stage_no)
- core/rules.py: 평가목적별 제약 규칙 로더 (일단 YAML 4종 골격만)
- 각 모듈 단위 테스트 포함 (오버라이드 시 사유 없으면 예외, 상위 Stage 변경 시 하위 DRAFT 전환 검증)

## 3단계: Stage 0~2 수직 슬라이스
- sources/dart.py: 회사 검색 → corp_code, 기업개황, 최근 5개년 재무제표(fnlttSinglAcntAll) 수집. 캐시 우선, 원본 JSON 저장, api_call_log 기록. vcr 카세트로 테스트.
- sources/ecos.py: 기준일 국고채 10Y 수익률 조회
- stages/s2_normalize.py: DART 표준계정 → 내부 계정(매출, EBIT, D&A, CAPEX, NWC, 순차입금, 비지배지분) 매핑. 매핑 실패 계정은 'unmapped' 리스트로 반환.
- excel/: Stage 1 원본 덤프 다운로드, Stage 2 정규화 재무 다운로드, 계정 매핑표 템플릿 다운로드/업로드(검증 포함)
- api/: POST /cases, POST /cases/{id}/stages/1/run, GET /cases/{id}/stages/2/review, POST /cases/{id}/stages/2/approve, 오버라이드·엑셀 엔드포인트
- frontend: 케이스 생성 → Stage 1 수집 결과 검토 화면 → Stage 2 매핑 검토 화면(오버라이드 셀 + 승인 버튼 + 엑셀 업/다운로드) → StageStepper 반영

## 완료 기준
- `docker compose up` 후 삼성전자(005930)로 케이스 만들어 Stage 2 승인까지 UI에서 가능
- pytest 전부 통과, 네트워크 없이도 통과
- docs/ai_dev_log.md 에 오늘 작업 기록

시작하기 전에 불명확한 점이 있으면 먼저 질문해라. 특히 계정 매핑 기준처럼 회계 판단이 필요한 부분은 내가 정한다.
```

---

## 4. 주말 일정 제안

| 시간 | 작업 | 산출 |
|---|---|---|
| 금 저녁 | API 키 발급 확인, pykrx/FDR 동작 테스트, 위 파일 3개 준비 | 환경 검증 |
| 토 오전 | 첫 프롬프트 1~2단계 | 스켈레톤 + core/ + 테스트 |
| 토 오후 | 3단계 (Stage 0~2 수직 슬라이스) | UI에서 승인까지 동작 |
| 토 저녁 | Stage 3~4 (유사기업, WACC) — 같은 패턴 반복 | |
| 일 오전 | Stage 5 DCF + Stage 9 목적별 제약·레드플래그 (도메인 차별점) | |
| 일 오후 | Stage 8 몬테카를로(기본형) + 풋볼필드 + 최종 워크북 다운로드 | |
| 일 저녁 | 배포(App Runner/Render), README·캡처·ai_dev_log 정리 | 공개 URL + repo |

Stage 6·7과 PDF 리포트는 로드맵으로 README에 남기고, 시간이 남으면 추가.
