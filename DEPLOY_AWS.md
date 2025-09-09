# Deploying Truck Planner to AWS + Supabase

This guide sets up:
- Backend API on ECS Fargate behind an Application Load Balancer (ALB)
- Frontend on S3 + CloudFront
- ECR for container images, GitHub Actions for CI/CD
- S3 uploads bucket for direct-to-S3 browser uploads
- Supabase Postgres connection via environment variables

## Prerequisites
- AWS account with permissions to create ECS/ECR/ALB/S3/CloudFront/IAM
- Supabase project and connection string (sslmode=require)
- GitHub repository for CI/CD (optional but recommended)

## 1) Core AWS resources
1. ECR
   - Create repository: e.g., `truck-planner-api`
2. VPC and networking
   - Two public subnets (for ALB) and two private subnets (for ECS tasks)
   - NAT Gateway for egress from private subnets
3. ECS (Fargate)
   - Create a cluster (Fargate)
4. Load Balancer
   - Create an ALB across public subnets
   - Target group: IP target type, port 8080, HTTP health check `/health`
   - Listeners: 80 → redirect to 443; 443 → forward to target group (needs ACM cert)
5. IAM roles
   - Task execution role with `AmazonECSTaskExecutionRolePolicy`
   - Task role with S3 access to the uploads bucket (GetObject for preview; backend does not need PutObject)
6. S3 buckets
   - Web bucket (for static site) — use CloudFront Origin Access Control (OAC) instead of public access
   - Uploads bucket for presigned POST uploads
     - Lifecycle: delete objects older than 14 days
     - CORS (example below)
7. CloudFront
   - Distribution pointing to the web bucket via OAC
   - Default root: `index.html`

### Example CORS for uploads bucket
Apply to the uploads bucket (adjust origins):

```
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["POST", "GET"],
    "AllowedOrigins": [
      "https://your-frontend-domain",
      "http://localhost:5173"
    ],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3000
  }
]
```

## 2) ECS task definition
- Container port: 8080
- CPU/Memory: start with 1 vCPU / 2–4 GB RAM
- Desired count: 2 tasks
- Environment variables:
  - APP_ENV=prod
  - CORS_ALLOWED_ORIGINS=https://your-frontend-domain
  - AWS_REGION=us-east-2 (or your chosen region)
  - AWS_S3_BUCKET_UPLOADS=your-uploads-bucket
  - SUPABASE_DB_URL=postgresql://...sslmode=require

## 3) CI/CD (GitHub Actions)
Set repository secrets (Settings → Secrets and variables → Actions):
- AWS_GITHUB_ROLE_ARN — OIDC role ARN allowing ECR/ECS/S3/CloudFront
- AWS_REGION — e.g., `us-east-2`
- ECR_REPOSITORY — `truck-planner-api`
- ECS_CLUSTER_NAME — your cluster name
- ECS_SERVICE_NAME — your ECS service name
- ECS_CONTAINER_NAME — container name in the task def (e.g., `api`)
- ECS_TASK_DEFINITION_JSON — the JSON for your task definition (export from console)
- WEB_BUCKET — your web S3 bucket
- CF_DISTRIBUTION_ID — CloudFront distribution ID for the frontend

If you don’t have workflow files yet, ask the assistant to add backend (ECR/ECS) and frontend (S3/CloudFront) workflows.

## 4) Frontend configuration
- In production, point the frontend to your API base URL (e.g., `https://api.example.com`).
- For local dev, the Vite proxy is fine; it’s not used in production builds.

## 5) Supabase
- Use a US region close to your AWS region for lower latency.
- Ensure the connection string uses SSL: `sslmode=require`.
- If your VPC has no public egress, ensure NAT is configured so the API can reach Supabase.

## 6) First deploy checklist
- Backend image built and pushed to ECR (via CI)
- ECS service updated to new task definition
- Frontend built and synced to S3 (via CI), CloudFront invalidated
- Validate:
  - API: `GET /health` on your ALB/Domain returns `{ "status": "ok" }`
  - Frontend: Upload sample, see preview, run optimize successfully

## 7) Troubleshooting
- Presign or preview errors:
  - Verify `AWS_S3_BUCKET_UPLOADS`, task role S3 permissions, and bucket CORS
  - Check ALB target health and ECS task logs (CloudWatch)
- Database connectivity:
  - Confirm `SUPABASE_DB_URL` and NAT egress
- S3 403 on browser upload:
  - Ensure form uses presigned POST `url` and `fields` exactly; confirm AllowedOrigins in CORS include your frontend domain
