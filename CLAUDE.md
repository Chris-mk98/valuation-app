# Valuation App — 프로젝트 규칙

## 프로젝트 목적
회계법인 가치평가팀의 반복 업무를 자동화하되, 전문가의 판단을 구조화·기록하는 내부 도구.
전체 설계는 docs/data_flow.md 를 따른다. 설계와 충돌하는 구현은 하지 않는다.

## 절대 원칙 (예외 없음)
1. 체크포인트: 모든 Stage는 자동산출 → 검토화면 → 승인 후에만 다음 Stage 진행. core/stage_gate.py 경유.
2. 오버라이드: 시스템이 채운 모든 파생값은 사용자가 덮어쓸 수 있고, 사유 입력 필수. 🌐 원본 데이터는 수정 금지. 덮어쓰기는 반드시 core/lineage.py 의 record_override() 로만 처리.
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