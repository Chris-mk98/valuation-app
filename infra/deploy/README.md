# 배포 설정 (placeholder)

AWS App Runner 또는 Render 배포 설정을 여기에 둔다. (후속 작업)

- backend: `uvicorn app.main:app` 컨테이너, `/health` 헬스체크.
- frontend: 정적 빌드(dist) 서빙 + `/api` 프록시.
- 시크릿(DART/ECOS 키)은 배포 플랫폼 시크릿 매니저로 주입한다.
