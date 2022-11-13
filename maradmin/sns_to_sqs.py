import boto3
import os

from boto3.dynamodb.conditions import Key


def lambda_handler(event, context):
    # print(f'Event:{event}')  # sns_to_sqs is only fired once per new maradmin
    sqs = boto3.client('sqs')
    db = boto3.resource('dynamodb')
    subscriber_table = db.Table(os.environ['SUBSCRIBER_TABLE_NAME'])
    done = False
    start_key = None

    if 'Developer' in event:
        # use custom formatted sns_input.json for testing new features to prevent mass-emailing subscriber table
        query_kwargs = {
            'KeyConditionExpression': Key('email').eq('breencp@gmail.com')
        }
    else:
        query_kwargs = {
            'IndexName': 'VerifiedIndex',
            'KeyConditionExpression': Key('verified').eq('True')
        }

    while not done:
        if start_key:
            query_kwargs['ExclusiveStartKey'] = start_key
        db_response = subscriber_table.query(**query_kwargs)
        start_key = db_response.get('LastEvaluatedKey', None)
        done = start_key is None
        for item in db_response['Items']:
            email = item['email']
            # email_token = item['email_token']
            subject = event['Records'][0]['Sns']['Subject']
            sqs_response = sqs.send_message(
                QueueUrl=os.environ['SQS_QUEUE'],
                MessageBody=event['Records'][0]['Sns']['Message'],
                MessageAttributes={
                    'email': {
                        'DataType': 'String',
                        'StringValue': email
                    },
                    'subject': {
                        'DataType': 'String',
                        'StringValue': subject
                    },
                    # 'email_token': {
                    #     'DataType': 'String',
                    #     'StringValue': email_token
                    # }
                }
            )
            # Log CloudWatch
            print(f'Adding {subject} for {email} to SQS, Response:{sqs_response}')

    return {"statusCode": 200}
