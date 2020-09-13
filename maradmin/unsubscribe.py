from boto3.dynamodb.conditions import Key

from yattag import Doc
import boto3
import os
import re
import random
import string
from urllib.parse import unquote


def lambda_handler(event, context):
    card_title = 'Invalid'
    card_subtitle = 'Please try again'
    message = "I'm sorry, that token/email pair appears to be invalid.  Please try again, ensuring you are using the " \
              "unsubscribe link from the most recent email.  If you still encounter problems, send us an email from " \
              "the address you wish to unsubscribe and the word UNSUBSCRIBE in the subject line."
    try:
        email = sanitized(unquote(event['queryStringParameters']['email']))
        email_token = sanitized_token(event['queryStringParameters']['email_token'])
        if email and email_token:
            # email and token are formatted correctly, let's see if they match
            db = boto3.resource('dynamodb')
            subscriber_table = db.Table(os.environ['SUBSCRIBER_TABLE_NAME'])
            rs = subscriber_table.query(
                KeyConditionExpression=Key('email').eq(email)
            )
            if rs:
                if rs['Items'][0]['email_token'] == email_token:
                    card_title = 'Unsubscribed'
                    card_subtitle = 'Successfully removed'
                    message = 'Was it something we did?  You have been successfully unsubscribed and will no longer ' \
                              'receive MARADMIN Notifications. Please let us know if there was something we could have done better. ' \
                              'Send your feedback to maradmin@christopherbreen.com.'

                    # update verified status in subscriber table
                    db_response = subscriber_table.delete_item(
                        Key={
                            'email': email
                        }
                    )
                    # log to CloudWatch
                    print(F'WWW-UNSUBSCRIBE: {email} - {db_response}')

    except KeyError as err:
        print('KeyError')
    except ValueError as err:
        print('ValueError')
    except TypeError as err:
        print('TypeError')

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

    html_result = doc.getvalue()

    return {
        'statusCode': "200",
        'body': html_result,
        'headers': {
            'Content-Type': 'text/html',
        }
    }


def sanitized(user_input):
    regex = r"^([\w-]+(?:\.[\w-]+)*)@((?:[\w-]+\.)*\w[\w-]{0,66})\.([a-z]{2,6}(?:\.[a-z]{2})?)$"
    match = re.fullmatch(regex, user_input)
    if match:
        return match.string
    else:
        return None


def get_token():
    pool = string.ascii_letters
    email_token = ''.join(random.choice(pool) for i in range(16))
    return email_token


def sanitized_token(user_input):
    regex = r"^[a-zA-Z]{16}$"
    match = re.fullmatch(regex, user_input)
    if match:
        return match.string
    else:
        return None
