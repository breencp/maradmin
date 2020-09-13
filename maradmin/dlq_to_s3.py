import boto3
import os
import json
import uuid


def lambda_handler(event, context):
    s3 = boto3.client('s3')
    response = s3.put_object(
        Bucket=os.environ['DlqBucket'],
        Body=json.dumps(event),
        Key=f'DLQ {uuid.uuid4()}.json'
    )
    print(response)
    return {"statusCode": 200}
