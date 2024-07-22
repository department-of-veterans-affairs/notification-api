from unittest.mock import patch

import pytest

from app.celery.exceptions import AutoRetryException
from app.celery.process_ga4_measurement_tasks import post_to_ga4


def test_post_to_ga4_with_valid_data(ga4_sample_payload):
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


def test_post_to_ga4_returns_4xx(ga4_sample_payload):
    with patch('app.celery.process_ga4_measurement_tasks.requests.post') as mock_post:
        mock_post.return_value.status_code = 400
        response = post_to_ga4(
            ga4_sample_payload['notification_id'],
            ga4_sample_payload['template_name'],
            ga4_sample_payload['template_id'],
            ga4_sample_payload['service_id'],
            ga4_sample_payload['service_name'],
        )

    assert not response


def test_post_to_ga4_missing_config(ga4_sample_payload):
    with patch('app.celery.process_ga4_measurement_tasks.get_ga4_config') as mock_get_ga4_config:
        mock_get_ga4_config.return_value = ('', '')
        with pytest.raises(AutoRetryException):
            post_to_ga4(
                ga4_sample_payload['notification_id'],
                ga4_sample_payload['template_name'],
                ga4_sample_payload['template_id'],
                ga4_sample_payload['service_id'],
                ga4_sample_payload['service_name'],
            )
