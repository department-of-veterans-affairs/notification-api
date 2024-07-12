import os
from unittest.mock import patch

import pytest

from app.googleanalytics.pixels import build_dynamic_ga4_pixel_tracking_url


@pytest.mark.parametrize(
    'env, expected_domain',
    [
        ('test', 'https://test-api.va.gov/notify/'),
        ('development', 'https://dev-api.va.gov/notify/'),
        ('perf', 'https://sandbox-api.va.gov/notify/'),
        ('staging', 'https://staging-api.va.gov/notify/'),
        ('prod', 'https://api.va.gov/notify/'),
    ],
)
def test_build_dynamic_ga4_pixel_tracking_url_correct_domain_for_environment(
    notify_api,
    sample_notification_model_with_organization,
    env,
    expected_domain,
):
    with patch.dict(os.environ, {'NOTIFY_ENVIRONMENT': env}):
        url = build_dynamic_ga4_pixel_tracking_url(sample_notification_model_with_organization)
        assert expected_domain in url


def test_build_dynamic_ga4_pixel_tracking_url_contains_expected_parameters(
    notify_api,
    sample_notification_model_with_organization,
):
    with patch.dict(os.environ, {'NOTIFY_ENVIRONMENT': 'test'}):
        url = build_dynamic_ga4_pixel_tracking_url(sample_notification_model_with_organization)

        all_expected_parameters = [
            'campaign=',
            'campaign_id=',
            'name=email_opens',
            'source=vanotify',
            'medium=email',
            'content=',
        ]

        assert all(parameter in url for parameter in all_expected_parameters)
