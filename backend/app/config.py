from __future__ import annotations

import os
from functools import lru_cache
from pydantic import BaseModel, AnyHttpUrl
from dotenv import load_dotenv

# Load .env for local development
load_dotenv()


class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "local")
    cors_allowed_origins: str = os.getenv("CORS_ALLOWED_ORIGINS", "*")
    # Optional regex to allow wildcard subdomains (e.g., *.vercel.app)
    cors_allowed_origin_regex: str | None = os.getenv("CORS_ALLOWED_ORIGIN_REGEX")

    # AWS / S3
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    aws_s3_bucket_uploads: str | None = os.getenv("AWS_S3_BUCKET_UPLOADS")

    # Supabase Postgres
    supabase_db_url: str | None = os.getenv("SUPABASE_DB_URL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
