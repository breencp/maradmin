import json
import xml.etree.ElementTree as ET
import urllib.request
import boto3
import os

from boto3.dynamodb.conditions import Key


def lambda_handler(event, context):
    url = 'https://www.marines.mil/DesktopModules/ArticleCS/RSS.ashx?ContentType=6&Site=481&max=1&category=14336'
    req = urllib.request.Request(url)
    req.add_header('Accept-Encoding', 'identity;q=1.0')
    req.add_header('User-Agent', 'api.christopherbreen.com <maradmin@christopherbreen.com>')
    data = urllib.request.urlopen(req)
    msg = data.read().decode('utf-8')

    try:
        root = ET.fromstring(msg)
    except ET.ParseError:
        print(f'ParseError: data.info:{json.dumps(data.info())} msg:{str(msg)}')
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
