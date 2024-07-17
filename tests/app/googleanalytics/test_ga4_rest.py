"""Test endpoints for Google Analytics 4."""

from unittest import mock
from flask import url_for


def test_get_ga4_valid_data(notify_db_session, client, ga4_request_data):
    """
    A GET request with valid URL parameters should receive a 204 ("No Content") response.
    """

    # Patch the post_to_ga4 method
    with mock.patch('app.googleanalytics.ga4.post_to_ga4') as mock_ga4_task:
        response = client.get(
            path=url_for('ga4.get_ga4'),
            query_string=ga4_request_data,
        )
    assert response.status_code == 204, response.get_json()
    mock_ga4_task.delay.assert_called_once_with(
        notification_id='e774d2a6-4946-41b5-841a-7ac6a42d178b',
        template_name='hi',
        template_id='e774d2a6-4946-41b5-841a-7ac6a42d178b',
        service_id='e774d2a6-4946-41b5-841a-7ac6a42d178b',
        service_name='test',
    )


def test_get_ga4_invalid_data(client):
    """
    A GET request with invalid URL parameters should receive a 400 ("Bad Request") response.
    Test this by omitting all URL parameters.  Other tests validate the schema.
    """

    response = client.get(path=url_for('ga4.get_ga4'))
    assert response.status_code == 400, response.get_json()


def test_get_ga4_invalid_content(client, ga4_request_data):
    """
    A GET request with invalid content should receive a 400 ("Bad Request") response.
    Test this by changing the content to an invalid format.
    """

    ga4_request_data['content'] = 'invalid_content'

    response = client.get(
        path=url_for('ga4.get_ga4'),
        query_string=ga4_request_data,
    )

    assert response.status_code == 400, response.get_json()
