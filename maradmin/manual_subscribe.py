import json
import boto3

from maradmin_globals import get_token


def main(email):
    db = boto3.resource('dynamodb')
    subscriber_table = db.Table('maradmin-SubscriberTable-1P9FR9NSFPOOP')
    user_data = {
        'email': email,
        'verified': 'True',
        'email_token': get_token()
    }
    db_response = subscriber_table.put_item(Item=user_data)
    print(f'DB Response: {db_response}')

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

    print(ses_response)


if __name__ == '__main__':
    email = 'nicholas.rowden.mil@usmc.mil'
    main(email)

