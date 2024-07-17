"""Test endpoints for Google Analytics 4."""

from flask import url_for


def test_get_ga4_valid_data(client, ga4_request_data):
    """
    A GET request with valid URL parameters should receive a 204 ("No Content") response.
    """

    response = client.get(
        path=url_for('ga4.get_ga4'),
        query_string=ga4_request_data,
    )
    # Errors - FileNotFoundError: [Errno 2] No such file or directory:
    # /.venv/lib/python3.10/site-packages/test/images/pixel.png'
    assert response.status_code == 200, response.get_json()
    assert response.headers['Content-Type'].startswith('image/')


def test_get_ga4_invalid_data(client):
    """
    A GET request with invalid URL parameters should receive a 400 ("Bad Request") response.
    Test this by omitting all URL parameters.  Other tests validate the schema.
    """

    response = client.get(path=url_for('ga4.get_ga4'))
    assert response.status_code == 400, response.get_json()
