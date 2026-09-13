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
<!-- BEGIN AWS Agent Toolkit rules -->
# AWS Guidance for the new AWS experience

This user has signed up for the new AWS experience. This experience lets you sign into AWS using a social provider and requires the following additional context.

Where this guidance conflicts with the project's own instructions, the project's instructions take precedence.

## Context

### Terminology:

- Say "project" instead of "account" — a project contains an AWS account and settings for sharing with other collaborators
- Say "team member" instead of "IAM user" — users are invited by email, not created or federated in IAM
- Say "AWS Settings" when referring to management tasks at [settings.aws.com](https://settings.aws.com/) (project management, billing, team members, spend limits). Users view their actual AWS resources in the AWS Management Console.
- Say "selected Region" when referring to the user's Region — not "home Region"
- The user has a managed IAM experience. This includes a managed service control policies (SCP) and resource control policies (RCP) that govern the use of AWS. They will still need to use IAM to create policies to let services work with each other. If there are questions about the SCPs or RCPs, go to the documentation at https://docs.aws.amazon.com/accounts/latest/reference/scps-and-rcps-for-projects.html

### Constraints:

- All projects share a single AWS Region determined by the user's contact address. Resources cannot be created in other Regions
- When developing:
  - MUST create all Regional resources in the project's assigned Region
  - You CAN create AWS WAF and Cloudwatch Logs resources in us-east-1 when there are global resources (like a global WAF instance) that require a connection to dependencies in us-east-1. You should not use these for any other reason, because resources in the selected Region will provide lower cost (due to no cross-Region traffic), increased availability (due to no cross-Region traffic), and easier manageability (due to not needing to look in another Region). When you need to do an inventory of resources, you need to look in both the selected Region and us-east-1 for Cloudwatch Logs or WAF resources.
  - MUST NOT attempt to create Lambda, API Gateway, or other Regional resources in any other Region
  - MUST direct users to confirm their Region in AWS Settings > View all projects > Overview > Additional Info > Region. If the user cannot confirm their Region, check in ~/.aws/config
  - MUST NOT use Lambda@Edge — excluded from both Lambda and CloudFront
  - MUST NOT use CloudFormation StackSets — no multi-account or multi-Region deployments
  - MUST NOT attempt cross-Region actions — no cross-Region replication for DynamoDB/S3/RDS, no multi-Region KMS keys
  - MUST NOT use Route 53 cross-Region routing — geolocation, latency-based, and failover routing policies are not available
  - CloudFront is a global service and its actions ARE allowed in `us-east-1`. A user can create a CloudFront distribution pointing to their project-region Lambda function URL or API Gateway. However, Lambda and API Gateway themselves MUST NOT be created in `us-east-1` — they must be in the project Region.
  - Reduced availability in `eu-north-1` specifically: Amazon Rekognition, Amazon Textract, Amazon Personalize, AWS App Runner are not available in that Region.
- IAM permissions for human access are managed by AWS. Don't assign roles to team members unless absolutely necessary
- The user may have a spend limit if they are on the paid plan. The limit that pauses their project if it's exceeded. If resources suddenly become inaccessible, ask if they have a spend limit configured. Only project owners can modify a spend limit.
- When developing:
  - MUST ask about spend limit status if the user reports sudden "Access Denied" errors on operations that previously worked
  - MUST direct users to check spend status in AWS Settings > Billing
  - MUST check if a user has upgraded their account to the paid plan
  - MUST ask the user if they want to clean up the successfully created resources or keep them to reduce cost
- The user sets up billing, creates spend limits, and retrieves and pays invoices in AWS Settings. The user creates budgets and optimizes their costs in the AWS Billing and Cost Management console
- Not all AWS services are available. If a service isn't working, do the following:
  1. Run the command `aws freetier get-account-plan-state`
  2. If accountPlanType": "FREE", check the [Free Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-free-tier) next,
  3. If accountPlanType": "PAID", check the [Paid Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-paid-plan).
  4. If neither list shows the service, check the [Not supported for this experience list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#unsupported-services). The user will need to activate advanced features to access this service.
- Users can activate advanced AWS services and capabilities for their account.
- Before starting a task, check whether a relevant AWS skill is available. Load the skill with retrieve_skill and prefer its guidance over general knowledge.

### Help level

- help_level (required): LOW, MEDIUM, or HIGH. While a user is building, you MUST ask the user: "How much guidance would you like from me? Low (I only flag security risks), medium (I ask a couple of clarifying questions if something seems off), or high (I explain what I'm doing, suggest alternatives, and flag best practices)."

**Saved: help_level = HIGH** (2026-09-13, 사용자 선택)

You CAN update this rule file to save a user's help_level.

Constraints for each level:

**LOW:**

- MUST follow all constraints in this context file
- MUST execute the user’s request without modification
- MUST NOT ask clarifying questions unless the action would create a security vulnerability
- MUST NOT suggest alternatives or improvements

**MEDIUM:**

- MUST execute the user's request
- MAY ask up to two clarifying questions per task if the request has an ambiguity or a potential issue
- MUST NOT repeat a question or suggestion the user has already dismissed
- MUST NOT explain trade-offs or alternatives unless the user asks

**HIGH:**

- MUST explain what each step does and why before executing it
- MUST suggest alternatives when a better approach exists
- MUST flag best practices and explain trade-offs
- MUST still execute the user's choice if they disagree with a suggestion
<!-- END AWS Agent Toolkit rules -->
