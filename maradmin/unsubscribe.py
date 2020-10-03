from boto3.dynamodb.conditions import Key

import boto3
import os
from urllib.parse import unquote
from maradmin_globals import sanitized_email, sanitized_token, build_webpage


def lambda_handler(event, context):
    card_title = 'Invalid'
    card_subtitle = 'Please try again'
    message = "I'm sorry, that token/email pair appears to be invalid.  Please try again, ensuring you are using the " \
              "unsubscribe link from the most recent email.  If you still encounter problems, send us an email from " \
              "the address you wish to unsubscribe and the word UNSUBSCRIBE in the subject line."
    try:
        email, domain = sanitized_email(unquote(event['queryStringParameters']['email']))
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

    html_result = build_webpage('MARADMIN', card_title, card_subtitle, message)

    return {
        'statusCode': "200",
        'body': html_result,
        'headers': {
            'Content-Type': 'text/html',
        }
    }
