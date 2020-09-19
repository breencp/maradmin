import json
import xml.etree.ElementTree as ET
import urllib.request
import re
import boto3
import os

from boto3.dynamodb.conditions import Key
from urllib.error import HTTPError
from maradmin_globals import publish_error_sns


def lambda_handler(event, context):
    url = f'https://www.marines.mil/DesktopModules/ArticleCS/RSS.ashx?ContentType=6&Site=481&max=10&category=14336'
    try:
        response = urllib.request.urlopen(url).read()
    except HTTPError as err:
        # received 403 forbidden, we are being throttled
        # clear poll last pub date to ensure scraper gets executed again at next interval
        if err.code == 403:
            publish_error_sns('403 Error Scraping', f'Received HTTP 403 Forbidden Error attempting to read {url}')
        else:
            raise
    except:
        raise
    else:
        try:
            root = ET.fromstring(response)
            print('Successfully retrieved RSS Feed')
        except ET.ParseError:
            print('ParseError: ' + response)
            raise

        for child in root[0]:
            if child.tag == 'item':
                item = {
                    'desc': re.sub(r'<.*?>', '', str.strip(child[2].text)),
                    'pub_date': child[3].text,
                    'link': child[1].text,
                    'title': child[0].text
                }

                # check to see if msg already exists (via description)
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
        return {"statusCode": 200}


def publish_sns(item, body):
    sns_topic = os.environ['SNS_TOPIC']
    # sns_topic = 'arn:aws:sns:us-east-1:676250019162:maradmin-MaradminTable-Testing'
    sns = boto3.client('sns')
    title = constrain_sub(item['title'])
    link = item['link']
    text_msg = f'{title} {link}'
    message = json.dumps({
        'default': title,
        'lambda': body,
        'sms': text_msg[0:1600]  # max 1,600 characters
    })
    if len(message.encode('utf-8')) > 262144:
        # Message max of 256KB
        orig_len = len(message.encode('utf-8'))
        print(f'Truncating {title} from ' + str(orig_len / 1024) + f' KB')
        footer = f'...<br />Message Truncated.  Visit {link} to read the entire message.'
        trunc_len = orig_len - 262144
        abbr_body = body[0:(len(body.encode('utf-8')) - trunc_len - len(footer))] + footer
        message = json.dumps({
            'default': title,
            'lambda': abbr_body,
            'sms': text_msg[0:1600]  # max 1,600 characters
        })
        print('New Size ' + str(len(message.encode('utf-8'))) + ' of 262144')

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


