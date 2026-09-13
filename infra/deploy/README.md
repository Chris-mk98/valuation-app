# 배포 — AWS App Runner

이 앱은 **단일 컨테이너**로 배포된다: FastAPI 가 API(`/api`, `/health`)와 빌드된 프론트엔드(정적)를
같은 오리진에서 서빙한다(`infra/deploy/Dockerfile`). App Runner 서비스 1개 = URL 1개.

## 전제
- AWS 계정 + 권한(ECR, App Runner, IAM)
- App Runner ECR 접근 역할 `AppRunnerECRAccessRole` (최초 1회, 콘솔에서 서비스 생성 시 자동 제안됨)
- 리전 예: `ap-northeast-2`(서울)

## 방법 A — GitHub Actions (권장, 로컬 Docker 불필요)

1. 리포 **Settings → Secrets and variables → Actions** 에 시크릿 추가:
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
   - (선택 Variables) `ECR_REPO`(기본 `valuation-app`), `APPRUNNER_SERVICE`(기본 `valuation-app`)
2. **Actions → Deploy (App Runner) → Run workflow** 실행 → 이미지 빌드·ECR 푸시.
3. **최초 1회** App Runner 서비스 생성(콘솔 또는 아래 CLI). `AutoDeploymentsEnabled=true` 로 두면
   이후 워크플로 실행 시 새 이미지가 자동 재배포된다.

## 방법 B — 로컬 스크립트

```bash
aws configure                       # 또는 aws configure sso
export AWS_REGION=ap-northeast-2
bash infra/deploy/deploy-ecr.sh     # ECR 생성 → 빌드 → 푸시 → (서비스 있으면)재배포
```

## 최초 App Runner 서비스 생성 (콘솔 권장)

콘솔 → App Runner → Create service → **Container registry / Amazon ECR** →
이미지 `…/valuation-app:latest` 선택 → **ECR access role** 생성 수락 →
- Port `8000`, Health check path `/health`
- 환경변수 `DART_API_KEY`, `ECOS_API_KEY` 입력
- Auto deployments **ON**
- Instance `1 vCPU / 2 GB` (pandas·scipy·numpy 여유)

또는 CLI: `deploy-ecr.sh` 가 서비스 부재 시 `aws apprunner create-service …` 명령 템플릿을 출력한다.

## 주의
- `.env`(실제 키)는 이미지에 포함되지 않는다(루트 `.dockerignore`). 키는 App Runner 환경변수로 주입.
- SQLite 캐시는 컨테이너 재시작 시 사라진다. 영속이 필요하면 `DATABASE_URL` 을 PostgreSQL(RDS)로 지정.
- App Runner 는 실행 중 과금된다(대략 1 vCPU/2 GB 상시 기준 월 $25 내외). 미사용 시 서비스 일시중지/삭제.
