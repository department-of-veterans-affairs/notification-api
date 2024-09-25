from unittest.mock import patch

import pytest
import requests

from app.celery.exceptions import AutoRetryException
from app.celery.process_ga4_measurement_tasks import post_to_ga4


def test_it_post_to_ga4_with_valid_data(sample_notification, ga4_sample_payload):
    # Patch the requests.post method to return a 204 status code.
    notification = sample_notification()
    with patch('app.celery.process_ga4_measurement_tasks.requests.post') as mock_post:
        mock_post.return_value.status_code = 204
        response = post_to_ga4(
            notification.id,
            ga4_sample_payload['name'],
            ga4_sample_payload['source'],
            ga4_sample_payload['medium'],
        )

    assert response
    assert mock_post.called
    assert mock_post.call_args[0][0] == 'http://foo.bar/ga4?measurement_id=ga4_measurement_id&api_secret=ga4_api_secret'

    actual_ga4_payload = mock_post.call_args.kwargs['json']
    assert actual_ga4_payload['client_id'] == ga4_sample_payload['source']
    assert actual_ga4_payload['events'][0]['name'] == ga4_sample_payload['name']
    assert actual_ga4_payload['events'][0]['params']['campaign_id'] == str(notification.template.id)
    assert actual_ga4_payload['events'][0]['params']['campaign'] == notification.template.name
    assert actual_ga4_payload['events'][0]['params']['source'] == ga4_sample_payload['source']
    assert actual_ga4_payload['events'][0]['params']['medium'] == ga4_sample_payload['medium']
    assert actual_ga4_payload['events'][0]['params']['service_id'] == str(notification.service_id)
    assert actual_ga4_payload['events'][0]['params']['service_name'] == notification.service.name
    assert actual_ga4_payload['events'][0]['params']['notification_id'] == notification.id


def test_it_post_to_ga4_returns_4xx(ga4_sample_payload):
    with patch('app.celery.process_ga4_measurement_tasks.requests.post') as mock_post:
        mock_post.return_value.status_code = 400
        response = post_to_ga4(
            ga4_sample_payload['notification_id'],
            ga4_sample_payload['name'],
            ga4_sample_payload['source'],
            ga4_sample_payload['medium'],
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
            ga4_sample_payload['name'],
            ga4_sample_payload['source'],
            ga4_sample_payload['medium'],
        )

        assert not response


# Parameterize the exceptions that result in AutoRetries
@pytest.mark.parametrize(
    'mock_exception',
    [
        requests.Timeout,
        requests.ConnectionError,
        requests.HTTPError,
    ],
)
def test_it_post_to_ga4_exception(sample_notification, ga4_sample_payload, mock_exception):
    with patch('app.celery.process_ga4_measurement_tasks.requests.post') as mock_post:
        notification = sample_notification()
        mock_post.side_effect = mock_exception('Boom')
        with pytest.raises(AutoRetryException):
            post_to_ga4(
                notification.id,
                ga4_sample_payload['name'],
                ga4_sample_payload['source'],
                ga4_sample_payload['medium'],
            )


def test_it_post_to_ga4_does_not_retry_unhandled_exception(ga4_sample_payload):
    with patch('app.celery.process_ga4_measurement_tasks.requests.post') as mock_post:
        mock_post.post.side_effect = Exception('Boom')
        response = post_to_ga4(
            ga4_sample_payload['notification_id'],
            ga4_sample_payload['name'],
            ga4_sample_payload['source'],
            ga4_sample_payload['medium'],
        )
        assert not response
