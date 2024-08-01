import json
import xml.etree.ElementTree as ET
import urllib.request
import boto3
import os

from boto3.dynamodb.conditions import Key
from urllib.error import HTTPError, URLError
from maradmin_globals import publish_error_sns


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

        status_code = response.getcode()
        headers = response.info()
        msg = response.read().decode('utf-8')
        if not msg:
            print(f"HTTP Status Code: {status_code}")
            print("[ERROR] Response body is empty.")
            publish_error_sns('MARADMIN Poll response had empty message body', f'HTTP Status Code: {status_code}. Headers: {headers}')
            return {"statusCode": 500}
        try:
            root = ET.fromstring(msg)
        except ET.ParseError:
            try:
                print(f'ParseError: response.info:{json.dumps(response.info())} msg:{str(msg)}')
            except TypeError:
                print(f'ParseError: response.info:{response.info()} msg:{str(msg)}')
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
    req = urllib.request.Request(url)
    req.add_header('Accept-Encoding', 'identity;q=1.0')
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    attempt = 0
    while attempt <= retries:
        attempt += 1
        try:
            response = urllib.request.urlopen(req)
            return response
        except HTTPError as err:
            print(f"[WARNING] Received HTTP {err.code}. Retrying {attempt}/{retries}...")
            if attempt <= retries:
                continue
            else:
                publish_error_sns('MARADMIN Polling Error', str(err))
                return
        except URLError as err:
            print(f'[WARNING] URLError: {err}. Retrying {attempt}/{retries}...')
            if attempt <= retries:
                continue
            else:
                publish_error_sns('MARADMIN Polling Error', str(err))
                return
        except Exception as err:
            print(f'[ERROR] Exception: {err}. Retrying {attempt}/{retries}...')
            if attempt <= retries:
                continue
            else:
                raise
    return None