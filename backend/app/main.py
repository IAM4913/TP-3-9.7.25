from __future__ import annotations

import io
import json
import time
from typing import List, Optional

import boto3
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import get_settings
from .preview import generate_preview, PreviewResponse, PreviewRequest
from .models import OptimizeRequest, OptimizeResponse
from .optimizer import optimize
from .constants import NO_MULTI_STOP_CUSTOMERS
from fastapi.responses import StreamingResponse
from .exporter import export_trucks_workbook, export_dh_load_list_workbook

settings = get_settings()

app = FastAPI(title="Truck Planner API", version="0.1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip()
                   for o in settings.cors_allowed_origins.split(",")],
    allow_origin_regex=settings.cors_allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Health(BaseModel):
    status: str
    env: str


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok", env=settings.app_env)


@app.get("/db/ping")
def db_ping():
    if not settings.supabase_db_url:
        raise HTTPException(
            status_code=503, detail="SUPABASE_DB_URL not configured")
    try:
        with psycopg.connect(settings.supabase_db_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                _ = cur.fetchone()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class PresignRequest(BaseModel):
    key_prefix: Optional[str] = "uploads/"
    filename: str
    content_type: Optional[str] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    expires_in_seconds: int = 600


@app.post("/upload/presign")
def presign_upload(req: PresignRequest):
    if not settings.aws_s3_bucket_uploads:
        raise HTTPException(
            status_code=503, detail="AWS_S3_BUCKET_UPLOADS not configured")

    s3 = boto3.client("s3", region_name=settings.aws_region)
    # Key format: prefix/timestamp-filename to avoid collisions
    ts = int(time.time())
    key_prefix = req.key_prefix or "uploads/"
    key = f"{key_prefix.rstrip('/')}/{ts}-{req.filename}"

    try:
        params = s3.generate_presigned_post(
            Bucket=settings.aws_s3_bucket_uploads,
            Key=key,
            Fields={"Content-Type": req.content_type},
            Conditions=[["starts-with", "$Content-Type", "application/"]],
            ExpiresIn=req.expires_in_seconds,
        )
        return {"key": key, "presigned": params}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload/preview", response_model=PreviewResponse)
def upload_preview(req: PreviewRequest):
    try:
        return generate_preview(req)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/optimize", response_model=OptimizeResponse)
def optimize_endpoint(req: OptimizeRequest):
    try:
        return optimize(req)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_no_multi_stop_customers = set(name.lower()
                               for name in NO_MULTI_STOP_CUSTOMERS)


@app.get("/no-multi-stop-customers")
def get_no_multi_stop_customers():
    return {"customers": sorted(_no_multi_stop_customers)}


class UpdateCustomersRequest(BaseModel):
    customers: list[str]


@app.post("/no-multi-stop-customers")
def update_no_multi_stop_customers(req: UpdateCustomersRequest):
    global _no_multi_stop_customers
    _no_multi_stop_customers = set(n.strip().lower()
                                   for n in req.customers if n and n.strip())
    return {"ok": True, "count": len(_no_multi_stop_customers)}


class ExportRequest(BaseModel):
    s3_key: str
    sheet_name: Optional[str] = None


@app.post("/export/trucks")
def export_trucks(req: ExportRequest):
    try:
        wb = export_trucks_workbook(req.s3_key, req.sheet_name)
        return StreamingResponse(wb, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": "attachment; filename=truck_optimization_results.xlsx"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/export/dh-load-list")
def export_dh(req: ExportRequest):
    try:
        wb = export_dh_load_list_workbook(req.s3_key, req.sheet_name)
        return StreamingResponse(wb, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": "attachment; filename=dh_load_list.xlsx"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
