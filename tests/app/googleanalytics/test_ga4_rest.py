"""Test endpoints for Google Analytics 4."""

from flask import url_for


# def test_get_ga4_valid_data(client, ga4_request_data, mocker):
#     """
#     A GET request with valid URL parameters should receive a 204 ("No Content") response.
#     """

#     mock_celery = mocker.patch('app.celery.process_ga4_measurement_task')
#     response = client.get(
#         path=url_for('ga4.get_ga4'),
#         query_string=ga4_request_data,
#     )
#     mock_celery.si.call_count == 0
#     assert response.status_code == 204, response.get_json()


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
