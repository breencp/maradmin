from boto3.dynamodb.conditions import Key
from urllib.parse import unquote
from maradmin_globals import sanitized_email, sanitized_token, build_webpage
import boto3
import os


def lambda_handler(event, context):
    card_title = 'Invalid'
    card_subtitle = 'Please try again'
    message = "I'm sorry, that token/email pair appears to be invalid."
    try:
        email = sanitized_email(unquote(event['queryStringParameters']['email']))
        email_token = sanitized_token(event['queryStringParameters']['email_token'])
        if email and email_token:
            # email and token are formatted correctly, let's see if they match
            db = boto3.resource('dynamodb')
            subscriber_table = db.Table(os.environ['SUBSCRIBER_TABLE_NAME'])
            rs = subscriber_table.query(
                KeyConditionExpression=Key('email').eq(email)
            )
            if rs['Items']:
                if rs['Items'][0]['email_token'] == email_token or rs['Items'][0]['verified'] == 'True':
                    card_title = 'Success'
                    card_subtitle = 'Email Verified'
                    message = 'Be sure to add maradmin@christopherbreen.com to your contacts list and feel ' \
                              'free to reach out anytime at that same address.  Enjoy!'

                    # update verified status in subscriber table
                    subscriber_table.update_item(
                        Key={'email': email},
                        UpdateExpression='set verified = :verified',
                        ExpressionAttributeValues={':verified': 'True'})
                    print(f'WWW Verified: {email}')
                else:
                    print(f'Failed Verification - Incorrect Token: {email}')
            else:
                print(f'Failed Verification - Unknown Email: {email}')
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
