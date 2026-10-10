"""Assets (images, audio, rapports PDF) stockés dans le S3 local (RustFS)."""

import asyncio
import uuid

import boto3
from botocore.config import Config

from agence import db
from agence.config import settings


def _s3():
    s = settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
    )


async def save_asset(
    client_id: str, run_id: str | None, kind: str, data: bytes, ext: str, content_type: str, prompt: str | None = None
) -> dict:
    key = f"{client_id}/{run_id or 'manual'}/{kind}-{uuid.uuid4().hex[:10]}.{ext}"
    await asyncio.to_thread(
        _s3().put_object, Bucket=settings().s3_bucket_assets, Key=key, Body=data, ContentType=content_type
    )
    row = await db.fetchone(
        "INSERT INTO assets (client_id, run_id, kind, key, prompt) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        client_id,
        run_id,
        kind,
        key,
        prompt,
    )
    return {"id": row["id"], "kind": kind, "key": key}


def presigned_url(key: str, expires: int = 3600) -> str:
    return _s3().generate_presigned_url(
        "get_object", Params={"Bucket": settings().s3_bucket_assets, "Key": key}, ExpiresIn=expires
    )


async def read_asset(key: str) -> bytes:
    obj = await asyncio.to_thread(_s3().get_object, Bucket=settings().s3_bucket_assets, Key=key)
    return obj["Body"].read()
