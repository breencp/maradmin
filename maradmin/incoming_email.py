import json
import random
import string
import boto3
import os


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
                   '<p>Was it something we did?  You have been successfully unsubscribed and will no longer ' \
                   'receive MARADMIN Notifications. Please let us know if there was something we could have done ' \
                   'better.</p> '

        ses = boto3.client('ses')
        ses_response = ses.send_templated_email(
            Source='"MARADMIN" <maradmin@christopherbreen.com>',
            ReplyToAddresses=['maradmin@christopherbreen.com'],
            Destination={'ToAddresses': [email]},
            Template='NewSubscriberTemplate',
            TemplateData=json.dumps({
                'title': 'You have been unsubscribed from MARADMIN Notifications',
                'html_msg': html_msg
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
                   'to reach out anytime at this same address.  Enjoy!</p>'

        ses = boto3.client('ses')
        ses_response = ses.send_templated_email(
            Source='"MARADMIN" <maradmin@christopherbreen.com>',
            ReplyToAddresses=['maradmin@christopherbreen.com'],
            Destination={'ToAddresses': [email]},
            Template='NewSubscriberTemplate',
            TemplateData=json.dumps({
                'title': 'You are now subscribed to MARADMIN Notifications',
                'html_msg': html_msg
            }),
            ConfigurationSetName='maradmin',
        )
        # Log to CloudWatch
        print(ses_response)

    return {'actions': [{'action': {'type': action}, 'allRecipients': True}]}


def get_token():
    pool = string.ascii_letters
    email_token = ''.join(random.choice(pool) for i in range(16))
    return email_token
