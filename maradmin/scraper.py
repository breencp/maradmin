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
                        try:
                            full_body = fetch_page_with_curl_headers(item['link'])
                            start = full_body.find('<div class="body-text">')
                            end = full_body.find('</div>', start)
                            body = full_body[start + len('<div class="body-text">'):end]
                            # body is HTML portion of the page trimmed down to just the MARADMIN itself.
                        except requests.exceptions.Timeout as e:
                            print(f'[ERROR] Timeout fetching {item["link"]}: {e}')
                            raise
                        except requests.exceptions.ConnectionError as e:
                            print(f'[ERROR] Connection error fetching {item["link"]}: {e}')
                            raise
                        except requests.exceptions.HTTPError as e:
                            print(f'[ERROR] HTTP error fetching {item["link"]}: {e.response.status_code} - {e}')
                            raise
                        except Exception as e:
                            print(f'[ERROR] Unexpected error fetching {item["link"]}: {type(e).__name__} - {e}')
                            raise
                        
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
    print(f'[DEBUG] Attempting to fetch URL: {link}')
    try:
        response = session.get(link, timeout=10)
        print(f'[DEBUG] Response status code: {response.status_code}')
        response.raise_for_status()
        return response.text.replace('(slash)', '/')
    except requests.exceptions.Timeout:
        print(f'[ERROR] Request timed out after 10 seconds for URL: {link}')
        raise
    except requests.exceptions.ConnectionError as e:
        print(f'[ERROR] Connection error for URL {link}: {e}')
        raise
    except requests.exceptions.HTTPError as e:
        print(f'[ERROR] HTTP error {e.response.status_code} for URL {link}: {e}')
        raise
    except Exception as e:
        print(f'[ERROR] Unexpected error fetching URL {link}: {type(e).__name__} - {e}')
        raise


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
    debug = True
    lambda_handler(event, context)
