import os
import boto3
import logging
from botocore.client import Config
from datetime import (
    datetime, 
    timezone, 
    timedelta
)
from src import (
    bucket_name, 
    endpoint_url, 
    access_key_id, 
    secret_access_key
)

def delete_old_files(s3, bucket_name, prefix, threshold_minutes=60):
    objects = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

    if 'Contents' in objects:
        for obj in objects['Contents']:
            last_modified = obj['LastModified']
            age = datetime.now(timezone.utc) - last_modified

            if age > timedelta(minutes=threshold_minutes):
                s3.delete_object(Bucket=bucket_name, Key=obj['Key'])
                logging.info(f"Deleted old file: {obj['Key']}")

def upload(file_path, key):
    s3 = boto3.client('s3',
                      endpoint_url=endpoint_url,
                      aws_access_key_id=access_key_id,
                      aws_secret_access_key=secret_access_key,
                      config=Config(signature_version='s3v4'))

    delete_old_files(s3, bucket_name, key.rsplit('/', 1)[0])

    with open(file_path, 'rb') as file:
        s3.upload_fileobj(file, bucket_name, key)

    logging.info(f"Upload success: {key}")
