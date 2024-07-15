import os
from unittest.mock import patch

import pytest

from app.googleanalytics.pixels import build_dynamic_ga4_pixel_tracking_url


@pytest.mark.parametrize(
    'env, expected_domain',
    [
        ('test', 'https://test-api.va.gov/vanotify/'),
        ('development', 'https://dev-api.va.gov/vanotify/'),
        ('perf', 'https://sandbox-api.va.gov/vanotify/'),
        ('staging', 'https://staging-api.va.gov/vanotify/'),
        ('prod', 'https://api.va.gov/vanotify/'),
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
            'name=email_open',
            'source=vanotify',
            'medium=email',
            'content=',
        ]

        assert all(parameter in url for parameter in all_expected_parameters)


def test_build_dynamic_ga4_pixel_tracking_url_encodes_spaces(
    notify_api,
    sample_notification_model_with_organization,
):
    with patch.dict(os.environ, {'NOTIFY_ENVIRONMENT': 'test'}):
        sample_notification_model_with_organization.template.name = 'Test Campaign'
        sample_notification_model_with_organization.service.name = 'Test Service'

        url = build_dynamic_ga4_pixel_tracking_url(sample_notification_model_with_organization)

        assert 'Test%20Campaign' in url
        assert 'Test%20Service' in url
