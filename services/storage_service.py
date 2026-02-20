import boto3
import os
from uuid import uuid4

# Connect to S3
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)

BUCKET_NAME = os.getenv("S3_BUCKET_NAME")


def upload_file(file_obj):
    """Uploads file object to S3 and returns unique S3 key"""
    unique_name = f"{uuid4()}_{file_obj.filename}"

    s3.upload_fileobj(
        file_obj,
        BUCKET_NAME,
        unique_name,
        ExtraArgs={"ContentType": file_obj.content_type}
    )

    return unique_name


def generate_presigned_url(s3_key):
    """Returns a temporary URL valid for 1 hour"""
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET_NAME, "Key": s3_key},
        ExpiresIn=3600
    )
