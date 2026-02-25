import json
import os
import boto3
import email
import requests
from email import policy
from email.parser import BytesParser

s3 = boto3.client("s3")

WEBHOOK_URL = os.environ.get("INGEST_WEBHOOK_URL")


def lambda_handler(event, context):
    try:
        # Get S3 bucket + object key from SES trigger
        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        # Download raw email from S3
        response = s3.get_object(Bucket=bucket, Key=key)
        raw_email = response["Body"].read()

        # Parse MIME email
        msg = BytesParser(policy=policy.default).parsebytes(raw_email)

        # Extract recipient (clinic token)
        recipient = msg["To"]

        # Extract audio attachment
        audio_file = None
        audio_filename = None

        for part in msg.iter_attachments():
            content_type = part.get_content_type()
            if content_type.startswith("audio/"):
                audio_file = part.get_content()
                audio_filename = part.get_filename()
                break

        if not audio_file:
            print("No audio attachment found.")
            return {"statusCode": 400, "body": "No audio attachment"}

        # Send to Flask webhook
        files = {
            "file": (audio_filename, audio_file)
        }

        data = {
            "recipient": recipient
        }

        response = requests.post(WEBHOOK_URL, files=files, data=data, timeout=20)

        print("Webhook response:", response.status_code)

        return {
            "statusCode": 200,
            "body": "Processed successfully"
        }

    except Exception as e:
        print("Error:", str(e))
        return {
            "statusCode": 500,
            "body": str(e)
        }