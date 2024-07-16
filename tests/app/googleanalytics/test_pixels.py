import os
from unittest.mock import patch

import pytest

from app.googleanalytics.pixels import build_dynamic_ga4_pixel_tracking_url, get_domain_for_environment


class TestGA4PixelTracking:
    @pytest.mark.parametrize(
        'expected_domain',
        [
            'https://test-api.va.gov/vanotify/',
            'https://dev-api.va.gov/vanotify/',
            'https://sandbox-api.va.gov/vanotify/',
            'https://staging-api.va.gov/vanotify/',
            'https://api.va.gov/vanotify/',
        ],
    )
    def test_ut_build_dynamic_ga4_pixel_tracking_url_correct_domain_for_environment(
        self, sample_notification_model_with_organization, expected_domain
    ):
        with patch('app.googleanalytics.pixels.get_domain_for_environment', return_value=expected_domain):
            url = build_dynamic_ga4_pixel_tracking_url(sample_notification_model_with_organization)
            assert expected_domain in url

    def test_it_build_dynamic_ga4_pixel_tracking_url_contains_expected_parameters(
        self, sample_notification_model_with_organization
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

    def test_it_build_dynamic_ga4_pixel_tracking_url_encodes_spaces(self, sample_notification_model_with_organization):
        with patch.dict(os.environ, {'NOTIFY_ENVIRONMENT': 'test'}):
            sample_notification_model_with_organization.template.name = 'Test Campaign'
            sample_notification_model_with_organization.service.name = 'Test Service'

            url = build_dynamic_ga4_pixel_tracking_url(sample_notification_model_with_organization)

            assert 'Test%20Campaign' in url
            assert 'Test%20Service' in url

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
    def test_ut_get_domain_for_environment(self, env, expected_domain):
        with patch.dict(os.environ, {'NOTIFY_ENVIRONMENT': env}):
            assert get_domain_for_environment() == expected_domain

    def test_ut_get_domain_for_environment_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_domain_for_environment() == 'https://dev-api.va.gov/vanotify/'
