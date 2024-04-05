from boto3.dynamodb.conditions import Key

import boto3
import os
from urllib.parse import unquote
from maradmin_globals import sanitized_email, sanitized_token, build_webpage
import json


def lambda_handler(event, context):
    card_title = 'Invalid'
    card_subtitle = 'Please try again'
    message = "I'm sorry, that token/email pair appears to be invalid.  Please try again, ensuring you are using the " \
              "unsubscribe link from the most recent email.  If you still encounter problems, send us an email from " \
              "the address you wish to unsubscribe and the word UNSUBSCRIBE in the subject line."

    email_param = event['queryStringParameters'].get('email') if event.get('queryStringParameters') else None
    token_param = event['queryStringParameters'].get('email_token') if event.get('queryStringParameters') else None

    if email_param and token_param:
        try:
            email, domain = sanitized_email(unquote(email_param))
            email_token = sanitized_token(token_param)

            if email and email_token:
                db = boto3.resource('dynamodb')
                subscriber_table = db.Table(os.environ['SUBSCRIBER_TABLE_NAME'])
                rs = subscriber_table.query(KeyConditionExpression=Key('email').eq(email))
                if rs['Items'] and rs['Items'][0]['email_token'] == email_token:
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

        except Exception as e:
            print(json.dumps(context))
            raise e

    html_result = build_webpage('MARADMIN', card_title, card_subtitle, message)

    return {
        'statusCode': "200",
        'body': html_result,
        'headers': {
            'Content-Type': 'text/html',
        }
    }


if __name__ == '__main__':
    with open('../events/unsubscribe.json') as f:
        debug_event = json.load(f)

    result = lambda_handler(debug_event, None)
    print(result)
