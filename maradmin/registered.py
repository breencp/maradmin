import boto3
import os
import json

from urllib.parse import unquote
from boto3.dynamodb.conditions import Key

from maradmin_globals import get_token, sanitized_email, build_webpage


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
                verification_link = f'https://maradmin.christopherbreen.com/verify?email={email}&email_token={email_token}'
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

    html_result = build_webpage('MARADMIN', card_title, card_subtitle, message)

    return {
        'statusCode': "200",
        'body': html_result,
        'headers': {
            'Content-Type': 'text/html',
        }
    }


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
