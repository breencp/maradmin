from boto3.dynamodb.conditions import Key

from yattag import Doc
import boto3
import os
import re
import random
import string
import json
from urllib.parse import unquote


def lambda_handler(event, context):
    card_title = 'Invalid'
    card_subtitle = 'Please try again'
    message = "I'm sorry, that email address appears to be invalid."
    try:
        email, domain = sanitized_email(unquote(event['queryStringParameters']['email']))
        if email:
            card_title = 'Verification Pending'
            card_subtitle = 'Email Verification Sent'
            message = f'Search your inbox for a verification email sent from maradmin@christopherbreen.com. ' \
                      f'It is very likely in your junk, spam, or promotions tab (gmail users).'

            if already_verified(email):
                print(f'Duplicate Registration: {email}')
            else:
                print(f'Registering: {email}')

                # store information to subscriber table
                email_token = get_token()
                verification_link = f'https://api.christopherbreen.com/maradmin/verify?email={email}&email_token={email_token}'
                user_data = {
                    'email': email,
                    'verified': 'False',
                    'email_token': email_token
                }
                db = boto3.resource('dynamodb')
                table = db.Table(os.environ['SUBSCRIBER_TABLE_NAME'])
                db_response = table.put_item(
                    Item=user_data
                )
                # Log to CloudWatch
                print('Dynamo Response:', db_response)

                # send verification email
                html_msg = '<samp><p>Greetings,</p>' \
                           '<p>Thank you for subscribing to the MARADMIN Notifications service.</p>'
                if domain not in ['mil', 'gov']:
                    html_msg += f'<p>Please verify your email by visiting {verification_link}</p>'
                else:
                    html_msg += f'<p>Please reply to this email and change the subject to SUBSCRIBE to complete the verification process.</p>'

                ses = boto3.client('ses')
                ses_response = ses.send_templated_email(
                    Source='"MARADMIN" <maradmin@christopherbreen.com>',
                    ReplyToAddresses=['maradmin@christopherbreen.com'],
                    Destination={
                        'ToAddresses': [email],
                    },
                    Template='NewSubscriberTemplate',
                    TemplateData=json.dumps({
                        'title': 'Email Verification Link to enable MARADMIN Notifications',
                        'html_msg': html_msg,
                        'text_msg': html_msg
                    }),
                    ConfigurationSetName='maradmin',
                )
                # Log to CloudWatch
                print('SES Response:', ses_response)

    except (KeyError, ValueError, TypeError) as err:
        print(err)

    page_title = 'MARADMIN'
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
                text(
                    'body { background-image: url(https://s3.amazonaws.com/com.christopherbreen.static/maradmin/texture-hero-bg.jpg); }')

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
                                    text(
                                        'This site/service is not hosted nor endorsed by the U.S. Government or the U.S. Marine Corps.')
            line('script', '', src="https://code.jquery.com/jquery-3.5.1.slim.min.js",
                 integrity="sha384-DfXdz2htPH0lsSSs5nCTpuj/zy4C+OGpamoFVy38MVBnE+IbbVYUew+OrCXaRkfj",
                 crossorigin="anonymous")
            line('script', '', src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js",
                 integrity="sha384-B4gt1jrGC7Jh4AgTPSdUtOBvfO8shuf57BaghqFfPlYxofvL8/KUEfYiJOMMV+rV",
                 crossorigin="anonymous")

    html_result = doc.getvalue()

    return {
        'statusCode': "200",
        'body': html_result,
        'headers': {
            'Content-Type': 'text/html',
        }
    }


def sanitized_email(user_input):
    regex = r"^([\w-]+(?:\.[\w-]+)*)@((?:[\w-]+\.)*\w[\w-]{0,66})\.([a-z]{2,6}(?:\.[a-z]{2})?)$"
    match = re.match(regex, user_input)
    if match and match.group(3) in ['com', 'org', 'net', 'int', 'edu', 'gov', 'mil']:
        return match.string, match.group(3)
    else:
        return None, None


def get_token():
    pool = string.ascii_letters
    email_token = ''.join(random.choice(pool) for i in range(16))
    return email_token


def already_verified(email):
    db = boto3.resource('dynamodb')
    subscriber_table = db.Table(os.environ['SUBSCRIBER_TABLE_NAME'])
    rs = subscriber_table.query(
        KeyConditionExpression=Key('email').eq(email)
    )
    if rs['Count'] > 0 and rs['Items'][0]['verified'] == 'True':
        return True
    else:
        return False
