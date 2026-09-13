#!/usr/bin/env bash
# App Runner 배포: ECR 레포 생성(없으면) → 이미지 빌드/푸시 → App Runner 배포.
# 사전: aws CLI 인증(aws configure/SSO), docker.  리포 루트에서 실행: bash infra/deploy/deploy-ecr.sh
set -euo pipefail

AWS_REGION="${AWS_REGION:?AWS_REGION 을 설정하세요 (예: ap-northeast-2)}"
ECR_REPO="${ECR_REPO:-valuation-app}"
SERVICE="${SERVICE:-valuation-app}"
TAG="${TAG:-latest}"

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="${ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE="${REGISTRY}/${ECR_REPO}:${TAG}"

echo "▶ ECR 레포 확인/생성: ${ECR_REPO}"
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$AWS_REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" >/dev/null

echo "▶ ECR 로그인"
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"

echo "▶ 이미지 빌드/푸시: ${IMAGE}"
docker build -f infra/deploy/Dockerfile -t "$IMAGE" .
docker push "$IMAGE"

# 기존 서비스 있으면 재배포, 없으면 안내
ARN="$(aws apprunner list-services --region "$AWS_REGION" \
  --query "ServiceSummaryList[?ServiceName=='${SERVICE}'].ServiceArn" --output text 2>/dev/null || true)"

if [ -n "${ARN}" ] && [ "${ARN}" != "None" ]; then
  echo "▶ App Runner 재배포 트리거: ${ARN}"
  aws apprunner start-deployment --service-arn "$ARN" --region "$AWS_REGION" >/dev/null
  echo "✔ 재배포 시작됨. 상태: aws apprunner describe-service --service-arn $ARN"
else
  cat <<EOF
✔ 이미지 푸시 완료: ${IMAGE}

최초 App Runner 서비스는 콘솔 또는 아래 명령으로 1회 생성하세요
(ECR 접근용 역할 AppRunnerECRAccessRole 필요):

  aws apprunner create-service --region ${AWS_REGION} \\
    --service-name ${SERVICE} \\
    --source-configuration '{
      "ImageRepository": {
        "ImageIdentifier": "${IMAGE}",
        "ImageRepositoryType": "ECR",
        "ImageConfiguration": {
          "Port": "8000",
          "RuntimeEnvironmentVariables": {
            "DART_API_KEY": "<키>",
            "ECOS_API_KEY": "<키>"
          }
        }
      },
      "AutoDeploymentsEnabled": true,
      "AuthenticationConfiguration": {
        "AccessRoleArn": "arn:aws:iam::${ACCOUNT}:role/service-role/AppRunnerECRAccessRole"
      }
    }' \\
    --instance-configuration '{"Cpu":"1 vCPU","Memory":"2 GB"}' \\
    --health-check-configuration '{"Protocol":"HTTP","Path":"/health"}'
EOF
fi
