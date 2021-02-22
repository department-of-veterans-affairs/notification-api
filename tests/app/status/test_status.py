import pytest
from flask import json

from app.feature_flags import FeatureFlag
from app.notifications.notification_type import NotificationType
from tests.app.db import create_organisation, create_service


class TestStatus:

    @pytest.fixture
    def mock_provider_service(self, mocker):
        provider_service = mocker.Mock()
        mocker.patch('app.status.healthcheck.provider_service', new=provider_service)

        mock_strategy_1 = mocker.Mock()
        type(mock_strategy_1).__name__ = 'MOCK_STRATEGY_1'

        mock_strategy_2 = mocker.Mock()
        type(mock_strategy_2).__name__ = 'MOCK_STRATEGY_2'

        provider_service.strategies = {
            NotificationType.EMAIL: type(mock_strategy_1),
            NotificationType.SMS: type(mock_strategy_2)
        }

        return provider_service

    @pytest.mark.parametrize('path', ['/', '/_status'])
    def test_get_status_all_ok(self, client, notify_db_session, path, mock_provider_service):
        response = client.get(path)
        assert response.status_code == 200
        resp_json = json.loads(response.get_data(as_text=True))
        assert resp_json['status'] == 'ok'
        assert resp_json['db_version']
        assert resp_json['git_commit']
        assert resp_json['build_time']

        assert resp_json['email_strategy'] == 'MOCK_STRATEGY_1'
        assert resp_json['sms_strategy'] == 'MOCK_STRATEGY_2'

    def test_validates_provider_service_if_toggle_enabled(
            self,
            client,
            notify_db_session,
            mocker,
            mock_provider_service
    ):
        mock_is_feature_enabled = mocker.patch('app.status.healthcheck.is_feature_enabled', return_value=True)
        mock_provider_service.validate_strategies.side_effect = Exception()

        response = client.get('/')

        assert response.status_code == 503

        mock_is_feature_enabled.assert_called_with(FeatureFlag.PROVIDER_STRATEGIES_ENABLED)
        mock_provider_service.validate_strategies.assert_called()

    def test_does_not_validate_provider_service_if_toggle_not_enabled(
            self,
            client,
            notify_db_session,
            mocker,
            mock_provider_service
    ):
        mock_is_feature_enabled = mocker.patch('app.status.healthcheck.is_feature_enabled', return_value=False)
        mock_provider_service.validate_strategies.side_effect = Exception()

        response = client.get('/')

        assert response.status_code == 200

        mock_is_feature_enabled.assert_called_with(FeatureFlag.PROVIDER_STRATEGIES_ENABLED)
        mock_provider_service.validate_strategies.assert_not_called()


def test_empty_live_service_and_organisation_counts(admin_request):
    assert admin_request.get('status.live_service_and_organisation_counts') == {
        'organisations': 0,
        'services': 0,
    }


def test_populated_live_service_and_organisation_counts(admin_request):

    # Org 1 has three real live services and one fake, for a total of 3
    org_1 = create_organisation('org 1')
    live_service_1 = create_service(service_name='1')
    live_service_1.organisation = org_1
    live_service_2 = create_service(service_name='2')
    live_service_2.organisation = org_1
    live_service_3 = create_service(service_name='3')
    live_service_3.organisation = org_1
    fake_live_service_1 = create_service(service_name='f1', count_as_live=False)
    fake_live_service_1.organisation = org_1
    inactive_service_1 = create_service(service_name='i1', active=False)
    inactive_service_1.organisation = org_1

    # This service isn’t associated to an org, but should still be counted as live
    create_service(service_name='4')

    # Org 2 has no real live services
    org_2 = create_organisation('org 2')
    trial_service_1 = create_service(service_name='t1', restricted=True)
    trial_service_1.organisation = org_2
    fake_live_service_2 = create_service(service_name='f2', count_as_live=False)
    fake_live_service_2.organisation = org_2
    inactive_service_2 = create_service(service_name='i2', active=False)
    inactive_service_2.organisation = org_2

    # Org 2 has no services at all
    create_organisation('org 3')

    # This service isn’t associated to an org, and should not be counted as live
    # because it’s marked as not counted
    create_service(service_name='f3', count_as_live=False)

    # This service isn’t associated to an org, and should not be counted as live
    # because it’s in trial mode
    create_service(service_name='t', restricted=True)
    create_service(service_name='i', restricted=False, active=False)

    assert admin_request.get('status.live_service_and_organisation_counts') == {
        'organisations': 1,
        'services': 4,
    }
