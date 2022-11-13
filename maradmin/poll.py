import json
import xml.etree.ElementTree as ET
import urllib.request
import boto3
import os

from boto3.dynamodb.conditions import Key
from urllib.error import HTTPError, URLError


def lambda_handler(event, context):
    url = 'https://www.marines.mil/DesktopModules/ArticleCS/RSS.ashx?ContentType=6&Site=481&max=1&category=14336'
    req = urllib.request.Request(url)
    req.add_header('Accept-Encoding', 'identity;q=1.0')
    req.add_header('User-Agent', 'maradmin.christopherbreen.com <maradmin@christopherbreen.com>')

    try:
        data = urllib.request.urlopen(req)
    except HTTPError as err:
        # received 403 forbidden, we are being throttled
        if err.code == 403:
            # lambda_ip = requests.get('http://checkip.amazonaws.com').text.rstrip()
            print('[WARNING] Received HTTP 403 Forbidden Error.')
            # print(f'{lambda_ip} received HTTP 403 Forbidden Error attempting to read {url}')
            # publish_error_sns('403 Error Polling',
            #                  f'{lambda_ip} received HTTP 403 Forbidden Error attempting to read {url}')
        else:
            raise
    except URLError as err:
        # urlopen error [Errno 97] Address family not supported by protocol
        # Occurs at random, perhaps when USMC Maradmin server is down.
        print(f'[WARNING] {err}')
        pass
    except:
        raise
    else:
        msg = data.read().decode('utf-8')
        try:
            root = ET.fromstring(msg)
        except ET.ParseError:
            try:
                print(f'ParseError: data.info:{json.dumps(data.info())} msg:{str(msg)}')
            except TypeError:
                print(f'ParseError: data.info:{data.info()} msg:{str(msg)}')
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
            # server has newer publication
            client = boto3.client('lambda')
            invoke_response = client.invoke(
                FunctionName=os.environ['SCRAPER_FUNCTION'],
                InvocationType='Event',
                Payload='{}'
            )
            print(f"Invoking Scraper: {invoke_response}")
        return {"statusCode": 200}
