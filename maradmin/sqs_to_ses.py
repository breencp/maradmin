import boto3
import json


def lambda_handler(event, context):
    email = event['Records'][0]['messageAttributes']['email']['stringValue']
    html_msg = event['Records'][0]['body']
    subject = event['Records'][0]['messageAttributes']['subject']['stringValue']
    ses = boto3.client('ses')
    template_data = json.dumps({
        'title': subject,
        'html_msg': html_msg,
        'email': email,
    })
    ses_response = ses.send_templated_email(
        Source='"MARADMIN" <maradmin@christopherbreen.com>',
        ReplyToAddresses=['maradmin@christopherbreen.com'],
        Destination={'ToAddresses': [email]},
        Template='MaradminTemplate',
        TemplateData=template_data,
        ConfigurationSetName='maradmin',
    )
    # log response to CloudWatch (keep in production)
    print(f'Emailing {subject} to {email}, Response: {ses_response}')

    return {"statusCode": 200}
