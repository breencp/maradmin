# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MARADMIN is a serverless AWS application that scrapes Marine Corps Administrative Messages (MARADMINs) from the official USMC website, generates AI-powered summaries, and delivers them to subscribers via email.

## Architecture

The application follows an event-driven architecture using AWS Lambda, SNS, SQS, DynamoDB, and SES:

1. **Poll Function** (`poll.py`) - Checks the USMC RSS feed for new MARADMINs every N hours
2. **Scraper Function** (`scraper.py`) - Invoked by poll when new content is detected; fetches full MARADMIN content, generates BLUF summaries using OpenAI GPT-5, and publishes to SNS
3. **SNS → SQS Fan-out** (`sns_to_sqs.py`) - Triggered by SNS; queries all verified subscribers and enqueues individual messages to SQS
4. **SQS → SES Delivery** (`sqs_to_ses.py`) - Processes SQS messages and sends templated emails via SES
5. **Registration API** (`register.py`, `registered.py`, `verify.py`) - API Gateway endpoints for subscriber management
6. **Error Handling** (`dlq_to_s3.py`, `monitor_logs.py`) - Dead letter queue processing and CloudWatch log monitoring

### Data Flow
```
USMC RSS Feed → PollFunction → ScraperFunction → SNS Topic
                                                      ↓
                                            SnsToSqsFunction → SQS Queue → SqsToSesFunction → SES
```

### DynamoDB Tables

- **MaradminTable** - Stores published MARADMINs
  - Primary Key: `desc` (description with DTG and MARADMIN number)
  - GSI: `PubDateIndex` on `pub_date`

- **SubscriberTable** - Stores email subscribers
  - Primary Key: `email`
  - GSI: `VerifiedIndex` on `verified` status

## Development Commands

### Build and Deploy
```bash
# Build application (uses container to match Lambda environment)
sam build --use-container

# Deploy to AWS (first time - will prompt for configuration)
sam deploy --guided

# Deploy subsequent changes (uses samconfig.toml)
sam deploy
```

### Local Testing
```bash
# Invoke a specific function locally with test event
sam local invoke ScraperFunction --event events/event_scraper.json
sam local invoke PollFunction --event events/poll_event.json
sam local invoke RegisterFunction --event events/event_registered.json

# Start local API Gateway (API endpoints only)
sam local start-api
curl http://localhost:3000/register
```

### Testing
```bash
# Install test dependencies
pip install pytest pytest-mock

# Run unit tests
python -m pytest tests/ -v
```

### Logs
```bash
# Tail logs for a specific function
sam logs -n ScraperFunction --stack-name maradmin --tail
sam logs -n PollFunction --stack-name maradmin --tail
```

## Key Implementation Details

### OpenAI Integration
- API key stored in AWS SSM Parameter Store at `/maradmin/openai-api-key` (encrypted)
- Module-level caching in `scraper.py` prevents redundant SSM calls
- Uses GPT-5 model for BLUF (Bottom Line Up Front) generation
- System prompt optimized for military-style summaries including unit identification (MCCs, UICs, MOSs)

### Web Scraping Strategy
- Custom headers mimic browser requests to avoid 403 errors
- Implements retry logic with exponential backoff
- Processes RSS items in reverse order to handle mid-execution failures gracefully
- Replaces "(slash)" artifacts in HTML content

### SNS Message Size Limits
- SNS has 256 KB message limit
- `publish_sns()` in `scraper.py` implements truncation logic with footer when needed
- Preserves BLUF summary and truncates body content only

### Error Handling
- Dead Letter Queue (DLQ) for failed messages
- Errors topic (SNS) for critical failures
- Commented-out `publish_error_sns()` calls in production code
- Graceful degradation: BLUF generation failures don't block publication

### Email Delivery
- Uses SES templated emails (template: `MaradminTemplate`)
- Configuration set: `maradmin`
- Batch size of 1 for SQS processing to ensure individual delivery tracking
- Dead letter queue with max receive count of 5

## Important Configuration

- **Runtime**: Python 3.13
- **Scraper Timeout**: 900 seconds (15 minutes) - extended for OpenAI API calls
- **Stack Name**: `maradmin` (in samconfig.toml)
- **Region**: us-east-1
- **IAM**: Requires CAPABILITY_IAM for role creation

## Testing Notes

- Test events in `events/` directory for local invocation
- `Developer` key in SNS events limits email delivery to developer only (prevents mass emails during testing)
- Local scraper testing requires `OPENAI_API_KEY` environment variable