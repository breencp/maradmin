import json
import xml.etree.ElementTree as ET
import re
import boto3
import os
import time
from openai import OpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

from boto3.dynamodb.conditions import Key

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException


# from maradmin_globals import publish_error_sns

# Cache the API key at module level to avoid repeated SSM calls
_openai_api_key = None

def get_openai_api_key():
    """Fetch OpenAI API key from SSM Parameter Store with caching"""
    global _openai_api_key

    if _openai_api_key is None:
        # Check if running locally (for testing)
        if os.environ.get('AWS_EXECUTION_ENV') is None:
            # Running locally, try to get from environment variable
            _openai_api_key = os.environ.get('OPENAI_API_KEY')
            if not _openai_api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set for local testing")
        else:
            # Running in Lambda, fetch from SSM
            ssm = boto3.client('ssm')
            param_name = os.environ.get('OPENAI_API_KEY_PARAM', '/maradmin/openai-api-key')

            try:
                response = ssm.get_parameter(Name=param_name, WithDecryption=True)
                _openai_api_key = response['Parameter']['Value']
            except Exception as e:
                print(f"Error fetching API key from SSM: {e}")
                raise

    return _openai_api_key


def fetch_rss_feed(url):
    """
    Fetch RSS feed with cache-busting headers to avoid stale cached data.
    Uses the same approach as poll.py to ensure fresh data.

    Args:
        url: RSS feed URL

    Returns:
        Response text (XML string)

    Raises:
        requests.exceptions.HTTPError: For HTTP errors
        requests.exceptions.RequestException: For other request errors
    """
    session = requests.Session()
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9,ja;q=0.8',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://www.marines.mil/News/Messages/MARADMINS/',
        'sec-ch-ua': '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
    }
    session.headers.update(headers)

    print(f'[DEBUG] Fetching RSS feed with cache-busting headers from: {url}')
    response = session.get(url, timeout=600)  # 10 minute timeout
    print(f'[DEBUG] RSS feed response status code: {response.status_code}')

    # Log cache-related response headers
    cache_headers = ['Cache-Control', 'Age', 'X-Cache', 'CF-Cache-Status', 'Expires', 'Last-Modified', 'ETag']
    for header in cache_headers:
        if header in response.headers:
            print(f'[DEBUG] Response header {header}: {response.headers[header]}')

    response.raise_for_status()

    return response.text


def lambda_handler(event, context):
    url = f'https://www.marines.mil/DesktopModules/ArticleCS/RSS.ashx?ContentType=6&Site=481&max=20&category=14336'

    # Fetch RSS feed with cache-busting headers to avoid stale data
    try:
        response = fetch_rss_feed(url)
    except requests.exceptions.HTTPError as err:
        if err.response and err.response.status_code == 403:
            # received 403 forbidden, we are being throttled
            print('[WARNING] Received HTTP 403 Forbidden Error fetching RSS feed.')
            return {"statusCode": 500}
        else:
            raise
    except requests.exceptions.RequestException as err:
        print(f'[WARNING] Request error fetching RSS feed: {err}')
        return {"statusCode": 500}
    except Exception:
        raise
    else:
        try:
            root = ET.fromstring(response)
            print('Successfully retrieved RSS Feed')

            # Log RSS feed metadata for debugging cache issues
            channel = root[0]
            pub_date = None
            last_build_date = None

            for elem in channel:
                if elem.tag == 'pubDate':
                    pub_date = elem.text
                elif elem.tag == 'lastBuildDate':
                    last_build_date = elem.text

            print(f'[DEBUG] RSS Feed pubDate: {pub_date}')
            print(f'[DEBUG] RSS Feed lastBuildDate: {last_build_date}')

        except ET.ParseError:
            print('ParseError: ' + response)
            raise

        # iterate in reverse to ensure errors (particularly 403) mid-way do not prevent poll from instantiating scraper
        # at the next interval.
        for child in reversed(root[0]):
            if child.tag == 'item':
                item = {
                    'desc': re.sub(r'<.*?>', '', str.strip(child[2].text)),
                    'pub_date': child[3].text,
                    'link': child[1].text,
                    'title': child[0].text
                }

                if item['desc']:
                    # check to see if msg already exists (via description as it includes DTG and MARADMIN #, therefore ensuring uniqueness)
                    # title's have a much higher probability of being duplicated at some point
                    db = boto3.resource('dynamodb')
                    maradmin_table = db.Table(os.environ['MARADMIN_TABLE_NAME'])
                    rs = maradmin_table.query(
                        Select='COUNT',
                        KeyConditionExpression=Key('desc').eq(item['desc'])
                    )
                    if rs['Count'] == 0:  # or debug:
                        print('NEW: ' + item['desc'])
                        print('Fetching: ' + item['link'])
                        # message is new, get contents and broadcast
                        try:
                            full_body = fetch_page_with_curl_headers(item['link'])
                            start = full_body.find('<div class="body-text">')
                            end = full_body.find('</div>', start)
                            body = full_body[start + len('<div class="body-text">'):end]
                            # body is HTML portion of the page trimmed down to just the MARADMIN itself.

                            try:
                                bluf = generate_bluf(body)
                            except Exception as e:
                                print(f'[ERROR] Failed to generate BLUF for {item["link"]}: {type(e).__name__} - {e}')
                                bluf = '<p>BLUF: Unable to generate summary.</p>'

                            try:
                                publish_sns(item, bluf, body)
                            except Exception as e:
                                print(f'[ERROR] Failed to publish to SNS for {item["link"]}: {type(e).__name__} - {e}')
                                raise

                            try:
                                maradmin_table.put_item(Item=item)
                            except Exception as e:
                                print(f'[ERROR] Failed to save to DynamoDB for {item["link"]}: {type(e).__name__} - {e}')
                                raise
                        except requests.exceptions.HTTPError as e:
                            # HTTPError from fetch - check if 403
                            if hasattr(e, 'response') and e.response and e.response.status_code == 403:
                                print(f'[WARNING] Unable to fetch MARADMIN {item["desc"]} due to 403 after retries')
                                print(f'[WARNING] Will retry on next poll cycle (every 15 minutes)')
                                # Exit gracefully - return success so no alarms are triggered
                                return {"statusCode": 200}
                            else:
                                # Other HTTP errors should still raise
                                raise
                    else:
                        print('EXISTING: ' + item['desc'])
                else:
                    print('[WARNING] Empty description encountered, skipping this item.')
        return {"statusCode": 200}


def publish_sns(item, bluf, body):
    sns_topic = os.environ['SNS_TOPIC']
    sns = boto3.client('sns')
    title = constrain_sub(item['title'])
    link = item['link']
    text_msg = f'{title} {link}'
    base_message = {
        'default': title,
        'lambda': '',
        'sms': text_msg[:1600]  # max 1,600 characters
    }

    max_bytes = 262144  # 256 KB
    footer     = f'...<br />Message Truncated.  Visit {link} to read the entire message.'
    footer_b   = footer.encode('utf-8')

    # ---- build full MARADMIN once ----
    maradmin_b = (bluf + body).encode('utf-8', errors='replace')

    # ---- first attempt: no truncation ----
    base_message['lambda'] = maradmin_b.decode('utf-8', errors='ignore')
    message_b = json.dumps(base_message).encode('utf-8', errors='replace')

    if len(message_b) > max_bytes:
        # bytes we must shed from the body to fit the limit *including* footer
        overshoot   = len(message_b) - max_bytes
        keep_bytes  = max(0, len(maradmin_b) - overshoot - len(footer_b))
        truncated_b = maradmin_b[:keep_bytes]

        base_message['lambda'] = truncated_b.decode('utf-8', errors='ignore') + footer

        # --- one safety recompute in case JSON escaping changes length ---
        message_b = json.dumps(base_message).encode('utf-8', errors='replace')
        if len(message_b) > max_bytes:
            extra       = len(message_b) - max_bytes
            keep_bytes  = max(0, keep_bytes - extra)
            truncated_b = maradmin_b[:keep_bytes]
            base_message['lambda'] = truncated_b.decode('utf-8', errors='ignore') + footer
            message_b = json.dumps(base_message).encode('utf-8', errors='replace')

    # ---- publish or debug ----
    # if 'debug' in globals() and debug:
    #     print(f'[DEBUG] Final SNS size {len(message_b)} B (limit {max_bytes})')
    #     return

    response = sns.publish(
        TopicArn=sns_topic,
        Message=message_b.decode('utf-8'),
        Subject=title,
        MessageStructure='json'
    )
    print(f'Published {title} to SNS, Response:{response}')
    return response


def constrain_sub(orig_title):
    # SNS.Publish.Subject must be ASCII text that begins with a letter, number, or punctuation mark;
    # must not include line breaks or control characters; and must be less than 100 chars long
    regex = r'[^\x20-\x7F]'
    subst = ''
    title = re.sub(regex, subst, orig_title)
    if title:
        if not 32 < ord(title[0]) < 127:
            title = 'MARADMIN: ' + title
        return title[0:99]
    else:
        return 'A new MARADMIN has been published'


def fetch_page_with_curl_headers(link, rate_limit_delay=2.0):
    """
    Fetch a page, first trying requests with browser-like headers, then falling back to Selenium if blocked.
    Site uses Akamai CDN which may block requests that don't look like real browsers.

    Args:
        link: URL to fetch
        rate_limit_delay: Delay in seconds before first request to avoid rate limiting (default: 2.0)

    Returns:
        Response text with '(slash)' replaced by '/'

    Raises:
        requests.exceptions.HTTPError: For non-transient HTTP errors (including 403 after both attempts)
        TimeoutException: If Selenium fallback times out
        WebDriverException: For browser-related errors in Selenium fallback
    """
    # Add delay to avoid Akamai rate limiting on rapid successive requests
    if rate_limit_delay > 0:
        time.sleep(rate_limit_delay)

    # First attempt: Use requests with browser-like headers
    print(f'[DEBUG] Attempting to fetch with requests library: {link}')
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
            'Sec-Fetch-Dest': 'document'
        }
        response = requests.get(link, headers=headers, timeout=30)

        # Check if we got blocked
        if response.status_code == 403 or 'Access Denied' in response.text:
            print(f'[DEBUG] Requests blocked (status {response.status_code}), falling back to Selenium')
        else:
            response.raise_for_status()
            print(f'[DEBUG] Successfully fetched with requests ({len(response.text)} characters)')
            return response.text.replace('(slash)', '/')
    except Exception as e:
        print(f'[DEBUG] Requests failed: {type(e).__name__} - {e}, falling back to Selenium')

    # Second attempt: Use Selenium with headless Chrome (single attempt)
    print(f'[DEBUG] Attempting to fetch with Selenium: {link}')
    driver = None
    try:

            # Set up Chrome options for headless browsing
            chrome_options = Options()
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)

            # In Lambda, use the Chrome binary from the layer
            if os.environ.get('AWS_EXECUTION_ENV'):
                # Chrome for Testing layer paths for x86_64
                # LD_LIBRARY_PATH is set in template.yaml to include /opt/lib for NSS/X11 libraries
                chrome_options.binary_location = '/opt/chrome/chrome'
                chrome_options.add_argument('--single-process')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--window-size=1920,1080')
                chrome_options.add_argument('--disable-software-rasterizer')
                chrome_options.add_argument('--disable-setuid-sandbox')
                chrome_options.add_argument('--disable-dev-tools')
                chrome_options.add_argument('--no-zygote')
                chrome_options.add_argument('--disable-extensions')

                # Debug: Check if files exist in layer
                print(f'[DEBUG] /opt contents: {os.listdir("/opt") if os.path.exists("/opt") else "NOT FOUND"}')
                if os.path.exists('/opt/chrome'):
                    print(f'[DEBUG] /opt/chrome contents: {os.listdir("/opt/chrome")}')
                if os.path.exists('/opt/chromedriver'):
                    print(f'[DEBUG] /opt/chromedriver contents: {os.listdir("/opt/chromedriver")}')

                # Check chromedriver dependencies
                import subprocess
                try:
                    result = subprocess.run(['ldd', '/opt/chromedriver/chromedriver'],
                                          capture_output=True, text=True, timeout=5)
                    print(f'[DEBUG] chromedriver dependencies:\n{result.stdout}')
                except Exception as e:
                    print(f'[DEBUG] Could not check chromedriver dependencies: {e}')

                # Use chromedriver from the layer
                service = Service(executable_path='/opt/chromedriver/chromedriver')
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                # Running locally, let Selenium find chromedriver automatically
                # Make sure chromedriver is installed and in PATH
                driver = webdriver.Chrome(options=chrome_options)

            # Mask automation detection
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
            })
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # Navigate to page
            driver.get(link)

            # Wait for page to load (Akamai JS challenges need time)
            time.sleep(5)

            # Get page source
            page_source = driver.page_source

            # Check if we got blocked
            if 'Access Denied' in page_source:
                print(f'[ERROR] Access Denied page received from Selenium for URL {link}')
                error = requests.exceptions.HTTPError(f'403 Client Error: Forbidden for url: {link}')
                # Create a mock response object
                class MockResponse:
                    status_code = 403
                error.response = MockResponse()
                raise error

            print(f'[DEBUG] Successfully fetched page with Selenium ({len(page_source)} characters)')
            return page_source.replace('(slash)', '/')

    except TimeoutException as e:
        print(f'[ERROR] Browser timeout for URL: {link}')
        raise

    except WebDriverException as e:
        print(f'[ERROR] WebDriver error for URL {link}: {e}')
        raise

    except Exception as e:
        print(f'[ERROR] Unexpected error fetching URL {link}: {type(e).__name__} - {e}')
        raise

    finally:
        # Always close the browser
        if driver:
            try:
                driver.quit()
            except:
                pass


def generate_bluf(body):
    print(f'[DEBUG] Calling LLM for BLUF')
    # Extract the BLUF from the body
    system_prompt = (
        "Provide a short, military style BLUF summary of this MARADMIN. It should be one paragraph max, plain text with no headers or formatting. "
        "Prefix your response with 'BLUF: ', and get right to the point, i.e. do not include statements like 'This MARADMIN is about...'. "
        "If you find what appears to be military units, MCCs, UICs, etc., include an alphabetical list in the summary on a single line, "
        "comma seperated, but omit this line entirely if it's not relevant to the MARADMIN. Note that MCC and UIC are three digits. "
        "If it's four digits, it's likely an MOS.")
    
    # Get API key from SSM Parameter Store
    api_key = get_openai_api_key()
    client = OpenAI(api_key=api_key)

    completion = client.chat.completions.create(
        model="gpt-5",
        messages=[
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionUserMessageParam(role="user", content=body)
        ]
    )

    response = completion.choices[0].message.content
    print(f'[DEBUG] LLM returned BLUF')
    return '<p>' + response + '</p>'


if __name__ == '__main__':
    # For local testing
    event = {}
    context = None
    # debug = True
    lambda_handler(event, context)
