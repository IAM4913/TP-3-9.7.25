from __future__ import annotations

import io
from typing import Dict, List, Optional

import boto3
import pandas as pd
from fastapi import HTTPException
from pydantic import BaseModel

from .config import get_settings
from .constants import REQUIRED_COLUMNS
from .utils import map_headers, canonical_rename


class PreviewRequest(BaseModel):
    s3_key: str
    sheet_name: Optional[str] = None
    max_sample_rows: int = 5


class PreviewResponse(BaseModel):
    headers: List[str]
    rowCount: int
    missingRequiredColumns: List[str]
    sample: List[Dict]


def generate_preview(req: PreviewRequest) -> PreviewResponse:
    settings = get_settings()
    if not settings.aws_s3_bucket_uploads:
        raise HTTPException(
            status_code=503, detail="AWS_S3_BUCKET_UPLOADS not configured")

    s3 = boto3.client("s3", region_name=settings.aws_region)
    try:
        obj = s3.get_object(
            Bucket=settings.aws_s3_bucket_uploads, Key=req.s3_key)
        data = obj["Body"].read()
    except Exception as e:
        raise HTTPException(
            status_code=404, detail=f"File not found or not accessible: {e}")

    try:
        excel = pd.ExcelFile(io.BytesIO(data))
        df = excel.parse(req.sheet_name) if req.sheet_name else excel.parse(
            excel.sheet_names[0])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel file: {e}")

    df = canonical_rename(df)
    headers = list(df.columns.astype(str))
    mapping = map_headers(headers)

    missing = [c for c in REQUIRED_COLUMNS if c not in mapping]
    # Per requirements: Planning Whse must exist or fail
    if "Planning Whse" in [m for m in REQUIRED_COLUMNS] and "Planning Whse" not in mapping:
        # Ensure Planning Whse reported as missing
        if "Planning Whse" not in missing:
            missing.append("Planning Whse")

    sample_rows = (
        df.head(req.max_sample_rows).to_dict(orient="records")
        if not df.empty
        else []
    )

    return PreviewResponse(
        headers=headers,
        rowCount=int(len(df)),
        missingRequiredColumns=missing,
        sample=sample_rows,
    )
