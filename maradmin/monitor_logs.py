import boto3
import os
import re
from datetime import datetime, timedelta, timezone

# Initialize AWS clients
logs_client = boto3.client('logs')
ses_client = boto3.client('ses')

# Get log group names from environment variables with fallbacks
POLL_LOG_GROUP = os.environ.get('POLL_LOG_GROUP', '/aws/lambda/maradmin-PollFunction-HPDHW6O635NP')
SCRAPER_LOG_GROUP = os.environ.get('SCRAPER_LOG_GROUP', '/aws/lambda/maradmin-ScraperFunction-XXXXXXXX')
EMAIL_SENDER = 'MARADMIN <maradmin@christopherbreen.com>'
EMAIL_RECIPIENT = 'maradmin@christopherbreen.com'

def lambda_handler(event, context):
    # Calculate time range for the past 6 hours (timezone-aware)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=6)

    # Convert to milliseconds
    start_time_ms = int(start_time.timestamp() * 1000)
    end_time_ms = int(end_time.timestamp() * 1000)

    pattern = re.compile(r'\[(WARNING|ERROR)]')

    all_log_events = []

    # Monitor both PollFunction and ScraperFunction log groups
    log_groups = [
        ('PollFunction', POLL_LOG_GROUP),
        ('ScraperFunction', SCRAPER_LOG_GROUP)
    ]

    for function_name, log_group_name in log_groups:
        try:
            log_streams = logs_client.describe_log_streams(
                logGroupName=log_group_name,
                orderBy='LastEventTime',
                descending=True,
                limit=50  # Limit to most recent 50 streams for performance
            )

            for stream in log_streams['logStreams']:
                log_stream_name = stream['logStreamName']

                events = logs_client.get_log_events(
                    logGroupName=log_group_name,
                    logStreamName=log_stream_name,
                    startTime=start_time_ms,
                    endTime=end_time_ms,
                    startFromHead=True
                )

                for event in events['events']:
                    message = event['message']
                    timestamp = datetime.fromtimestamp(event['timestamp'] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                    if pattern.search(message):
                        all_log_events.append(f'[{function_name}] {timestamp} - {message}')

        except Exception as e:
            print(f'[ERROR] Failed to fetch logs from {log_group_name}: {e}')
            all_log_events.append(f'[{function_name}] ERROR: Failed to fetch logs - {e}')

    if all_log_events:
        email_subject = f"6-Hour Log Summary: {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%H:%M')} UTC"
        email_body = "Summary of MARADMIN log entries with [WARNING] or [ERROR]:\n\n"
        email_body += f"Monitoring: PollFunction and ScraperFunction\n"
        email_body += f"Time Range: {start_time.strftime('%Y-%m-%d %H:%M:%S')} to {end_time.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        email_body += f"Total Events: {len(all_log_events)}\n\n"
        email_body += "-" * 80 + "\n\n"
        email_body += "\n".join(all_log_events)

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
        print(f'Email sent successfully: {ses_response["MessageId"]}')
        print(f'Found {len(all_log_events)} warning/error events')
        return {"statusCode": 200, "body": f"Email sent with {len(all_log_events)} events"}
    else:
        print('No warnings or errors found in the logs')
        return {"statusCode": 200, "body": "No warnings or errors found in the logs"}

