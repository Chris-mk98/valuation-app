# AI 개발 로그

Claude Code 작업 기록: 무엇을 시켰고 / 무엇이 문제였고 / 어떻게 고쳤는지. (포트폴리오 증빙)

---

## 2026-09-12 · 1단계 프로젝트 스켈레톤

- **작업**: 설계서(§1) 폴더구조대로 backend(FastAPI, `/health`)·frontend(React+Vite 빈 대시보드)·
  infra(docker-compose)·.github(CI: ruff+pytest+build) 스켈레톤 생성. core/sources/stages/excel/api 등
  패키지 자리 확보, pydantic-settings 설정 로더, SQLAlchemy 세션/Base, VCR conftest 골격, README·ADR 작성.
- **발견된 문제**: 문서 파일명이 CLAUDE.md 참조(`data_flow.md`)와 불일치(`valuation_app_data_flow.md`).
  `.env` 에 DART_API_KEY 누락, ECOS_API_KEY 는 이름 뒤 공백으로 로딩 실패 위험.
- **해결**: 문서를 `docs/data_flow.md` 로 rename(참조 일치). 설정 로더를 키 없이도 기동(경고만)하도록 구현,
  `.env.example` 에 "이름 뒤 공백 금지" 명시. DART 실녹화는 3단계 진입 전 키 확보 후 진행(없으면 합성 카세트).

## 2026-09-12 · 2단계 횡단 관심사 core/

- **작업**: §6 스키마대로 `db/models.py` 에 Lineage·StageStatus + SourceType/StageState enum 추가.
  `core/lineage.py`(record_value/record_override/get_lineage), `core/stage_gate.py`(mark_reviewed/approve/
  invalidate_downstream), `core/rules.py`(목적별 YAML 4종 + review_flags 로더). in-memory SQLite 픽스처로
  단위 테스트 23건 작성 — 오버라이드 사유 누락 예외, 상위 승인 후 하위 DRAFT 전환 포함.
- **발견된 문제**: ruff UP042(str+Enum 다중상속) 경고. `.env` DART 키 여전히 미발급(3단계 영향).
- **해결**: enum.StrEnum(파이썬 3.12)로 전환 + import 정렬 자동수정. ruff 통과, pytest 23 passed(네트워크 무관).
  재오버라이드 시 최초 system_value 보존 로직 추가(감사추적 정확성).

## 2026-09-12 · 3단계 Stage 0~2 수직 슬라이스

- **작업**: sources/dart·ecos(캐시 우선·원본 보존·api_call_log, corpCode 검색), stages/s2_normalize(순수함수,
  손계산 fixture), excel I/O(원본덤프·정규화·매핑표 템플릿/업로드 검증), API 12개(케이스·Stage1 run·Stage2
  review/override/approve·엑셀), React UI(CaseCreate→Stage1→Stage2 오버라이드+StageStepper). VCR 카세트 녹화.
  회계판단 4건(EBIT=공시영업이익, D&A 후보→unmapped, NWC 영업운전자본, 순차입금 현금만 차감)은 사용자 확정.
- **발견된 문제**: 삼성 D&A 개별 라인 부재(주석) → unmapped 필요. 단기차입금 account_id 미사용 → 계정명 매칭.
  인메모리 SQLite 가 FastAPI 스레드풀과 테이블 격리. 한글 파일명이 HTTP 헤더 latin-1 인코딩 실패.
  httpx INFO 로그에 DART 인증키가 URL 로 노출.
- **해결**: 매칭을 account_id 우선+account_nm 폴백으로. StaticPool 로 스레드 간 단일 연결. Content-Disposition
  RFC 5987(filename*). httpx/httpcore 로거 WARNING 으로 키 로그 차단. pytest 43 passed(네트워크 없이),
  ruff 통과. 실계 종단검증: 삼성 매출 258,935,494·EBIT 6,566,976·capex 60,534,167·net_debt −56,394,949
  백만원으로 Stage 2 승인까지 성공. VCR 카세트 키 누출 없음 확인. docker compose config 는 유효하나 이미지
  빌드는 디스크 여유 부족(91% 사용)으로 미실행.

## 2026-09-12 · Stage 3(유사기업) · Stage 4(WACC)

- **작업**: Stage 3 — sources/price.py(FDR/pykrx 상장사 유니버스·주가, 캐시+CSV 폴백), stages/s3_peers.py
  (순수 스크리닝), KRX 업종 프리필터 → DART KSIC 중분류 엄격 확정 → 재무 필터, 포함/제외 사유필수·수동추가·
  엑셀·UI. Stage 4 — params/param_tables.py(다모다란 ERP·국가위험·세율·규모프리미엄 시드), stages/s4_wacc.py
  (순수함수 β OLS·언레버/리레버·CAPM Ke·WACC), run/override(하위 재계산)/approve·빌드업 엑셀·UI. 손계산·
  monkeypatch 테스트 26건 추가(총 69). 도메인 판단 확정: KSIC 중분류, 주간2년/KOSPI, 다모다란 시드, Kd 자동.
- **발견된 문제**: KRX-DESC Sector 대량 NaN(943/2873) → Industry(업종명)로 프리필터 대체. 소형사 연결(CFS)
  미제출 → 별도(OFS) 폴백. 상장일이 DART 부재 → FDR ListingDate 사용. **금융비용(FinanceCosts)≠이자비용**
  으로 삼성 Kd 110% 과대. 인메모리 SQLite NaN 저장.
- **해결**: 위 각각 반영. Kd 를 '이자의 지급'(InterestPaid) 기준으로 교정 → 삼성 Kd 7.34%. 순현금 기업은
  자본구조상 부채가중 0으로 단순화(경고 표시). 실계 검증: 삼성 → LG전자 유사기업 확정, β 1.0(R² 0.31),
  WACC 8.68%(=Ke, 순현금). pytest 69 passed(네트워크 없이), ruff 통과, frontend 빌드 성공.

## 2026-09-12 · Stage 5(수익접근법 DCF)

- **작업**: stages/s5_dcf.py(순수함수: 과거비율 산출·FCFF 예측·고든 TV·EV·주주가치·주당가치), DB DcfAssumption·
  DcfResult, 서비스 run/override(가정 오버라이드→재계산)/approve, 예측가정+FCFF 엑셀, frontend Stage5Review
  (가정표·FCFF 예측·TV비중·오버라이드·승인). 손계산 테스트 10건 추가(총 79). 도메인 확정: D&A/매출 과거평균,
  고든 영구성장률 1.0% 고정, 주주가치=EV−순차입금+비영업자산.
- **발견된 문제**: 삼성 D&A 가 Stage 2 unmapped(주석 항목)라 dna_ratio=0 → CAPEX 17.6% 대비 FCFF 지속 음수
  → EV 음수(−308조). 계산 자체는 정확하나 입력 결손이 결과를 왜곡.
- **해결**: D&A 미입력·EV<0 경고를 리뷰에 추가(오버라이드 유도). 실무 흐름대로 Stage 2 에서 D&A 오버라이드 후
  재실행 → 삼성 EV 170.5조·주주가치 226.9조·주당 38,814원·TV비중 66%(정상). 전체 Stage 0~5 실계 종단 성공.
  pytest 79 passed(네트워크 없이), ruff 통과, frontend 빌드 성공.

## 2026-09-12 · Stage 6(시장접근법)

- **작업**: stages/s6_market.py(순수함수: EV/EBITDA·PER·PBR, IQR 1.5× 이상치 제거, 중앙값 적용),
  DB MarketResult, 서비스 run/override(적용배수→재적용)/approve, 멀티플 엑셀·거래사례 템플릿/업로드 검증,
  frontend Stage6Review(적용가치·유사기업 멀티플 표·배수 오버라이드). 손계산·monkeypatch 테스트 9건(총 88).
  도메인 확정: 3종 멀티플(D&A결손 peer는 EV/EBITDA에서만 제외), IQR+중앙값, 거래사례는 엑셀 업로드만.
- **발견된 문제**: 유사기업(LG전자) D&A 도 unmapped → EBITDA 산출 불가로 EV/EBITDA 표본 0. 확정 유사기업 1개(<5).
- **해결**: Q1대로 D&A결손 peer 는 EV/EBITDA 에서만 제외(PER·PBR 유지)하고 경고로 표면화. 실계: 삼성 PER 28.2·
  PBR 1.65 적용 → 가치범위 437~584조(레드플래그 2건 표시). 전체 Stage 0~6 실계 종단 성공. pytest 88 passed
  (네트워크 없이), ruff 통과, frontend 빌드 성공.

## 2026-09-12 · Stage 7(자산접근법)

- **작업**: stages/s7_asset.py(순수함수: 조정순자산·최대주주 할증), DB AssetAdjustment·AssetResult,
  서비스 run/조정추가·삭제(사유필수)/할증 오버라이드/approve, 조정순자산 엑셀·조정항목 템플릿 업로드(케이스 반영),
  frontend Stage7Review(순자산·조정내역·추가/삭제·할증 수정). 손계산·monkeypatch 테스트 9건(총 97).
  도메인 확정: 순자산=지배주주지분(owners_equity), 상증세법 목적 시 규칙 할증률(20%) 자동적용·오버라이드 가능.
- **발견된 문제**: 특이사항 없음(가벼운 단계).
- **해결**: 실계 삼성 장부순자산 353.2조·투자부동산 조정 후 358.2조·주당 61,276원(실제 BPS 부합). 상증세법
  목적 케이스는 할증 20% 자동 적용(테스트 검증). 전체 Stage 0~7 실계 종단 성공. pytest 97 passed(네트워크
  없이), ruff 통과, frontend 빌드 성공.

## 2026-09-12 · Stage 8(몬테카를로)

- **작업**: stages/s8_montecarlo.py(순수함수: 6변수 정규분포, 촐레스키 상관 반영 난수, N회 DCF 재계산,
  평균·P10/50/90·히스토그램·토네이도, seed 재현성), DB McDistribution·McResult, 서비스 run/σ 오버라이드/approve,
  결과 엑셀, frontend Stage8Review(recharts 히스토그램·토네이도 바·σ 표). 손계산·재현성 테스트 9건(총 106).
  도메인 확정: 6변수, 정규분포(σ 기본제공), 사전정의 상관(성장↔마진 +0.3 등).
- **발견된 문제**: 상관행렬이 PSD 아닐 위험(촐레스키 실패), WACC≤영구성장률 무효 표본 발생 가능.
- **해결**: _psd_cholesky(고유값 클리핑)로 보정, 무효 표본은 스킵·카운트·경고. 실계 삼성 10,000회 0.1초:
  P10 104조·P50 226조(DCF 점추정 227조와 일치)·P90 363조, 토네이도 1위 CAPEX/매출(자본집약 반영).
  pytest 106 passed(네트워크 없이), ruff 통과, frontend 빌드 성공.

## 2026-09-13 · Stage 9(목적별 조정 & 리뷰)

- **작업**: stages/s9_review.py(순수: 목적별 가중종합·순자산 하한·손상검사 병렬·레드플래그 평가),
  sources/ecos 명목GDP 수집(200Y113/10106 연간, CAGR), Stage4에 베타 R²최소 저장(플래그용), DB FinalValue,
  서비스 run/가중치 오버라이드(잠금 목적 거부)/플래그 승인/approve(미승인 플래그 시 차단), 최종요약 엑셀,
  frontend Stage9Review(방법론 가치·가중·레드플래그 배지·승인). 손계산·monkeypatch 테스트 13건(총 119).
  도메인 확정: 시장=범위·중앙값 가중, 손상=사용가치(DCF) vs 공정가치(시장) 병렬, 명목GDP=ECOS, 일반M&A 균등.
- **발견된 문제**: 특이사항 없음(설계 그대로 rules.py 규칙 적용).
- **해결**: 실계 삼성 일반M&A → 수익227·자산353·시장511조 균등가중 최종 363.6조, ECOS 명목GDP 3.71%로 영구
  성장률 플래그 판정, 유사기업<5 발동→승인 후 Stage9 APPROVED. 합병 1.5:1·상증세 3:2 잠금·손상 병렬은
  단위테스트로 검증. pytest 119 passed(네트워크 없이), ruff 통과, frontend 빌드 성공.

## 2026-09-13 · Stage 10(산출물) — 파이프라인 완성

- **작업**: service 집계(football_field/stage10_summary/lineage_rows/export_case_json), reports/report.py
  (한글 안전 HTML 리포트·인라인 풋볼필드), excel full_workbook(10개 시트), api/outputs.py(summary·lineage
  웹/CSV·case JSON·workbook·report). frontend Stage10Summary(풋볼필드 CSS 바·레드플래그 배지·감사추적 표·
  다운로드). 테스트 6건(총 125). 결정(자율·권장안): 리포트는 HTML(브라우저 인쇄→PDF)로 CJK 폰트 의존 회피.
- **발견된 문제**: PDF 직접생성은 reportlab CJK 폰트 자산 필요 → 회피.
- **해결**: HTML 리포트로 한글 안전 확보. 실계 삼성 전체 0→10 종단: 풋볼필드(수익 104~363조·시장 437~584조·
  자산 353조·최종 363.6조), 케이스 JSON 12섹션·lineage 117건, 워크북 10시트, 리포트 4KB. pytest 125 passed
  (네트워크 없이), ruff 통과, frontend 빌드 성공.
- **프로젝트 현황**: Stage 0~10 전 파이프라인 완성. 삼성전자로 케이스 생성→수집→정규화→유사기업→WACC→DCF→
  시장→자산→몬테카를로→목적별 종합→산출물까지 실계 동작. 승인 연쇄·하위 무효화·lineage·오버라이드 사유필수
  ·목적별 규칙·레드플래그 승인 게이트 일관 적용.

## 2026-09-13 · 커밋 정리·GitHub push·CI·README

- **작업**: 스테이지별 11개 커밋으로 정리(스켈레톤/core/Stage0-2~Stage10), master→main 개명, SSH로
  github.com/Chris-mk98/valuation-app push. README 포트폴리오 정비(CI 배지·10스테이지 표·실계 삼성 예시·풋볼필드).
- **발견된 문제**: 한 세션 일괄 구현이라 중간 히스토리 없음 → 공유 프레임워크 파일은 도입 Stage 커밋에 전체 내용 포함.
  CI엔 sources extra(FDR/pykrx) 미설치 — 최상위 import 있으면 실패 위험.
- **해결**: FDR/pykrx는 함수 내 지연 import라 CI 무영향 확인. GitHub Actions backend(ruff+pytest)·frontend(build)
  **모두 success**. README 스텍 중복 잔재 제거. 시크릿·캐시 미커밋(키 히스토리 누출 없음) 확인.

## 2026-09-13 · App Runner 배포 준비

- **작업**: 단일 서비스화(FastAPI가 API+프론트 정적 서빙, FRONTEND_DIST opt-in) + DATA_DIR env 오버라이드.
  결합 Dockerfile(node 빌드→python+정적), 루트 .dockerignore(.env·캐시 제외), GitHub Actions deploy.yml
  (빌드→ECR→App Runner), deploy-ecr.sh, infra/deploy/README(콘솔/CLI 절차·과금 주의).
- **발견된 문제**: 환경에 AWS CLI·자격증명 없음, 디스크 92%(3.9GB)로 로컬 Docker 빌드 위험 → 배포 실행 불가.
- **해결**: 실행 대신 배포 자산 완비. Dockerfile 린트체크 통과, 단일 서비스 로컬 검증(/ UI·/health·/openapi 동시
  응답). pytest 125 통과 유지. 실제 배포는 사용자 AWS 자격증명 필요 — 방법 A(GH Actions 시크릿)·B(로컬 aws
  configure) 안내. 이미지에 .env 미포함(키는 App Runner 환경변수 주입).

## 2026-09-13 · AWS ECS Express Mode 배포 완료

- **작업**: App Runner 신규가입 중단(2026-04-30) 확인 → ECS Express Mode 로 전환. AWS 에이전트 툴킷 설정(AWS
  CLI v2·브라우저 로그인·MCP·스킬 23종·CLAUDE.md 규칙). GitHub Actions Deploy 워크플로로 ECR 푸시. IAM 실행/인프라
  역할(관리형 정책) + 클러스터 생성 → create-express-gateway-service(ALB·SG·오토스케일 자동). 키는 Secrets Manager
  → update-express-gateway-service 로 주입.
- **발견된 문제**: 첫 시크릿 배포가 ROLLBACK_SUCCESSFUL("active alarm") — 초기 배포 안정화 중 RollbackAlarm 전이
  상태 타이밍 이슈(새 태스크는 /health 200 정상). 인프라 관리형 정책 ARN 이 service-role/ 경로.
- **해결**: 알람 OK 안정 후 재배포 → SUCCESSFUL. 라이브 검증: UI·API(54개)·DART 실호출(삼성 케이스 생성 200)
  전부 정상. URL: va-5456fafc704043908262540477e9856a.ecs.ap-northeast-2.on.aws. 이미지에 키 미포함(Secrets Manager).

## 2026-09-13 · 삼성 외 기업 수집·정규화 버그 수정

- **작업**: 사용자 제보 "삼성만 되고 세원물산 등은 수집부터 실패". 근본원인 2건 수정 + 테스트 2건(총 127).
- **발견된 문제**: ① Stage 1 수집이 연결(CFS)만 조회 → 연결 미제출 소형사(세원물산 등)는 전 연도 0행(삼성은
  CFS 있어 우연히 동작). ② 정규화가 `statement:"IS"`를 `sj_div="IS"`로만 매칭 → 매출·영업이익을 포괄손익계산서
  (CIS)에 싣는 소형사는 전부 None.
- **해결**: ① get_financials 에 CFS→OFS 폴백(status 013일 때만, OFS→CFS 역폴백 없음). ② s2_normalize._match
  가 IS 스펙일 때 CIS 도 포함(IS 우선). 검증: 세원물산 매출 1,930억·영업이익 59억·순현금 정상 정규화, 삼성 회귀
  통과. pytest 127 passed, ruff 통과. 재배포는 GitHub Actions Deploy(ECR→Express 자동배포).
- **라이브 반영**: ECS Express 는 :latest 재푸시로 자동배포 안 됨 → 새 digest 로 update-express-gateway-service
  재배포. 라이브 검증: 세원물산 수집 140행·정규화 매출 1,930억 정상.

## 2026-09-13 · 마무리: CLAUDE.md 커밋·데모정리·README 전면 재작성

- **작업**: CLAUDE.md(AWS 툴킷 규칙+help_level) 커밋. 데모 케이스 정리(ECS 태스크 중지→빈 SQLite 재기동).
  README 전면 재작성 — 데이터 흐름(mermaid), 10단계, 기능, 배포환경(AWS 초보자용 용어표·아키텍처), 코드수정·
  배포전략(digest 재배포·롤백 주의), TO-DO(영속화·UI/UX·자동화 등).
- **발견된 문제**: 케이스 삭제 API 부재 → 데모정리 수단 없음. SQLite 휘발성(재시작 시 소실).
- **해결**: 삭제 엔드포인트 추가 대신(YAGNI) 태스크 재시작으로 임시 DB 초기화(이전 검증케이스 404 확인).
  영속화·삭제기능·digest 자동배포를 README TO-DO 에 명시. 오늘 작업 종료.
