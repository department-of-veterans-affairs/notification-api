from unittest.mock import MagicMock, patch

import pytest
import requests

from app.celery.exceptions import AutoRetryException
from app.celery.process_ga4_measurement_tasks import post_to_ga4


def test_it_post_to_ga4_with_valid_data(ga4_sample_payload):
    # Patch the requests.post method to return a 200 status code.
    with patch('app.celery.process_ga4_measurement_tasks.requests') as mock_requests:
        mock_requests.post.return_value = MagicMock(status_code=204)
        response = post_to_ga4(
            ga4_sample_payload['notification_id'],
            ga4_sample_payload['template_name'],
            ga4_sample_payload['template_id'],
            ga4_sample_payload['service_id'],
            ga4_sample_payload['service_name'],
            client_id=ga4_sample_payload['client_id'],
            name=ga4_sample_payload['name'],
            source=ga4_sample_payload['source'],
            medium=ga4_sample_payload['medium'],
        )

    assert response


def test_it_post_to_ga4_returns_4xx(ga4_sample_payload):
    with patch('app.celery.process_ga4_measurement_tasks.requests') as mock_requests:
        mock_requests.post.return_value.status_code = 400
        response = post_to_ga4(
            ga4_sample_payload['notification_id'],
            ga4_sample_payload['template_name'],
            ga4_sample_payload['template_id'],
            ga4_sample_payload['service_id'],
            ga4_sample_payload['service_name'],
        )

    assert not response


# Parameterize the possibible get_ga4_config return values.
@pytest.mark.parametrize(
    'ga4_config',
    [
        ('', 'GA4_MEASUREMENT_ID'),
        ('GA4_API_SECRET', ''),
        ('', ''),
    ],
)
def test_it_post_to_ga4_missing_config(ga4_sample_payload, ga4_config):
    with patch('app.celery.process_ga4_measurement_tasks.get_ga4_config') as mock_get_ga4_config:
        mock_get_ga4_config.return_value = ga4_config
        response = post_to_ga4(
            ga4_sample_payload['notification_id'],
            ga4_sample_payload['template_name'],
            ga4_sample_payload['template_id'],
            ga4_sample_payload['service_id'],
            ga4_sample_payload['service_name'],
        )

        assert not response


def test_it_post_to_ga4_exception(ga4_sample_payload):
    with patch('app.celery.process_ga4_measurement_tasks.requests') as mock_requests:
        # Test the exception handling by raising an exception.
        mock_requests.post.side_effect = requests.exceptions.HTTPError()
        with pytest.raises(AutoRetryException):
            post_to_ga4(
                ga4_sample_payload['notification_id'],
                ga4_sample_payload['template_name'],
                ga4_sample_payload['template_id'],
                ga4_sample_payload['service_id'],
                ga4_sample_payload['service_name'],
            )


# def test_it_post_to_ga4_does_not_retry_unhandled_exception(ga4_sample_payload):
#     with patch('app.celery.process_ga4_measurement_tasks.requests') as mock_requests:
#         mock_requests.post.side_effect = Exception
#         response = post_to_ga4(
#             ga4_sample_payload['notification_id'],
#             ga4_sample_payload['template_name'],
#             ga4_sample_payload['template_id'],
#             ga4_sample_payload['service_id'],
#             ga4_sample_payload['service_name'],
#         )
#         assert not response
