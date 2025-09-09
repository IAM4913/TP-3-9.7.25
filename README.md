# Truck Planner – Monorepo

Overview
- Backend: FastAPI service for preview, optimization, and export.
- Frontend: React (Vite + Tailwind) for upload, preview, run optimization, and export.
- Infra: Deploy API on ECS Fargate; Supabase for Postgres.

What’s here now
- Backend with endpoints:
  - GET /health
  - GET /db/ping (Supabase connection test)
  - POST /upload/presign (S3 pre-signed upload URL)
  - POST /upload/preview (reads uploaded Excel from S3)
  - POST /optimize (implements PRD packing rules)
  - POST /export/trucks and /export/dh-load-list (basic formatting)
- Frontend app in `frontend/` wired to API (configurable base URL)
- Dockerfile for backend; GitHub Actions for backend and frontend deploy

Quickstart (Windows PowerShell)
- Backend
  - cd backend
  - py -3.11 -m venv .venv; .\.venv\Scripts\Activate.ps1
  - pip install -r requirements.txt
  - copy .env.example .env (fill AWS and DB values)
  - $env:PYTHONPATH = "${PWD}"; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
- Frontend
  - cd frontend
  - npm i
  - npm run dev

Environment variables (backend)
- APP_ENV=local|dev|prod
- CORS_ALLOWED_ORIGINS=http://localhost:5173
- AWS_REGION=us-east-2
- AWS_S3_BUCKET_UPLOADS=your-uploads-bucket
- AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (local only)
- SUPABASE_DB_URL=postgresql://user:pass@host:5432/db?sslmode=require

Deploy
- See `DEPLOY_AWS.md` for AWS + CI/CD.
- Frontend can be hosted on Vercel temporarily; set `VITE_API_URL` to your API.

Notes
- S3 pre-sign supports direct browser uploads; add bucket CORS (see DEPLOY_AWS.md).
- Optimizer targets 98% weight per truck, respects TX weight limits, piece-only splits, and Late/NearDue under-min allowances.
