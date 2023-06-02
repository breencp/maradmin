from yattag import Doc


def lambda_handler(event, context):
    page_title = 'MARADMIN'
    doc, tag, text, line = Doc().ttl()

    doc.asis('<!DOCTYPE html>')
    with tag('html', lang='en'):
        with tag('head'):
            with tag('script', 'async', src='https://www.googletagmanager.com/gtag/js?id=G-LNFSXHGK4H'):
                pass
            with tag('script'):
                text('window.dataLayer = window.dataLayer || [];'
                     'function gtag(){dataLayer.push(arguments);}'
                     'gtag(\'js\', new Date());'
                     'gtag(\'config\', \'G-LNFSXHGK4H\');')
            doc.stag('meta', charset='UTF-8')
            doc.stag('meta', ('initial-scale', 1), ('shrink-to-fit', 'no'), name='viewport',
                     content='width=device-width')
            doc.stag('meta', property='og:title', content='MARADMIN Notifications')
            doc.stag('meta', property='og:type', content='website')
            doc.stag('meta', property='og:url', content='https://maradmin.christopherbreen.com')
            doc.stag('meta', property='og:image',
                     content='https://s3.amazonaws.com/com.christopherbreen.static/maradmin/maradmin_logo_1200x630.png')
            doc.stag('meta', property='og:description',
                     content='Receive new MARADMINs directly to your inbox via email.')
            # doc.stag('meta', property='fb:app_id', content='896134517576896')
            with tag('title'):
                text(page_title)
            doc.stag('link', rel='stylesheet',
                     href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css",
                     integrity="sha384-JcKb8q3iqJ61gNV9KGb8thSsNjpSL0n8PARn9HuZOnIxN0hoP+VmmDGMN5t9UJ0Z",
                     crossorigin="anonymous")
            with tag('style'):
                text(
                    'body { background-image: url(https://s3.amazonaws.com/com.christopherbreen.static/maradmin/texture-hero-bg.jpg); }')

        with tag('body'):
            with tag('main'):
                with tag('div', klass='container'):
                    line('h1', 'MARADMIN Notifications', klass='text-center logo my-4', style='color: white')
                    with tag('div', klass='row justify-content-center'):
                        with tag('div', klass='col-lg-8 col-md-10 col-sm-12'):
                            with tag('div', klass='card'):
                                with tag('div', klass='card-body'):
                                    line('h3', 'Register', klass='card-title')
                                    with tag('form', action='registered/', method='get'):
                                        with tag('div', klass='form-group'):
                                            with tag('label', ('for', 'email')):
                                                text('Email Address')
                                            doc.stag('input', ('id', 'email'), ('aria-describedby', 'email_help'),
                                                     type='email', klass='form-control', name='email', required='True',
                                                     autocomplete='username')
                                            with tag('small', ('id', 'email_help'), klass='form-text text-muted'):
                                                text(
                                                    'Your email will not be sold, shared, or otherwise spammed.  You will ONLY receive an email when a new MARADMIN is published. ')
                                                line('a', 'Privacy Policy',
                                                     href='https://s3.amazonaws.com/com.christopherbreen.static/maradmin/privacy.html')
                                            doc.stag('br')
                                            line('button', 'Submit', type='submit', klass='btn btn-primary')
                                with tag('div', klass='card-footer text-muted text-center'):
                                    text(
                                        'This site/service is not hosted nor endorsed by the U.S. Government or the U.S. Marine Corps.')
            line('script', '', src="https://code.jquery.com/jquery-3.5.1.slim.min.js",
                 integrity="sha384-DfXdz2htPH0lsSSs5nCTpuj/zy4C+OGpamoFVy38MVBnE+IbbVYUew+OrCXaRkfj",
                 crossorigin="anonymous")
            line('script', '', src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js",
                 integrity="sha384-B4gt1jrGC7Jh4AgTPSdUtOBvfO8shuf57BaghqFfPlYxofvL8/KUEfYiJOMMV+rV",
                 crossorigin="anonymous")

    html_result = doc.getvalue()

    return {
        'statusCode': "200",
        'body': html_result,
        'headers': {
            'Content-Type': 'text/html',
        }
    }
