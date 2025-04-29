import json
import boto3
import pytest
import os


def test_scraper_lambda_handler(mocker):
    # Set required environment variables for the test.
    mocker.patch.dict(os.environ, {'MARADMIN_TABLE_NAME': 'dummy_table', 'SNS_TOPIC': 'dummy_topic'})

    # Patch DynamoDB resource so that the Table method returns a mock table.
    dynamodb_resource_mock = mocker.patch('boto3.resource')
    db_mock_instance = dynamodb_resource_mock.return_value
    table_mock = db_mock_instance.Table.return_value
    table_mock.query.return_value = {'Count': 0}
    table_mock.put_item.return_value = {}

    # Patch fetch_page_with_curl_headers to return dummy HTML with a body.
    dummy_html = '<html><div class="body-text">Test Body</div></html>'
    mocker.patch('scraper.fetch_page_with_curl_headers', return_value=dummy_html)

    # Patch generate_bluf to return a dummy BLUF summary.
    mocker.patch('scraper.generate_bluf', return_value="Test BLUF")

    # Patch boto3 SNS client so publish gets called but doesn't make a real request.
    sns_client_mock = mocker.patch('boto3.client')
    sns_instance = sns_client_mock.return_value
    sns_instance.publish.return_value = {"MessageId": "dummy-id"}

    # Import and invoke lambda_handler.
    from scraper import lambda_handler
    dummy_event = {}
    dummy_context = None
    response = lambda_handler(dummy_event, dummy_context)

    # Assertions to verify behavior.
    assert response["statusCode"] == 200
    sns_instance.publish.assert_called_once()
    table_mock.query.assert_called_once()
    table_mock.put_item.assert_called_once()