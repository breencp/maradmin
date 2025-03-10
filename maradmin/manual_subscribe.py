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

    # send confirmation email
    ses = boto3.client('ses')
    ses_response = ses.send_templated_email(
        Source='"MARADMIN" <maradmin@christopherbreen.com>',
        ReplyToAddresses=['maradmin@christopherbreen.com'],
        Destination={'ToAddresses': [email]},
        Template='NewSubscriberTemplate',
        TemplateData=json.dumps({
            'title': 'You are now subscribed to MARADMIN Notifications',
            'html_msg': html_msg,
            'text_msg': text_msg
        }),
        ConfigurationSetName='maradmin',
    )

    print(ses_response)


if __name__ == '__main__':
    email = '3DIV_RECON_BN@usmc.mil'
    main(email)
