import json
import random
import string
import re
import boto3

from yattag import Doc


def publish_error_sns(title, body):
    sns_topic = 'arn:aws:sns:us-east-1:676250019162:Default_CloudWatch_Alarms_Topic'
    sns = boto3.client('sns')
    message = json.dumps({
        'default': title,
        'email': body,
        'sms': title[0:1600]  # max 1,600 characters
    })

    try:
        response = sns.publish(
            TopicArn=sns_topic,
            Message=message,
            Subject=title,
            MessageStructure='json'
        )
        print(f'Published {title} to Error SNS, Response:{response}')
    except:
        print('Error processing ' + title)
        raise
    return response


def sanitized_email(user_input):
    regex = r"^([\w-]+(?:\.[\w-]+)*)@((?:[\w-]+\.)*\w[\w-]{0,66})\.([a-z]{2,6}(?:\.[a-z]{2})?)$"
    match = re.match(regex, user_input)
    if match and match.group(3) in ['com', 'org', 'net', 'int', 'edu', 'gov', 'mil']:
        return match.string, match.group(3)
    else:
        return None, None


def sanitized_token(user_input):
    regex = r"^[a-zA-Z]{16}$"
    match = re.fullmatch(regex, user_input)
    if match:
        return match.string
    else:
        return None


def get_token():
    pool = string.ascii_letters
    email_token = ''.join(random.choice(pool) for i in range(16))
    return email_token


def build_webpage(page_title, card_title, card_subtitle, message):
    doc, tag, text, line = Doc().ttl()

    doc.asis('<!DOCTYPE html>')
    with tag('html', lang='en'):
        with tag('head'):
            with tag('script', 'async', src='https://www.googletagmanager.com/gtag/js?id=UA-176788003-1'):
                pass
            with tag('script'):
                text('window.dataLayer = window.dataLayer || [];function gtag(){dataLayer.push(arguments);}'
                     'gtag(\'js\', new Date());'
                     'gtag(\'config\', \'UA-176788003-1\');')
            doc.stag('meta', charset='UTF-8')
            doc.stag('meta', ('initial-scale', 1), ('shrink-to-fit', 'no'), name='viewport',
                     content='width=device-width')
            with tag('title'):
                text(page_title)
            doc.stag('link', rel='stylesheet',
                     href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css",
                     integrity="sha384-JcKb8q3iqJ61gNV9KGb8thSsNjpSL0n8PARn9HuZOnIxN0hoP+VmmDGMN5t9UJ0Z",
                     crossorigin="anonymous")
            with tag('style'):
                text('body { background-image: url(https://s3.amazonaws.com/com.christopherbreen.static/maradmin/texture-hero-bg.jpg); }')

        with tag('body'):
            with tag('main'):
                with tag('div', klass='container'):
                    line('h1', 'MARADMIN Notifications', klass='text-center logo my-4', style='color: white')
                    with tag('div', klass='row justify-content-center'):
                        with tag('div', klass='col-lg-8 col-md-10 col-sm-12'):
                            with tag('div', klass='card'):
                                with tag('div', klass='card-body'):
                                    line('h3', card_title, klass='card-title')
                                    line('h5', card_subtitle, klass='card-subtitle mb-2 text-muted')
                                    line('p', message, klass='card-text')
                                with tag('div', klass='card-footer text-muted text-center'):
                                    text('This site/service is not hosted nor endorsed by the U.S. Government or the U.S. Marine Corps.')
            line('script', '', src="https://code.jquery.com/jquery-3.5.1.slim.min.js",
                 integrity="sha384-DfXdz2htPH0lsSSs5nCTpuj/zy4C+OGpamoFVy38MVBnE+IbbVYUew+OrCXaRkfj",
                 crossorigin="anonymous")
            line('script', '', src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js",
                 integrity="sha384-B4gt1jrGC7Jh4AgTPSdUtOBvfO8shuf57BaghqFfPlYxofvL8/KUEfYiJOMMV+rV",
                 crossorigin="anonymous")

    return doc.getvalue()
