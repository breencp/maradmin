import json
import xml.etree.ElementTree as ET
import urllib.request
import re
import boto3
import os
# import requests

from boto3.dynamodb.conditions import Key
from urllib.error import HTTPError, URLError

# from maradmin_globals import publish_error_sns


def lambda_handler(event, context):
    url = f'https://www.marines.mil/DesktopModules/ArticleCS/RSS.ashx?ContentType=6&Site=481&max=10&category=14336'
    try:
        response = urllib.request.urlopen(url).read()
    except HTTPError as err:
        if err.code == 403:
            # received 403 forbidden, we are being throttled
            # lambda_ip = requests.get('http://checkip.amazonaws.com').text.rstrip()
            #publish_error_sns('403 Error Scraping',
            #                  f'{lambda_ip} received HTTP 403 Forbidden Error attempting to read {url}')
            # print(f'{lambda_ip} received HTTP 403 Forbidden Error attempting to read {url}')
            print('[WARNING] Received HTTP 403 Forbidden Error.')
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
        try:
            root = ET.fromstring(response)
            print('Successfully retrieved RSS Feed')
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
                    if rs['Count'] == 0:
                        # message is new, get contents and broadcast
                        full_body = urllib.request.urlopen(item['link']).read().decode('utf-8').replace('(slash)', '/')
                        start = full_body.find('<div class="body-text">')
                        end = full_body.find('</div>', start)
                        body = full_body[start + len('<div class="body-text">'):end]
                        publish_sns(item, body)
                        maradmin_table.put_item(Item=item)
                        print('NEW: ' + item['desc'])
                    else:
                        print('EXISTING: ' + item['desc'])
                else:
                    print('[WARNING] Empty description encountered, skipping this item.')
        return {"statusCode": 200}


def publish_sns(item, body):
    sns_topic = os.environ['SNS_TOPIC']
    sns = boto3.client('sns')
    title = constrain_sub(item['title'])
    link = item['link']
    text_msg = f'{title} {link}'
    base_message = {
        'default': title,
        'lambda': '',
        'sms': text_msg[0:1600]  # max 1,600 characters
    }

    body = body.encode('utf-8', errors='replace').decode('utf-8')
    json_overhead = len(json.dumps(base_message).encode('utf-8', errors='replace'))
    max_message_size = 262144  # 256KB
    footer = f'...<br />Message Truncated.  Visit {link} to read the entire message.'
    allowed_body_size = max_message_size - json_overhead - len(footer.encode('utf-8'))

    if len(body.encode('utf-8')) > allowed_body_size:
        print(f'Truncating {title} from {len(body.encode("utf-8")) / 1024:.2f} KB')
        abbr_body = body[:allowed_body_size].encode('utf-8').decode('utf-8') + footer
        base_message['lambda'] = abbr_body
    else:
        base_message['lambda'] = body

    message = json.dumps(base_message)

    try:
        response = sns.publish(
            TopicArn=sns_topic,
            Message=message,
            Subject=title,
            MessageStructure='json'
        )
        print(f'Published {title} to SNS, Response:{response}')
    except:
        print('Error processing ' + title)
        raise
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
