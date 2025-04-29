import json
import xml.etree.ElementTree as ET
import urllib.request
import re
import boto3
import os
import requests
from openai import OpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam

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
            # publish_error_sns('403 Error Scraping',
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
                    if rs['Count'] == 0:  # or debug:
                        print('NEW: ' + item['desc'])
                        print('Fetching: ' + item['link'])
                        # message is new, get contents and broadcast
                        full_body = fetch_page_with_curl_headers(item['link'])
                        start = full_body.find('<div class="body-text">')
                        end = full_body.find('</div>', start)
                        body = full_body[start + len('<div class="body-text">'):end]
                        # body is HTML portion of the page trimmed down to just the MARADMIN itself.
                        bluf = generate_bluf(body)
                        publish_sns(item, bluf, body)
                        maradmin_table.put_item(Item=item)
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
        'sms': text_msg[0:1600]  # max 1,600 characters
    }

    body = body.encode('utf-8', errors='replace').decode('utf-8')
    bluf = bluf.encode('utf-8', errors='replace').decode('utf-8')
    maradmin = f'{bluf}{body}'

    json_overhead = len(json.dumps(base_message).encode('utf-8', errors='replace'))
    max_message_size = 262144  # 256KB
    footer = f'...<br />Message Truncated.  Visit {link} to read the entire message.'
    allowed_body_size = max_message_size - json_overhead - len(footer.encode('utf-8'))

    if len(maradmin.encode('utf-8')) > allowed_body_size:
        print(f'Truncating {title} from {len(maradmin.encode("utf-8")) / 1024:.2f} KB')
        abbr_maradmin = maradmin[:allowed_body_size].encode('utf-8').decode('utf-8') + footer
        base_message['lambda'] = abbr_maradmin
    else:
        base_message['lambda'] = maradmin

    message = json.dumps(base_message)

    # if debug:
    #     return

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


def fetch_page_with_curl_headers(link):
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
    response = session.get(link, timeout=10)
    response.raise_for_status()
    return response.text.replace('(slash)', '/')


def generate_bluf(body):
    # Extract the BLUF from the body
    system_prompt = (
        "Provide a short, military style BLUF summary of this MARADMIN. It should be one paragraph max, plain text with no headers or formatting. "
        "Prefix your response with 'BLUF: ', and get right to the point, i.e. do not include statements like 'This MARADMIN is about...'. "
        "If you find what appears to be military units, MCCs, UICs, etc., include an alphabetical list in the summary on a single line, "
        "comma seperated, but omit this line entirely if it's not relevant to the MARADMIN. Note that MCC and UIC are three digits. "
        "If it's four digits, it's likely an MOS.")
    client = OpenAI()

    completion = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionUserMessageParam(role="user", content=body)
        ]
    )

    response = completion.choices[0].message.content
    return '<p>' + response + '</p>'


if __name__ == '__main__':
    # For local testing
    event = {}
    context = None
    debug = True
    lambda_handler(event, context)
