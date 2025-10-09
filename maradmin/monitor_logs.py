import boto3
# import os
import re
from datetime import datetime, timedelta, timezone

# Initialize AWS clients
logs_client = boto3.client('logs')
ses_client = boto3.client('ses')

LOG_GROUP_NAME = '/aws/lambda/maradmin-PollFunction-HPDHW6O635NP'
EMAIL_SENDER = 'MARADMIN <maradmin@christopherbreen.com>'
EMAIL_RECIPIENT = 'maradmin@christopherbreen.com'

def lambda_handler(event, context):
    # Calculate time range for the past day (timezone-aware)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=6)

    # Convert to milliseconds
    start_time_ms = int(start_time.timestamp() * 1000)
    end_time_ms = int(end_time.timestamp() * 1000)

    log_streams = logs_client.describe_log_streams(
        logGroupName=LOG_GROUP_NAME,
        orderBy='LastEventTime',
        descending=True
    )

    pattern = re.compile(r'\[(WARNING|ERROR)]')

    log_events = []
    for stream in log_streams['logStreams']:
        log_stream_name = stream['logStreamName']

        events = logs_client.get_log_events(
            logGroupName=LOG_GROUP_NAME,
            logStreamName=log_stream_name,
            startTime=start_time_ms,
            endTime=end_time_ms,
            startFromHead=True
        )

        for event in events['events']:
            message = event['message']
            timestamp = datetime.fromtimestamp(event['timestamp'] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            if pattern.search(message):
                log_events.append(f'{timestamp} - {message}')

    if log_events:
        email_subject = f"Daily Log Summary for {start_time.date()} - {start_time.time()} to {end_time.time()}"
        email_body = "Summary of MARADMIN Poll function log entries with [WARNING] or [ERROR]:\n\n"
        email_body += "\n".join(log_events)

        ses_response = ses_client.send_email(
            Source=EMAIL_SENDER,
            Destination={
                'ToAddresses': [EMAIL_RECIPIENT]
            },
            Message={
                'Subject': {
                    'Data': email_subject
                },
                'Body': {
                    'Text': {
                        'Data': email_body
                    }
                }
            }
        )
        print(f'{ses_response}')
        return {"statusCode": 200, "body": "Email sent successfully"}
    else:
        return {"statusCode": 200, "body": "No warnings or errors found in the logs"}

