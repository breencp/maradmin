# Selenium/Chrome Setup for Lambda

## Summary of Changes

We've fixed the Selenium/WebDriver setup to work with Python 3.13 on Lambda. The old `chrome-aws-lambda` layer is deprecated and doesn't support Python 3.13.

## What Was Fixed

1. **RSS Feed Caching Issue**:
   - Added cache-busting headers to `scraper.py` RSS fetch
   - Now uses same approach as `poll.py` to get fresh data
   - Added debug logging for RSS metadata (pubDate, lastBuildDate)

2. **Chrome/Selenium Setup**:
   - Created `chrome-layer/build-x86.sh` to build a custom Lambda layer
   - Updated `scraper.py` to use correct Chrome paths (`/opt/chrome/chromium`)
   - Added additional Chrome arguments for Lambda environment

## Steps to Complete Setup

### 1. Build the Chrome Layer

```bash
cd chrome-layer
./build-x86.sh
```

This downloads:
- **Chromium v133** from Sparticuz (optimized for Lambda)
- **Chromedriver v133** (matching version)

Output: `chrome-layer.zip` (~100-150 MB)

### 2. Publish Layer to AWS

```bash
aws lambda publish-layer-version \
  --layer-name chromium-selenium-x86 \
  --description 'Chromium and Chromedriver for Selenium on Lambda x86_64' \
  --zip-file fileb://chrome-layer.zip \
  --compatible-runtimes python3.13 python3.12 python3.11 \
  --compatible-architectures x86_64 \
  --region us-east-1
```

**Copy the `LayerVersionArn` from the output!** It looks like:
```
arn:aws:lambda:us-east-1:123456789012:layer:chromium-selenium-x86:1
```

### 3. Update template.yaml

Replace line 81 in `template.yaml` with your layer ARN:

```yaml
Layers:
  - arn:aws:lambda:us-east-1:YOUR_ACCOUNT_ID:layer:chromium-selenium-x86:1
```

### 4. Build and Deploy

```bash
cd ..
sam build --use-container
sam deploy
```

## Verification

After deployment, check CloudWatch logs for the ScraperFunction:

**Success indicators:**
```
[DEBUG] Fetching RSS feed with cache-busting headers from: ...
[DEBUG] RSS feed response status code: 200
[DEBUG] RSS Feed pubDate: Fri, 14 Nov 2025 21:56:01 GMT
Successfully retrieved RSS Feed
NEW: R 141840Z NOV 25MARADMIN 547/25
[DEBUG] Attempting to fetch URL with Selenium (attempt 1/3): https://...
[DEBUG] Successfully fetched page (XXXXX characters)
```

**Failure indicators:**
```
Unable to obtain driver for chrome
```
→ Check that layer ARN is correct in template.yaml

```
Access Denied
```
→ Akamai blocking; already has retry logic with exponential backoff

## Architecture Notes

- **x86_64**: Template specifies this architecture (line 7)
- **Memory**: 2048 MB required for Chrome (line 76)
- **Timeout**: 900 seconds (15 minutes) for scraping (line 75)

## File Locations

- Layer build script: `chrome-layer/build-x86.sh`
- Layer documentation: `chrome-layer/README.md`
- Scraper code: `maradmin/scraper.py`
- SAM template: `template.yaml`

## Troubleshooting

### "Unable to obtain driver for chrome"
- Layer ARN is wrong or not applied
- Check line 81 in template.yaml
- Verify layer exists: `aws lambda list-layer-versions --layer-name chromium-selenium-x86`

### "Access Denied" from Akamai
- Already handled with retry logic
- Function will exit gracefully and retry on next poll (15 min)

### Memory errors
- Increase MemorySize in template.yaml (currently 2048 MB)
- Chrome requires at least 1536 MB, 2048 MB recommended

### Layer too large
- Sparticuz Chromium is optimized (~80-120 MB compressed)
- Lambda limit is 250 MB unzipped, 50 MB zipped
- You should be well under the limit

## References

- [Sparticuz Chromium](https://github.com/Sparticuz/chromium) - Lambda-optimized Chromium
- [Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/) - Chromedriver downloads
- [AWS Lambda Layers](https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html)