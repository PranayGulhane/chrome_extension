import boto3
from botocore.config import Config as BotoConfig
from starlette.concurrency import run_in_threadpool

from core.config import get_settings


def _client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )


async def upload_pdf(key: str, data: bytes) -> None:
    settings = get_settings()

    def _put() -> None:
        _client().put_object(Bucket=settings.r2_bucket_name, Key=key, Body=data, ContentType="application/pdf")

    await run_in_threadpool(_put)


async def download_pdf(key: str) -> bytes:
    settings = get_settings()

    def _get() -> bytes:
        response = _client().get_object(Bucket=settings.r2_bucket_name, Key=key)
        return response["Body"].read()

    return await run_in_threadpool(_get)
