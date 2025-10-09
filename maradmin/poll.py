import json
import xml.etree.ElementTree as ET
import boto3
import os
import requests
from boto3.dynamodb.conditions import Key
# from maradmin_globals import publish_error_sns


def lambda_handler(event, context):
    """
    We use publish_error_sns when previously identified issues occur trying to scrape the website.
    We raise the error for all other exceptions.

    :param event:
    :param context:
    :return: Status code 200 or 500.
    """

    url = 'https://www.marines.mil/DesktopModules/ArticleCS/RSS.ashx?ContentType=6&Site=481&max=1&category=14336'
    retries = 1
    try:
        response = fetch_url_with_retry(url, retries=retries)
        if response is None:
            # printing and publish_error_sns takes place inside fetch_url_with_retry
            return {"statusCode": 500}

        status_code = response.status_code
        headers = response.headers
        msg = response.text
        if not msg:
            print(f"[ERROR] Response body is empty. HTTP Status Code: {status_code}. Headers: {headers}")
            # publish_error_sns('MARADMIN Poll response had empty message body', f'HTTP Status Code: {status_code}. Headers: {headers}')
            return {"statusCode": 500}
        try:
            root = ET.fromstring(msg)
        except ET.ParseError:
            try:
                print(f'ParseError: response.headers:{json.dumps(dict(response.headers))} msg:{str(msg)}')
            except TypeError:
                print(f'ParseError: response.headers:{dict(response.headers)} msg:{str(msg)}')
            finally:
                raise

        latest_pub = root[0][4].text
        print(f'{latest_pub} is latest publication on server.')

        db = boto3.resource('dynamodb')
        maradmin_table = db.Table(os.environ['MARADMIN_TABLE_NAME'])
        query_kwargs = {
            'IndexName': 'PubDateIndex',
            'KeyConditionExpression': Key('pub_date').eq(latest_pub)
        }
        rs = maradmin_table.query(**query_kwargs)
        if rs['Count'] == 0:
            # MARADMIN website has newer publication
            client = boto3.client('lambda')
            invoke_response = client.invoke(
                FunctionName=os.environ['SCRAPER_FUNCTION'],
                InvocationType='Event',
                Payload='{}'
            )
            print(f"Invoking Scraper: {invoke_response}")
        return {"statusCode": 200}

    except Exception:
        raise


def fetch_url_with_retry(url, retries=3):
    """
    Fetch URL with comprehensive browser headers to avoid bot detection.
    Uses the same approach as fetch_page_with_curl_headers in scraper.py.
    """
    # Get and log Lambda IP address
    try:
        lambda_ip = requests.get('http://checkip.amazonaws.com', timeout=3).text.strip()
        print(f'[INFO] Lambda IP address: {lambda_ip}')
    except Exception as e:
        print(f'[WARNING] Could not determine Lambda IP: {e}')
        lambda_ip = 'unknown'

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

    print(f'[DEBUG] Attempting to fetch RSS feed from IP: {lambda_ip}')
    try:
        response = session.get(url, timeout=600)  # 10 minute timeout
        print(f'[DEBUG] Response status code: {response.status_code}')
        response.raise_for_status()
        return response
    except requests.exceptions.Timeout:
        print(f'[ERROR] Request timed out after 10 minutes for URL: {url}')
        # publish_error_sns('MARADMIN Polling Error', 'Request timeout')
        return None
    except requests.exceptions.ConnectionError as e:
        print(f'[ERROR] Connection error for URL {url}: {e}')
        # publish_error_sns('MARADMIN Polling Error', str(e))
        return None
    except requests.exceptions.HTTPError as e:
        print(f'[ERROR] HTTP error {e.response.status_code} for URL {url}: {e}')
        # publish_error_sns('MARADMIN Polling Error', str(e))
        return None
    except Exception as e:
        print(f'[ERROR] Unexpected error fetching URL {url}: {type(e).__name__} - {e}')
        raise