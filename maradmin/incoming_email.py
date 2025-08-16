import json
import boto3
import os

from maradmin_globals import get_token


def lambda_handler(event, context):
    action = 'DEFAULT'
    if event['subject'].upper() == 'UNSUBSCRIBE':
        db = boto3.resource('dynamodb')
        subscriber_table = db.Table(os.environ['SUBSCRIBER_TABLE_NAME'])
        email = event['envelope']['mailFrom']['address']
        db_response = subscriber_table.delete_item(Key={'email': email})
        action = 'DROP'
        print(f'EMAIL-UNSUBSCRIBE: {email} - {db_response}')

        # send email
        html_msg = '<samp><p>Greetings,</p>' \
                   '<p>You have been successfully unsubscribed and will no longer ' \
                   'receive MARADMIN Notifications. I hope it provided some value. Feel free to re-subscribe anytime.</p> '
        text_msg = 'Greetings,\n' \
                     'You have been successfully unsubscribed and will no longer ' \
                        'receive MARADMIN Notifications. I hope it provided some value. Feel free to re-subscribe anytime.'


        ses = boto3.client('ses')
        ses_response = ses.send_templated_email(
            Source='"MARADMIN" <maradmin@christopherbreen.com>',
            ReplyToAddresses=['maradmin@christopherbreen.com'],
            Destination={'ToAddresses': [email], 'BccAddresses': ['me@christopherbreen.com']},
            Template='NewSubscriberTemplate',
            TemplateData=json.dumps({
                'title': 'You have been unsubscribed from MARADMIN Notifications',
                'html_msg': html_msg,
                'text_msg': text_msg
            }),
            ConfigurationSetName='maradmin',
        )
        # Log to CloudWatch
        print(ses_response)

    elif event['subject'].upper() == 'SUBSCRIBE':
        db = boto3.resource('dynamodb')
        subscriber_table = db.Table(os.environ['SUBSCRIBER_TABLE_NAME'])
        email = event['envelope']['mailFrom']['address']
        user_data = {
            'email': email,
            'verified': 'True',
            'email_token': get_token()
        }
        db_response = subscriber_table.put_item(Item=user_data)
        action = 'DROP'
        print(f'EMAIL-SUBSCRIBE: {email} - {db_response}')

        # send confirmation email
        html_msg = '<samp><p>Greetings,</p>' \
                   '<p>Thank you for subscribing to the MARADMIN Notifications service.</p>' \
                   f'<p>You will now begin to receive emails of MARADMINS soon after they are posted. ' \
                   'Be sure to add maradmin@christopherbreen.com to your contacts and feel free ' \
                   'to reach out anytime at this same address.</p>' \
                   '<p><a ses:no-track href=https://www.christopherbreen.com?utm_source=email&utm_medium=maradmin&utm_campaign=maradmin_sub_cta target=_blank>Visit www.christopherbreen.com to explore more solutions</a></p>' \
                   '<p>Sent autonomously on behalf of, <br />Christopher Breen</p></samp>'

        text_msg = 'Greetings,\n' \
                   'Thank you for subscribing to the MARADMIN Notifications service.\n' \
                   'You will now begin to receive emails of MARADMINS soon after they are posted. ' \
                   'Be sure to add maradmin@christopherbreen.com to your contacts and feel free ' \
                   'to reach out anytime at this same address.\n' \
                   'Visit www.christopherbreen.com to explore more solutions\n' \
                   'Sent autonomously on behalf of, Christopher Breen'

        ses = boto3.client('ses')
        ses_response = ses.send_templated_email(
            Source='"MARADMIN" <maradmin@christopherbreen.com>',
            ReplyToAddresses=['maradmin@christopherbreen.com'],
            Destination={'ToAddresses': [email], 'BccAddresses': ['me@christopherbreen.com']},
            Template='NewSubscriberTemplate',
            TemplateData=json.dumps({
                'title': 'You are now subscribed to MARADMIN Notifications',
                'html_msg': html_msg,
                'text_msg': text_msg
            }),
            ConfigurationSetName='maradmin',
        )
        # Log to CloudWatch
        print(ses_response)

    return {'actions': [{'action': {'type': action}, 'allRecipients': True}]}
